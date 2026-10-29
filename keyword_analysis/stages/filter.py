"""
Stage 3: Filter

Applies quality and relevance gates:
- Drops the exact seed
- Drops generic 1-word head terms
- Drops near-duplicates (high token overlap)
- Selectively filters brand terms while keeping comparison queries
- Drops off-topic or gibberish phrases
- Logs every discarded candidate with reason for debugging
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from keyword_analysis.config import Config
from keyword_analysis.stages.enrich import EnrichedKeyword
from keyword_analysis.utils.logger import get_logger
from keyword_analysis.utils.normalizer import jaccard_similarity, normalize

log = get_logger(__name__)


# Common brand names or platforms that might appear
COMMON_BRANDS = {
    "ikea", "livspace", "homelane", "urban ladder", "pepperfry", "urban company",
    "houzz", "pinterest", "instagram", "youtube", "amazon", "flipkart",
    "fiverr", "upwork", "freelancer", "justdial", "sulekha"
}


@dataclass
class DiscardedKeyword:
    text: str
    reason: str
    stage: str = "filter"


class FilterStage:
    def __init__(self, config: Config):
        self.cfg = config
        self.brand_blocklist = set(config.filter.brand_blocklist) | COMMON_BRANDS

    def _is_comparison_query(self, text: str) -> bool:
        """Keep brand if it's part of a comparative/alternative search."""
        return bool(re.search(r"\b(vs|versus|alternative|alternatives|like|compared to|or)\b", text))

    def _contains_disallowed_brand(self, text: str) -> bool:
        words = text.split()
        for brand in self.brand_blocklist:
            if brand in text:
                # If it's a comparison query, keep it!
                if self._is_comparison_query(text):
                    return False
                return True
        return False

    def _is_junk(self, text: str) -> bool:
        # Too many numbers or special patterns
        if re.search(r"\b\d{4,}\b", text):  # 4+ digit numbers (e.g. phone numbers or random IDs)
            return True
        # Check repeated characters like "aaaa"
        if re.search(r"(.)\1{3,}", text):
            return True
        return False

    def run(
        self, keywords: List[EnrichedKeyword], seed: str
    ) -> Tuple[List[EnrichedKeyword], List[DiscardedKeyword]]:
        norm_seed = normalize(seed)
        log.info("=== Starting Stage 3: Filter (%d candidates) ===", len(keywords))

        survivors: List[EnrichedKeyword] = []
        discarded: List[DiscardedKeyword] = []

        # Sort by unique sources descending, then similarity descending
        # so near-duplicate filtering keeps the stronger candidate
        sorted_keywords = sorted(
            keywords,
            key=lambda k: (k.unique_sources, k.similarity_to_seed, -k.distance),
            reverse=True,
        )

        kept_canonical_texts: List[str] = []

        for kw in sorted_keywords:
            text = kw.text

            # 1. Drop exact seed
            if text == norm_seed:
                discarded.append(DiscardedKeyword(text=text, reason="exact_seed"))
                continue

            # 2. Word count bounds
            if kw.word_count < self.cfg.filter.min_word_count:
                # Allow single word ONLY if it has strong intent modifier (rare)
                discarded.append(DiscardedKeyword(text=text, reason="generic_head_term_too_short"))
                continue

            if kw.word_count > self.cfg.filter.max_word_count:
                discarded.append(DiscardedKeyword(text=text, reason="phrase_too_long"))
                continue

            # 3. Relevance gate
            if kw.similarity_to_seed < self.cfg.thresholds.keep_threshold:
                discarded.append(
                    DiscardedKeyword(
                        text=text,
                        reason=f"similarity_below_keep_threshold ({kw.similarity_to_seed:.2f} < {self.cfg.thresholds.keep_threshold:.2f})",
                    )
                )
                continue

            # 4. Brand check
            if self._contains_disallowed_brand(text):
                discarded.append(DiscardedKeyword(text=text, reason="brand_without_comparison"))
                continue

            # 5. Junk / gibberish check
            if self._is_junk(text):
                discarded.append(DiscardedKeyword(text=text, reason="junk_or_malformed"))
                continue

            # 6. Near-duplicate suppression
            is_near_dup = False
            for kept in kept_canonical_texts:
                if jaccard_similarity(text, kept) >= self.cfg.filter.near_duplicate_threshold:
                    discarded.append(
                        DiscardedKeyword(
                            text=text,
                            reason=f"near_duplicate_of '{kept}' (jaccard >= {self.cfg.filter.near_duplicate_threshold})",
                        )
                    )
                    is_near_dup = True
                    break

            if is_near_dup:
                continue

            # All checks passed!
            survivors.append(kw)
            kept_canonical_texts.append(text)

        log.info(
            "Stage 3 complete: %d keywords kept, %d discarded",
            len(survivors),
            len(discarded),
        )
        return survivors, discarded
