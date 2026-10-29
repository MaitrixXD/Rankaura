"""
Abstract base adapter.

Every data source (autocomplete, Datamuse, WordNet, Wikipedia, etc.) inherits
from BaseAdapter and implements _fetch_impl(). The base class handles:
  - Disk caching (via DiskCache)
  - Rate limiting (via RateLimiter)
  - Global request budget enforcement
  - Retry with exponential backoff
  - Graceful failure (returns [] on error, never raises)
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from keyword_analysis.utils.cache import DiskCache
from keyword_analysis.utils.logger import get_logger
from keyword_analysis.utils.rate_limiter import RateLimiter, RequestBudget

log = get_logger(__name__)


@dataclass
class Candidate:
    """A keyword candidate produced by an adapter."""
    text: str
    source: str           # Adapter name that produced this
    distance: int = 0     # 0=seed, 1=Layer1/autocomplete-on-seed, 2=autocomplete-on-L1
    rank: Optional[int] = None           # Position in autocomplete list (if applicable)
    raw_query: Optional[str] = None      # The query that produced this candidate
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAdapter(ABC):
    """
    Base class for all data-source adapters.

    Subclasses implement _fetch_impl() which does the actual work.
    Call fetch() to get results with caching, rate-limiting, and retries.
    """

    name: str = "base"

    def __init__(
        self,
        cache: DiskCache,
        rate_limiter: RateLimiter,
        budget: RequestBudget,
        max_retries: int = 3,
        retry_backoff: float = 1.5,
    ):
        self._cache = cache
        self._limiter = rate_limiter
        self._budget = budget
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

    @abstractmethod
    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        """
        Subclass implements the actual data fetch.
        Should return a list of Candidate objects.
        Must NOT handle caching or rate-limiting (base class does that).
        """
        ...

    def fetch(self, query: str, **kwargs) -> List[Candidate]:
        """
        Fetch results with caching, rate-limiting, budget check, and retries.
        Never raises — returns [] on failure.
        """
        # Check cache first
        cache_params = {"q": query, **kwargs}
        cached = self._cache.get(self.name, cache_params)
        if cached is not None:
            return [Candidate(**c) for c in cached]

        # Budget check
        if self._budget.exhausted:
            log.warning("[%s] Budget exhausted, skipping query: %s", self.name, query)
            return []

        # Retry loop with backoff
        last_err = None
        for attempt in range(1, self._max_retries + 1):
            try:
                self._limiter.wait()
                if not self._budget.consume(1):
                    return []

                results = self._fetch_impl(query, **kwargs)

                # Cache the results
                self._cache.set(
                    self.name, cache_params,
                    [{"text": c.text, "source": c.source, "distance": c.distance,
                      "rank": c.rank, "raw_query": c.raw_query, "metadata": c.metadata}
                     for c in results]
                )
                return results

            except Exception as e:
                last_err = e
                if attempt < self._max_retries:
                    wait = self._retry_backoff ** attempt
                    log.warning(
                        "[%s] Attempt %d failed (%s), retrying in %.1fs",
                        self.name, attempt, e, wait
                    )
                    time.sleep(wait)

        log.error(
            "[%s] All %d attempts failed for query '%s': %s\n%s",
            self.name, self._max_retries, query, last_err, traceback.format_exc()
        )
        return []

    def is_available(self) -> bool:
        """Check if this adapter is functional. Override for dependency checks."""
        return True
