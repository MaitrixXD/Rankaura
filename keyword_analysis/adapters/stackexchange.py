"""
StackExchange adapter — preferred customer-language source.

Uses the free StackExchange API (no key needed for low-volume reads).
Searches for question titles containing the seed, then extracts
n-gram phrases from those titles.
"""

from __future__ import annotations

from typing import List, Set

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger
from keyword_analysis.utils.normalizer import extract_ngrams, normalize

log = get_logger(__name__)

API = "https://api.stackexchange.com/2.3"


class StackExchangeAdapter(BaseAdapter):
    name = "stackexchange"

    def __init__(self, max_results: int = 20, sites: List[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._max_results = max_results
        self._sites = sites or ["diy", "stackoverflow"]

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        phrases: Set[str] = set()
        titles: List[str] = []

        for site in self._sites:
            try:
                resp = requests.get(f"{API}/search/excerpts", params={
                    "order": "desc", "sort": "relevance",
                    "q": query, "site": site, "pagesize": 15,
                    "filter": "default",
                }, timeout=10)
                resp.raise_for_status()
                items = resp.json().get("items", [])
                for item in items:
                    title = item.get("title", "")
                    if title:
                        titles.append(title)
            except Exception as e:
                log.warning("[%s] Failed for site %s: %s", self.name, site, e)
                continue

        # Extract n-gram phrases from question titles
        seed_norm = normalize(query)
        for title in titles:
            ngrams = extract_ngrams(title, min_n=2, max_n=5)
            for ng in ngrams:
                # Keep phrases that contain at least one seed word
                seed_tokens = set(seed_norm.split())
                ng_tokens = set(ng.split())
                if seed_tokens & ng_tokens:
                    phrases.add(ng)

        # Also add cleaned full titles as candidates
        for title in titles:
            normed = normalize(title)
            if len(normed.split()) <= 8:
                phrases.add(normed)

        results = sorted(phrases)[:self._max_results]
        return [
            Candidate(text=p, source=self.name, distance=1, raw_query=query)
            for p in results
        ]
