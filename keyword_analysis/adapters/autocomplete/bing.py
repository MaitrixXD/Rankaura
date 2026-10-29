"""
Bing Autocomplete adapter. Optional, off by default.
"""

from __future__ import annotations

from typing import List

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

ENDPOINT = "https://api.bing.com/osjson.aspx"


class BingAutocompleteAdapter(BaseAdapter):
    name = "bing_autocomplete"

    def __init__(self, market: str = "en-IN", **kwargs):
        super().__init__(**kwargs)
        self._market = market

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        distance = kwargs.get("distance", 1)
        resp = requests.get(
            ENDPOINT,
            params={"query": query, "market": self._market},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        suggestions = data[1] if len(data) > 1 else []
        return [
            Candidate(
                text=s, source=self.name, distance=distance,
                rank=i + 1, raw_query=query
            )
            for i, s in enumerate(suggestions)
            if isinstance(s, str) and s.strip()
        ]
