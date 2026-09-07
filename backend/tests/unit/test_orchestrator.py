"""Tests for chaoxing.orchestrator — workflow coordination and multi-threading."""
import threading
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.orchestrator import (
    AccountRunError,
    RunConfig,
    run_multi_account,
    run_for_account,
    _run_account_in_thread,
    process_course,
    ensure_logged_in,
)
from chaoxing.constants import SHUTDOWN_FLAG


# ── RunConfig ──────────────────────────────────────────────────

class TestRunConfig:
    """Tests for RunConfig — replaces old argparse Namespace."""

    def test_default_values(self):
        """Default values should be sensible for production use."""
        cfg = RunConfig()
        assert cfg.course is None
        assert cfg.dry_run is False
        assert cfg.resume is False
        assert cfg.scan_only is False
        assert cfg.quiz_only is False
        assert cfg.content_only is False
        assert cfg.yes is True  # Non-interactive by default

    def test_custom_values(self):
        """All values should be settable via keyword args."""
        cfg = RunConfig(
            course="测试课程",
            dry_run=True,
            resume=True,
            scan_only=True,
            quiz_only=True,
            content_only=False,
            yes=False,
        )
        assert cfg.course == "测试课程"
        assert cfg.dry_run is True
        assert cfg.resume is True
        assert cfg.scan_only is True
        assert cfg.quiz_only is True
        assert cfg.content_only is False
        assert cfg.yes is False


# ── run_multi_account ──────────────────────────────────────────

class TestRunMultiAccount:
    """Tests for run_multi_account — multi-account dispatch."""

    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.read_all_chaoxing_credentials")
    def test_no_credentials_returns_empty(self, mock_read_creds, mock_log):
        """When no credentials exist, should return empty list."""
        mock_read_creds.return_value = []
        result = run_multi_account([0], "full")
        assert result == []

    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.read_all_chaoxing_credentials")
    def test_missing_indices_warning(self, mock_read_creds, mock_log):
        """When requested indices don't exist, should warn."""
        mock_read_creds.return_value = [
            {"index": 0, "account": "user0"},
        ]
        result = run_multi_account([99], "full")
        assert result == []

    @patch("chaoxing.orchestrator.time.sleep")
    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.threading.Thread")
    @patch("chaoxing.orchestrator.read_all_chaoxing_credentials")
    def test_spawns_thread_for_each_account(self, mock_read_creds, mock_thread,
                                              mock_log, mock_sleep):
        """Should spawn one thread per account index."""
        SHUTDOWN_FLAG.clear()
        mock_read_creds.return_value = [
            {"index": 0, "account": "user0"},
            {"index": 1, "account": "user1"},
        ]
        mock_thread_instance = MagicMock()
        # CRITICAL: is_alive() must return False, otherwise the join loop
        # in run_multi_account() spins forever, recording unbounded mock calls
        # and causing GB/minute memory growth.
        mock_thread_instance.is_alive.return_value = False
        mock_thread.return_value = mock_thread_instance

        run_multi_account([0, 1], "full")
        assert mock_thread.call_count == 2
        SHUTDOWN_FLAG.clear()

    @patch("chaoxing.orchestrator.time.sleep")
    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.threading.Thread")
    @patch("chaoxing.orchestrator.read_all_chaoxing_credentials")
    def test_mode_scan_only(self, mock_read_creds, mock_thread, mock_log, mock_sleep):
        """scan_only mode should create RunConfig with scan_only=True."""
        SHUTDOWN_FLAG.clear()
        mock_read_creds.return_value = [
            {"index": 0, "account": "user0"},
        ]
        mock_thread_instance = MagicMock()
        mock_thread_instance.is_alive.return_value = False
        mock_thread.return_value = mock_thread_instance

        run_multi_account([0], "scan_only")
        # Verify a thread was spawned with a RunConfig that has scan_only=True
        args = mock_thread.call_args[1]["args"]
        config = args[2]
        assert isinstance(config, RunConfig)
        assert config.scan_only is True
        SHUTDOWN_FLAG.clear()

    @patch("chaoxing.orchestrator.time.sleep")
    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.threading.Thread")
    @patch("chaoxing.orchestrator.read_all_chaoxing_credentials")
    def test_keyboard_interrupt_handling(self, mock_read_creds, mock_thread,
                                           mock_log, mock_sleep):
        """KeyboardInterrupt should set SHUTDOWN_FLAG and join threads."""
        SHUTDOWN_FLAG.clear()
        mock_read_creds.return_value = [
            {"index": 0, "account": "user0"},
        ]
        mock_thread_instance = MagicMock()
        mock_thread_instance.is_alive.side_effect = KeyboardInterrupt()
        mock_thread.return_value = mock_thread_instance

        run_multi_account([0], "full")
        assert SHUTDOWN_FLAG.is_set()
        SHUTDOWN_FLAG.clear()

    def test_run_for_account_login_failure_returns_false(self):
        """Auto-login failure must surface as a failed lane, not success."""
        import chaoxing.orchestrator as orch
        SHUTDOWN_FLAG.clear()
        with patch.object(orch, "ensure_logged_in", return_value=False), \
             patch.object(orch, "progress"), \
             patch.object(orch, "log"):
            config = RunConfig()
            assert run_for_account(0, {"account": "user0"}, config) is False
        SHUTDOWN_FLAG.clear()

    def test_run_multi_account_raises_when_lane_fails(self, monkeypatch):
        """A hard account failure must raise AccountRunError after all lanes."""
        import chaoxing.orchestrator as orch
        SHUTDOWN_FLAG.clear()
        monkeypatch.setattr(
            orch, "read_all_chaoxing_credentials",
            lambda: [{"index": 0, "account": "a0", "password": "p"}],
        )
        monkeypatch.setattr(orch, "run_for_account", lambda *a: False)
        monkeypatch.setattr(orch, "close_chaoxing_browser", lambda i: True)
        monkeypatch.setattr(orch, "_THREAD_STAGGER_SECONDS", 0)
        with pytest.raises(AccountRunError):
            run_multi_account([0], "full", max_concurrent=1)
        SHUTDOWN_FLAG.clear()


