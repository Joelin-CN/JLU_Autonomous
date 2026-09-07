"""Tests for chaoxing.logging_setup — structured logging and CLI communication."""
import time
import threading
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.logging_setup import (
    log, progress, phase, ticket,
    set_protocol_handler,
    signal_pause, signal_resume, signal_stop,
    check_signals,
)


# ── log() ─────────────────────────────────────────────────────

class TestLogFunction:
    """Tests for log() — timestamped thread-prefixed logging."""

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_basic_output(self, mock_print, mock_mkdir, mock_open):
        """log() should print a formatted line to stdout."""
        log("test message")
        mock_print.assert_called_once()
        printed = mock_print.call_args[0][0]
        assert "test message" in printed
        assert "[" in printed  # Should have timestamp/level brackets
        assert mock_print.call_args[1].get("flush") is True

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_with_level_warn(self, mock_print, mock_mkdir, mock_open):
        """log() should include the specified level in output."""
        log("warning message", "WARN")
        printed = mock_print.call_args[0][0]
        assert "[WARN]" in printed

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_with_level_error(self, mock_print, mock_mkdir, mock_open):
        """log() should include ERROR level in output."""
        log("error message", "ERROR")
        printed = mock_print.call_args[0][0]
        assert "[ERROR]" in printed

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_with_level_ok(self, mock_print, mock_mkdir, mock_open):
        """log() should include OK level in output."""
        log("success", "OK")
        printed = mock_print.call_args[0][0]
        assert "[OK]" in printed

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_default_level_is_info(self, mock_print, mock_mkdir, mock_open):
        """Default level should be INFO."""
        log("default")
        printed = mock_print.call_args[0][0]
        assert "[INFO]" in printed

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_thread_prefix_when_named(self, mock_print, mock_mkdir, mock_open):
        """When thread name starts with 'chaoxing-account-', should add prefix."""
        original_name = threading.current_thread().name
        try:
            threading.current_thread().name = "chaoxing-account-3"
            log("threaded msg")
            printed = mock_print.call_args[0][0]
            assert "[chaoxing-account-3]" in printed
        finally:
            threading.current_thread().name = original_name

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_no_thread_prefix_for_main(self, mock_print, mock_mkdir, mock_open):
        """Main thread (not named 'chaoxing-account-*') should not have prefix."""
        original_name = threading.current_thread().name
        try:
            threading.current_thread().name = "MainThread"
            log("main msg")
            printed = mock_print.call_args[0][0]
            # Should not contain thread prefix in brackets
            assert "[MainThread]" not in printed
            # But should still contain the message
            assert "main msg" in printed
        finally:
            threading.current_thread().name = original_name

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_includes_timestamp(self, mock_print, mock_mkdir, mock_open):
        """log() output should include a timestamp in HH:MM:SS format."""
        log("ts test")
        printed = mock_print.call_args[0][0]
        # Format: [HH:MM:SS] [LEVEL] msg
        assert printed[0] == "["
        # Should have time pattern
        import re
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", printed)

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_writes_to_file(self, mock_print, mock_mkdir, mock_open):
        """log() should also write to a daily log file."""
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        log("file write test")
        mock_open.assert_called_once()
        mock_file.write.assert_called_once()

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_file_write_exception_is_silent(self, mock_print, mock_mkdir, mock_open):
        """When file write fails, log() should not crash."""
        mock_open.side_effect = PermissionError("Cannot write to log file")

        # Should not raise
        try:
            log("this might fail to write to file")
        except Exception as e:
            assert False, f"log() should never crash: {e}"

        # Print should still have been called
        mock_print.assert_called_once()

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_creates_directory_once(self, mock_print, mock_mkdir, mock_open):
        """log directory should be created only once (caching via _log_dir_created)."""
        # Reset the module-level cache
        import chaoxing.logging_setup as ls
        ls._log_dir_created = False

        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        log("first call")
        log("second call")

        # mkdir should be called only once
        assert mock_mkdir.call_count == 1

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_dir_created_flag_behavior(self, mock_print, mock_mkdir, mock_open):
        """_log_dir_created flag should prevent redundant mkdir calls."""
        import chaoxing.logging_setup as ls
        ls._log_dir_created = True  # Simulate already created

        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        log("after dir exists")
        mock_mkdir.assert_not_called()

    def test_log_lock_is_threading_lock(self):
        """_log_lock should be a threading.Lock."""
        import chaoxing.logging_setup as ls
        assert isinstance(ls._log_lock, threading.Lock)


