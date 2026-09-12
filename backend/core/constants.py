"""
Global constants: paths, locks, and process-wide flags.

These are the foundational constants extracted from utils.py.
All other modules depend on these — constants.py has zero internal dependencies.
"""

import os
import sys
import io
import threading
from pathlib import Path

# ── Force UTF-8 on Windows ────────────────────────────────────
if sys.platform == "win32":
    if sys.stdout.buffer is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    if sys.stderr.buffer is not None:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ── Paths ──────────────────────────────────────────────────────
WORKSPACE = Path(os.environ.get("CHAOXING_WORKSPACE", str(Path(__file__).parent.parent)))

# Runtime data root. In dev this is the repo-level data/ directory next to the
# backend subtree; when packaged (CHAOXING_WORKSPACE -> userData/workspace) it
# resolves to userData/data. An explicit CHAOXING_DATA_DIR always wins.
DATA_ROOT = Path(os.environ.get("CHAOXING_DATA_DIR", str(WORKSPACE.parent / "data")))

SCRIPT_DIR = WORKSPACE / "scripts"      # Read-only JS assets (font decrypt, player)
CONFIG_PATH = WORKSPACE / "chaoxing_config.json"   # Project root (moved out of scripts/)
OUTPUT_DIR = DATA_ROOT / "output"       # Runtime output (progress, discovered courses)
TMP_DIR = DATA_ROOT / "temp"            # Temporary files (JS scripts, screenshots)
LOG_DIR = DATA_ROOT / "logs"            # Daily logs + error logs
SCREENSHOTS_DIR = DATA_ROOT / "screenshots"  # Manual/debug screenshots
CHROME_PROFILES_DIR = DATA_ROOT / "chrome-profiles"  # Persistent browser profiles
CREDS_DIR = DATA_ROOT / "passwords"     # Credential files (never committed)
DOCUMENTS_DIR = DATA_ROOT / "documents" # Personal reference documents

# ── Package data paths (JS injection files, font tables) ─────
PACKAGE_DIR = Path(__file__).parent
JS_DIR = PACKAGE_DIR / "js"
DATA_DIR = PACKAGE_DIR / "data"

# ── Account list sanity cap (NOT a concurrency limit) ───────────
# Concurrency is decided per job by the memory/CPU plan (chaoxing.memory).
MAX_ACCOUNTS = 50

# ── Graceful Shutdown ──────────────────────────────────────────
# Set by the orchestrator when Ctrl+C is caught. Worker threads
# check this flag at safe yield points and exit cleanly.
SHUTDOWN_FLAG = threading.Event()
