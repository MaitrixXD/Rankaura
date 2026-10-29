"""
Stage 5: Verify (Optional)

Uses Gemini to verify that the top keywords make sense and are good for ranking.
Filters out nonsense keywords and selects the 5 best ones.
"""

from __future__ import annotations

from typing import List, Optional

from keyword_analysis.adapters.llm import GeminiAdapter
from keyword_analysis.config import Config
from keyword_analysis.stages.filter import is_safe_top_keyword
from keyword_analysis.stages.score import ScoredKeyword
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)


class VerifyStage:
    def __init__(self, config: Config, gemini_adapter: Optional[GeminiAdapter] = None):
        self.cfg = config
        self.gemini = gemini_adapter

    def run(self, seed: str, scored_keywords: List[ScoredKeyword]) -> List[ScoredKeyword]:
        """Original verification method (keeping for compatibility)."""
        safe_scored = [k for k in scored_keywords if is_safe_top_keyword(k.text, seed)]
        if not self.gemini or not self.cfg.providers.gemini or not self.gemini.is_available():
            log.info("Gemini verification skipped: adapter not available or disabled.")
            return safe_scored[:5]

        log.info("=== Starting Stage 6: Verify (using Gemini) ===")
        
        # Take the top 25 safe candidates for verification
        candidates = safe_scored[:25]
        candidate_texts = [k.text for k in candidates]
        
        verified_texts = self.gemini.verify_keywords(seed, candidate_texts)
        
        # Map verified texts back to ScoredKeyword objects
        verified_keywords = []
        text_to_kw = {k.text.lower(): k for k in safe_scored}
        
        for text in verified_texts:
            norm_text = text.lower()
            if norm_text in text_to_kw:
                verified_keywords.append(text_to_kw[norm_text])
            else:
                log.debug(f"Gemini suggested keyword not in original list: {text}")
                
        # If verification failed or returned nothing, fallback to original top 5
        if not verified_keywords:
            log.warning("Gemini verification returned no valid keywords. Falling back to safe scored.")
            return safe_scored[:5]
            
        log.info(f"Gemini verification complete: selected {len(verified_keywords)} best keywords")
        return verified_keywords[:5]

    def verify_from_clusters(self, seed: str, clusters: List[KeywordCluster]) -> Dict[str, List[ScoredKeyword]]:
        """
        Gathers primary and top supporting keywords from clusters,
        filters out any locations, songs, and junk, and lets Gemini 
        pick the absolute best 5 High and 5 Medium competition keywords from those.
        """
        # Gather candidate keywords from clusters
        candidates: List[ScoredKeyword] = []
        for c in clusters:
            candidates.append(c.primary_keyword)
            candidates.extend(c.supporting_keywords[:3])

        # Deduplicate while preserving ranking order, take top 40 candidates
        seen_texts = set()
        unique_candidates: List[ScoredKeyword] = []
        for kw in candidates:
            norm = kw.text.lower()
            if norm not in seen_texts:
                seen_texts.add(norm)
                unique_candidates.append(kw)
        unique_candidates = unique_candidates[:40]

        if not self.gemini or not self.cfg.providers.gemini or not self.gemini.is_available():
            log.info("Gemini verification skipped: adapter not available or disabled.")
            safe_cands = [kw for kw in unique_candidates if is_safe_top_keyword(kw.text, seed)]
            return {
                "high": safe_cands[:5],
                "medium": safe_cands[5:10]
            }

        log.info("=== Starting Gemini Post-Cluster Verification ===")
        
        candidate_texts = [k.text for k in unique_candidates]
        verified_texts = self.gemini.verify_keywords(seed, candidate_texts)
        
        verified_keywords = []
        text_to_kw = {k.text.lower(): k for k in unique_candidates}
        
        for text in verified_texts:
            norm_text = text.lower().strip()
            if norm_text in text_to_kw:
                verified_keywords.append(text_to_kw[norm_text])
            else:
                # Near-match resolution
                for cand_text, kw in text_to_kw.items():
                    if cand_text == norm_text or cand_text in norm_text or norm_text in cand_text:
                        if kw not in verified_keywords:
                            verified_keywords.append(kw)
                            break
        
        # Filter verified keywords
        final_keywords = [
            k for k in verified_keywords 
            if is_safe_top_keyword(k.text, seed)
        ]
        
        # Backfill if we have fewer than 10
        if len(final_keywords) < 10:
            existing_texts = {k.text.lower() for k in final_keywords}
            for kw in unique_candidates:
                if kw.text.lower() not in existing_texts and is_safe_top_keyword(kw.text, seed):
                    final_keywords.append(kw)
                    existing_texts.add(kw.text.lower())
                    if len(final_keywords) >= 10:
                        break

        return {
            "high": final_keywords[:5],
            "medium": final_keywords[5:10]
        }