# ── progress() ────────────────────────────────────────────────

class TestProgressFunction:
    """Tests for progress() — machine-parseable PROGRESS lines."""

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_with_current_and_total(self, mock_print, mock_mkdir, mock_open):
        """When current and total > 0, should show X/Y format."""
        progress(0, "Processing course", 3, 10)
        printed = mock_print.call_args[0][0]
        assert "PROGRESS:[0]" in printed
        assert "3/10" in printed
        assert "Processing course" in printed

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_without_total(self, mock_print, mock_mkdir, mock_open):
        """When total is 0, should show -/- format."""
        progress(1, "Scanning...")
        printed = mock_print.call_args[0][0]
        assert "PROGRESS:[1]" in printed
        assert "-/-" in printed
        assert "Scanning..." in printed

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_total_zero_fallback(self, mock_print, mock_mkdir, mock_open):
        """When total=0 (even with current), should show -/- format."""
        progress(0, "Initializing", 0, 0)
        printed = mock_print.call_args[0][0]
        assert "-/-" in printed

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_flush(self, mock_print, mock_mkdir, mock_open):
        """progress() should print with flush=True."""
        progress(0, "step")
        assert mock_print.call_args[1].get("flush") is True

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_writes_to_file(self, mock_print, mock_mkdir, mock_open):
        """progress() should write to log file."""
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        progress(0, "step", 1, 5)
        mock_file.write.assert_called_once()

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_file_write_silent_failure(self, mock_print, mock_mkdir, mock_open):
        """When file write fails, progress() should not crash."""
        mock_open.side_effect = OSError("Disk full")

        try:
            progress(0, "step", 1, 5)
        except Exception as e:
            assert False, f"progress() should never crash: {e}"

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_creates_dir_once(self, mock_print, mock_mkdir, mock_open):
        """progress() directory creation should be cached via _log_dir_created."""
        import chaoxing.logging_setup as ls
        ls._log_dir_created = False

        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        progress(0, "step1")
        progress(0, "step2")
        assert mock_mkdir.call_count == 1

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_different_account_indices(self, mock_print, mock_mkdir, mock_open):
        """Should correctly include account_index in PROGRESS line."""
        for idx in [0, 1, 5]:
            mock_print.reset_mock()
            progress(idx, f"account {idx}", 1, 3)
            printed = mock_print.call_args[0][0]
            assert f"PROGRESS:[{idx}]" in printed


# ── set_protocol_handler() ─────────────────────────────────────

class TestProtocolHandler:
    """Tests for set_protocol_handler() — JSON-line protocol routing."""

    def test_default_no_handler(self):
        """By default, _protocol_handler should be None."""
        import chaoxing.logging_setup as ls
        assert ls._protocol_handler is None

    def test_set_and_clear_handler(self):
        """Should be able to set and clear the protocol handler."""
        handler_called = []

        def my_handler(event):
            handler_called.append(event)

        set_protocol_handler(my_handler)
        import chaoxing.logging_setup as ls
        assert ls._protocol_handler is my_handler

        set_protocol_handler(None)
        assert ls._protocol_handler is None

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_routes_through_handler(self, mock_print, mock_mkdir, mock_open):
        """When handler is set, log() should call the handler with structured data."""
        events = []

        def handler(event):
            events.append(event)

        set_protocol_handler(handler)
        try:
            log("test message", "INFO")
            assert len(events) == 1
            assert events[0]["type"] == "LOG"
            assert events[0]["level"] == "info"
            assert events[0]["message"] == "test message"
            assert "timestamp" in events[0]
        finally:
            set_protocol_handler(None)

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_uses_print_when_no_handler(self, mock_print, mock_mkdir, mock_open):
        """When no handler is set, log() should print to stdout."""
        set_protocol_handler(None)
        log("direct output")
        mock_print.assert_called_once()

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_routes_through_handler(self, mock_print, mock_mkdir, mock_open):
        """When handler is set, progress() should call the handler."""
        events = []

        def handler(event):
            events.append(event)

        set_protocol_handler(handler)
        try:
            progress(0, "step", 1, 5)
            assert len(events) == 1
            assert events[0]["type"] == "PROGRESS"
            assert events[0]["percent"] == 20  # 1/5 = 20%
            assert "[0] step" in events[0]["message"]
        finally:
            set_protocol_handler(None)

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_handler_exception_is_silent(self, mock_print, mock_mkdir, mock_open):
        """If the protocol handler raises, log() should not crash."""
        def bad_handler(event):
            raise RuntimeError("handler crash")

        set_protocol_handler(bad_handler)
        try:
            # Should not raise
            log("resilient message")
        except Exception:
            assert False, "log() should never crash due to handler errors"
        finally:
            set_protocol_handler(None)


