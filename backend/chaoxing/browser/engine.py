"""
Playwright CLI engine — low-level wrapper around playwright-cli commands.

Provides the core pw() function plus convenience wrappers for snapshot,
click, goto, fill, and run-code. All functions automatically target the
current thread's active session (via _get_active_session).
"""

import os
import sys
import subprocess
import time

from ..constants import WORKSPACE
from ..config import cfg
from ..session import _get_active_session
from ..logging_setup import log


# ── Argument Quoting ────────────────────────────────────────────

def _quote_arg(arg: str) -> str:
    """Quote an argument for Windows shell if it contains special chars.

    Also collapses newlines to avoid cmd.exe truncating multi-line
    JavaScript/arguments at line breaks.

    Escapes internal double quotes to prevent command injection when
    arguments containing " are wrapped in outer double quotes.
    """
    # Collapse whitespace (including newlines) to prevent cmd.exe splitting
    arg = " ".join(arg.split())
    # Escape internal double quotes for cmd.exe: " → \"
    arg = arg.replace('"', '\\"')
    special = {'&', '?', '=', ' ', '%', '^', '|', '<', '>', '(', ')'}
    if any(c in arg for c in special):
        return f'"{arg}"'
    return arg


def _escape_ps_string(text: str) -> str:
    """Escape a string for safe interpolation into a PowerShell double-quoted string.

    PowerShell special characters inside double-quoted strings:
        $   → variable expansion  → escape with backtick: `$
        `   → escape character    → double it: ``
        "   → string terminator   → double it: ""
        #   → comment (line start) → escape with backtick: `#
        \\n  → not special inside PS double quotes, but newlines must be collapsed
    """
    text = " ".join(text.split())  # collapse whitespace/newlines
    text = text.replace('`', '``')
    text = text.replace('$', '`$')
    text = text.replace('"', '""')
    text = text.replace('#', '`#')
    return text


# ── Core pw() ───────────────────────────────────────────────────

_CLI_AVAILABILITY_CACHE: set = set()

# stderr fragments the daemon prints when its Chrome target died between
# commands (e.g. the browser process was killed mid-job). Distinct from a
# timeout: the CLI returns immediately with a nonzero rc.
_SESSION_DEAD_MARKERS = (
    "target page, context or browser has been closed",
    "browser has been closed",
    "browser has been disconnected",
    "target closed",
    # CLI-client local error once the daemon deregistered the session
    "is not open. run",
)


class SessionDeadError(RuntimeError):
    """The playwright-cli daemon lost its Chrome target (browser died)."""


class PlaywrightCliMissingError(RuntimeError):
    """playwright-cli is not installed or not reachable on PATH."""

    def __init__(self, cli: str):
        super().__init__(
            f"未找到 playwright-cli（{cli}）。请先安装 Node.js 18+，再执行 "
            f"npm install -g playwright-cli，并确认其位于系统 PATH 中"
            f"（安装说明见 README「前置依赖」）。"
        )


def ensure_cli_available(cli: str) -> None:
    """Raise a friendly PlaywrightCliMissingError when the CLI is missing.

    pw() runs hundreds of times per job, so the PATH scan result is cached
    per CLI name — it only needs to fail once to be conclusive.
    """
    if cli in _CLI_AVAILABILITY_CACHE:
        return
    from shutil import which
    if which(cli) is None and which(cli.removesuffix(".cmd").removesuffix(".bat")) is None:
        raise PlaywrightCliMissingError(cli)
    _CLI_AVAILABILITY_CACHE.add(cli)


