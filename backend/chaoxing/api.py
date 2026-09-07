"""
Chaoxing Backend API Entry Point -- JSON-line protocol for Electron IPC.

This module REPLACES orchestrator.main() as the primary entry point.
It communicates with the Electron main process via:
  - stdout: JSON-line events (PROGRESS/PHASE/LOG/TICKET/RESULT/ERROR/DONE)
  - stdin:  control signals (PAUSE/RESUME/STOP)
  - stderr: debug logging only

Architecture:
    StdioProtocol    -- encapsulates emit_* methods for the 7 event types
    StdinController  -- background daemon thread that reads stdin line-by-line
    main()           -- wires everything together and dispatches to orchestrator

Key design decisions:
    1. sys.stdout is the protocol channel -- NEVER print() to it.
    2. sys.stderr is for debug logging.
    3. log() and progress() are routed through logging_setup's protocol
       handler (set via set_protocol_handler()), which bridges to JSON
       LOG/PROGRESS events on stdout.  No monkey-patching needed because
       logging_setup already has the _protocol_handler hook.
    4. threading.Event signals (via logging_setup.signal_pause/resume/stop)
       replace file-based pause/quit flags.
    5. A threading.Lock serializes all stdout writes from the protocol
       handler to prevent interleaving when multiple account threads
       emit events simultaneously.

CLI arguments (replaces orchestrator.main() argparse):
    --job-id     : string, required. Job unique identifier.
    --accounts   : string, required. Comma-separated account indices, max 50.
    --mode       : string, required. One of: full | scan_only | solve_only.
    --courses    : string, optional. Comma-separated course IDs.

Usage:
    python -m chaoxing.api --job-id "job_123" --accounts "0" --mode full
    python -m chaoxing.api --job-id "job_456" --accounts "0,1,2" --mode scan_only
    python -m chaoxing.api --job-id "job_789" --accounts "0" --mode solve_only --courses "..."
"""

import sys
import json
import time
import argparse
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional

from chaoxing.constants import SHUTDOWN_FLAG
from chaoxing.logging_setup import (
    set_protocol_handler,
    signal_pause,
    signal_resume,
    signal_stop,
)
from chaoxing.orchestrator import run_multi_account


# =========================================================================
#  Module-level state
# =========================================================================

_job_id: str = ""
"""Active job identifier, set by main() before any event emission."""

_stdout_lock = threading.Lock()
"""Serializes all writes to stdout to prevent JSON-line interleaving."""

_current_phase: str = "idle"
"""Tracks the current phase so RESUME can restore the pre-pause phase."""

_VALID_PHASES = frozenset({
    "idle", "login", "scan_courses", "process_sections",
    "solve_quiz", "completed", "paused", "stopped", "error",
})


# =========================================================================
#  JSON-line protocol helpers (internal)
# =========================================================================

