"""
In-process TTL cache for chat query results.

Architecture role: replaces the "Cache lookup / Cache write" boxes in the
pipeline diagram. No Redis dependency — uses a thread-safe in-memory dict
with per-entry expiry. Safe to swap with a Redis-backed implementation
later by keeping the same get/set/make_key signature.
"""

from __future__ import annotations

import re
import time
import threading
import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


_DEFAULT_TTL_SECONDS = 60
_MAX_ENTRIES = 512

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


_WS_RE = re.compile(r'\s+')


def _normalize(text: str) -> str:
    return _WS_RE.sub(' ', text.strip().lower())


def make_key(employee_id: int, intent: str, message: str) -> str:
    norm = _normalize(message)
    digest = hashlib.sha1(f'{employee_id}|{intent}|{norm}'.encode('utf-8')).hexdigest()
    return f'chat:{digest}'


def get(key: str) -> Optional[Any]:
    now = time.time()
    with _lock:
        entry = _store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < now:
            _store.pop(key, None)
            return None
        return value


def set(key: str, value: Any, ttl: int = _DEFAULT_TTL_SECONDS) -> None:
    expires_at = time.time() + max(1, ttl)
    with _lock:
        if len(_store) >= _MAX_ENTRIES:
            # cheap eviction: drop the oldest-expiring entry
            oldest_key = min(_store, key=lambda k: _store[k][0])
            _store.pop(oldest_key, None)
        _store[key] = (expires_at, value)


def clear() -> None:
    with _lock:
        _store.clear()


def stats() -> dict:
    with _lock:
        return {'entries': len(_store), 'max_entries': _MAX_ENTRIES}
