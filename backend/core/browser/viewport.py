"""
Viewport management — ensure the browser window is large enough for screenshots.

The Chaoxing quiz UI requires a large viewport to capture complete question
content (title number + stem + options). This module checks and resizes the
chaoxing-chrome viewport as needed.
"""

import json

from ..session import _get_active_session
from ..logging_setup import log
from .js_runner import _run_js_file


def ensure_chaoxing_viewport(width: int = 2048, height: int = 1152):
    """Resize the chaoxing-chrome viewport if it doesn't match target size.

    Only applies to the chaoxing session — never touches doubao or other
    sessions. Screenshots require a large viewport to capture complete
    question content (题目编号+题干+选项).
    """
    if not _get_active_session().startswith("chaoxing-chrome"):
        return  # Only resize chaoxing browser

    target_w, target_h = width, height
    try:
        check_js = """
        async (page) => {
            const vw = await page.evaluate(() => window.innerWidth);
            const vh = await page.evaluate(() => window.innerHeight);
            return JSON.stringify({vw, vh});
        }
        """
        dims_raw = _run_js_file(check_js, timeout=10)
        dims = json.loads(dims_raw)
        cur_w, cur_h = dims.get("vw", 0), dims.get("vh", 0)

        if cur_w < target_w or cur_h < target_h:
            log(f"[Viewport] Resizing chaoxing-chrome from {cur_w}x{cur_h} to {target_w}x{target_h}")
            resize_js = f"""
            async (page) => {{
                await page.setViewportSize({{ width: {target_w}, height: {target_h} }});
                return 'OK';
            }}
            """
            _run_js_file(resize_js, timeout=10)
        else:
            log(f"[Viewport] chaoxing-chrome: {cur_w}x{cur_h} OK")
    except Exception as e:
        log(f"[Viewport] Could not check/resize: {e}")
