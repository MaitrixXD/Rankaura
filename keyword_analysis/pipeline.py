"""
Master Keyword Analysis Pipeline

Connects all 6 stages into an end-to-end workflow:
Seed -> 1. Expand -> 2. Enrich -> 3. Filter -> 4. Score -> 5. Cluster -> 6. Output
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from keyword_analysis.adapters.serp import SerpAdapter
from keyword_analysis.adapters.llm import OllamaAdapter, GeminiAdapter
from keyword_analysis.config import Config, load_config
from keyword_analysis.stages.cluster import ClusterStage, KeywordCluster
from keyword_analysis.stages.enrich import EnrichStage, EnrichedKeyword
from keyword_analysis.stages.expand import ExpandStage
from keyword_analysis.stages.filter import DiscardedKeyword, FilterStage
from keyword_analysis.stages.output import OutputStage
from keyword_analysis.stages.score import ScoreStage, ScoredKeyword
from keyword_analysis.stages.verify import VerifyStage
from keyword_analysis.utils.cache import DiskCache
from keyword_analysis.utils.logger import get_logger
from keyword_analysis.utils.rate_limiter import RateLimiter, RequestBudget

log = get_logger(__name__)


@dataclass
class PipelineResult:
    seed: str
    execution_time_seconds: float
    total_raw_candidates: int
    enriched_count: int
    kept_count: int
    discarded_count: int
    clusters_count: int
    clusters: List[KeywordCluster]
    discarded: List[DiscardedKeyword]
    output_dict: Dict[str, Any]
    csv_data: str


class KeywordPipeline:
    def __init__(self, config: Optional[Config] = None):
        self.cfg = config or load_config()
        self.cache = DiskCache(ttl_hours=self.cfg.budget.cache_ttl_hours)
        self.budget = RequestBudget(max_requests=self.cfg.budget.global_max_requests)

        # Initialize optional SERP adapter
        self.serp_adapter = None
        if self.cfg.serp.enabled and self.cfg.serp.api_key and self.cfg.serp.cx:
            rate_limiter = RateLimiter(delay=1.0)
            self.serp_adapter = SerpAdapter(
                api_key=self.cfg.serp.api_key,
                cx=self.cfg.serp.cx,
                daily_quota=self.cfg.serp.daily_quota,
                safety_margin=self.cfg.serp.safety_margin,
                cache=self.cache,
                rate_limiter=rate_limiter,
                budget=self.budget,
            )

        # Initialize optional Gemini adapter
        self.gemini_adapter = None
        if self.cfg.providers.gemini and self.cfg.gemini.api_key:
            rate_limiter = RateLimiter(delay=1.0)
            self.gemini_adapter = GeminiAdapter(
                api_key=self.cfg.gemini.api_key,
                model=self.cfg.gemini.model,
                timeout=self.cfg.gemini.timeout,
                cache=self.cache,
                rate_limiter=rate_limiter,
                budget=self.budget,
            )

        # Instantiate stages
        self.stage_expand = ExpandStage(self.cfg, cache=self.cache, budget=self.budget)
        self.stage_enrich = EnrichStage(self.cfg)
        self.stage_filter = FilterStage(self.cfg)
        self.stage_score = ScoreStage(self.cfg, serp_adapter=self.serp_adapter)
        self.stage_verify = VerifyStage(self.cfg, gemini_adapter=self.gemini_adapter)
        self.stage_cluster = ClusterStage(self.cfg)
        self.stage_output = OutputStage()

    def run(
        self,
        seed: str,
        export_base_path: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> PipelineResult:
        """
        Execute the full keyword analysis pipeline.
        progress_callback(stage_name, percent_complete)
        """
        start_time = time.time()

        # Reset request budget so each search gets its full quota
        self.budget.reset()

        log.info("Starting Keyword Analysis Pipeline for seed: '%s'", seed)

        def report(stage_name: str, pct: int):
            if progress_callback:
                progress_callback(stage_name, pct)

        # 1. Expand
        report("Expanding search space (Layer 1 + Autocomplete)...", 15)
        raw_candidates = self.stage_expand.run(seed)

        # 2. Enrich
        report("Enriching & detecting intent signals...", 35)
        enriched = self.stage_enrich.run(raw_candidates, seed)

        # 3. Filter
        report("Filtering near-duplicates and noise...", 55)
        survivors, discarded = self.stage_filter.run(enriched, seed)

        # 4. Score
        report("Calculating bounded opportunity scores...", 75)
        scored = self.stage_score.run(survivors)

        # 5. Cluster
        report("Clustering keywords by topic and intent...", 85)
        clusters = self.stage_cluster.run(scored)

        # 6. Verify (Gemini) - Move after clustering to ensure final selection is clean
        report("Verifying top keywords with Gemini...", 95)
        verified_results = self.stage_verify.verify_from_clusters(seed, clusters)
        
        # 7. Output
        report("Formatting outputs...", 98)
        output_dict = self.stage_output.to_dict(
            clusters, 
            seed, 
            scored=scored, 
            verified_high=verified_results.get("high"),
            verified_medium=verified_results.get("medium")
        )
        csv_data = self.stage_output.to_csv(clusters, seed)

        if export_base_path:
            self.stage_output.export_files(
                clusters, 
                seed, 
                export_base_path, 
                verified_high=verified_results.get("high"),
                verified_medium=verified_results.get("medium")
            )

        elapsed = round(time.time() - start_time, 2)
        report("Complete!", 100)

        log.info(
            "Pipeline complete for '%s' in %.2fs: %d clusters, %d total keywords",
            seed,
            elapsed,
            len(clusters),
            output_dict["total_keywords"],
        )

        return PipelineResult(
            seed=seed,
            execution_time_seconds=elapsed,
            total_raw_candidates=len(raw_candidates),
            enriched_count=len(enriched),
            kept_count=len(survivors),
            discarded_count=len(discarded),
            clusters_count=len(clusters),
            clusters=clusters,
            discarded=discarded,
            output_dict=output_dict,
            csv_data=csv_data,
        )
