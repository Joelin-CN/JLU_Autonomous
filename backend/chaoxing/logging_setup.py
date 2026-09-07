"""
Structured logging and CLI communication.

Provides human-readable logging with timestamp + thread prefix,
machine-parseable PROGRESS lines, and JSON-line protocol support
for frontend-backend communication.

When a protocol handler is registered via set_protocol_handler(),
all log/progress output is routed as structured dicts instead of
being printed to stdout (which is reserved for the JSON-line protocol).
"""

import time
import sys
import threading
from typing import Callable, Optional

from chaoxing.constants import LOG_DIR, SHUTDOWN_FLAG

# Thread safety for multi-account file writes
_log_lock = threading.Lock()
_log_dir_created = False

# Protocol handler — when set, log/progress output is routed through
# this callback instead of being printed to stdout. The handler
# receives a dict with type/level/message/timestamp fields.
_protocol_handler: Optional[Callable[[dict], None]] = None


def set_protocol_handler(handler: Optional[Callable[[dict], None]]):
    """Register a callback for JSON-line protocol output.

    When set, all log() and progress() output is routed through
    handler(dict) instead of being printed to stdout. This keeps
    stdout clean for the JSON-line protocol channel.

    The handler receives dicts with keys:
        type:      "LOG" or "PROGRESS"
        level:     "info" | "warn" | "error" | "debug" (LOG only)
        message:   str
        timestamp: ISO 8601 UTC string

    Pass None to remove the handler and restore default print() behavior.

    Args:
        handler: Callable that receives a structured log dict, or None.
    """
    global _protocol_handler
    _protocol_handler = handler


def _emit_protocol(event: dict):
    """Emit a structured event through the protocol handler if one is set.

    Args:
        event: Dict with type, level, message, timestamp keys.
    """
    if _protocol_handler:
        try:
            _protocol_handler(event)
        except Exception:
            pass  # Never crash because of protocol handler


def emit_memory(payload: dict) -> None:
    """Emit a MEMORY event through the protocol handler (no-op in CLI mode)."""
    _emit_protocol(payload)


