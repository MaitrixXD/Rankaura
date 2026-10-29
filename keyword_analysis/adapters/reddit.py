"""
Reddit adapter — optional, uses public JSON endpoints (no API key).

Searches subreddit titles for the seed topic and extracts phrases.
Verify access before relying on this — Reddit can block non-authenticated requests.
"""

from __future__ import annotations

from typing import List, Set

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger
from keyword_analysis.utils.normalizer import extract_ngrams, normalize

log = get_logger(__name__)


class RedditAdapter(BaseAdapter):
    name = "reddit"

    def __init__(self, max_results: int = 20, **kwargs):
        super().__init__(**kwargs)
        self._max_results = max_results

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        phrases: Set[str] = set()

        # Reddit public JSON search (no auth needed, but rate-limited)
        resp = requests.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "limit": 25, "sort": "relevance", "t": "year"},
            timeout=10,
            headers={"User-Agent": "KeywordAnalysis/0.1 (research tool)"},
        )
        resp.raise_for_status()
        posts = resp.json().get("data", {}).get("children", [])

        titles = [p["data"]["title"] for p in posts if p.get("data", {}).get("title")]

        seed_norm = normalize(query)
        seed_tokens = set(seed_norm.split())

        for title in titles:
            # Extract n-gram phrases
            ngrams = extract_ngrams(title, min_n=2, max_n=5)
            for ng in ngrams:
                ng_tokens = set(ng.split())
                if seed_tokens & ng_tokens:
                    phrases.add(ng)

            # Short titles as full candidates
            normed = normalize(title)
            if len(normed.split()) <= 8:
                phrases.add(normed)

        results = sorted(phrases)[:self._max_results]
        return [
            Candidate(text=p, source=self.name, distance=1, raw_query=query)
            for p in results
        ]
