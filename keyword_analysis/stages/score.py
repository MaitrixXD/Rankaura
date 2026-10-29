"""
Stage 4: Score

Calculates a bounded opportunity score with component breakdown and confidence rating.
Never divides by zero or lets extreme values blow up the score.
Honesty rule: Missing competition data is neutral (0.5) with LOW confidence, never zero competition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from keyword_analysis.adapters.serp import SerpAdapter
from keyword_analysis.config import Config
from keyword_analysis.stages.enrich import EnrichedKeyword
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

# Fallback word frequency checker if wordfreq is not installed
_WORDFREQ_AVAILABLE = False
try:
    import wordfreq
    _WORDFREQ_AVAILABLE = True
except ImportError:
    pass


@dataclass
class ScoredKeyword:
    text: str
    opportunity_score: float
    score_band: str  # "High", "Medium", "Low"
    confidence: str  # "High", "Medium", "Low"
    components: Dict[str, float]
    intent_class: str
    unique_sources: int
    source_names: List[str]
    best_autocomplete_rank: Optional[int]
    word_count: int
    distance: int
    similarity_to_seed: float
    metadata: Dict[str, any] = field(default_factory=dict)


class ScoreStage:
    def __init__(self, config: Config, serp_adapter: Optional[SerpAdapter] = None):
        self.cfg = config
        self.serp = serp_adapter
        self.weights = config.scoring.weights

    def _compute_demand(self, kw: EnrichedKeyword, max_unique_sources: int) -> float:
        """
        Proxy for demand based on unique sources and autocomplete rank.
        Range: [0.0 - 1.0].
        """
        # Unique sources contribution: 0 to 1
        src_score = kw.unique_sources / max(1, max_unique_sources)

        # Autocomplete rank contribution: rank 1 -> 1.0, rank 10 -> 0.1, none -> 0.2
        if kw.best_autocomplete_rank is not None:
            # Rank typically 1 to 10
            rank_score = max(0.1, 1.0 - (kw.best_autocomplete_rank - 1) * 0.09)
        else:
            rank_score = 0.25

        # 60% source consensus + 40% autocomplete prominence
        demand = 0.60 * src_score + 0.40 * rank_score
        return round(min(max(demand, 0.0), 1.0), 4)

    def _compute_specificity(self, kw: EnrichedKeyword) -> float:
        """
        Rewards specific phrases (3-6 words) and presence of target modifiers.
        Penalises very common dictionary words.
        Range: [0.0 - 1.0].
        """
        # Length curve: optimal is 3 to 6 words
        wc = kw.word_count
        if 3 <= wc <= 6:
            length_score = 1.0
        elif wc == 2:
            length_score = 0.6
        elif 7 <= wc <= 8:
            length_score = 0.75
        else:
            length_score = 0.4

        # Modifiers bonus
        mod_count = sum(1 for v in kw.modifier_flags.values() if v)
        mod_score = min(1.0, mod_count * 0.35)

        # Common word penalty using wordfreq if available
        commonness_penalty = 0.0
        if _WORDFREQ_AVAILABLE:
            words = kw.text.split()
            freqs = [wordfreq.zipf_frequency(w, "en") for w in words]
            avg_freq = sum(freqs) / len(freqs) if freqs else 0.0
            # Zipf frequency 6+ represents ultra-common head words (the, of, is, car, home)
            if avg_freq > 5.5:
                commonness_penalty = 0.2
            elif avg_freq > 4.5:
                commonness_penalty = 0.1

        specificity = 0.60 * length_score + 0.40 * mod_score - commonness_penalty
        return round(min(max(specificity, 0.0), 1.0), 4)

    def _compute_intent(self, kw: EnrichedKeyword) -> float:
        """Neutral baseline for query intent without artificial taxonomy bias."""
        score = 0.60
        # Gentle boost if modifier indicates high practical specificity (pricing, location, audience)
        if kw.modifier_flags.get("has_price") or kw.modifier_flags.get("has_location") or kw.modifier_flags.get("has_audience"):
            score = min(1.0, score + 0.15)
        return round(score, 4)

    def _compute_distance_penalty(self, distance: int) -> float:
        """
        Penalty for derivation distance from seed:
        distance 0 = 0.0
        distance 1 = 0.10
        distance 2 = 0.25
        """
        if distance == 0:
            return 0.0
        elif distance == 1:
            return 0.10
        return 0.25

    def run(self, keywords: List[EnrichedKeyword]) -> List[ScoredKeyword]:
        log.info("=== Starting Stage 4: Score (%d keywords) ===", len(keywords))
        if not keywords:
            return []

        max_sources = max((k.unique_sources for k in keywords), default=1)

        # Preliminary pass to compute raw opportunity without SERP
        scored_candidates: List[ScoredKeyword] = []

        for kw in keywords:
            demand = self._compute_demand(kw, max_sources)
            specificity = self._compute_specificity(kw)
            intent = self._compute_intent(kw)
            dist_pen = self._compute_distance_penalty(kw.distance)

            # Default competition fallback is neutral 0.5 with low confidence
            competition = self.cfg.scoring.competition_fallback
            confidence = "Medium" if kw.unique_sources >= 2 else "Low"

            # Bounded formula:
            # opportunity = 0.30*demand + 0.25*(1-competition) + 0.20*specificity + 0.15*intent + 0.10*(1-dist_pen)
            opp = (
                self.weights.demand * demand
                + self.weights.competition * (1.0 - competition)
                + self.weights.specificity * specificity
                + self.weights.intent * intent
                + self.weights.distance * (1.0 - dist_pen)
            )

            # Relevance gate multiplier: if similarity is between keep_threshold and 1.0, scale gracefully
            relevance_gate = min(1.0, kw.similarity_to_seed / 0.8)
            opp *= relevance_gate
            opp = round(min(max(opp, 0.0), 1.0), 3)

            band = (
                "High"
                if opp >= self.cfg.scoring.score_bands.high
                else "Medium"
                if opp >= self.cfg.scoring.score_bands.medium
                else "Low"
            )

            components = {
                "demand": demand,
                "competition": competition,
                "specificity": specificity,
                "intent": intent,
                "distance_penalty": dist_pen,
                "relevance_gate": round(relevance_gate, 3),
            }

            scored_candidates.append(
                ScoredKeyword(
                    text=kw.text,
                    opportunity_score=opp,
                    score_band=band,
                    confidence=confidence,
                    components=components,
                    intent_class=kw.intent_class,
                    unique_sources=kw.unique_sources,
                    source_names=kw.source_names,
                    best_autocomplete_rank=kw.best_autocomplete_rank,
                    word_count=kw.word_count,
                    distance=kw.distance,
                    similarity_to_seed=kw.similarity_to_seed,
                )
            )

        # Sort by opportunity score descending
        scored_candidates.sort(key=lambda s: s.opportunity_score, reverse=True)

        # Optional: Run SERP competition check on top ~50 survivors ONLY
        if self.serp and self.serp.is_available() and self.cfg.serp.enabled:
            top_k = min(self.cfg.serp.max_keywords, len(scored_candidates))
            log.info("Running optional SERP competition check on top %d keywords...", top_k)
            for item in scored_candidates[:top_k]:
                analysis = self.serp.analyse_competition(item.text)
                if analysis:
                    item.components["competition"] = analysis.competition_score
                    item.confidence = analysis.confidence.capitalize()
                    item.metadata["serp"] = analysis.details

                    # Recompute score with real competition data
                    opp = (
                        self.weights.demand * item.components["demand"]
                        + self.weights.competition * (1.0 - analysis.competition_score)
                        + self.weights.specificity * item.components["specificity"]
                        + self.weights.intent * item.components["intent"]
                        + self.weights.distance * (1.0 - item.components["distance_penalty"])
                    ) * item.components["relevance_gate"]
                    item.opportunity_score = round(min(max(opp, 0.0), 1.0), 3)
                    item.score_band = (
                        "High"
                        if item.opportunity_score >= self.cfg.scoring.score_bands.high
                        else "Medium"
                        if item.opportunity_score >= self.cfg.scoring.score_bands.medium
                        else "Low"
                    )

            # Re-sort after SERP updates
            scored_candidates.sort(key=lambda s: s.opportunity_score, reverse=True)

        log.info("Stage 4 complete: %d keywords scored", len(scored_candidates))
        return scored_candidates