def log(msg: str, level: str = "INFO"):
    """Log a message with timestamp and thread prefix.

    Automatically detects multi-account threads and prefixes with
    the thread name for readability. Also writes to daily log file.

    When a protocol handler is registered, output is routed through
    it as a structured dict; otherwise it is printed to stdout.

    Args:
        msg: The message to log.
        level: Log level (INFO, WARN, ERROR, OK, DEBUG).
    """
    global _log_dir_created
    timestamp = time.strftime("%H:%M:%S")
    # Include thread name for multi-account readability
    tname = threading.current_thread().name
    if tname.startswith("chaoxing-account-"):
        prefix = f" [{tname}]"
    else:
        prefix = ""
    line = f"[{timestamp}] [{level}]{prefix} {msg}"

    if _protocol_handler:
        from datetime import datetime, timezone
        _emit_protocol({
            "type": "LOG",
            "level": level.lower(),
            "message": msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    else:
        print(line, flush=True)

    # Also write to daily log file
    try:
        log_dir = LOG_DIR
        if not _log_dir_created:
            log_dir.mkdir(parents=True, exist_ok=True)
            _log_dir_created = True
        log_file = log_dir / f"chaoxing_{time.strftime('%Y%m%d')}.log"
        with _log_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass  # Never crash because of logging


def progress(account_index: int, step: str, current: int = 0, total: int = 0,
             lane_status: str = None):
    """Emit a machine-parseable progress line for the CLI panel.

    Format: PROGRESS:[N] current/total step_description

    The PS1 panel parses these lines to render per-account progress bars.
    When a protocol handler is registered, output is routed through it
    as a structured dict; otherwise it is printed to stdout.
    Also written to the daily log file.

    Args:
        account_index: Zero-based account index (for multi-account display).
        step: Human-readable step description.
        current: Current item number (0 if not applicable).
        total: Total items (0 if not applicable).
        lane_status: Optional lane state hint ('queued' | 'running' | 'error')
            forwarded through the JSON-line protocol to the renderer.
    """
    global _log_dir_created

    if total > 0:
        line = f"PROGRESS:[{account_index}] {current}/{total} {step}"
    else:
        line = f"PROGRESS:[{account_index}] -/- {step}"

    if _protocol_handler:
        from datetime import datetime, timezone
        percent = int((current / total) * 100) if total > 0 else 0
        payload = {
            "type": "PROGRESS",
            "percent": percent,
            "message": f"[{account_index}] {step}",
            "accountId": account_index,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if lane_status:
            payload["laneStatus"] = lane_status
        _emit_protocol(payload)
    else:
        print(line, flush=True)

    # Also write to daily log
    try:
        log_dir = LOG_DIR
        if not _log_dir_created:
            log_dir.mkdir(parents=True, exist_ok=True)
            _log_dir_created = True
        log_file = log_dir / f"chaoxing_{time.strftime('%Y%m%d')}.log"
        with _log_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {line}\n")
    except Exception:
        pass


def phase(phase_name: str):
    """Emit a PHASE transition event through the protocol handler.

    Mirrors log()/progress(): when a protocol handler is registered, the
    phase transition is routed to it as a structured dict; otherwise it is
    a no-op for stdout (phases are only meaningful for the JSON-line
    protocol consumed by the Electron frontend), but still written to the
    daily log file for traceability.

    Valid phase names: idle, login, scan_courses, process_sections,
    solve_quiz, completed, paused, stopped, error.

    Args:
        phase_name: One of the valid phase enum values.
    """
    global _log_dir_created

    if _protocol_handler:
        from datetime import datetime, timezone
        _emit_protocol({
            "type": "PHASE",
            "phase": phase_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Always trace to the daily log file (independent of protocol handler).
    try:
        log_dir = LOG_DIR
        if not _log_dir_created:
            log_dir.mkdir(parents=True, exist_ok=True)
            _log_dir_created = True
        log_file = log_dir / f"chaoxing_{time.strftime('%Y%m%d')}.log"
        with _log_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] PHASE: {phase_name}\n")
    except Exception:
        pass


def ticket(ticket_dict: dict):
    """Emit a TICKET event (manual intervention required) through the handler.

    Mirrors phase(): when a protocol handler is registered, the ticket is
    routed to it as a structured dict that api.py forwards to the frontend
    as a JSON-line TICKET event. When no handler is set (CLI mode), this is
    a no-op for stdout — tickets are only actionable by the Electron
    frontend — but a one-line trace is still written to the daily log so the
    intervention is recorded.

    The full ticket dict (id, type, title, message, imageBase64, options,
    resolved, createdAt, ...) is passed through verbatim; the protocol layer
    is responsible for the on-wire shape.

    Args:
        ticket_dict: Free-form ticket payload (see FRONTEND_BACKEND_API.md).
    """
    global _log_dir_created

    if _protocol_handler:
        _emit_protocol({
            "type": "TICKET",
            "ticket": ticket_dict,
        })

    # Always trace to the daily log (without the base64 image, to avoid
    # flooding the file). Independent of whether a handler is registered.
    try:
        log_dir = LOG_DIR
        if not _log_dir_created:
            log_dir.mkdir(parents=True, exist_ok=True)
            _log_dir_created = True
        log_file = log_dir / f"chaoxing_{time.strftime('%Y%m%d')}.log"
        tid = ticket_dict.get("id", "?")
        ttype = ticket_dict.get("type", "?")
        resolved = ticket_dict.get("resolved", False)
        with _log_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"[{time.strftime('%H:%M:%S')}] TICKET: "
                    f"id={tid} type={ttype} resolved={resolved}\n"
                )
    except Exception:
        pass


def log_exception(context: str, exc: Exception = None):
    """Log a full exception with traceback to the daily error log.

    Writes to ``LOG_DIR/chaoxing_errors_YYYYMMDD.log`` with:
      - ISO 8601 UTC timestamp
      - Context string (e.g. account index, course name, thread name)
      - Exception type, message, and full traceback

    Crash-safe: never raises, even if the log file cannot be written.
    Follows the same directory/lock convention as log() and progress().

    Args:
        context: Human-readable context (e.g. "Account 3: course 高等数学").
        exc: The exception instance. If None, uses sys.exc_info().
    """
    import traceback as _tb
    global _log_dir_created

    if exc is None:
        exc = sys.exc_info()[1]

    exc_type = type(exc).__name__ if exc else "Unknown"
    exc_msg = str(exc) if exc else "No exception details"
    tb_lines = _tb.format_exc()

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat(timespec='seconds')

    entry = (
        f"\n{'─' * 60}\n"
        f"Timestamp : {ts}\n"
        f"Context   : {context}\n"
        f"Exception : {exc_type}: {exc_msg}\n"
        f"{'─' * 60}\n"
        f"{tb_lines}\n"
        f"{'─' * 60}\n"
    )

    # Write to stderr so it's visible in console output (not stdout protocol)
    try:
        sys.stderr.write(entry)
        sys.stderr.flush()
    except Exception:
        pass

    # Also write to daily error log file
    try:
        log_dir = LOG_DIR
        if not _log_dir_created:
            log_dir.mkdir(parents=True, exist_ok=True)
            _log_dir_created = True
        err_file = log_dir / f"chaoxing_errors_{time.strftime('%Y%m%d')}.log"
        with _log_lock:
            with open(err_file, "a", encoding="utf-8") as f:
                f.write(entry)
    except Exception:
        pass  # Never crash because of error logging


# ══════════════════════════════════════════════════════════════════
#  System RAM guard — prevents runaway memory from crashing the OS
# ══════════════════════════════════════════════════════════════════

import ctypes

class _MEMORYSTATUSEX(ctypes.Structure):
    """Windows GlobalMemoryStatusEx structure for ctypes."""
    _fields_ = [
        ("dwLength",             ctypes.c_ulong),
        ("dwMemoryLoad",         ctypes.c_ulong),
        ("ullTotalPhys",         ctypes.c_ulonglong),
        ("ullAvailPhys",         ctypes.c_ulonglong),
        ("ullTotalPageFile",     ctypes.c_ulonglong),
        ("ullAvailPageFile",     ctypes.c_ulonglong),
        ("ullTotalVirtual",      ctypes.c_ulonglong),
        ("ullAvailVirtual",      ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]

_RAM_WARN_GB = 20       # Log warning when system used RAM exceeds this
_RAM_THROTTLE_GB = 22   # Inject sleep delays when system used RAM exceeds this
_RAM_CRITICAL_GB = 24   # Trigger emergency stop when system used RAM exceeds this

_ram_limit_override = None


def set_ram_limit_gb(limit_gb):
    """Override the absolute RAM guard thresholds for the current job.

    Pass None to restore the legacy 20/22/24 GB thresholds (CLI mode).
    """
    global _ram_limit_override
    _ram_limit_override = float(limit_gb) if limit_gb else None


def _ram_thresholds():
    if _ram_limit_override:
        return (_ram_limit_override - 2.0,
                _ram_limit_override - 1.0,
                _ram_limit_override)
    return (_RAM_WARN_GB, _RAM_THROTTLE_GB, _RAM_CRITICAL_GB)


_last_ram_check_time = 0.0
_ram_check_interval = 5.0  # Seconds between Windows API calls
_last_ram_usage_gb = 0.0   # Cached value between check intervals


def _get_system_ram_usage_gb() -> float:
    """Return system-wide physical RAM currently in use (GB).

    Uses the Windows GlobalMemoryStatusEx API via ctypes.
    Caches the result for _ram_check_interval seconds to avoid
    excessive syscalls on every check_signals() invocation.
    """
    global _last_ram_check_time, _last_ram_usage_gb
    now = time.time()
    if now - _last_ram_check_time < _ram_check_interval:
        return _last_ram_usage_gb

    ms = _MEMORYSTATUSEX()
    ms.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    used_bytes = ms.ullTotalPhys - ms.ullAvailPhys
    _last_ram_usage_gb = used_bytes / (1024 ** 3)
    _last_ram_check_time = now
    return _last_ram_usage_gb


# ══════════════════════════════════════════════════════════════════
#  Signal checking (for API protocol stdin control)
# ══════════════════════════════════════════════════════════════════

# Runtime control signals set by api.py's stdin reader thread.
# Worker code calls check_signals() at safe yield points.
_pause_event = threading.Event()
_stop_event = threading.Event()


def signal_pause():
    """Set the pause flag — worker threads will block at next safe point."""
    _pause_event.set()


def signal_resume():
    """Clear the pause flag — worker threads will resume."""
    _pause_event.clear()


def signal_stop():
    """Set the stop flag — worker threads will raise KeyboardInterrupt.

    Also sets the process-wide SHUTDOWN_FLAG so orchestrator loops that
    poll ``SHUTDOWN_FLAG.is_set()`` (rather than calling check_signals())
    observe the stop request too. The two flags are deliberately kept in
    sync: _stop_event drives check_signals() at fine-grained yield points,
    SHUTDOWN_FLAG drives the coarse course/account loop guards.
    """
    _stop_event.set()
    SHUTDOWN_FLAG.set()


def check_signals():
    """Check for pause/stop signals at safe yield points.

    Blocks while paused. Raises KeyboardInterrupt if stopped.
    Also monitors system RAM usage and triggers protective actions:
      - >=20 GB: log warning
      - >=22 GB: inject 2s sleep to throttle allocations
      - >=24 GB: emergency stop (raise KeyboardInterrupt)

    Call this at safe points: after navigation, between batches, after each quiz.
    """
    # -- System RAM guard (check BEFORE blocking on pause) ----------
    ram_gb = _get_system_ram_usage_gb()
    warn_gb, throttle_gb, critical_gb = _ram_thresholds()

    if ram_gb >= critical_gb:
        _stop_event.set()
        SHUTDOWN_FLAG.set()
        raise KeyboardInterrupt(
            f"EMERGENCY STOP: System RAM usage {ram_gb:.1f} GB >= "
            f"{critical_gb} GB hard limit — initiating shutdown"
        )

    if ram_gb >= warn_gb:
        level = "CRITICAL" if ram_gb >= throttle_gb else "WARN"
        # Use stderr to avoid interfering with the JSON-line protocol on stdout
        msg = (
            f"[RAM {level}] System memory: {ram_gb:.1f} GB in use. "
            f"Thresholds: warn={warn_gb}G throttle={throttle_gb}G "
            f"critical={critical_gb}G"
        )
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()

        if ram_gb >= throttle_gb:
            time.sleep(2.0)  # Slow down all threads to reduce allocation rate

    # -- Pause / Stop signals ---------------------------------------
    if _stop_event.is_set():
        raise KeyboardInterrupt("STOP signal received — graceful shutdown")
    while _pause_event.is_set():
        if _stop_event.is_set():
            raise KeyboardInterrupt("STOP signal received — graceful shutdown")
        time.sleep(0.5)
