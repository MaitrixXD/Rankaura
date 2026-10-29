"""
Wikipedia adapter — free, no API key.

Uses the Wikipedia API to find related articles, categories, and links
for a seed topic. Extracts entity names as candidate terms.
"""

from __future__ import annotations

from typing import List, Set

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

API = "https://en.wikipedia.org/w/api.php"


class WikipediaAdapter(BaseAdapter):
    name = "wikipedia"

    def __init__(self, max_results: int = 20, **kwargs):
        super().__init__(**kwargs)
        self._max_results = max_results

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        terms: Set[str] = set()
        headers = {"User-Agent": "KeyProspectorBot/1.0 (https://github.com; contact@example.com) requests"}

        # 1. Search for related articles
        search_resp = requests.get(API, params={
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": 10, "format": "json",
        }, headers=headers, timeout=10)
        search_resp.raise_for_status()
        search_results = search_resp.json().get("query", {}).get("search", [])
        for r in search_results:
            title = r.get("title", "")
            if title:
                terms.add(title.lower())

        # 2. Get categories and links from the top result
        if search_results:
            top_title = search_results[0]["title"]

            # Categories
            cat_resp = requests.get(API, params={
                "action": "query", "titles": top_title,
                "prop": "categories", "cllimit": 20, "format": "json",
            }, headers=headers, timeout=10)
            cat_resp.raise_for_status()
            pages = cat_resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                for cat in page.get("categories", []):
                    cat_title = cat.get("title", "").replace("Category:", "").lower()
                    if cat_title and not cat_title.startswith("articles"):
                        terms.add(cat_title)

            # Links (outgoing links from the article)
            link_resp = requests.get(API, params={
                "action": "query", "titles": top_title,
                "prop": "links", "pllimit": 30, "format": "json",
            }, headers=headers, timeout=10)
            link_resp.raise_for_status()
            pages = link_resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                for link in page.get("links", []):
                    link_title = link.get("title", "").lower()
                    if link_title and ":" not in link_title:
                        terms.add(link_title)

        results = sorted(terms)[:self._max_results]
        return [
            Candidate(text=t, source=self.name, distance=1, raw_query=query)
            for t in results
        ]
