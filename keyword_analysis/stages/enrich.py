"""
Stage 2: Enrich

Normalizes, deduplicates, and annotates candidates with demand signals,
intent classifications, modifier detection, and distance metrics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from keyword_analysis.adapters.base import Candidate
from keyword_analysis.config import Config
from keyword_analysis.utils.logger import get_logger
from keyword_analysis.utils.normalizer import normalize, tokenize

log = get_logger(__name__)


@dataclass
class EnrichedKeyword:
    text: str
    unique_sources: int
    source_names: List[str]
    best_autocomplete_rank: Optional[int]
    word_count: int
    similarity_to_seed: float
    distance: int
    intent_class: str = ""
    modifier_flags: Dict[str, bool] = field(default_factory=dict)
    raw_occurrences: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


class EnrichStage:
    def __init__(self, config: Config):
        self.cfg = config

    def _detect_modifiers(self, text: str) -> Dict[str, bool]:
        """Detect presence of specific modifier categories."""
        return {
            "has_price": bool(re.search(r"\b(cost|price|pricing|rate|budget|cheap|affordable|fee)\b", text)),
            "has_location": bool(re.search(r"\b(near me|in [a-z]+|mumbai|delhi|bangalore|hyderabad|pune|chennai|nearby)\b", text)),
            "has_audience": bool(re.search(r"\b(for (beginners|small (apartments|spaces|homes)|flats|2bhk|3bhk|offices|luxury|villas|budget))\b", text)),
            "has_problem": bool(re.search(r"\b(without|fix|low budget|small|renovation|remodel|diy)\b", text)),
            "has_comparison": bool(re.search(r"\b(vs|versus|alternative|or|difference)\b", text)),
        }

    def run(self, candidates: List[Candidate], seed: str) -> List[EnrichedKeyword]:
        """
        Group by canonical text, count UNIQUE independent sources,
        find minimum distance and best autocomplete rank, and annotate.
        """
        norm_seed = normalize(seed)
        log.info("=== Starting Stage 2: Enrich (%d raw candidates) ===", len(candidates))

        # Grouping container: canonical_text -> dict of aggregated signals
        grouped: Dict[str, Dict[str, Any]] = {}

        for c in candidates:
            norm_text = normalize(c.text)
            if not norm_text:
                continue

            if norm_text not in grouped:
                grouped[norm_text] = {
                    "text": norm_text,
                    "sources": set(),
                    "ranks": [],
                    "distances": [],
                    "similarity": c.metadata.get("similarity_to_seed", 0.0),
                    "occurrences": 0,
                }

            grouped[norm_text]["sources"].add(c.source)
            grouped[norm_text]["distances"].append(c.distance)
            grouped[norm_text]["occurrences"] += 1
            if c.rank is not None:
                grouped[norm_text]["ranks"].append(c.rank)
            if "similarity_to_seed" in c.metadata:
                grouped[norm_text]["similarity"] = max(
                    grouped[norm_text]["similarity"], c.metadata["similarity_to_seed"]
                )

        enriched: List[EnrichedKeyword] = []

        for norm_text, data in grouped.items():
            words = tokenize(norm_text)
            best_rank = min(data["ranks"]) if data["ranks"] else None
            min_distance = min(data["distances"]) if data["distances"] else 1
            unique_sources = len(data["sources"])

            mod_flags = self._detect_modifiers(norm_text)

            enriched.append(
                EnrichedKeyword(
                    text=norm_text,
                    unique_sources=unique_sources,
                    source_names=sorted(list(data["sources"])),
                    best_autocomplete_rank=best_rank,
                    word_count=len(words),
                    similarity_to_seed=data["similarity"],
                    distance=min_distance,
                    intent_class="",
                    modifier_flags=mod_flags,
                    raw_occurrences=data["occurrences"],
                )
            )

        log.info(
            "Stage 2 complete: %d unique enriched keywords produced", len(enriched)
        )
        return enriched
