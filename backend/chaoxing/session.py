"""
Thread-local session management.

Supports multi-account parallel execution: each thread gets its own
active_session and font_decrypt_loaded state. Thread N sets
`_thread_local.store.active_session = "chaoxing-chrome-N"`, and all
pw_* calls in that thread target that session automatically.
"""

import threading
from typing import Optional


class _ThreadLocalStore:
    """Per-thread mutable state for browser session isolation."""

    def __init__(self):
        self.active_session: Optional[str] = None
        self.font_decrypt_loaded: bool = False


_thread_local = threading.local()


def _get_tls() -> _ThreadLocalStore:
    """Get or lazily create the thread-local store for the current thread."""
    if not hasattr(_thread_local, 'store'):
        _thread_local.store = _ThreadLocalStore()
    return _thread_local.store


def set_active_session(name: Optional[str]):
    """Override the Playwright session for the CURRENT THREAD only.

    In multi-threaded mode each thread calls this with its own session
    (e.g. "chaoxing-chrome-0", "chaoxing-chrome-1").  In single-account
    mode the default thread never calls it, so active_session stays None
    and _get_active_session() falls back to cfg("session").
    """
    _get_tls().active_session = name


def _get_active_session() -> str:
    """Return the active session for the CURRENT THREAD.

    Priority: thread-local override > config default.
    """
    # Deferred import to avoid circular dependency at module load time
    from chaoxing.config import cfg
    return _get_tls().active_session or cfg("session") or "chaoxing-chrome"
