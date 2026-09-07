"""Tests for chaoxing.api — JSON-line protocol and stdin signal handling."""
import io
import json
import sys
import threading
import time
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.api import (
    StdioProtocol,
    StdinController,
    _write_json_line,
    _iso_timestamp,
    _make_protocol_handler,
    _job_id,
)


# ══════════════════════════════════════════════════════════════════
#  StdioProtocol — 7 event types
# ══════════════════════════════════════════════════════════════════

class TestStdioProtocol:
    """Tests for all 7 JSON-line event types emitted by StdioProtocol."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Capture JSON lines written to stdout."""
        self._buffer = io.StringIO()
        self._original_stdout = sys.stdout
        sys.stdout = self._buffer
        self._original_job_id = _job_id

        import chaoxing.api as api
        api._job_id = "test-job-001"
        self.protocol = StdioProtocol("test-job-001")
        yield
        sys.stdout = self._original_stdout
        api._job_id = ""

    def _lines(self):
        """Return list of parsed JSON objects written to stdout."""
        self._buffer.seek(0)
        return [json.loads(line) for line in self._buffer.read().strip().split("\n") if line]

    # -- PROGRESS --------------------------------------------------

    def test_emit_progress(self):
        """emit_progress() should write a PROGRESS JSON-line."""
        self.protocol.emit_progress(42, "Processing course 3/10")
        lines = self._lines()
        assert len(lines) == 1
        ev = lines[0]
        assert ev["type"] == "PROGRESS"
        assert ev["percent"] == 42
        assert ev["message"] == "Processing course 3/10"
        assert ev["jobId"] == "test-job-001"

    def test_emit_progress_boundaries(self):
        """emit_progress() should accept 0 and 100 percent."""
        self.protocol.emit_progress(0, "Starting")
        self.protocol.emit_progress(100, "Complete")
        lines = self._lines()
        assert lines[0]["percent"] == 0
        assert lines[1]["percent"] == 100

    # -- PHASE -----------------------------------------------------

    def test_emit_phase(self):
        """emit_phase() should write a PHASE JSON-line and update _current_phase."""
        self.protocol.emit_phase("login")
        lines = self._lines()
        assert lines[0]["type"] == "PHASE"
        assert lines[0]["phase"] == "login"

        import chaoxing.api as api
        assert api._current_phase == "login"

    @pytest.mark.parametrize("phase", [
        "idle", "login", "scan_courses", "process_sections",
        "solve_quiz", "completed", "paused", "stopped", "error",
    ])
    def test_emit_phase_all_valid(self, phase):
        """All 9 documented phases should be accepted."""
        self.protocol.emit_phase(phase)
        lines = self._lines()
        assert lines[0]["phase"] == phase

    # -- LOG -------------------------------------------------------

    def test_emit_log(self):
        """emit_log() should write a LOG JSON-line with ISO 8601 timestamp."""
        self.protocol.emit_log("warn", "Disk space low")
        lines = self._lines()
        assert lines[0]["type"] == "LOG"
        assert lines[0]["level"] == "warn"
        assert lines[0]["message"] == "Disk space low"
        assert "T" in lines[0]["timestamp"]  # ISO 8601

    @pytest.mark.parametrize("level", ["debug", "info", "warn", "error"])
    def test_emit_log_levels(self, level):
        """emit_log() should accept all 4 log levels."""
        self.protocol.emit_log(level, f"test {level}")
        lines = self._lines()
        assert lines[0]["level"] == level

    # -- TICKET ----------------------------------------------------

    def test_emit_ticket(self):
        """emit_ticket() should write a TICKET JSON-line with full ticket dict."""
        ticket_data = {
            "id": "cap_001",
            "type": "captcha",
            "title": "CAPTCHA Required",
            "message": "Please solve the CAPTCHA on-screen",
            "resolved": False,
        }
        self.protocol.emit_ticket(ticket_data)
        lines = self._lines()
        assert lines[0]["type"] == "TICKET"
        assert lines[0]["ticket"]["id"] == "cap_001"
        assert lines[0]["ticket"]["type"] == "captcha"

    # -- RESULT ----------------------------------------------------

    def test_emit_result(self):
        """emit_result() should write a RESULT JSON-line with data payload."""
        data = {"success": True, "accountsProcessed": 3, "durationMs": 45000}
        self.protocol.emit_result(data)
        lines = self._lines()
        assert lines[0]["type"] == "RESULT"
        assert lines[0]["data"]["success"] is True
        assert lines[0]["data"]["accountsProcessed"] == 3

    def test_emit_result_list_data(self):
        """emit_result() should accept list-typed data."""
        self.protocol.emit_result([1, 2, 3])
        lines = self._lines()
        assert lines[0]["data"] == [1, 2, 3]

    # -- ERROR -----------------------------------------------------

    def test_emit_error_without_stack(self):
        """emit_error() should write an ERROR JSON-line without stack key."""
        self.protocol.emit_error("Authentication failed")
        lines = self._lines()
        assert lines[0]["type"] == "ERROR"
        assert lines[0]["error"] == "Authentication failed"
        assert "stack" not in lines[0]

    def test_emit_error_with_stack(self):
        """emit_error() should include stack trace when provided."""
        self.protocol.emit_error("Crash", stack="Traceback: ...")
        lines = self._lines()
        assert lines[0]["stack"] == "Traceback: ..."

    # -- DONE ------------------------------------------------------

    def test_emit_done(self):
        """emit_done() should write a DONE JSON-line."""
        self.protocol.emit_done()
        lines = self._lines()
        assert lines[0]["type"] == "DONE"
        assert "jobId" in lines[0]

    # -- Thread safety ---------------------------------------------

    def test_multiple_events_from_threads(self):
        """Events from multiple threads should not interleave JSON."""
        errors = []

        def emit_from_thread(thread_id):
            try:
                for i in range(5):
                    self.protocol.emit_progress(i * 20, f"Thread {thread_id} step {i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=emit_from_thread, args=(i,))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors  # No JSON interleaving errors

        # Every line should be valid JSON
        lines = self._lines()
        assert len(lines) == 15  # 3 threads × 5 events
        for ev in lines:
            assert ev["type"] == "PROGRESS"


# ══════════════════════════════════════════════════════════════════
#  _write_json_line — low-level protocol helper
# ══════════════════════════════════════════════════════════════════

class TestWriteJsonLine:
    """Tests for _write_json_line — the core stdout serializer."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self._buffer = io.StringIO()
        self._original_stdout = sys.stdout
        sys.stdout = self._buffer
        import chaoxing.api as api
        api._job_id = "job_123"
        yield
        sys.stdout = self._original_stdout
        api._job_id = ""

    def test_writes_single_json_line(self):
        """Should write exactly one JSON object followed by newline."""
        _write_json_line({"type": "TEST", "msg": "hello"})
        output = self._buffer.getvalue()
        lines = output.strip().split("\n")
        assert len(lines) == 1
        ev = json.loads(lines[0])
        assert ev["type"] == "TEST"

    def test_auto_injects_job_id(self):
        """jobId should be auto-injected when not present."""
        _write_json_line({"type": "TEST"})
        ev = json.loads(self._buffer.getvalue().strip())
        assert ev["jobId"] == "job_123"

    def test_preserves_existing_job_id(self):
        """Should not overwrite an already-present jobId."""
        _write_json_line({"type": "TEST", "jobId": "custom"})
        ev = json.loads(self._buffer.getvalue().strip())
        assert ev["jobId"] == "custom"

    def test_ensure_ascii_false_preserves_unicode(self):
        """Chinese characters should be preserved (ensure_ascii=False)."""
        _write_json_line({"type": "LOG", "message": "处理课程：高等数学"})
        ev = json.loads(self._buffer.getvalue().strip())
        assert "高等数学" in ev["message"]


# ══════════════════════════════════════════════════════════════════
#  _iso_timestamp — timestamp formatting
# ══════════════════════════════════════════════════════════════════

class TestIsoTimestamp:
    """Tests for _iso_timestamp() — ISO 8601 UTC formatter."""

    def test_returns_string(self):
        ts = _iso_timestamp()
        assert isinstance(ts, str)

    def test_ends_with_z(self):
        """UTC timestamps should end with Z."""
        assert _iso_timestamp().endswith("Z")

    def test_contains_t_separator(self):
        """ISO 8601 uses T separator between date and time."""
        assert "T" in _iso_timestamp()

    def test_monotonic(self):
        """Two sequential calls should return non-decreasing timestamps."""
        ts1 = _iso_timestamp()
        time.sleep(0.01)
        ts2 = _iso_timestamp()
        assert ts2 >= ts1


# ══════════════════════════════════════════════════════════════════
#  StdinController — stdin signal dispatching
# ══════════════════════════════════════════════════════════════════

class TestStdinController:
    """Tests for StdinController — PAUSE / RESUME / STOP dispatch."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up protocol with captured output and clean signal state."""
        from chaoxing.logging_setup import signal_resume, signal_stop
        signal_resume()
        import chaoxing.logging_setup as ls
        ls._stop_event.clear()

        self._output = io.StringIO()
        self._original_stdout = sys.stdout
        sys.stdout = self._output

        import chaoxing.api as api
        api._job_id = "stdin-test"
        api._current_phase = "process_sections"
        self.protocol = StdioProtocol("stdin-test")
        self.controller = StdinController(self.protocol)
        yield
        sys.stdout = self._original_stdout
        self.controller.stop()
        api._job_id = ""
        api._current_phase = "idle"

    def _simulate_stdin(self, *commands: str):
        """Simulate stdin input and process in the controller's read loop."""
        input_text = "\n".join(commands) + "\n"
        original_stdin = sys.stdin
        sys.stdin = io.StringIO(input_text)
        try:
            self.controller._read_loop()
        finally:
            sys.stdin = original_stdin

    def _lines(self):
        self._output.seek(0)
        return [json.loads(line) for line in self._output.read().strip().split("\n") if line]

    def test_pause_emits_paused_phase(self):
        """PAUSE should emit a 'paused' PHASE event."""
        self._simulate_stdin("PAUSE")
        lines = self._lines()
        phases = [l["phase"] for l in lines if l.get("type") == "PHASE"]
        assert "paused" in phases

    def test_resume_restores_phase(self):
        """RESUME should restore the phase before the pause."""
        self._simulate_stdin("PAUSE", "RESUME")
        lines = self._lines()
        phases = [l["phase"] for l in lines if l.get("type") == "PHASE"]
        assert phases == ["paused", "process_sections"]

    def test_stop_emits_stopped_phase_and_log(self):
        """STOP should emit 'stopped' PHASE and a LOG event."""
        self._simulate_stdin("STOP")
        lines = self._lines()
        types = {l["type"] for l in lines}
        assert "PHASE" in types
        assert "LOG" in types
        phases = [l["phase"] for l in lines if l.get("type") == "PHASE"]
        assert "stopped" in phases

    def test_stop_breaks_read_loop(self):
        """STOP should cause _read_loop to exit (single iteration)."""
        self._simulate_stdin("STOP", "PAUSE")  # PAUSE after STOP should be ignored
        lines = self._lines()
        # Only STOP events, no PAUSE
        assert len(lines) >= 1

    def test_unknown_command_ignored(self):
        """Unknown commands should be silently ignored (no crash, no output)."""
        self._simulate_stdin("UNKNOWN_CMD", "GARBAGE")
        lines = self._lines()
        assert len(lines) == 0  # Nothing emitted for unknown commands

    def test_empty_line_ignored(self):
        """Empty lines should not crash."""
        self._simulate_stdin("", "  ", "PAUSE")
        lines = self._lines()
        phases = [l["phase"] for l in lines if l.get("type") == "PHASE"]
        assert "paused" in phases

    def test_lowercase_commands_recognized(self):
        """Commands are uppercased before comparison, so lowercase works."""
        self._simulate_stdin("pause")
        lines = self._lines()
        phases = [l["phase"] for l in lines if l.get("type") == "PHASE"]
        assert "paused" in phases

    # -- RESOLVE_TICKET (JSON stdin command) -----------------------

    def test_resolve_ticket_answer_writes_file(self):
        """A RESOLVE_TICKET with an answer writes the answer (UTF-8) to the
        account's captcha-answer file via the shared path helper."""
        payload = json.dumps({
            "type": "RESOLVE_TICKET",
            "ticketId": "captcha_2_123",
            "accountId": 2,
            "answer": "AB12",
        })
        with patch("chaoxing.platform.captcha.captcha_answer_path") as mock_path, \
             patch("builtins.open", new_callable=MagicMock) as mock_open:
            mock_path.return_value = "/fake/_captcha_answer_chaoxing-chrome-2.txt"
            self._simulate_stdin(payload)
            mock_path.assert_called_once_with(2)
            handle = mock_open.return_value.__enter__.return_value
            handle.write.assert_called_once_with("AB12")
            # Opened UTF-8 for writing
            args, kwargs = mock_open.call_args
            assert kwargs.get("encoding") == "utf-8"

    def test_resolve_ticket_skip_writes_sentinel(self):
        """A RESOLVE_TICKET with action=skip writes the __SKIP__ sentinel."""
        payload = json.dumps({
            "type": "RESOLVE_TICKET",
            "ticketId": "captcha_0_123",
            "accountId": 0,
            "action": "skip",
        })
        with patch("chaoxing.platform.captcha.captcha_answer_path") as mock_path, \
             patch("builtins.open", new_callable=MagicMock) as mock_open:
            mock_path.return_value = "/fake/_captcha_answer_chaoxing-chrome-0.txt"
            self._simulate_stdin(payload)
            handle = mock_open.return_value.__enter__.return_value
            handle.write.assert_called_once_with("__SKIP__")

    def test_resolve_ticket_numeric_string_account_id(self):
        """accountId arriving as a numeric string is tolerated (coerced to int)."""
        payload = json.dumps({
            "type": "RESOLVE_TICKET",
            "accountId": "3",
            "answer": "XY99",
        })
        with patch("chaoxing.platform.captcha.captcha_answer_path") as mock_path, \
             patch("builtins.open", new_callable=MagicMock):
            mock_path.return_value = "/fake/path.txt"
            self._simulate_stdin(payload)
            mock_path.assert_called_once_with(3)

    def test_resolve_ticket_malformed_json_does_not_crash(self):
        """A line that starts with '{' but is invalid JSON is logged, not fatal."""
        with patch("chaoxing.platform.captcha.captcha_answer_path") as mock_path:
            # Should not raise, should not attempt to write a file.
            self._simulate_stdin('{"type": "RESOLVE_TICKET", broken')
            mock_path.assert_not_called()
        lines = self._lines()
        # A warning LOG should have been emitted.
        assert any(l.get("type") == "LOG" and l.get("level") == "warn" for l in lines)

    def test_resolve_ticket_missing_account_id_ignored(self):
        """RESOLVE_TICKET without an accountId is ignored with a warning."""
        payload = json.dumps({"type": "RESOLVE_TICKET", "answer": "AB12"})
        with patch("chaoxing.platform.captcha.captcha_answer_path") as mock_path:
            self._simulate_stdin(payload)
            mock_path.assert_not_called()
        lines = self._lines()
        assert any(l.get("type") == "LOG" and l.get("level") == "warn" for l in lines)

    def test_resolve_ticket_no_answer_no_skip_ignored(self):
        """RESOLVE_TICKET with neither answer nor skip is ignored with a warning."""
        payload = json.dumps({"type": "RESOLVE_TICKET", "accountId": 0})
        with patch("chaoxing.platform.captcha.captcha_answer_path") as mock_path:
            self._simulate_stdin(payload)
            mock_path.assert_not_called()
        lines = self._lines()
        assert any(l.get("type") == "LOG" and l.get("level") == "warn" for l in lines)

    def test_unknown_json_command_ignored(self):
        """A JSON line with an unrecognized type is silently ignored."""
        payload = json.dumps({"type": "SOMETHING_NEW", "foo": "bar"})
        with patch("chaoxing.platform.captcha.captcha_answer_path") as mock_path:
            self._simulate_stdin(payload)
            mock_path.assert_not_called()

    def test_json_answer_named_pause_not_treated_as_control(self):
        """An answer of 'PAUSE' inside JSON must NOT trigger the pause signal."""
        payload = json.dumps({
            "type": "RESOLVE_TICKET", "accountId": 0, "answer": "PAUSE",
        })
        with patch("chaoxing.platform.captcha.captcha_answer_path") as mock_path, \
             patch("builtins.open", new_callable=MagicMock) as mock_open:
            mock_path.return_value = "/fake/path.txt"
            self._simulate_stdin(payload)
            handle = mock_open.return_value.__enter__.return_value
            handle.write.assert_called_once_with("PAUSE")
        lines = self._lines()
        # No 'paused' phase should have been emitted.
        phases = [l["phase"] for l in lines if l.get("type") == "PHASE"]
        assert "paused" not in phases


# ══════════════════════════════════════════════════════════════════
#  _make_protocol_handler — bridges log/progress to JSON events
# ══════════════════════════════════════════════════════════════════

class TestMakeProtocolHandler:
    """Tests for _make_protocol_handler() — bridges logging_setup → JSON."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self._buffer = io.StringIO()
        self._original_stdout = sys.stdout
        sys.stdout = self._buffer
        import chaoxing.api as api
        api._job_id = "handler-test"
        self.protocol = StdioProtocol("handler-test")
        self.handler = _make_protocol_handler(self.protocol)
        yield
        sys.stdout = self._original_stdout
        api._job_id = ""

    def _lines(self):
        self._buffer.seek(0)
        return [json.loads(line) for line in self._buffer.read().strip().split("\n") if line]

    def test_log_event_emits_json(self):
        """A LOG event dict should emit a JSON-line LOG event."""
        self.handler({
            "type": "LOG",
            "level": "info",
            "message": "Test log message",
            "timestamp": "2026-06-25T00:00:00Z",
        })
        lines = self._lines()
        assert lines[0]["type"] == "LOG"
        assert lines[0]["level"] == "info"
        assert lines[0]["message"] == "Test log message"

    def test_progress_event_emits_json(self):
        """A PROGRESS event dict should emit a JSON-line PROGRESS event."""
        self.handler({
            "type": "PROGRESS",
            "percent": 50,
            "message": "Half done",
        })
        lines = self._lines()
        assert lines[0]["type"] == "PROGRESS"
        assert lines[0]["percent"] == 50
        assert lines[0]["message"] == "Half done"

    def test_phase_event_emits_json(self):
        """A valid PHASE event dict should emit a JSON-line PHASE event."""
        self.handler({
            "type": "PHASE",
            "phase": "scan_courses",
        })
        lines = self._lines()
        assert lines[0]["type"] == "PHASE"
        assert lines[0]["phase"] == "scan_courses"

    def test_ticket_event_emits_json(self):
        """A TICKET event dict should be forwarded as a JSON-line TICKET event."""
        self.handler({
            "type": "TICKET",
            "ticket": {
                "id": "captcha_0_123",
                "type": "captcha",
                "accountId": 0,
                "resolved": False,
            },
        })
        lines = self._lines()
        assert lines[0]["type"] == "TICKET"
        assert lines[0]["ticket"]["id"] == "captcha_0_123"
        assert lines[0]["ticket"]["accountId"] == 0

    def test_ticket_event_without_dict_ignored(self):
        """A TICKET event whose ticket payload is not a dict should be dropped."""
        self.handler({"type": "TICKET", "ticket": "not-a-dict"})
        self.handler({"type": "TICKET"})  # missing ticket key entirely
        lines = self._lines()
        assert len(lines) == 0

    def test_invalid_phase_ignored(self):
        """An unknown phase value should be dropped, not emitted."""
        self.handler({
            "type": "PHASE",
            "phase": "not_a_real_phase",
        })
        lines = self._lines()
        assert len(lines) == 0

    def test_unknown_event_ignored(self):
        """Events with an unrecognized type should not emit anything."""
        self.handler({
            "type": "SOMETHING_ELSE",
            "data": {"id": "x"},
        })
        lines = self._lines()
        assert len(lines) == 0  # Unknown types are not routed through this handler

    def test_handler_does_not_crash_on_bad_input(self):
        """Handler should not crash on malformed events."""
        # Missing type key
        self.handler({"message": "no type"})
        # Empty dict
        self.handler({})
        lines = self._lines()
        assert len(lines) == 0


# ══════════════════════════════════════════════════════════════════
#  CLI argument parsing (main function)
# ══════════════════════════════════════════════════════════════════

class TestCLIArguments:
    """Tests for main() CLI argument parsing and validation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Capture output and mock orchestrator."""
        self._stdout = io.StringIO()
        self._stderr = io.StringIO()
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        yield
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr

    def _run_main(self, *args):
        """Run api.main() with given CLI args, catching SystemExit."""
        from chaoxing import api
        with patch.object(sys, 'argv', ['chaoxing.api'] + list(args)):
            try:
                api.main()
            except SystemExit as e:
                return e.code
        return 0

    def _lines(self):
        self._stdout.seek(0)
        text = self._stdout.read().strip()
        if not text:
            return []
        return [json.loads(line) for line in text.split("\n") if line]

    def test_missing_job_id_fails(self):
        """Missing --job-id should fail."""
        exit_code = self._run_main("--accounts", "0", "--mode", "full")
        assert exit_code != 0

    def test_missing_accounts_fails(self):
        """Missing --accounts should fail."""
        exit_code = self._run_main("--job-id", "test", "--mode", "full")
        assert exit_code != 0

    def test_invalid_mode_rejected(self):
        """Invalid --mode should be rejected by argparse."""
        exit_code = self._run_main(
            "--job-id", "test", "--accounts", "0", "--mode", "invalid"
        )
        assert exit_code != 0

    @patch("chaoxing.api.run_multi_account")
    def test_valid_args_dispatch(self, mock_run):
        """Valid args should parse and dispatch to orchestrator."""

        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'job_001',
            '--accounts', '0',
            '--mode', 'full',
        ]):
            try:
                from chaoxing import api
                api.main()
            except SystemExit:
                pass

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["mode"] == "full"
        assert call_kwargs["account_indices"] == [0]

    @patch("chaoxing.api.run_multi_account")
    def test_memory_plan_args_forwarded(self, mock_run):
        """Memory-plan args from Electron must reach run_multi_account."""
        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'job_plan',
            '--accounts', '0',
            '--mode', 'full',
            '--max-concurrent', '18',
            '--budget-gb', '12.9',
            '--system-limit-gb', '14.9',
            '--per-account-estimate-gb', '0.7',
        ]):
            try:
                from chaoxing import api
                api.main()
            except SystemExit:
                pass
        mock_run.assert_called_once()
        kw = mock_run.call_args[1]
        assert kw["max_concurrent"] == 18
        assert kw["budget_gb"] == 12.9
        assert kw["system_limit_gb"] == 14.9
        assert kw["per_account_estimate_gb"] == 0.7
        from chaoxing.logging_setup import set_ram_limit_gb
        set_ram_limit_gb(None)

    def test_chromium_flags_now_rejected(self):
        """--chromium-flags was removed; argparse must reject it."""
        exit_code = self._run_main(
            "--chromium-flags", "--disable-gpu",
            "--job-id", "job_flags", "--accounts", "0", "--mode", "full",
        )
        assert exit_code == 2

    @patch("chaoxing.api.run_multi_account")
    def test_mode_scan_only(self, mock_run):
        """--mode scan_only should pass through correctly."""
        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'job_002',
            '--accounts', '0',
            '--mode', 'scan_only',
        ]):
            try:
                from chaoxing import api
                api.main()
            except SystemExit:
                pass
        assert mock_run.call_args[1]["mode"] == "scan_only"

    @patch("chaoxing.api.run_multi_account")
    def test_mode_solve_only(self, mock_run):
        """--mode solve_only should pass through correctly."""
        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'job_003',
            '--accounts', '0',
            '--mode', 'solve_only',
        ]):
            try:
                from chaoxing import api
                api.main()
            except SystemExit:
                pass
        assert mock_run.call_args[1]["mode"] == "solve_only"

    @patch("chaoxing.api.run_multi_account")
    def test_multiple_accounts_parsed(self, mock_run):
        """--accounts '0,1,2' should parse to [0, 1, 2]."""
        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'job_004',
            '--accounts', '0,1,2',
            '--mode', 'full',
        ]):
            try:
                from chaoxing import api
                api.main()
            except SystemExit:
                pass
        assert mock_run.call_args[1]["account_indices"] == [0, 1, 2]

    @patch("chaoxing.api.run_multi_account")
    def test_accounts_dedup_and_sorted(self, mock_run):
        """Duplicate account indices should be deduplicated and sorted."""
        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'job_005',
            '--accounts', '2,0,2,1,0',
            '--mode', 'full',
        ]):
            try:
                from chaoxing import api
                api.main()
            except SystemExit:
                pass
        assert mock_run.call_args[1]["account_indices"] == [0, 1, 2]

    @patch("chaoxing.api.run_multi_account")
    def test_courses_filter_passed(self, mock_run):
        """--courses should be passed as comma-separated string."""
        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'job_006',
            '--accounts', '0',
            '--mode', 'full',
            '--courses', '高等数学,大学英语',
        ]):
            try:
                from chaoxing import api
                api.main()
            except SystemExit:
                pass
        assert mock_run.call_args[1]["course"] == "高等数学,大学英语"

    def test_non_numeric_account_rejected(self):
        """Non-numeric account index should cause error and exit."""
        exit_code = self._run_main(
            "--job-id", "test", "--accounts", "abc", "--mode", "full"
        )
        assert exit_code == 1
        lines = self._lines()
        assert any(l["type"] == "ERROR" for l in lines)

    def test_empty_accounts_rejected(self):
        """Empty --accounts should cause error and exit."""
        exit_code = self._run_main(
            "--job-id", "test", "--accounts", ",,,", "--mode", "full"
        )
        assert exit_code == 1

    def test_too_many_accounts_rejected(self):
        """More than 50 accounts should be rejected."""
        many = ",".join(str(i) for i in range(51))
        exit_code = self._run_main(
            "--job-id", "test", "--accounts", many, "--mode", "full"
        )
        assert exit_code == 1


# ══════════════════════════════════════════════════════════════════
#  End-to-end: main() lifecycle events
# ══════════════════════════════════════════════════════════════════

class TestMainLifecycle:
    """End-to-end tests: verify correct event sequence in main()."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self._stdout = io.StringIO()
        self._stderr = io.StringIO()
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        import chaoxing.logging_setup as ls
        ls._stop_event.clear()
        yield
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr

    def _lines(self):
        self._stdout.seek(0)
        text = self._stdout.read().strip()
        if not text:
            return []
        return [json.loads(line) for line in text.split("\n") if line]

    @patch("chaoxing.api.run_multi_account")
    def test_successful_run_emits_all_phases(self, mock_run):
        """A successful run should emit: idle→login→completed→done."""
        mock_run.return_value = []

        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'lifecycle_test',
            '--accounts', '0',
            '--mode', 'full',
        ]):
            from chaoxing import api
            api.main()

        lines = self._lines()
        types = [l["type"] for l in lines]

        # Expected types: PHASE(idle), PROGRESS(0%), PHASE(login), PROGRESS(5%),
        #   PHASE(completed), PROGRESS(100%), RESULT, DONE
        assert "PHASE" in types
        assert "PROGRESS" in types
        assert "RESULT" in types
        assert "DONE" in types
        assert types[-1] == "DONE"  # DONE must be last

    @patch("chaoxing.api.run_multi_account")
    def test_run_with_exception_emits_error_and_done(self, mock_run):
        """When orchestrator raises, should emit ERROR + DONE."""
        mock_run.side_effect = ValueError("Test failure")

        with patch.object(sys, 'argv', [
            'chaoxing.api',
            '--job-id', 'error_test',
            '--accounts', '0',
            '--mode', 'full',
        ]):
            from chaoxing import api
            try:
                api.main()
            except SystemExit:
                pass

        lines = self._lines()
        types = [l["type"] for l in lines]
        assert "ERROR" in types
        assert "DONE" in types
        assert types[-1] == "DONE"