def pw(*args, timeout: int = None, use_shell: bool = False) -> str:
    """Run a playwright-cli command and return stdout.

    Defaults to shell=False for security (avoids cmd.exe injection).
    Pass use_shell=True only for legacy callers that require it.

    All args are quoted properly for Windows shell (cmd.exe).
    URLs with & are wrapped in double quotes to avoid command chaining.
    Multi-line args (e.g. JavaScript) are collapsed to single line.

    Daemon-wedge resilience: a long idle (e.g. the 120s anti-spider delay)
    can leave the playwright-cli daemon unresponsive, and the first command
    after the idle then times out — historically failing the whole course.
    On TimeoutExpired we (1) retry once, (2) rebuild the session
    (close → sweep orphans → reopen) and try a final time. Self-contained
    commands (goto/run-code) recover cleanly; page-dependent ones may see a
    fresh page, which still beats a hard course failure.
    """
    session = _get_active_session()
    cli = cfg("playwright_cli", "playwright-cli.cmd")
    ensure_cli_available(cli)
    t = timeout or cfg("timeouts.snapshot", 15)

    try:
        return _pw_once(cli, session, args, t, use_shell)
    except (subprocess.TimeoutExpired, SessionDeadError) as first_err:
        log(f"[pw] '{args[0] if args else '?'}' failed ({type(first_err).__name__}) "
            f"— retrying once (daemon may be waking)", "WARN")
        time.sleep(2.0)

    try:
        return _pw_once(cli, session, args, t, use_shell)
    except (subprocess.TimeoutExpired, SessionDeadError):
        log(f"[pw] retry also failed — rebuilding browser session "
            f"'{session}'", "WARN")
        _rebuild_session(session)

    return _pw_once(cli, session, args, t, use_shell)


def _pw_once(cli: str, session: str, args, t: int, use_shell: bool) -> str:
    """Single playwright-cli invocation (the pre-retry body of pw())."""
    # Headed mode: check CHAOXING_HEADED env var (set by chaoxing_cli.ps1 --headed)
    # Only append --headed for actions that accept it (not snapshot/run-code)
    _headed_actions = {"open", "click", "fill", "press", "goto", "type", "hover", "select-option", "check", "uncheck", "drag"}
    _action = args[0] if args else ""
    _want_headed = os.environ.get("CHAOXING_HEADED", "0") == "1" and _action in _headed_actions
    headed_flag = " --headed" if _want_headed else ""

    if use_shell:
        # Build command string with shell-safe quoting
        quoted = [_quote_arg(a) for a in args]
        cmd_str = f"{cli}{headed_flag} -s={session} " + " ".join(quoted)
        result = subprocess.run(
            cmd_str,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=t,
            shell=True,
        )
    else:
        # Use list form (shell=False) to avoid pipe buffer deadlock
        # on Windows for long-running commands
        cmd = [cli] + (["--headed"] if headed_flag else []) + [f"-s={session}"] + list(args)
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=t,
            shell=False,
        )

    stderr = result.stderr or ""
    stdout = result.stdout or ""
    if result.returncode != 0:
        # shell=True path: cmd.exe reports a missing command instead of
        # raising FileNotFoundError, so detect its localized error text too.
        if ("is not recognized" in stderr
                or "不是内部或外部命令" in stderr) and cli.split(".")[0] in stderr:
            raise PlaywrightCliMissingError(cli)
        if stderr:
            log(f"[pw] Warning: {stderr[:200]}", "WARN")
    # The CLI reports a dead browser target on STDOUT ("### Error
    # Error: Target page, context or browser has been closed") with rc=0 —
    # check both streams for the dead markers.
    for stream in (stderr, stdout):
        low = stream.lower()
        if "### error" in low or result.returncode != 0:
            if any(m in low for m in _SESSION_DEAD_MARKERS):
                raise SessionDeadError(stream.strip()[:200])
    return result.stdout


