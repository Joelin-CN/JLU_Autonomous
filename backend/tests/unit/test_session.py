"""Tests for chaoxing.session module."""

import threading

from chaoxing.session import _get_tls, _ThreadLocalStore, set_active_session, _get_active_session


class TestThreadLocalStore:
    """Test thread-local session management."""

    def test_default_store(self):
        """_get_tls() should return a _ThreadLocalStore instance."""
        # Other tests may leave the main thread's session set; reset first so
        # this test checks the store's default state, not a stale override.
        set_active_session(None)
        tls = _get_tls()
        assert isinstance(tls, _ThreadLocalStore)
        assert tls.active_session is None
        assert tls.font_decrypt_loaded is False

    def test_set_active_session(self):
        """set_active_session() should update thread-local state."""
        set_active_session("chaoxing-chrome-0")
        assert _get_tls().active_session == "chaoxing-chrome-0"
        # Reset for other tests
        set_active_session(None)

    def test_get_active_session_fallback(self):
        """_get_active_session() should fall back to config default."""
        session = _get_active_session()
        assert session  # Should be a non-empty string from config or thread-local

    def test_thread_isolation(self):
        """Each thread should have its own session state."""
        results = {}

        def thread_worker(thread_id):
            set_active_session(f"chaoxing-chrome-{thread_id}")
            results[thread_id] = _get_tls().active_session

        t1 = threading.Thread(target=thread_worker, args=(1,))
        t2 = threading.Thread(target=thread_worker, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.get(1) == "chaoxing-chrome-1"
        assert results.get(2) == "chaoxing-chrome-2"

    def test_font_decrypt_state(self):
        """font_decrypt_loaded should be persistent per thread."""
        tls = _get_tls()
        assert tls.font_decrypt_loaded is False
        tls.font_decrypt_loaded = True
        assert tls.font_decrypt_loaded is True
        tls.font_decrypt_loaded = False  # Reset
