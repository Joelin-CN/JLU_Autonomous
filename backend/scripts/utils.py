"""
Chaoxing Automation Utilities

Backward-compatible shim — re-exports from chaoxing.* subpackages.
All real logic lives in the chaoxing/ package (41 modules, 12 subpackages).

This file exists so that existing scripts and tests that do
`from utils import ...` continue to work.
"""
import sys
from pathlib import Path

# When invoked through backend/scripts (e.g. tests/_test_phase_c.py), make sure
# the backend root is importable so `chaoxing.*` resolves correctly.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# ══════════════════════════════════════════════════════════════════
#  Paths & Constants
# ══════════════════════════════════════════════════════════════════
from chaoxing.constants import (
    WORKSPACE,
    SCRIPT_DIR,
    CONFIG_PATH,
    OUTPUT_DIR,
    TMP_DIR,
    SHUTDOWN_FLAG,
)

# ══════════════════════════════════════════════════════════════════
#  Config
# ══════════════════════════════════════════════════════════════════
from chaoxing.config import load_config, cfg

# ══════════════════════════════════════════════════════════════════
#  Session
# ══════════════════════════════════════════════════════════════════
from chaoxing.session import (
    _get_tls,
    set_active_session,
    _get_active_session,
    _ThreadLocalStore,
)

# ══════════════════════════════════════════════════════════════════
#  Logging
# ══════════════════════════════════════════════════════════════════
from chaoxing.logging_setup import log, progress, check_signals

# ══════════════════════════════════════════════════════════════════
#  Browser Engine
# ══════════════════════════════════════════════════════════════════
from chaoxing.browser.engine import (
    pw,
    pw_snapshot,
    pw_click,
    pw_goto,
    pw_fill,
    pw_run_code,
    _quote_arg,
)
from chaoxing.browser.js_runner import (
    pw_run_code_file,
    pw_extract_result,
    _run_js_file,
)
from chaoxing.browser.viewport import ensure_chaoxing_viewport

# ══════════════════════════════════════════════════════════════════
#  Platform: Navigation
# ══════════════════════════════════════════════════════════════════
from chaoxing.platform.navigation import (
    pw_goto_course,
    pw_get_iframe_snapshot,
)

# ══════════════════════════════════════════════════════════════════
#  Platform: Auth
# ══════════════════════════════════════════════════════════════════
from chaoxing.platform.auth import (
    _parse_credential_block,
    read_all_chaoxing_credentials,
    read_chaoxing_credentials,
    is_chaoxing_browser_open,
    ensure_chaoxing_browser,
    chaoxing_login,
)

# ══════════════════════════════════════════════════════════════════
#  Platform: Scanner
# ══════════════════════════════════════════════════════════════════
from chaoxing.platform.scanner import (
    scan_courses,
    scan_course_sections,
)

# ══════════════════════════════════════════════════════════════════
#  Utils (snapshot parsing)
# ══════════════════════════════════════════════════════════════════
from chaoxing.utils import (
    find_ref_by_text,
    find_refs_by_pattern,
    parse_progress_from_snapshot,
)

# ══════════════════════════════════════════════════════════════════
#  Tracking
# ══════════════════════════════════════════════════════════════════
from chaoxing.tracking import ProgressTracker

# ══════════════════════════════════════════════════════════════════
#  Font Decryption
# ══════════════════════════════════════════════════════════════════
from chaoxing.font import (
    ensure_font_decrypt_loaded,
    decrypt_font_cxsecret,
    get_decrypted_quiz_text,
)

# ══════════════════════════════════════════════════════════════════
#  AI — Router (convenience wrappers)
# ══════════════════════════════════════════════════════════════════
from chaoxing.ai.router import (
    ai_solve_quiz,
    ai_solve_quiz_image,
    ai_grade_quiz_image,
)

# ══════════════════════════════════════════════════════════════════
#  AI — Doubao API (direct)
# ══════════════════════════════════════════════════════════════════
from chaoxing.ai.doubao import (
    ai_solve_quiz_doubao,
    ai_solve_quiz_image_doubao,
)
