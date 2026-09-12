"""
JS injection helpers — execute JavaScript in the browser page context.

Provides the tempfile-based JS execution pipeline:
    pw_run_code_file() -> pw_extract_result()
    _run_js_file() combines both with automatic cleanup.
"""

import os as _os
import json
import tempfile as _tmp

from ..constants import TMP_DIR
from .engine import pw


def pw_run_code_file(filepath: str, timeout: int = 20) -> str:
    """Execute JS from a file via run-code --filename.

    Avoids shell quoting issues with complex multi-line JavaScript.
    Uses use_shell=False to prevent pipe buffer deadlock on Windows
    for long-running JS (e.g. route+seek+detect taking 60+ seconds).
    """
    return pw("run-code", f"--filename={filepath}", timeout=timeout, use_shell=False)


def pw_extract_result(pw_output: str) -> str:
    """Extract the actual result value from playwright-cli output.

    playwright-cli echoes the JS code (which may contain the expected
    return strings), so naive substring checks like ``"clicked:" in output``
    can produce false positives. This function extracts only the ``### Result``
    section from the output.

    Playwright returns the result as a JSON-encoded value (e.g. ``"a string"``
    or ``"{\\"key\\":\\"val\\"}"``). We parse as JSON first to correctly
    handle escaped characters, falling back to raw stripping.
    """
    import re
    match = re.search(r"### Result\s*\n(.*?)(?:\n###|\Z)", pw_output, re.DOTALL)
    if match:
        val = match.group(1).strip()
        # Try JSON decode — Playwright returns values as JSON strings
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            # Fallback: strip outer quotes (handles unicode/raw strings)
            return val.strip('"')
    return pw_output.strip()


def _run_js_file(js_code: str, timeout: int = 20, extract: bool = True) -> str:
    """Write JS to temp file, execute via pw_run_code_file, clean up, return result.

    Centralizes the tempfile lifecycle so no orphan tmp*.js files are left behind.

    Args:
        js_code: JavaScript source to run.
        timeout: Per-command timeout in seconds.
        extract: When True (default) return the extracted ``### Result`` value.
            When False return the raw playwright-cli stdout — used by
            pw_run_code() so its return contract stays identical for single-
            and multi-line JS (callers extract themselves).
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    t = _tmp.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    try:
        t.write(js_code)
        t.close()
        raw = pw_run_code_file(t.name, timeout=timeout)
        return pw_extract_result(raw) if extract else raw
    finally:
        try:
            _os.unlink(t.name)
        except Exception:
            pass
