"""
Amazon Autocomplete adapter. OFF by default (product-oriented).
Only useful for product seeds, not services.
"""

from __future__ import annotations

from typing import List

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

ENDPOINT = "https://completion.amazon.in/api/2017/suggestions"


class AmazonAutocompleteAdapter(BaseAdapter):
    name = "amazon_autocomplete"

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        distance = kwargs.get("distance", 1)
        resp = requests.get(
            ENDPOINT,
            params={
                "mid": "A21TJRUUN4KGV",  # Amazon India
                "alias": "aps",
                "prefix": query,
            },
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        suggestions = data.get("suggestions", [])
        return [
            Candidate(
                text=s.get("value", ""), source=self.name,
                distance=distance, rank=i + 1, raw_query=query
            )
            for i, s in enumerate(suggestions)
            if s.get("value", "").strip()
        ]
