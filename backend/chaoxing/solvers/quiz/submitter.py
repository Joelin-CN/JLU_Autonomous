"""
Quiz submission — native DOM submit, snapshot-based fallback, score parsing.

Submits completed quizzes using the page-native btnBlueSubmit() function with
DOM button click and noSubmit save as fallbacks, plus snapshot text search
as last resort.
"""

import json as _json
import re
import time
import tempfile
import os

from ...constants import TMP_DIR
from ...logging_setup import log
from ...browser.engine import pw_snapshot, pw_click
from ...browser.js_runner import pw_run_code_file, pw_extract_result
from ...utils import find_ref_by_text
from ...utils import human_delay


def _submit_quiz() -> bool:
    """Submit quiz using native function with snapshot fallback."""
    # PRIMARY: native submit
    if _submit_quiz_native():
        return True

    # FALLBACK: snapshot text search for submit button
    log("  Native submit failed, trying snapshot-based submit...", "WARN")
    submit_snap = pw_snapshot()
    submit_ref = find_ref_by_text(submit_snap, "提交")
    if not submit_ref:
        submit_ref = find_ref_by_text(submit_snap, "交卷")
    if not submit_ref:
        submit_ref = find_ref_by_text(submit_snap, "暂存")
    if submit_ref:
        pw_click(submit_ref)
        human_delay(2.0, 0.25)

        # Confirm dialog if present
        confirm_snap = pw_snapshot()
        confirm_ref = find_ref_by_text(confirm_snap, "确定")
        if not confirm_ref:
            confirm_ref = find_ref_by_text(confirm_snap, "确认")
        if confirm_ref:
            pw_click(confirm_ref)
            human_delay(1.0, 0.3)
        return True

    log("  Could not find submit button via any method", "WARN")
    return False


def _submit_quiz_native() -> bool:
    """Submit quiz using page-native btnBlueSubmit() function.

    Reference scripts (referrence_scripts.txt:5567-5569,
    referrence_scripts2.txt:2943-2945, 3336-3340) all use:
        await iframeWindow.btnBlueSubmit();
        await sleep(N);
        await iframeWindow.submitCheckTimes();

    Falls back through: DOM button click -> noSubmit save -> snapshot text search.
    Returns True if submitted successfully via any method.
    """
    js = r"""
    async (page) => {
        const candidates = page.frames().filter(f =>
            f !== page.mainFrame() &&
            (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
             f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
        );
        if (candidates.length === 0) return JSON.stringify({ok: false, reason: 'no-iframe'});

        for (const iframe of candidates) {
            // ── Primary: btnBlueSubmit() native function ──
            try {
                const hasFn = await iframe.evaluate(() => {
                    return typeof window.btnBlueSubmit === 'function';
                });
                if (hasFn) {
                    await iframe.evaluate(() => { window.btnBlueSubmit(); });
                    return JSON.stringify({ok: true, method: 'btnBlueSubmit'});
                }
            } catch(e) {}

            // ── Fallback 1: DOM button with onclick ──
            try {
                const sel = 'button[onclick*="btnBlueSubmit"], a[onclick*="btnBlueSubmit"], ' +
                            '.Btn_blue_1, .sub_btn, button:has-text("提交"), button:has-text("交卷")';
                const btn = iframe.locator(sel).first();
                if (await btn.count() > 0) {
                    await btn.click();
                    return JSON.stringify({ok: true, method: 'dom-btn-click'});
                }
            } catch(e) {}

            // ── Fallback 2: noSubmit (save without submitting) ──
            try {
                const hasNoSubmit = await iframe.evaluate(() => {
                    return typeof window.noSubmit === 'function';
                });
                if (hasNoSubmit) {
                    // If noSubmit exists, btnBlueSubmit might also exist
                    // Try clicking .Btn_blue_1 as last resort
                    try {
                        const blueBtn = iframe.locator('.Btn_blue_1').first();
                        if (await blueBtn.count() > 0) {
                            await blueBtn.click();
                            return JSON.stringify({ok: true, method: 'Btn_blue_1-fallback'});
                        }
                    } catch(e) {}
                }
            } catch(e) {}
        }
        return JSON.stringify({ok: false, reason: 'no-submit-method-found'});
    }
    """

    js_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    try:
        js_file.write(js)
        js_file.close()
        raw = pw_run_code_file(js_file.name, timeout=15)
    finally:
        try:
            os.unlink(js_file.name)
        except Exception:
            pass

    result_str = pw_extract_result(raw)
    try:
        result = _json.loads(result_str)
        if result.get("ok"):
            log(f"  Submit: {result.get('method', '?')}")
            human_delay(2.0, 0.25)

            # Check for confirmation dialog (like submitCheckTimes)
            human_delay(1.0, 0.3)
            confirm_snap = pw_snapshot()
            confirm_ref = find_ref_by_text(confirm_snap, "确定")
            if not confirm_ref:
                confirm_ref = find_ref_by_text(confirm_snap, "确认")
            if confirm_ref:
                pw_click(confirm_ref)
                human_delay(1.0, 0.3)
            return True
    except _json.JSONDecodeError:
        log(f"  Native submit result parse error: {result_str[:80]}", "WARN")
    return False


def _parse_score(snap: str) -> int | None:
    """Extract score percentage from result snapshot."""
    # Patterns: "得分：85", "成绩：90分", "score: 95%", "100分"
    patterns = [
        r'(\d+)\s*分',
        r'得分[：:]\s*(\d+)',
        r'成绩[：:]\s*(\d+)',
        r'(\d+)\s*%',
    ]
    for pat in patterns:
        match = re.search(pat, snap)
        if match:
            return int(match.group(1))
    return None