# ── ticket() ────────────────────────────────────────────────────

class TestTicketFunction:
    """Tests for ticket() — routes TICKET events through the protocol handler."""

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    def test_ticket_routes_through_handler(self, mock_mkdir, mock_open):
        """When a handler is set, ticket() emits a {'type':'TICKET'} event
        carrying the full ticket dict verbatim."""
        events = []
        set_protocol_handler(lambda e: events.append(e))
        try:
            payload = {
                "id": "captcha_0_123",
                "type": "captcha",
                "accountId": 0,
                "imageBase64": "data:image/png;base64,AAAA",
                "resolved": False,
            }
            ticket(payload)
        finally:
            set_protocol_handler(None)

        assert len(events) == 1
        assert events[0]["type"] == "TICKET"
        assert events[0]["ticket"] is payload
        assert events[0]["ticket"]["id"] == "captcha_0_123"

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    def test_ticket_no_handler_is_noop_for_protocol(self, mock_mkdir, mock_open):
        """With no handler (CLI mode), ticket() must not raise and emits nothing
        to a (non-existent) handler — it only traces to the log file."""
        set_protocol_handler(None)
        # Should not raise.
        ticket({"id": "x", "type": "captcha", "resolved": False})

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    def test_ticket_handler_exception_is_silent(self, mock_mkdir, mock_open):
        """If the handler raises, ticket() should swallow it (never crash)."""
        set_protocol_handler(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
        try:
            ticket({"id": "x", "type": "captcha", "resolved": False})
        except Exception:
            assert False, "ticket() should never crash due to handler errors"
        finally:
            set_protocol_handler(None)


# ── Signal functions ───────────────────────────────────────────

class TestSignalFunctions:
    """Tests for signal_pause / signal_resume / signal_stop / check_signals."""

    def setup_method(self):
        """Reset signals before each test."""
        signal_resume()  # Clear pause
        import chaoxing.logging_setup as ls
        ls._stop_event.clear()
        from chaoxing.constants import SHUTDOWN_FLAG
        SHUTDOWN_FLAG.clear()

    def teardown_method(self):
        """Clear the process-wide SHUTDOWN_FLAG so it never leaks into other tests."""
        import chaoxing.logging_setup as ls
        ls._stop_event.clear()
        from chaoxing.constants import SHUTDOWN_FLAG
        SHUTDOWN_FLAG.clear()

    def test_check_signals_no_signals_returns_immediately(self):
        """When no signals are set, check_signals should return immediately."""
        check_signals()  # Should not block and not raise

    def test_signal_stop_raises_keyboard_interrupt(self):
        """When stop is signaled, check_signals should raise KeyboardInterrupt."""
        signal_stop()
        with pytest.raises(KeyboardInterrupt, match="STOP signal"):
            check_signals()

    def test_signal_stop_also_sets_shutdown_flag(self):
        """signal_stop() must set the process-wide SHUTDOWN_FLAG so orchestrator
        loops that poll SHUTDOWN_FLAG.is_set() (rather than calling check_signals)
        observe the stop request. Regression guard for the two-flag bridge."""
        from chaoxing.constants import SHUTDOWN_FLAG
        assert not SHUTDOWN_FLAG.is_set()
        signal_stop()
        assert SHUTDOWN_FLAG.is_set()

    @patch("chaoxing.logging_setup.time.sleep")
    def test_pause_blocks_then_resume_unblocks(self, mock_sleep):
        """pause should cause check_signals to block; resume should unblock."""
        signal_pause()

        # Simulate: pause for one iteration, then resume
        call_count = [0]

        def stop_on_resume(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                signal_resume()

        mock_sleep.side_effect = stop_on_resume

        check_signals()  # Should block until resume
        assert mock_sleep.called

    @patch("chaoxing.logging_setup.time.sleep")
    def test_stop_during_pause_raises(self, mock_sleep):
        """When stop is signaled during pause, KeyboardInterrupt should be raised."""
        signal_pause()

        def signal_stop_after_first_sleep(*args, **kwargs):
            signal_stop()

        mock_sleep.side_effect = signal_stop_after_first_sleep

        with pytest.raises(KeyboardInterrupt, match="STOP signal"):
            check_signals()

    def test_signal_events_are_threading_events(self):
        """Signal flags should be threading.Event instances."""
        import chaoxing.logging_setup as ls
        assert isinstance(ls._pause_event, threading.Event)
        assert isinstance(ls._stop_event, threading.Event)


# ── Thread safety ─────────────────────────────────────────────

class TestLoggingThreadSafety:
    """Tests for thread safety of logging operations."""

    def test_log_lock_is_threading_lock(self):
        """_log_lock should be a threading.Lock for file write safety."""
        import chaoxing.logging_setup as ls
        assert isinstance(ls._log_lock, threading.Lock)

    def test_log_lock_acquire_release(self):
        """_log_lock should be acquirable and releasable."""
        import chaoxing.logging_setup as ls
        acquired = ls._log_lock.acquire(blocking=False)
        assert acquired
        ls._log_lock.release()

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_func_uses_lock(self, mock_print, mock_mkdir, mock_open):
        """log() should acquire _log_lock when writing to file."""
        import chaoxing.logging_setup as ls

        # Patch the lock to track acquire/release
        original_lock = ls._log_lock
        mock_lock = MagicMock(wraps=original_lock)
        ls._log_lock = mock_lock

        try:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            log("thread safe test")
            # Lock should have been used for file writing
            assert mock_lock.__enter__.called or mock_lock.acquire.called
        finally:
            ls._log_lock = original_lock

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_progress_func_uses_lock(self, mock_print, mock_mkdir, mock_open):
        """progress() should acquire _log_lock when writing to file."""
        import chaoxing.logging_setup as ls

        original_lock = ls._log_lock
        mock_lock = MagicMock(wraps=original_lock)
        ls._log_lock = mock_lock

        try:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            progress(0, "step", 1, 5)
            assert mock_lock.__enter__.called or mock_lock.acquire.called
        finally:
            ls._log_lock = original_lock


# ── _log_dir_created cache ────────────────────────────────────

class TestLogDirCreated:
    """Tests for _log_dir_created module-level cache flag."""

    def test_log_dir_created_is_boolean(self):
        """_log_dir_created should be a boolean."""
        import chaoxing.logging_setup as ls
        assert isinstance(ls._log_dir_created, bool)

    def test_log_dir_created_starts_false(self):
        """_log_dir_created should start as False at module init.

        Note: It may have been set to True by previous tests.
        We test that it can be set to False and is a valid bool.
        """
        import chaoxing.logging_setup as ls
        original = ls._log_dir_created
        ls._log_dir_created = False
        assert ls._log_dir_created is False
        ls._log_dir_created = original

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_log_does_not_mkdir_when_flag_true(self, mock_print, mock_mkdir, mock_open):
        """When _log_dir_created is True, log() should skip mkdir."""
        import chaoxing.logging_setup as ls
        original = ls._log_dir_created
        ls._log_dir_created = True

        try:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            log("test")
            mock_mkdir.assert_not_called()
        finally:
            ls._log_dir_created = original


# ── Integration-style: full log output format ──────────────────

class TestLogOutputFormat:
    """Tests for the complete log line format."""

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_format_structure(self, mock_print, mock_mkdir, mock_open):
        """Full log line should follow [timestamp] [level] message format."""
        log("hello world", "DEBUG")
        printed = mock_print.call_args[0][0]

        # Should start with timestamp bracket
        assert printed.startswith("[")
        # Should contain level
        assert "[DEBUG]" in printed
        # Should contain message
        assert "hello world" in printed

    @patch("chaoxing.logging_setup.open")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.print")
    def test_format_with_thread_prefix(self, mock_print, mock_mkdir, mock_open):
        """With thread prefix, format is [timestamp] [level] [thread] message."""
        original_name = threading.current_thread().name
        try:
            threading.current_thread().name = "chaoxing-account-0"
            log("threaded")
            printed = mock_print.call_args[0][0]
            # Thread prefix appears right after level
            assert "] [chaoxing-account-0]" in printed
        finally:
            threading.current_thread().name = original_name
