"""
Stage 1: Expand

Two-layer keyword expansion with strict drift control and request budget management.
Layer 1: Discovers related terms (Datamuse, WordNet, Wikipedia, Customer-language, Ollama)
Layer 2: Autocomplete expansion (Google, Bing, YouTube, Amazon) on seed and qualified related terms.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.adapters.autocomplete.google import GoogleAutocompleteAdapter
from keyword_analysis.adapters.autocomplete.bing import BingAutocompleteAdapter
from keyword_analysis.adapters.autocomplete.youtube import YouTubeAutocompleteAdapter
from keyword_analysis.adapters.autocomplete.amazon import AmazonAutocompleteAdapter
from keyword_analysis.adapters.datamuse import DatamuseAdapter
from keyword_analysis.adapters.wordnet_adapter import WordNetAdapter
from keyword_analysis.adapters.wikipedia import WikipediaAdapter
from keyword_analysis.adapters.stackexchange import StackExchangeAdapter
from keyword_analysis.adapters.reddit import RedditAdapter
from keyword_analysis.adapters.llm import OllamaAdapter
from keyword_analysis.config import Config
from keyword_analysis.similarity import SimilarityEngine, get_similarity_engine
from keyword_analysis.utils.cache import DiskCache
from keyword_analysis.utils.logger import get_logger
from keyword_analysis.utils.normalizer import normalize
from keyword_analysis.utils.rate_limiter import RateLimiter, RequestBudget

log = get_logger(__name__)


class ExpandStage:
    def __init__(
        self,
        config: Config,
        cache: Optional[DiskCache] = None,
        budget: Optional[RequestBudget] = None,
        similarity_engine: Optional[SimilarityEngine] = None,
    ):
        self.cfg = config
        self.cache = cache or DiskCache(ttl_hours=config.budget.cache_ttl_hours)
        self.budget = budget or RequestBudget(max_requests=config.budget.global_max_requests)
        self.similarity = similarity_engine or get_similarity_engine(config)

        # Build active adapters
        self.rate_limiter = RateLimiter(delay=config.budget.delay_seconds)
        self._init_adapters()

    def _init_adapters(self):
        common = {
            "cache": self.cache,
            "rate_limiter": self.rate_limiter,
            "budget": self.budget,
            "max_retries": self.cfg.budget.max_retries,
            "retry_backoff": self.cfg.budget.retry_backoff,
        }

        # Autocomplete adapters
        self.ac_google = GoogleAutocompleteAdapter(hl=self.cfg.locale.hl, gl=self.cfg.locale.gl, **common)
        self.ac_bing = BingAutocompleteAdapter(market=f"{self.cfg.locale.hl}-{self.cfg.locale.gl.upper()}", **common)
        self.ac_yt = YouTubeAutocompleteAdapter(hl=self.cfg.locale.hl, gl=self.cfg.locale.gl, **common)
        self.ac_amazon = AmazonAutocompleteAdapter(**common)

        # Related terms adapters (Layer 1)
        self.datamuse = DatamuseAdapter(max_results=self.cfg.expansion.max_related_per_source, **common)
        self.wordnet = WordNetAdapter(max_results=self.cfg.expansion.max_related_per_source, **common)
        self.wikipedia = WikipediaAdapter(max_results=self.cfg.expansion.max_related_per_source, **common)
        self.stackexchange = StackExchangeAdapter(max_results=self.cfg.expansion.max_related_per_source, **common)
        self.reddit = RedditAdapter(max_results=self.cfg.expansion.max_related_per_source, **common)
        self.ollama = OllamaAdapter(
            model=self.cfg.ollama.model,
            base_url=self.cfg.ollama.base_url,
            timeout=self.cfg.ollama.timeout,
            max_suggestions=self.cfg.ollama.max_suggestions,
            **common,
        )

    def _get_active_autocomplete_adapters(self) -> List[BaseAdapter]:
        adapters: List[BaseAdapter] = []
        if self.cfg.providers.google_autocomplete:
            adapters.append(self.ac_google)
        if self.cfg.providers.bing_autocomplete:
            adapters.append(self.ac_bing)
        if self.cfg.providers.youtube_autocomplete:
            adapters.append(self.ac_yt)
        if self.cfg.providers.amazon_autocomplete:
            adapters.append(self.ac_amazon)
        return adapters

    def estimate_request_count(self, num_eligible_seeds: int) -> int:
        """
        Estimate number of HTTP calls to verify budget feasibility.
        Seed + top N get full sweep; rest get modifiers + question words.
        """
        ac_providers = len(self._get_active_autocomplete_adapters())
        # a-z before and after = 26 * 2 = 52 calls
        # question words = len(modifiers.question_words)
        # intent words = len(modifiers.intent_words)
        full_sweep_queries = 52 + len(self.cfg.modifiers.question_words) + len(self.cfg.modifiers.intent_words)
        reduced_queries = len(self.cfg.modifiers.question_words) + len(self.cfg.modifiers.intent_words)

        top_n = min(self.cfg.expansion.top_n_full_sweep, num_eligible_seeds)
        other_n = max(0, num_eligible_seeds - top_n)

        # Layer 1 calls (~5 adapters)
        l1_calls = 5
        # Layer 2 calls
        l2_calls = (1 + top_n) * full_sweep_queries * ac_providers + (other_n * reduced_queries * ac_providers)
        return l1_calls + l2_calls

    def _run_layer1(self, seed: str) -> List[Candidate]:
        """Fetch related terms from Layer 1 adapters (distance = 1)."""
        log.info("Running Layer 1 (Related-term discovery) for seed: '%s'", seed)
        candidates: List[Candidate] = []

        if self.cfg.providers.datamuse:
            candidates.extend(self.datamuse.fetch(seed))
        if self.cfg.providers.wordnet and self.wordnet.is_available():
            candidates.extend(self.wordnet.fetch(seed))
        if self.cfg.providers.wikipedia:
            candidates.extend(self.wikipedia.fetch(seed))
        if self.cfg.providers.stackexchange:
            candidates.extend(self.stackexchange.fetch(seed))
        if self.cfg.providers.reddit:
            candidates.extend(self.reddit.fetch(seed))
        if self.cfg.providers.ollama and self.ollama.is_available():
            candidates.extend(self.ollama.fetch(seed))

        # Enforce distance = 1 for all Layer 1 items
        for c in candidates:
            c.distance = 1

        log.info("Layer 1 produced %d raw candidates across sources", len(candidates))
        return candidates

    def _sweep_term(
        self,
        term: str,
        is_full_sweep: bool,
        distance: int,
    ) -> List[Candidate]:
        """Run autocomplete sweeps for a given term using concurrent workers."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        ac_adapters = self._get_active_autocomplete_adapters()
        queries_to_run: List[str] = [term]

        # Question words
        for qw in self.cfg.modifiers.question_words:
            queries_to_run.append(f"{qw} {term}")

        # Intent modifiers
        for iw in self.cfg.modifiers.intent_words:
            q = f"{iw} {term}" if iw in ["best", "top", "cheap", "affordable"] else f"{term} {iw}"
            queries_to_run.append(q)

        # Alphabet sweeps ONLY if is_full_sweep
        if is_full_sweep:
            for letter in self.cfg.modifiers.letters:
                queries_to_run.append(f"{term} {letter}")
                if distance == 1:
                    queries_to_run.append(f"{letter} {term}")

        results: List[Candidate] = []

        def _fetch_single(q: str):
            if self.budget.exhausted:
                return []
            sub_res = []
            for adapter in ac_adapters:
                sub_res.extend(adapter.fetch(q, distance=distance))
            return sub_res

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_fetch_single, q) for q in queries_to_run]
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        results.extend(res)
                except Exception as e:
                    log.warning("Autocomplete sweep error: %s", e)

        return results

    def run(self, seed: str) -> List[Candidate]:
        """
        Run the complete Stage 1 Expansion pipeline:
        1. Seed candidate (distance 0)
        2. Layer 1 related terms (distance 1)
        3. Qualification via seed_threshold for Layer 2 expansion
        4. Layer 2 autocomplete on seed (distance 1) and qualified terms (distance 2)
        5. Drift check on every candidate against ORIGINAL seed using keep_threshold
        """
        norm_seed = normalize(seed)
        log.info("=== Starting Stage 1: Expand for '%s' ===", norm_seed)

        all_candidates: List[Candidate] = [
            Candidate(text=norm_seed, source="seed", distance=0, rank=1, raw_query=norm_seed)
        ]

        # 1. Run Layer 1
        l1_candidates = self._run_layer1(norm_seed)
        all_candidates.extend(l1_candidates)

        # Compute similarity to seed for all Layer 1 candidates to decide eligibility
        l1_texts = [c.text for c in l1_candidates]
        sim_scores = self.similarity.compute_batch_similarity(l1_texts, norm_seed)
        for cand, sim in zip(l1_candidates, sim_scores):
            cand.metadata["similarity_to_seed"] = sim

        # 2. Select eligible terms for Layer 2 expansion
        # Must meet seed_threshold (default 0.60)
        eligible_for_expansion: List[Tuple[Candidate, float]] = []
        for cand in l1_candidates:
            sim = cand.metadata.get("similarity_to_seed", 0.0)
            if sim >= self.cfg.thresholds.seed_threshold and len(cand.text.split()) <= 4:
                eligible_for_expansion.append((cand, sim))

        # Sort by similarity descending
        eligible_for_expansion.sort(key=lambda x: x[1], reverse=True)
        # Cap the expansion frontier (default max 20)
        eligible_for_expansion = eligible_for_expansion[: self.cfg.expansion.frontier_cap]

        log.info(
            "Found %d Layer 1 terms meeting seed_threshold >= %.2f for expansion",
            len(eligible_for_expansion),
            self.cfg.thresholds.seed_threshold,
        )

        # Budget estimate & logging
        estimated_calls = self.estimate_request_count(len(eligible_for_expansion))
        log.info(
            "Estimated HTTP requests: ~%d (Budget: %d, Remaining: %d)",
            estimated_calls,
            self.cfg.budget.global_max_requests,
            self.budget.remaining,
        )

        # 3. Layer 2: Autocomplete on SEED directly (distance = 1, full sweep)
        log.info("Running full autocomplete sweep on seed '%s' (distance 1)", norm_seed)
        seed_ac_results = self._sweep_term(norm_seed, is_full_sweep=True, distance=1)
        all_candidates.extend(seed_ac_results)

        # 4. Layer 2: Autocomplete on qualified Layer 1 terms (distance = 2)
        top_n = self.cfg.expansion.top_n_full_sweep
        for idx, (cand, sim) in enumerate(eligible_for_expansion):
            if self.budget.exhausted:
                log.warning("Request budget exhausted during Layer 2 expansion.")
                break

            term = cand.text
            is_full = idx < top_n  # Only top N get full a-z sweep
            log.info(
                "Expanding L1 term [%d/%d] '%s' (sim=%.2f, full_sweep=%s, distance=2)",
                idx + 1,
                len(eligible_for_expansion),
                term,
                sim,
                is_full,
            )
            term_results = self._sweep_term(term, is_full_sweep=is_full, distance=2)
            all_candidates.extend(term_results)

        # 5. Global Drift Check: Compare EVERY candidate to ORIGINAL seed
        log.info("Applying global drift check to all %d raw candidates...", len(all_candidates))
        unique_texts = list({c.text for c in all_candidates})
        all_sims = dict(zip(unique_texts, self.similarity.compute_batch_similarity(unique_texts, norm_seed)))

        surviving_candidates: List[Candidate] = []
        drift_dropped = 0
        keep_thresh = self.cfg.thresholds.keep_threshold

        for cand in all_candidates:
            sim = all_sims.get(cand.text, 0.0)
            cand.metadata["similarity_to_seed"] = sim

            # Always keep original seed; otherwise check keep_threshold
            if cand.distance == 0 or sim >= keep_thresh:
                surviving_candidates.append(cand)
            else:
                drift_dropped += 1

        log.info(
            "Stage 1 complete: %d candidates survived drift check (%d dropped, keep_threshold=%.2f)",
            len(surviving_candidates),
            drift_dropped,
            keep_thresh,
        )
        return surviving_candidates