def _iso_timestamp() -> str:
    """Return current UTC time as ISO 8601 string with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _write_json_line(obj: dict) -> None:
    """Write a single JSON object as one line to stdout (thread-safe).

    Automatically injects ``jobId`` if not already present.
    Never call print() targeting stdout -- always use this function.
    """
    obj.setdefault("jobId", _job_id)
    line = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    with _stdout_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


# =========================================================================
#  StdioProtocol -- JSON event emission for the 7 event types
# =========================================================================

class StdioProtocol:
    """Encapsulates the 7 JSON-line event types for frontend-backend IPC.

    Every method writes exactly one JSON object (one line) to stdout.
    All methods are thread-safe via :func:`_write_json_line`.

    Event types
    -----------
    PROGRESS
        Progress update with ``percent`` (0-100) and human-readable ``message``.
    PHASE
        Phase transition.  Valid phases: idle, login, scan_courses,
        process_sections, solve_quiz, completed, paused, stopped, error.
    LOG
        Structured log entry with ``level`` (debug/info/warn/error) and
        ISO 8601 ``timestamp``.
    TICKET
        Manual intervention required (CAPTCHA, verification, warning, error).
        Payload is a free-form ``ticket`` dict.
    RESULT
        Arbitrary result data payload in ``data`` field.
    ERROR
        Error event with ``error`` message and optional ``stack`` trace.
    DONE
        Terminal event: the job has finished (success or failure).
    """

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id

    # -- Progress -------------------------------------------------------

    def emit_progress(self, percent: int, message: str,
                      account_id: int = None, lane_status: str = None) -> None:
        """Emit a PROGRESS event, optionally scoped to one account lane.

        Args:
            percent: Completion percentage (0-100).
            message: Human-readable status message.
            account_id: Optional zero-based account index this event targets.
            lane_status: Optional lane state hint ('queued' | 'running' |
                'error'), forwarded to the renderer's lane status machine.
        """
        payload = {"type": "PROGRESS", "percent": percent, "message": message}
        if account_id is not None:
            payload["accountId"] = account_id
        if lane_status:
            payload["laneStatus"] = lane_status
        _write_json_line(payload)

    # -- Memory ----------------------------------------------------------

    def emit_memory(self, payload: dict) -> None:
        """Emit a MEMORY event with the runtime memory-budget snapshot."""
        _write_json_line(payload)

    # -- Phase ----------------------------------------------------------

    def emit_phase(self, phase: str) -> None:
        """Emit a PHASE event and update the module-level phase tracker.

        Args:
            phase: One of idle, login, scan_courses, process_sections,
                   solve_quiz, completed, paused, stopped, error.
        """
        global _current_phase
        _current_phase = phase
        _write_json_line({
            "type": "PHASE",
            "phase": phase,
        })

    # -- Log ------------------------------------------------------------

    def emit_log(self, level: str, message: str) -> None:
        """Emit a LOG event.

        Args:
            level: One of debug, info, warn, error.
            message: Log message text.
        """
        _write_json_line({
            "type": "LOG",
            "level": level,
            "message": message,
            "timestamp": _iso_timestamp(),
        })

    # -- Ticket ---------------------------------------------------------

    def emit_ticket(self, ticket: dict) -> None:
        """Emit a TICKET event for manual intervention.

        Args:
            ticket: Dict with at least id, type, title, message, resolved keys.
        """
        _write_json_line({
            "type": "TICKET",
            "ticket": ticket,
        })

    # -- Result ---------------------------------------------------------

    def emit_result(self, data) -> None:
        """Emit a RESULT event with arbitrary payload.

        Args:
            data: Any JSON-serializable value.
        """
        _write_json_line({
            "type": "RESULT",
            "data": data,
        })

    # -- Error ----------------------------------------------------------

    def emit_error(self, error_msg: str, stack: Optional[str] = None) -> None:
        """Emit an ERROR event.

        Args:
            error_msg: Human-readable error description.
            stack: Optional Python traceback string.
        """
        payload: dict = {
            "type": "ERROR",
            "error": error_msg,
        }
        if stack:
            payload["stack"] = stack
        _write_json_line(payload)

    # -- Done -----------------------------------------------------------

    def emit_done(self) -> None:
        """Emit a DONE event.  Always call this before exiting, even on error."""
        _write_json_line({
            "type": "DONE",
        })


# =========================================================================
#  Protocol handler -- bridges log() / progress() to JSON-line events
# =========================================================================

def _make_protocol_handler(protocol: StdioProtocol):
    """Build a callback for logging_setup.set_protocol_handler().

    The handler receives structured dicts from log() and progress()
    when the protocol handler is active, and forwards them as JSON-line
    LOG / PROGRESS events to stdout.

    This is registered once in main() BEFORE run_multi_account() is
    called, so every log() / progress() call from orchestrator threads
    automatically emits properly-formatted JSON events.
    """

    def handler(event: dict) -> None:
        event_type = event.get("type", "")
        if event_type == "LOG":
            protocol.emit_log(
                level=event.get("level", "info"),
                message=event["message"],
            )
        elif event_type == "PROGRESS":
            protocol.emit_progress(
                percent=event.get("percent", 0),
                message=event.get("message", ""),
                account_id=event.get("accountId"),
                lane_status=event.get("laneStatus"),
            )
        elif event_type == "PHASE":
            phase = event.get("phase", "")
            if phase in _VALID_PHASES:
                protocol.emit_phase(phase)
        elif event_type == "TICKET":
            ticket = event.get("ticket")
            if isinstance(ticket, dict):
                protocol.emit_ticket(ticket)
        elif event_type == "MEMORY":
            protocol.emit_memory(event)

    return handler


# =========================================================================
#  StdinController -- background stdin reader for control signals
# =========================================================================

class StdinController:
    """Reads stdin line-by-line in a daemon thread, dispatching control signals.

    The Electron main process writes one-line commands to the Python
    subprocess's stdin::

        PAUSE\\n   -- suspend execution at the next yield point
        RESUME\\n  -- continue execution
        STOP\\n    -- initiate graceful shutdown
        {"type":"RESOLVE_TICKET",...}\\n -- answer/skip a manual-intervention ticket

    Plain-text control commands (PAUSE/RESUME/STOP) are matched
    case-insensitively. A line that begins with ``{`` is parsed as a JSON
    command instead — currently only ``RESOLVE_TICKET`` (CAPTCHA manual
    answer or skip), which is written to the per-account answer file the
    content handler's fallback loop polls.

    Implementation
    --------------
    * PAUSE calls :func:`chaoxing.logging_setup.signal_pause` (sets global
      pause event; worker threads block in check_signals()).
    * RESUME calls :func:`chaoxing.logging_setup.signal_resume` and emits
      a PHASE event restoring the pre-pause phase.
    * STOP calls :func:`chaoxing.logging_setup.signal_stop` (sets SHUTDOWN_FLAG;
      threads exit cleanly) and emits a "stopped" PHASE event.
    * RESOLVE_TICKET writes the answer (or a ``__SKIP__`` sentinel) to the
      account's ``_captcha_answer_chaoxing-chrome-<N>.txt`` file. Malformed
      JSON or missing fields are logged as warnings and ignored — never fatal.

    The reader thread exits when stdin is closed (EOF) or :meth:`stop` is called.
    """

    def __init__(self, protocol: StdioProtocol) -> None:
        self._protocol = protocol
        self._running = True
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Launch the stdin reader as a daemon thread."""
        if self._thread is not None:
            return  # Already started
        self._thread = threading.Thread(
            target=self._read_loop,
            name="api-stdin-controller",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the reader loop to exit at the next iteration."""
        self._running = False

    def _read_loop(self) -> None:
        """Main loop: read stdin line-by-line, dispatch commands."""
        while self._running:
            try:
                line = sys.stdin.readline()
            except (EOFError, OSError):
                # stdin closed or unavailable -- exit silently
                break

            if not line:
                # EOF -- parent process exited or pipe closed
                break

            stripped = line.strip()

            # JSON commands (e.g. RESOLVE_TICKET) start with '{'. Route them
            # before the plain-text .upper() matching so a CAPTCHA answer of
            # "PAUSE" inside JSON is never mistaken for a control signal.
            if stripped.startswith("{"):
                self._handle_json_command(stripped)
                continue

            cmd = stripped.upper()

            if cmd == "PAUSE":
                signal_pause()
                self._protocol.emit_phase("paused")

            elif cmd == "RESUME":
                signal_resume()
                # Restore the phase we were in before the pause
                if _current_phase == "paused":
                    self._protocol.emit_phase("process_sections")
                else:
                    self._protocol.emit_phase(_current_phase)

            elif cmd == "STOP":
                signal_stop()
                self._protocol.emit_phase("stopped")
                self._protocol.emit_log(
                    "warn",
                    "STOP signal received -- initiating graceful shutdown",
                )
                break

            # Unknown commands are silently ignored

    def _handle_json_command(self, raw: str) -> None:
        """Parse and dispatch a JSON-line command from stdin.

        Currently handles only ``RESOLVE_TICKET`` (CAPTCHA manual answer or
        skip). Any parse error or unknown command type is logged as a warning
        and ignored — a malformed control line must never crash the reader
        thread or abort the job.

        Args:
            raw: A single stripped stdin line beginning with ``{``.
        """
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            self._protocol.emit_log("warn", "Ignoring malformed JSON stdin line")
            return

        if not isinstance(obj, dict):
            self._protocol.emit_log("warn", "Ignoring non-object JSON stdin line")
            return

        if obj.get("type") == "RESOLVE_TICKET":
            self._handle_resolve_ticket(obj)
        # Unknown JSON command types are silently ignored

    def _handle_resolve_ticket(self, obj: dict) -> None:
        """Write a CAPTCHA answer (or skip sentinel) to the account's file.

        The content handler's fallback loop polls
        ``_captcha_answer_chaoxing-chrome-<accountId>.txt``; this writes the
        frontend-supplied answer (UTF-8) there, or the ``__SKIP__`` sentinel
        when the user chose to skip the course. The frontend only sends an
        ``accountId`` — it never needs to know the file name.

        Args:
            obj: Parsed RESOLVE_TICKET payload with ``accountId`` and either
                 ``answer`` (str) or ``action == "skip"``.
        """
        account_id = obj.get("accountId")
        if not isinstance(account_id, int):
            # Tolerate a numeric string; reject anything else.
            try:
                account_id = int(account_id)
            except (ValueError, TypeError):
                self._protocol.emit_log(
                    "warn", "RESOLVE_TICKET missing valid accountId — ignored"
                )
                return

        if obj.get("action") == "skip":
            content = "__SKIP__"
        else:
            answer = obj.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                self._protocol.emit_log(
                    "warn", "RESOLVE_TICKET has no answer and no skip action — ignored"
                )
                return
            content = answer.strip()

        # Deferred import: keeps api.py import light and avoids any chance of
        # a circular import at module load (captcha → browser/ai stacks).
        from chaoxing.platform.captcha import captcha_answer_path

        try:
            path = captcha_answer_path(account_id)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            # Do not echo the answer itself (could be noise / PII-ish).
            self._protocol.emit_log(
                "info",
                f"Resolved ticket for account {account_id} "
                f"({'skip' if content == '__SKIP__' else 'answer'})",
            )
        except OSError as e:
            self._protocol.emit_log(
                "warn", f"Could not write CAPTCHA answer for account {account_id}: {e}"
            )


# =========================================================================
#  Main entry point
# =========================================================================

def main() -> None:
    """Parse CLI args, wire protocol + controller, dispatch to orchestrator.

    CLI interface (replaces orchestrator.main() argparse)::

        --job-id    (required)  Job unique identifier string
        --accounts  (required)  Comma-separated account indices, max 50
        --mode      (required)  One of: full | scan_only | solve_only
        --courses   (optional)  Comma-separated course names or IDs

    Lifecycle
    ---------
    1. Parse and validate CLI arguments.
    2. Start StdinController daemon thread.
    3. Register protocol handler so log()/progress() emit JSON events.
    4. Dispatch to orchestrator.run_multi_account().
    5. Always emit DONE before exit (success, error, or interruption).
    """
    global _job_id

    # -- CLI ------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description="Chaoxing Backend API -- JSON-line protocol for Electron IPC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Event types emitted on stdout (one JSON object per line):
  PROGRESS  -- progress update with percent (0-100) and message
  PHASE     -- phase transition (idle/login/scan_courses/process_sections/solve_quiz/completed/paused/stopped/error)
  LOG       -- structured log entry with level (debug/info/warn/error) and ISO 8601 timestamp
  TICKET    -- manual intervention needed (captcha, verification, warning, error)
  RESULT    -- arbitrary result data payload
  ERROR     -- error message with optional Python stack trace
  DONE      -- terminal event signalling job completion

Stdin control signals (one per line, read by background thread):
  PAUSE     -- suspend execution at next yield point
  RESUME    -- continue execution
  STOP      -- initiate graceful shutdown""",
    )
    parser.add_argument(
        "--job-id", type=str, required=True,
        help="Job unique identifier (e.g. 'job_1719312000000_a1b2c3')",
    )
    parser.add_argument(
        "--accounts", type=str, required=True,
        help="Comma-separated account indices (e.g. '0' or '0,1,2'), max 50",
    )
    parser.add_argument(
        "--mode", type=str, required=True,
        choices=["full", "scan_only", "solve_only"],
        help="Execution mode: full (quiz + content), scan_only (scan + report), "
             "solve_only (quiz solving, skip content)",
    )
    parser.add_argument(
        "--courses", type=str, default=None,
        help="Comma-separated course names or IDs to filter by (optional, all if omitted)",
    )
    parser.add_argument(
        "--grade-only", action="store_true", default=False,
        help="模拟运行: solve quizzes, fill answers, screenshot and AI-grade them "
             "WITHOUT submitting; content sections navigate + detect type but are "
             "not completed. Maps to the frontend '模拟运行' toggle.",
    )
    parser.add_argument(
        "--content-only", action="store_true", default=False,
        help="Skip the quiz phase; only complete content sections (仅内容).",
    )
    parser.add_argument(
        "--max-concurrent", type=int, default=None,
        help="Runtime size of the account semaphore (Electron computes this "
             "from the memory/CPU plan; CLI runs fall back to config).",
    )
    parser.add_argument(
        "--budget-gb", type=float, default=None,
        help="Project memory budget in GB (Electron-computed).",
    )
    parser.add_argument(
        "--system-limit-gb", type=float, default=None,
        help="Absolute system-used-RAM emergency threshold in GB "
             "(baseline + budget + margin, Electron-computed).",
    )
    parser.add_argument(
        "--per-account-estimate-gb", type=float, default=None,
        help="Initial per-Chrome memory estimate in GB (default 0.7).",
    )
    cli = parser.parse_args()

    _job_id = cli.job_id
    protocol = StdioProtocol(cli.job_id)
    from chaoxing.logging_setup import set_ram_limit_gb
    if cli.system_limit_gb:
        set_ram_limit_gb(float(cli.system_limit_gb))

    # -- Validate --accounts -------------------------------------------
    account_indices_raw = [
        x.strip() for x in cli.accounts.split(",") if x.strip()
    ]
    if not account_indices_raw:
        protocol.emit_error("No valid account indices in --accounts")
        protocol.emit_done()
        sys.exit(1)

    account_indices: list[int] = []
    for s in account_indices_raw:
        if s.isdigit():
            account_indices.append(int(s))
        else:
            protocol.emit_log("warn", f"Ignoring non-numeric account index: '{s}'")

    if not account_indices:
        protocol.emit_error("No valid numeric indices in --accounts")
        protocol.emit_done()
        sys.exit(1)

    if len(account_indices) > 50:
        protocol.emit_error(
            f"Maximum 50 accounts allowed, got {len(account_indices)}"
        )
        protocol.emit_done()
        sys.exit(1)

    account_indices = sorted(set(account_indices))  # dedup and sort

    # -- Parse --courses ------------------------------------------------
    course_filter: Optional[str] = None
    if cli.courses:
        course_ids = [c.strip() for c in cli.courses.split(",") if c.strip()]
        if course_ids:
            course_filter = ",".join(course_ids)

    # -- Start stdin controller daemon ----------------------------------
    stdin_ctrl = StdinController(protocol)
    stdin_ctrl.start()

    # -- Register protocol handler (routes log()/progress() to JSON) ---
    set_protocol_handler(_make_protocol_handler(protocol))

    # -- Pre-flight: credentials must exist for the requested accounts ----
    # Without this, run_multi_account() silently returns [] and the job would
    # be reported as "completed" even though nothing ran.
    from chaoxing.platform.auth import read_all_chaoxing_credentials

    all_creds = read_all_chaoxing_credentials()
    if not all_creds:
        protocol.emit_error("No accounts found in data/passwords/chaoxing.txt")
        protocol.emit_done()
        stdin_ctrl.stop()
        sys.exit(1)

    available_indices = {c["index"] for c in all_creds}
    missing_indices = set(account_indices) - available_indices
    if missing_indices:
        protocol.emit_error(f"Account indices not found: {sorted(missing_indices)}")
        protocol.emit_done()
        stdin_ctrl.stop()
        sys.exit(1)

    # -- Emit initial state ---------------------------------------------
    protocol.emit_phase("idle")
    protocol.emit_progress(0,
        f"Job {cli.job_id} starting -- mode={cli.mode}, "
        f"accounts={account_indices}, "
        f"courses={course_filter or 'all'}")

    # -- Execute --------------------------------------------------------
    start_time = time.time()
    try:
        protocol.emit_phase("login")
        protocol.emit_progress(5, "Starting account processing...")

        run_multi_account(
            account_indices=account_indices,
            mode=cli.mode,
            course=course_filter,
            grade_only=cli.grade_only,
            content_only=cli.content_only,
            max_concurrent=cli.max_concurrent,
            budget_gb=cli.budget_gb,
            system_limit_gb=cli.system_limit_gb,
            per_account_estimate_gb=cli.per_account_estimate_gb,
        )

        # A user STOP sets the shutdown flag while threads exit cleanly. Do NOT
        # report that as "completed" — the StdinController already emitted a
        # "stopped" phase, so end the job here as an error/stop.
        if SHUTDOWN_FLAG.is_set():
            elapsed = time.time() - start_time
            protocol.emit_phase("stopped")
            protocol.emit_error(f"Job stopped by user after {elapsed:.0f}s")
            protocol.emit_done()
            return

        # -- Success ----------------------------------------------------
        elapsed = time.time() - start_time
        protocol.emit_phase("completed")
        protocol.emit_progress(100, f"All accounts processed in {elapsed:.0f}s")
        protocol.emit_result({
            "success": True,
            "durationMs": int(elapsed * 1000),
            "accountsProcessed": len(account_indices),
            "mode": cli.mode,
        })
        protocol.emit_done()

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        protocol.emit_phase("stopped")
        protocol.emit_error(f"Job stopped by user after {elapsed:.0f}s")
        protocol.emit_done()

    except Exception as e:
        protocol.emit_phase("error")
        protocol.emit_error(str(e), stack=traceback.format_exc())
        protocol.emit_done()
        sys.exit(1)

    finally:
        # Clean up: unregister the protocol handler so any subsequent
        # output (e.g. from atexit hooks) does not go through the protocol.
        set_protocol_handler(None)
        SHUTDOWN_FLAG.clear()
        stdin_ctrl.stop()


if __name__ == "__main__":
    main()
