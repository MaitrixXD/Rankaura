"""
SERP competition adapter — optional, requires Google Programmable Search API key.

Analyses the top 10 search results for a keyword to estimate competition.
Only runs on the top ~50 scored keywords to respect the free daily quota.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# Domains that indicate high competition
BIG_DOMAINS = {
    "wikipedia.org", "amazon.com", "amazon.in", "flipkart.com",
    "youtube.com", "facebook.com", "instagram.com", "linkedin.com",
    "quora.com", "reddit.com", "twitter.com", "x.com",
    "forbes.com", "businessinsider.com", "nytimes.com",
}


@dataclass
class SerpAnalysis:
    """Competition analysis results from SERP."""
    keyword: str
    competition_score: float    # 0-1, higher = more competitive
    confidence: str             # high/medium/low
    big_domain_count: int
    unique_domains: int
    title_match_ratio: float    # Fraction of results with keyword in title
    forum_count: int            # Number of forum/blog results (low competition signal)
    details: dict


class SerpAdapter(BaseAdapter):
    name = "serp"

    def __init__(self, api_key: str, cx: str, daily_quota: int = 100,
                 safety_margin: int = 10, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key
        self._cx = cx
        self._daily_quota = daily_quota
        self._safety_margin = safety_margin
        self._daily_used = 0

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        # This adapter doesn't return candidates — it analyses competition
        # The fetch method is used for caching infrastructure
        return []

    def analyse_competition(self, keyword: str) -> Optional[SerpAnalysis]:
        """Analyse SERP competition for a single keyword."""
        if self._daily_used >= (self._daily_quota - self._safety_margin):
            log.warning("SERP daily quota nearly exhausted (%d/%d)",
                        self._daily_used, self._daily_quota)
            return None

        cache_params = {"q": keyword, "type": "serp_analysis"}
        cached = self._cache.get(self.name, cache_params)
        if cached is not None:
            return SerpAnalysis(**cached)

        self._limiter.wait()
        try:
            resp = requests.get(ENDPOINT, params={
                "key": self._api_key, "cx": self._cx,
                "q": keyword, "num": 10,
            }, timeout=15)
            resp.raise_for_status()
            self._daily_used += 1
            results = resp.json().get("items", [])
        except Exception as e:
            log.error("SERP request failed for '%s': %s", keyword, e)
            return None

        if not results:
            return None

        # Analyse the top 10 results
        domains = set()
        big_domain_count = 0
        title_matches = 0
        forum_count = 0
        keyword_lower = keyword.lower()
        keyword_tokens = set(keyword_lower.split())

        for item in results[:10]:
            link = item.get("link", "")
            title = item.get("title", "").lower()
            # Extract domain
            try:
                from urllib.parse import urlparse
                domain = urlparse(link).netloc.replace("www.", "")
                domains.add(domain)
                if any(bd in domain for bd in BIG_DOMAINS):
                    big_domain_count += 1
                # Forums/blogs suggest lower competition
                if any(w in domain for w in ["forum", "blog", "reddit", "quora", "stackexchange"]):
                    forum_count += 1
            except Exception:
                pass
            # Title keyword match
            if keyword_tokens and len(keyword_tokens & set(title.split())) >= len(keyword_tokens) * 0.6:
                title_matches += 1

        unique_domains = len(domains)
        title_match_ratio = title_matches / max(len(results[:10]), 1)

        # Competition score: higher = more competitive
        # Big domains + many exact title matches = competitive
        # Few domains + forums = less competitive
        comp = 0.0
        comp += min(big_domain_count / 5, 1.0) * 0.4
        comp += title_match_ratio * 0.3
        comp += min(unique_domains / 10, 1.0) * 0.15
        comp -= min(forum_count / 3, 1.0) * 0.15
        comp = max(0.0, min(1.0, comp))

        confidence = "high" if len(results) >= 8 else "medium" if len(results) >= 4 else "low"

        analysis = SerpAnalysis(
            keyword=keyword,
            competition_score=round(comp, 2),
            confidence=confidence,
            big_domain_count=big_domain_count,
            unique_domains=unique_domains,
            title_match_ratio=round(title_match_ratio, 2),
            forum_count=forum_count,
            details={"results_count": len(results)},
        )

        # Cache the analysis
        self._cache.set(self.name, cache_params, {
            "keyword": analysis.keyword,
            "competition_score": analysis.competition_score,
            "confidence": analysis.confidence,
            "big_domain_count": analysis.big_domain_count,
            "unique_domains": analysis.unique_domains,
            "title_match_ratio": analysis.title_match_ratio,
            "forum_count": analysis.forum_count,
            "details": analysis.details,
        })

        return analysis

    def is_available(self) -> bool:
        return bool(self._api_key and self._cx)