def _rebuild_session(session: str) -> None:
    """Close and reopen a wedged browser session (best effort).

    Mirrors auth.ensure_chaoxing_browser's open invocation (no --headless
    flag: headless is the daemon default; --headed only in headed mode).
    Deferred import: platform.auth imports this module at load time, so the
    reverse dependency must stay inside the function.
    """
    from ..platform.auth import _kill_orphaned_chrome  # noqa: WPS433
    cli = cfg("playwright_cli", "playwright-cli.cmd")
    try:
        idx = int(session.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        idx = 0
    try:
        subprocess.run(
            [cli, f"-s={session}", "close"],
            cwd=str(WORKSPACE), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10, shell=True,
        )
    except Exception as e:
        log(f"[pw] close during rebuild failed: {e}", "WARN")
    _kill_orphaned_chrome(idx)
    profile_dir = _default_profile_dir(idx)
    cmd = [cli, f"-s={session}", "open", "--browser=chrome", "--persistent",
           f"--profile={profile_dir}", "about:blank"]
    if os.environ.get("CHAOXING_HEADED", "0") == "1":
        cmd.append("--headed")
    try:
        result = subprocess.run(
            cmd, cwd=str(WORKSPACE), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30, shell=False,
        )
        if result.returncode != 0:
            log(f"[pw] session rebuild open rc={result.returncode}: "
                f"{(result.stderr or result.stdout or '')[:200]}", "WARN")
    except Exception as e:
        log(f"[pw] session rebuild open failed: {e}", "WARN")
    if _wait_session_ready(cli, session):
        log(f"[pw] session '{session}' rebuilt and ready — command will retry "
            f"on a fresh page; course context is re-entered by the solver on "
            f"navigation failure", "WARN")
    else:
        log(f"[pw] session '{session}' rebuilt but NOT ready within deadline "
            f"— retry may still fail", "WARN")


def _wait_session_ready(cli: str, session: str, deadline_s: float = 25.0) -> bool:
    """Poll until the reopened session actually executes a trivial command.

    `open` returns before Chrome finishes booting; retrying the real command
    immediately can blow its whole timeout on browser startup. A ready-probe
    costs one lightweight run-code round-trip per attempt.
    """
    start = time.time()
    while time.time() - start < deadline_s:
        try:
            r = subprocess.run(
                [cli, f"-s={session}", "run-code", "async (page) => 1"],
                cwd=str(WORKSPACE), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=8, shell=False,
            )
            if r.returncode == 0 and "### error" not in (r.stdout or "").lower():
                return True
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        time.sleep(1.5)
    return False


def _default_profile_dir(idx: int):
    from ..constants import CHROME_PROFILES_DIR
    return CHROME_PROFILES_DIR / f"account-{idx}"


# ── Convenience Wrappers ────────────────────────────────────────

def pw_snapshot() -> str:
    """Take a boxed snapshot and return YAML text."""
    return pw("snapshot", "--boxes")


def pw_click(ref: str):
    """Click an element by snapshot ref."""
    return pw("click", ref, timeout=cfg("timeouts.click_action", 10))


def pw_goto(url: str):
    """Navigate to a URL.

    Uses _run_js_file for navigation to avoid cmd.exe shell escaping
    issues with & in query parameters (even with shell=False, .cmd
    wrappers go through cmd.exe which interprets & as command separator).
    """
    # Deferred import to break circular dependency with js_runner
    from .js_runner import _run_js_file
    import json as _json

    safe_url = _json.dumps(url)  # JSON-encoded -> safe for JS string literal
    js = f"async (page) => {{ await page.goto({safe_url}); return 'ok'; }}"
    _run_js_file(js, timeout=cfg("timeouts.page_load", 30))


def pw_fill(ref: str, text: str):
    """Fill a textbox by ref (uses clipboard to avoid echo).

    Text is PowerShell-escaped to prevent command injection.
    Clipboard is cleared after paste to prevent credential lingering.
    """
    import subprocess as sp
    session = _get_active_session()
    cli = cfg("playwright_cli", "playwright-cli.cmd")
    safe_text = _escape_ps_string(text)
    ps_cmd = (
        f'$null = Set-Clipboard "{safe_text}"; '
        f'{cli} -s={session} click {ref}; '
        f'{cli} -s={session} press Control+V; '
        f'Start-Sleep -Milliseconds 200; '
        f'$null = Set-Clipboard ""'
    )
    sp.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        cwd=str(WORKSPACE), capture_output=True, text=True, timeout=30
    )


def pw_run_code(js_code: str) -> str:
    """Execute JS in the page context via run-code.

    Multi-line JS is routed through the temp-file path (_run_js_file): the
    shell=False command line is NOT whitespace-collapsed, so on Windows the
    .cmd wrapper truncates the invocation at the first newline, handing
    playwright-cli a broken arrow function ("SyntaxError: Unexpected token
    ')'"). Single-line JS goes direct. This makes every caller newline-safe
    without each having to remember the tempfile dance.
    """
    if "\n" in js_code:
        # Deferred import: js_runner imports from engine, so importing it at
        # module load would be circular. extract=False keeps the raw-output
        # contract identical to the single-line branch below.
        from .js_runner import _run_js_file
        return _run_js_file(js_code, timeout=20, extract=False)
    return pw("run-code", js_code, timeout=20)