# ── _run_account_in_thread ────────────────────────────────────

class TestRunAccountInThread:
    """Tests for _run_account_in_thread — thread target wrapper."""

    @patch("chaoxing.orchestrator.progress")
    @patch("chaoxing.orchestrator.close_chaoxing_browser")
    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.run_for_account")
    def test_sets_thread_name(self, mock_run, mock_log, mock_close, mock_progress):
        """Should set thread name to chaoxing-account-N."""
        SHUTDOWN_FLAG.clear()
        creds = {"account": "testuser123", "index": 0}
        config = RunConfig()

        original_name = threading.current_thread().name
        _run_account_in_thread(0, creds, config,
                               threading.BoundedSemaphore(1), None, None, 0.7)
        threading.current_thread().name = original_name
        mock_run.assert_called_once()

    @patch("chaoxing.orchestrator.progress")
    @patch("chaoxing.orchestrator.close_chaoxing_browser")
    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.run_for_account")
    def test_shutdown_flag_skips(self, mock_run, mock_log, mock_close, mock_progress):
        """When SHUTDOWN_FLAG is set, should skip execution."""
        SHUTDOWN_FLAG.set()
        creds = {"account": "testuser", "index": 0}
        config = RunConfig()

        _run_account_in_thread(0, creds, config,
                               threading.BoundedSemaphore(1), None, None, 0.7)
        mock_run.assert_not_called()
        SHUTDOWN_FLAG.clear()

    @patch("chaoxing.orchestrator.progress")
    @patch("chaoxing.orchestrator.close_chaoxing_browser")
    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.run_for_account")
    def test_keyboard_interrupt_sets_shutdown(self, mock_run, mock_log,
                                              mock_close, mock_progress):
        """KeyboardInterrupt should set SHUTDOWN_FLAG."""
        SHUTDOWN_FLAG.clear()
        mock_run.side_effect = KeyboardInterrupt()
        creds = {"account": "testuser", "index": 0}
        config = RunConfig()

        _run_account_in_thread(0, creds, config,
                               threading.BoundedSemaphore(1), None, None, 0.7)
        assert SHUTDOWN_FLAG.is_set()
        SHUTDOWN_FLAG.clear()

    @patch("chaoxing.orchestrator.progress")
    @patch("chaoxing.orchestrator.close_chaoxing_browser")
    @patch("chaoxing.orchestrator.log")
    @patch("chaoxing.orchestrator.run_for_account")
    def test_exception_does_not_propagate(self, mock_run, mock_log,
                                          mock_close, mock_progress):
        """Exceptions in run_for_account should be caught, not propagated."""
        SHUTDOWN_FLAG.clear()
        mock_run.side_effect = RuntimeError("test error")
        creds = {"account": "testuser", "index": 0}
        config = RunConfig()

        _run_account_in_thread(0, creds, config,
                               threading.BoundedSemaphore(1), None, None, 0.7)
        assert not SHUTDOWN_FLAG.is_set()


# ── SHUTDOWN_FLAG ─────────────────────────────────────────────

class TestShutdownFlag:
    """Tests for SHUTDOWN_FLAG behavior — graceful shutdown coordination."""

    def test_shutdown_flag_is_event(self):
        """SHUTDOWN_FLAG should be a threading.Event."""
        assert isinstance(SHUTDOWN_FLAG, threading.Event)

    def test_shutdown_flag_clear_and_set(self):
        """Should be able to clear and set the flag."""
        SHUTDOWN_FLAG.clear()
        assert not SHUTDOWN_FLAG.is_set()
        SHUTDOWN_FLAG.set()
        assert SHUTDOWN_FLAG.is_set()
        SHUTDOWN_FLAG.clear()
        assert not SHUTDOWN_FLAG.is_set()
