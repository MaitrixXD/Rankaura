"""
Disk-based request cache using SQLite.

Stores HTTP response payloads keyed by (adapter_name, request_params_hash).
TTL-aware: entries older than cache_ttl_hours are treated as expired.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

# Default cache location — project_root/.cache/keyword_analysis.db
_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"


class DiskCache:
    """
    SQLite-backed cache for adapter responses.

    Each entry stores:
        key     — deterministic hash of (adapter, params)
        value   — JSON-serialised response
        ts      — Unix timestamp of insertion
    """

    def __init__(
        self,
        ttl_hours: int = 72,
        db_dir: Optional[Path] = None,
    ):
        import threading
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_hours * 3600
        db_dir = db_dir or _DEFAULT_DIR
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_dir / "keyword_analysis.db"
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._init_table()
        log.info("Cache opened at %s (TTL=%dh)", self._db_path, ttl_hours)

    def _init_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                ts    REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def _make_key(adapter: str, params: dict) -> str:
        raw = json.dumps({"a": adapter, "p": params}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, adapter: str, params: dict) -> Optional[Any]:
        """Return cached value or None if missing/expired."""
        key = self._make_key(adapter, params)
        with self._lock:
            row = self._conn.execute(
                "SELECT value, ts FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            value_json, ts = row
            if ts is None or (time.time() - float(ts)) > self._ttl_seconds:
                # Expired — remove and return None
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
                return None
            try:
                return json.loads(value_json)
            except Exception:
                return None

    def set(self, adapter: str, params: dict, value: Any) -> None:
        """Store a value in the cache (upsert)."""
        key = self._make_key(adapter, params)
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, ts) VALUES (?, ?, ?)",
                    (key, json.dumps(value), time.time()),
                )
                self._conn.commit()
            except Exception as e:
                log.warning("Cache write error: %s", e)

    def clear(self) -> None:
        """Drop all cached entries."""
        self._conn.execute("DELETE FROM cache")
        self._conn.commit()
        log.info("Cache cleared")

    def purge_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        cutoff = time.time() - self._ttl_seconds
        cursor = self._conn.execute("DELETE FROM cache WHERE ts < ?", (cutoff,))
        self._conn.commit()
        removed = cursor.rowcount
        if removed:
            log.info("Purged %d expired cache entries", removed)
        return removed

    def close(self) -> None:
        self._conn.close()
