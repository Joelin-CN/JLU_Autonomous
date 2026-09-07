"""
Content handlers and CAPTCHA guard for chapter content completion.

Defines a ContentHandler ABC and four implementations:
  - VideoHandler   — v17 inline-chained video playback
  - DocumentHandler — document/PDF scrolling
  - AudioHandler   — audio playback waiting
  - GenericHandler — fallback for unknown content types

Also includes the anti-spider CAPTCHA detection + auto-solve pipeline
used by the content bot during section processing.
"""

import os
import re
import json
import time
import base64
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from ...constants import SCRIPT_DIR, TMP_DIR
from ...logging_setup import log, check_signals, ticket
from ...session import _get_active_session
from ...browser.engine import pw_snapshot, pw_click, pw_run_code
from ...browser.js_runner import pw_run_code_file, pw_extract_result
from ...platform.navigation import pw_goto_course
from ...platform.captcha import solve_captcha_image, captcha_paths_for_session
from .navigator import find_ref_by_text
from ...utils import human_delay


# ══════════════════════════════════════════════════════════════════
#  Standalone Helpers
# ══════════════════════════════════════════════════════════════════

def _is_section_complete(snap: str) -> bool:
    """Check if the current section is marked complete in the snapshot."""
    indicators = [
        "任务点完成",
        "已完成",
        "学习完成",
        "green_check",
        "completed",
    ]
    return any(ind in snap for ind in indicators)


def _try_force_complete() -> bool:
    """Last resort: try to mark section complete by interacting with elements.

    Avoids clicking "下一节" because that causes a full page redirect
    to the studentstudy page, breaking the chapter-tree navigation.
    """
    log("    Attempting force completion...")
    snap = pw_snapshot()

    # Safest: click "确定" or "关闭" to dismiss any dialog
    safe_ref = (
        find_ref_by_text(snap, "确定") or
        find_ref_by_text(snap, "关闭") or
        find_ref_by_text(snap, "继续")
    )
    if safe_ref:
        pw_click(safe_ref)
        human_delay(2.0, 0.25)
        return True

    # "下一节" causes redirect — avoid unless no other option
    next_ref = find_ref_by_text(snap, "下一节")
    if next_ref:
        log("    Only found '下一节' — will cause page redirect", "WARN")
        pw_click(next_ref)
        human_delay(3.0, 0.25)
        return True

    return False


def return_to_course_page(courseid: str, clazzid: str, cpi: str):
    """Navigate the main page back to the course page from studentstudy.

    After a section completes, the main page is on studentstudy
    (mooc1.chaoxing.com/mycourse/studentstudy), which has no chapter
    tree. Uses the standard stucoursemiddle entry URL to ensure
    proper session setup.
    """
    log("    Returning to course page...")
    pw_goto_course(courseid, clazzid, cpi)
    human_delay(3.0, 0.25)
    log("    Returned to course page")


# ══════════════════════════════════════════════════════════════════
#  CAPTCHA Detection & Auto-Solve
# ══════════════════════════════════════════════════════════════════

def _build_extract_js(has_inline_captcha: bool, captcha_img: str) -> str:
    """Build the Playwright JS that extracts the CAPTCHA image to disk.

    Tries a DOM fetch (preserves original quality, returns a data: URL) and
    falls back to a clipped screenshot written to ``captcha_img``. The inline
    variant searches the antispider/mooc iframe; the redirect variant uses the
    main page. Factored out so the manual-fallback loop can re-grab a refreshed
    image after a wrong answer (the on-page CAPTCHA changes each attempt).
    """
    if has_inline_captcha:
        return """
        async (page) => {
            // Find the CAPTCHA-containing iframe
            let targetFrame = page.frames().find(f =>
                f !== page.mainFrame() && f.url().includes('antispider'));
            if (!targetFrame) {
                targetFrame = page.frames().find(f =>
                    f !== page.mainFrame() && f.url().includes('mooc')
                    && !f.url().includes('antispider'));
            }
            if (!targetFrame) return 'no-captcha-frame';

            // Try DOM fetch first – download the img src directly
            try {
                const dataUrl = await targetFrame.evaluate(async () => {
                    const imgs = document.querySelectorAll('img');
                    for (const img of imgs) {
                        if (img.naturalWidth > 50 && img.naturalHeight > 20) {
                            const resp = await fetch(img.src);
                            const blob = await resp.blob();
                            return new Promise(resolve => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result);
                                reader.readAsDataURL(blob);
                            });
                        }
                    }
                    return null;
                });
                if (dataUrl) return dataUrl;
            } catch(e) {
                // DOM fetch failed, fall through to screenshot fallback
            }

            // Fallback: screenshot via clip (iframe coordinate correction)
            const imgs = await targetFrame.locator('img').all();
            let freshBox = null;
            for (const img of imgs) {
                const box = await img.boundingBox();
                if (box && box.width > 50 && box.height > 20) {
                    await img.scrollIntoViewIfNeeded();
                    await page.waitForTimeout(300);
                    freshBox = await img.boundingBox();
                    break;
                }
            }
            if (!freshBox) return 'no-captcha-img';

            let iframeOffsetX = 0, iframeOffsetY = 0;
            const iframeEls = await page.locator('iframe').all();
            for (const el of iframeEls) {
                const src = await el.getAttribute('src');
                if (src && (src.includes('antispider') || src.includes('mooc'))) {
                    const elBox = await el.boundingBox();
                    if (elBox) { iframeOffsetX = elBox.x; iframeOffsetY = elBox.y; }
                    break;
                }
            }
            const clipX = iframeOffsetX + freshBox.x;
            const clipY = iframeOffsetY + freshBox.y;
            await page.screenshot({
                path: '""" + captcha_img.replace('\\', '\\\\') + """',
                clip: {x: clipX, y: clipY, width: freshBox.width, height: freshBox.height}
            });
            return 'ok-' + Math.round(freshBox.width) + 'x' + Math.round(freshBox.height);
        }
        """
    return """
        async (page) => {
            // Try DOM fetch first – download the img src directly
            try {
                const dataUrl = await page.evaluate(async () => {
                    const imgs = document.querySelectorAll('img');
                    for (const img of imgs) {
                        if (img.naturalWidth > 50 && img.naturalHeight > 20) {
                            const resp = await fetch(img.src);
                            const blob = await resp.blob();
                            return new Promise(resolve => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result);
                                reader.readAsDataURL(blob);
                            });
                        }
                    }
                    return null;
                });
                if (dataUrl) return dataUrl;
            } catch(e) {
                // DOM fetch failed, fall through to screenshot fallback
            }

            // Fallback: screenshot via clip
            const img = page.locator('img').first();
            const box = await img.boundingBox();
            if (!box) return 'no-box';
            await page.screenshot({
                path: '""" + captcha_img.replace('\\', '\\\\') + """',
                clip: {x: box.x, y: box.y, width: box.width, height: box.height}
            });
            return 'ok-' + Math.round(box.width) + 'x' + Math.round(box.height);
        }
        """


def _extract_and_write_captcha_image(has_inline_captcha: bool, captcha_img: str):
    """Run the extraction JS and ensure the CAPTCHA image lands at captcha_img.

    If the JS returns a ``data:image/...`` URL (DOM-fetch path), decode and
    write it; otherwise the JS already screenshotted to ``captcha_img``.
    Returns the raw JS result string for logging. Safe to call repeatedly.
    """
    js_extract = _build_extract_js(has_inline_captcha, captcha_img)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
    tmp.write(js_extract)
    tmp.close()
    raw = pw_run_code_file(tmp.name, timeout=15)
    try:
        os.unlink(tmp.name)
    except Exception:
        pass

    captcha_result = pw_extract_result(raw)
    if captcha_result and isinstance(captcha_result, str) and captcha_result.startswith('data:image/'):
        try:
            _, b64_data = captcha_result.split(',', 1)
            with open(captcha_img, 'wb') as f:
                f.write(base64.b64decode(b64_data))
            log(f"  CAPTCHA extracted from DOM: {len(b64_data)} bytes base64 -> {os.path.getsize(captcha_img)} bytes PNG")
        except Exception as e:
            log(f"  CAPTCHA base64 decode failed: {e}")
    else:
        log(f"  CAPTCHA image: {captcha_result}")
    return captcha_result


def _captcha_image_data_uri(captcha_img: str) -> str:
    """Read captcha_img off disk and return a PNG data: URI (or "" if absent)."""
    if os.path.exists(captcha_img) and os.path.getsize(captcha_img) > 100:
        try:
            with open(captcha_img, 'rb') as imf:
                b64 = base64.b64encode(imf.read()).decode('ascii')
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            log(f"  Could not base64-encode CAPTCHA image: {e}", "WARN")
    return ""


def check_anti_spider() -> bool:
    """Check for anti-spider verification (URL redirect OR in-page/iframe CAPTCHA).

    Two CAPTCHA types exist:
    1. Full-page redirect: URL contains "antispider"
    2. In-page/iframe CAPTCHA: text "操作异常" / "验证码" / "9010" inside
       the studentstudy iframe (blocks video playback silently)

    Detection pipeline:
      1. Check page URL for "antispider"
      2. Check antispider iframe for CAPTCHA text
      3. Check mooc iframe for CAPTCHA text
      4. If detected: extract image (DOM fetch -> screenshot fallback)
      5. Send to Doubao for OCR
      6. Regex-extract answer
      7. Auto-fill and submit
      8. Manual fallback: wait up to 10 min, check answer file, poll

    Returns:
        True if we're clear to continue (no CAPTCHA, or solved successfully).
    """

    # ── Check 1: antispider URL redirect ──
    js_url = "async (page) => page.url()"
    raw = pw_run_code(js_url)
    current_url = pw_extract_result(raw)

    is_antispider_page = "antispider" in str(current_url).lower()

    # ── Check 2: in-page CAPTCHA (antispider iframe OR mooc iframe text) ──
    has_inline_captcha = False
    captcha_text = ""
    captcha_in_antispider_frame = False

    js_check_iframe = """
    async (page) => {
        // Strategy: find antispider iframe FIRST (most precise)
        const af = page.frames().find(f =>
            f !== page.mainFrame() && f.url().includes('antispider'));
        if (af) {
            const bt = await af.locator('body').innerText();
            return JSON.stringify({
                captcha: true,
                text: bt.substring(0, 300),
                inAntispiderFrame: true
            });
        }
        // Fallback: check mooc iframe body for CAPTCHA text
        const mf = page.frames().find(f =>
            f !== page.mainFrame() && f.url().includes('mooc')
            && !f.url().includes('antispider'));
        if (!mf) return JSON.stringify({captcha: false});
        const bt = await mf.locator('body').innerText();
        const hasCaptcha = bt.includes('操作异常') || bt.includes('验证码') || bt.includes('9010');
        return JSON.stringify({
            captcha: hasCaptcha,
            text: bt.substring(0, 300),
            inAntispiderFrame: false
        });
    }
    """

    try:
        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
        tmp.write(js_check_iframe)
        tmp.close()
        raw_iframe = pw_run_code_file(tmp.name, timeout=15)
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        result = json.loads(pw_extract_result(raw_iframe))
        has_inline_captcha = result.get('captcha', False)
        captcha_text = result.get('text', '')
        captcha_in_antispider_frame = result.get('inAntispiderFrame', False)
    except Exception:
        pass  # If we can't check, proceed and hope for the best

    if not is_antispider_page and not has_inline_captcha:
        return True  # All clear

    # ── CAPTCHA detected — try to auto-solve via Doubao ──
    captcha_type = "URL antispider" if is_antispider_page else "in-page (iframe)"
    log(f"CAPTCHA DETECTED ({captcha_type})!", "ERROR")
    log(f"  Page text snippet: {captcha_text[:200]}")

    session = _get_active_session()
    captcha_img, captcha_answer = captcha_paths_for_session(session)
    # Parse the zero-based account index from the session name
    # ("chaoxing-chrome-2" -> 2) for ticket routing. Single-account default
    # session ("chaoxing-chrome") has no index → account 0.
    m_acct = re.search(r'chaoxing-chrome-(\d+)$', session or "")
    account_id = int(m_acct.group(1)) if m_acct else 0
    for f in [captcha_img, captcha_answer]:
        try:
            os.unlink(f)
        except Exception:
            pass

    # Extract CAPTCHA image directly from DOM (fetch img src -> base64).
    # This preserves the original image quality, unlike page.screenshot().
    # Falls back to screenshot if DOM extraction fails.
    _extract_and_write_captcha_image(has_inline_captcha, captcha_img)

    # Try to auto-solve via shared CAPTCHA image solver
    answer = None
    if os.path.exists(captcha_img) and os.path.getsize(captcha_img) > 100:
        try:
            answer = solve_captcha_image(captcha_img)
            log(f"  Doubao recognized: '{answer}'")
        except Exception as e:
            log(f"  Doubao auto-solve failed: {e}")

    if answer and len(answer) <= 10:
        # Auto-fill the answer
        if has_inline_captcha:
            js_fill = f"""
            async (page) => {{
                // Find the CAPTCHA iframe (antispider first, then mooc)
                let tf = page.frames().find(f =>
                    f !== page.mainFrame() && f.url().includes('antispider'));
                if (!tf) {{
                    tf = page.frames().find(f =>
                        f !== page.mainFrame() && f.url().includes('mooc')
                        && !f.url().includes('antispider'));
                }}
                if (!tf) return 'no-captcha-frame';

                // Fill CAPTCHA input — try specific selector first
                let tb = tf.locator('input[name="ucode"]');
                if (await tb.count() === 0) {{
                    tb = tf.locator('input[type="text"], textbox, input').first();
                }}
                if (await tb.count() === 0) return 'no-textbox';
                await tb.fill('{answer}');
                await page.waitForTimeout(300);

                // Submit — try specific submit input first, then button
                let btn = tf.locator('input[type="submit"]');
                if (await btn.count() === 0) {{
                    btn = tf.locator('button').filter({{hasText: '提交'}}).first();
                }}
                if (await btn.count() > 0) {{
                    await btn.click();
                    await page.waitForTimeout(3000);
                }}

                // Verify solved
                const newBt = await tf.locator('body').innerText();
                const stillCaptcha = newBt.includes('操作异常') || newBt.includes('验证码') || newBt.includes('9010');
                // Also check if antispider frame is gone
                const afGone = !page.frames().some(f => f.url().includes('antispider'));
                return (stillCaptcha && !afGone) ? 'still-captcha' : 'solved';
            }}
            """
        else:
            js_fill = f"""
            async (page) => {{
                const tb = page.getByRole('textbox', {{name: '输入验证码'}});
                await tb.fill('{answer}');
                await page.getByRole('button', {{name: '提交'}}).click();
                await page.waitForTimeout(2500 + Math.floor(Math.random() * 1200));
                return page.url().includes('antispider') ? 'still-captcha' : 'solved';
            }}
            """

        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
        try:
            tmp.write(js_fill)
            tmp.close()
            raw3 = pw_run_code_file(tmp.name, timeout=15)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
        fill_result = pw_extract_result(raw3)
        log(f"  Auto-fill result: {fill_result}")

        if 'solved' in str(fill_result):
            try:
                os.unlink(captcha_img)
            except Exception:
                pass
            log("  CAPTCHA auto-solved!", "OK")
            human_delay(3.0, 0.25)
            return True

    # ── Fallback: wait for manual solve ──
    # AI could not solve it. Notify the frontend with a TICKET carrying the
    # CAPTCHA image (base64) so the user can type the answer; the answer comes
    # back over stdin (RESOLVE_TICKET) and is written to ``captcha_answer`` by
    # api.StdinController, which the poll loop below reads. Also still honours
    # a manually-solved CAPTCHA in the headed Chrome window.
    #
    # ``created_at`` is stamped ONCE and reused on every re-emit (including the
    # wrong-answer refresh below) so the frontend's 10-minute countdown counts
    # from the original request and is not reset by a retry.
    ticket_id = f"captcha_{account_id}_{int(time.time())}"
    created_at = datetime.now(timezone.utc).isoformat()
    image_data_uri = _captcha_image_data_uri(captcha_img)

    ticket({
        "id": ticket_id,
        "type": "captcha",
        "accountId": account_id,
        "title": "需要人工输入验证码",
        "message": f"账号 {account_id} 在反爬验证码处受阻，AI 识别失败，请人工输入",
        "imageBase64": image_data_uri,
        "options": ["输入验证码", "跳过此课程"],
        "resolved": False,
        "createdAt": created_at,
    })

    log("  Waiting for manual solve (frontend ticket or headed Chrome window)...")
    for i in range(120):  # Up to 10 minutes
        human_delay(5.0, 0.15)

        # Check for answer file (frontend RESOLVE_TICKET writes this)
        if os.path.exists(captcha_answer):
            man_answer = ""
            try:
                with open(captcha_answer, 'r', encoding='utf-8') as f:
                    man_answer = f.read().strip()
            except Exception as e:
                log(f"  Manual solve read error: {e}")
            # Always remove the answer file once read — correct OR wrong. This
            # is the bug fix: a stale wrong answer left on disk was re-submitted
            # every 5s until timeout. Each answer now gets exactly one attempt.
            try:
                os.unlink(captcha_answer)
            except Exception:
                pass

            try:
                # Skip sentinel: user chose "跳过此课程". Clean up and bail
                # out (return False → caller skips this course's content).
                if man_answer == "__SKIP__":
                    log("  User chose to skip this course (ticket).", "WARN")
                    try:
                        os.unlink(captcha_img)
                    except Exception:
                        pass
                    ticket({
                        "id": ticket_id,
                        "type": "captcha",
                        "accountId": account_id,
                        "resolved": True,
                        "resolution": "skipped",
                        "createdAt": created_at,
                    })
                    return False

                if man_answer:
                    # Fill using the answer
                    if has_inline_captcha:
                        js_fill_m = f"""
                        async (page) => {{
                            let tf = page.frames().find(f =>
                                f !== page.mainFrame() && f.url().includes('antispider'));
                            if (!tf) {{
                                tf = page.frames().find(f =>
                                    f !== page.mainFrame() && f.url().includes('mooc')
                                    && !f.url().includes('antispider'));
                            }}
                            if (!tf) return 'no-captcha-frame';
                            let tb = tf.locator('input[name="ucode"]');
                            if (await tb.count() === 0) {{
                                tb = tf.locator('input[type="text"], textbox, input').first();
                            }}
                            await tb.fill('{man_answer}');
                            await page.waitForTimeout(300);
                            let btn = tf.locator('input[type="submit"]');
                            if (await btn.count() === 0) {{
                                btn = tf.locator('button').filter({{hasText: '提交'}}).first();
                            }}
                            if (await btn.count() > 0) await btn.click();
                            await page.waitForTimeout(3000);
                            const newBt = await tf.locator('body').innerText();
                            const stillCaptcha = newBt.includes('操作异常') || newBt.includes('验证码') || newBt.includes('9010');
                            const afGone = !page.frames().some(f => f.url().includes('antispider'));
                            return (stillCaptcha && !afGone) ? 'still-captcha' : 'solved';
                        }}
                        """
                    else:
                        js_fill_m = f"""
                        async (page) => {{
                            const tb = page.getByRole('textbox', {{name: '输入验证码'}});
                            await tb.fill('{man_answer}');
                            await page.getByRole('button', {{name: '提交'}}).click();
                            await page.waitForTimeout(3000);
                            return page.url().includes('antispider') ? 'still-captcha' : 'solved';
                        }}
                        """
                    tm = tempfile.NamedTemporaryFile(
                        mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
                    tm.write(js_fill_m)
                    tm.close()
                    raw_m = pw_run_code_file(tm.name, timeout=15)
                    try:
                        os.unlink(tm.name)
                    except Exception:
                        pass
                    fill_m = pw_extract_result(raw_m)
                    log(f"  Manual fill result: {fill_m}")
                    if 'solved' in str(fill_m):
                        try:
                            os.unlink(captcha_img)
                        except Exception:
                            pass
                        log("  CAPTCHA solved via answer file!", "OK")
                        ticket({
                            "id": ticket_id,
                            "type": "captcha",
                            "accountId": account_id,
                            "resolved": True,
                            "resolution": "solved",
                            "createdAt": created_at,
                        })
                        time.sleep(3)
                        return True
                    else:
                        # Wrong answer. Superstar refreshes the on-page CAPTCHA
                        # after a failed submit, so the old image is now stale.
                        # Re-grab the refreshed image and re-emit the SAME ticket
                        # (same id + original createdAt, resolved:false) so the
                        # frontend reopens its input with the new picture and its
                        # 10-min countdown continues uninterrupted.
                        log("  Wrong CAPTCHA answer — refreshing image for retry.", "WARN")
                        try:
                            os.unlink(captcha_img)
                        except Exception:
                            pass
                        _extract_and_write_captcha_image(has_inline_captcha, captcha_img)
                        ticket({
                            "id": ticket_id,
                            "type": "captcha",
                            "accountId": account_id,
                            "title": "需要人工输入验证码",
                            "message": f"账号 {account_id} 验证码输入有误，请查看新验证码后重新输入",
                            "imageBase64": _captcha_image_data_uri(captcha_img),
                            "options": ["输入验证码", "跳过此课程"],
                            "resolved": False,
                            "createdAt": created_at,
                        })
            except Exception as e:
                log(f"  Manual solve error: {e}")

        # Check if CAPTCHA disappeared (user solved manually in Chrome)
        if has_inline_captcha:
            try:
                tmp2 = tempfile.NamedTemporaryFile(
                    mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
                tmp2.write(js_check_iframe)
                tmp2.close()
                raw_iframe2 = pw_run_code_file(tmp2.name, timeout=10)
                try:
                    os.unlink(tmp2.name)
                except Exception:
                    pass
                result2 = json.loads(pw_extract_result(raw_iframe2))
                if not result2.get('captcha', False):
                    log("  CAPTCHA appears solved! Resuming...")
                    for fp in [captcha_answer, captcha_img]:
                        try:
                            os.unlink(fp)
                        except Exception:
                            pass
                    ticket({
                        "id": ticket_id,
                        "type": "captcha",
                        "accountId": account_id,
                        "resolved": True,
                        "resolution": "solved",
                        "createdAt": created_at,
                    })
                    time.sleep(3)
                    return True
            except Exception:
                pass
        else:
            raw_url2 = pw_run_code(js_url)
            new_url = pw_extract_result(raw_url2)
            if "antispider" not in str(new_url).lower():
                log("  CAPTCHA appears solved! Resuming...")
                for fp in [captcha_answer, captcha_img]:
                    try:
                        os.unlink(fp)
                    except Exception:
                        pass
                ticket({
                    "id": ticket_id,
                    "type": "captcha",
                    "accountId": account_id,
                    "resolved": True,
                    "resolution": "solved",
                    "createdAt": created_at,
                })
                time.sleep(3)
                return True

    log("  Timeout waiting for CAPTCHA solution", "ERROR")
    for fp in [captcha_answer, captcha_img]:
        try:
            os.unlink(fp)
        except Exception:
            pass
    # Void the ticket so the frontend closes its input dialog.
    ticket({
        "id": ticket_id,
        "type": "captcha",
        "accountId": account_id,
        "resolved": True,
        "resolution": "timeout",
        "createdAt": created_at,
    })
    return False


# ══════════════════════════════════════════════════════════════════
#  ContentHandler ABC
# ══════════════════════════════════════════════════════════════════

class ContentHandler(ABC):
    """Abstract base class for content-type handlers.

    Each handler declares which content type(s) it can process via
    ``can_handle()``, and implements ``handle()`` to execute the
    content-completion strategy for that type.

    The ``handle()`` method receives the bot instance so it can
    access course config (courseid, clazzid, cpi, name, dry_run)
    and progress tracking state.
    """

    @staticmethod
    @abstractmethod
    def can_handle(content_type: str) -> bool:
        """Return True if this handler can process the given content type."""
        ...

    @abstractmethod
    def handle(self, bot, chapter_num: int, section_num: int,
               task_count: int) -> str:
        """Execute the content-completion strategy.

        Args:
            bot: The ChapterContentBot instance (for config + state access).
            chapter_num: Chapter number (1-indexed).
            section_num: Section number within the chapter (1-indexed).
            task_count: Number of task points in this section.

        Returns:
            Result code: "advanced", "completed", "no-video", "failed", etc.
        """
        ...


# ══════════════════════════════════════════════════════════════════
#  Video Handler
# ══════════════════════════════════════════════════════════════════

class VideoHandler(ContentHandler):
    """Handle video content — play at normal speed until natural completion.

    Uses v17 section player which auto-advances to next section via
    "下一节" after video completion (reference script gotoNextSection logic).

    Return codes:
      "advanced"   — page auto-advanced to next section (no need to go back)
      "completed"  — all tasks done, returned to course page
      "no-video"   — no video frames found, try document handling
      "failed"     — playback failed after retries
    """

    @staticmethod
    def can_handle(content_type: str) -> bool:
        return content_type == "video"

    def handle(self, bot, chapter_num: int, section_num: int,
               task_count: int) -> str:
        # ── Pre-check: CAPTCHA in iframe blocks video playback silently ──
        if not check_anti_spider():
            log("    CAPTCHA blocking video playback, cannot continue", "ERROR")
            return "failed"

        log("    Playing video at normal speed (v17 with auto-advance)...")

        # Retry loop: if CAPTCHA appears mid-playback, solve it and retry
        max_retries = 3
        for attempt in range(max_retries):
            result = self._play_videos()

            if result and result.startswith("advanced:"):
                # v17 auto-clicked "下一节" — we're now on the NEXT section's page!
                # No need to return to course page; caller should chain to next section.
                log("    Video completed + auto-advanced to next section!", "OK")
                return "advanced"

            elif result and result.startswith("all-complete:"):
                # All tasks done but couldn't auto-advance (no "下一节" button found)
                log("    Video completed! (no auto-advance available)", "OK")
                return_to_course_page(bot.courseid, bot.clazzid, bot.cpi)
                return "completed"

            elif result and result.startswith("captcha-detected:"):
                log(f"    CAPTCHA detected during playback (attempt {attempt+1}/{max_retries})", "WARN")
                if check_anti_spider():
                    log("    CAPTCHA solved, resuming playback...")
                    continue  # Retry playback
                else:
                    log("    CAPTCHA solve failed", "ERROR")
                    return_to_course_page(bot.courseid, bot.clazzid, bot.cpi)
                    return "failed"

            elif result == "no-videos" or result == "no-video-frames":
                log("    No video frames found — may be a document", "WARN")
                return "no-video"

            elif result == "no-kc-frame":
                log("    No knowledge/cards iframe — page may not have loaded correctly", "WARN")
                return_to_course_page(bot.courseid, bot.clazzid, bot.cpi)
                return "failed"

            else:
                log(f"    Video playback failed: {str(result)[:100]}", "WARN")
                # Check if CAPTCHA caused the failure
                check_anti_spider()
                return_to_course_page(bot.courseid, bot.clazzid, bot.cpi)
                return "failed"

        log(f"    Video playback failed after {max_retries} CAPTCHA interruptions", "ERROR")
        return_to_course_page(bot.courseid, bot.clazzid, bot.cpi)
        return "failed"

    # ── Video timing ──────────────────────────────────────────────

    def _get_video_remaining_time(self) -> dict:
        """Quickly read video durations to calculate playback timeout.

        Tries video element durations first, falls back to JC.attachments.
        Since we always play from the beginning (no seeking),
        remaining time equals full duration.

        Returns dict with: totalDuration, maxDuration, count.
        Uses a temp file to avoid shell escaping issues with inline run-code.
        """
        js_code = """async (page) => {
            var totalDur = 0, maxDur = 0, videoCount = 0;

            // Try reading from video elements
            var vfs = page.frames().filter(function(f) { return f.url().indexOf('video/index.html') >= 0; });
            for (var i = 0; i < vfs.length; i++) {
                try {
                    var st = await vfs[i].evaluate(function() {
                        var v = document.querySelector('video');
                        return v ? {ct: v.currentTime || 0, dur: v.duration || 0} : null;
                    });
                    if (st && st.dur > 0 && st.dur < 99999) {
                        totalDur += st.dur;
                        if (st.dur > maxDur) maxDur = st.dur;
                        videoCount++;
                    }
                } catch(e) {}
            }

            // Fallback: read JC.attachments (metadata always available)
            if (totalDur <= 0) {
                var kcFrame = page.frames().find(function(f) { return f.url().indexOf('knowledge/cards') >= 0; });
                if (kcFrame) {
                    try {
                        var atts = await kcFrame.evaluate(function() {
                            if (typeof JC === 'undefined' || !JC.attachments) return [];
                            return JC.attachments.map(function(a) { return a.attDuration || 0; });
                        });
                        for (var j = 0; j < atts.length; j++) {
                            totalDur += atts[j];
                            if (atts[j] > maxDur) maxDur = atts[j];
                        }
                        if (atts.length > videoCount) videoCount = atts.length;
                    } catch(e) {}
                }
            }

            // totalDur = sum of all video durations (sequential playback)
            // maxDur = longest single video
            return Math.round(totalDur) + '|' + Math.round(maxDur) + '|' + videoCount;
        }"""
        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
        tmp.write(js_code)
        tmp.close()
        try:
            raw = pw_run_code_file(tmp.name, timeout=30)
            result = pw_extract_result(raw)
            try:
                parts = result.strip().split('|')
                if len(parts) >= 3:
                    return {
                        "totalDuration": float(parts[0]),
                        "maxDuration": float(parts[1]),
                        "count": int(parts[2]),
                    }
            except Exception as e:
                log(f"    Failed to parse video timing '{str(result)[:80]}': {e}", "WARN")
        except Exception as e:
            log(f"    Failed to read video timing: {e}", "WARN")
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
        return {"totalDuration": 0, "maxDuration": 0, "count": 0}

    # ── Video playback ────────────────────────────────────────────

    def _play_videos(self) -> str:
        """Play video content sequentially with inline next-section navigation.

        Uses v17 section player (migrated from reference script):
        - Sequential video playback (one at a time)
        - Auto-resume on pause (3s delay — reference script approach)
        - CAPTCHA detection during playback
        - After all videos complete: auto-click "下一节" to chain to next section
          (avoids round-trip back to chapter tree — faster + more natural)

        Returns:
          "advanced:N:..."    — advanced to next section N times inline
          "all-complete:..."  — all tasks done, couldn't auto-advance
          "captcha-detected:..." — CAPTCHA blocked playback (retry needed)
          "no-video-frames"   — no video iframes found (may be document)
          "no-kc-frame"       — no knowledge/cards iframe
          "video-error:..."   — exception during playback
        """
        # Read the v17 section player JS
        js_file = os.path.join(str(SCRIPT_DIR), '_v17_section_player.js')
        try:
            with open(js_file, 'r', encoding='utf-8') as f:
                js_combined = f.read()
        except FileNotFoundError:
            log(f"    v17 section player script not found: {js_file}", "WARN")
            return "no-v17-script"

        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
        tmp.write(js_combined)
        tmp.close()
        # Read video timing to calculate dynamic timeout
        video_info = self._get_video_remaining_time()
        total_duration = int(video_info.get("totalDuration", 0))
        max_duration = int(video_info.get("maxDuration", 0))
        video_count = video_info.get("count", 0)
        # Use sum of all video durations (sequential playback), fall back to max single
        effective_duration = total_duration if total_duration > 0 else max_duration
        dynamic_timeout = effective_duration + 120
        dynamic_timeout = max(dynamic_timeout, 300)  # minimum 5 minutes
        log(f"    Video timeout: {dynamic_timeout}s (total={total_duration}s, max={max_duration}s, vids={video_count})")

        try:
            raw = pw_run_code_file(tmp.name, timeout=dynamic_timeout)
            result = pw_extract_result(raw)
            log(f"    Video result: {str(result)[:200]}")
            return str(result)
        except Exception as e:
            return f"video-error: {e}"
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════
#  Document Handler
# ══════════════════════════════════════════════════════════════════

class DocumentHandler(ContentHandler):
    """Scroll through a document/PDF section to trigger completion."""

    @staticmethod
    def can_handle(content_type: str) -> bool:
        return content_type == "document"

    def handle(self, bot, chapter_num: int, section_num: int,
               task_count: int) -> str:
        log("    Scrolling through document...")

        # Scroll the iframe content
        js = """
        async (page) => {
            const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2'));
            if (!iframe) return 'no-iframe';

            // Scroll to bottom
            await iframe.evaluate(() => {
                const scrollStep = 300;
                const scrollInterval = 500;
                const totalHeight = document.body.scrollHeight;
                let scrolled = 0;

                return new Promise((resolve) => {
                    const timer = setInterval(() => {
                        window.scrollBy(0, scrollStep);
                        scrolled += scrollStep;
                        if (scrolled >= totalHeight) {
                            clearInterval(timer);
                            resolve('scrolled');
                        }
                    }, scrollInterval);
                });
            });
            return 'scrolled';
        }
        """
        pw_run_code(js)
        human_delay(3.0, 0.25)

        snap = pw_snapshot()
        return "completed" if _is_section_complete(snap) else "failed"


# ══════════════════════════════════════════════════════════════════
#  Audio Handler
# ══════════════════════════════════════════════════════════════════

class AudioHandler(ContentHandler):
    """Wait for audio content to complete."""

    @staticmethod
    def can_handle(content_type: str) -> bool:
        return content_type == "audio"

    def handle(self, bot, chapter_num: int, section_num: int,
               task_count: int) -> str:
        log("    Waiting for audio completion...")

        # Click play if needed
        snap = pw_snapshot()
        play_ref = find_ref_by_text(snap, "播放") or find_ref_by_text(snap, "play")
        if play_ref:
            pw_click(play_ref)

        # Wait for completion
        content_timeout = getattr(bot, 'CONTENT_TIMEOUT', 180)
        start = time.time()
        while time.time() - start < content_timeout:
            # Yield point: responsive pause/stop/RAM-guard during long video waits.
            check_signals()
            human_delay(5.0, 0.15)
            snap = pw_snapshot()
            if _is_section_complete(snap):
                return "completed"

        return "completed" if _try_force_complete() else "failed"


# ══════════════════════════════════════════════════════════════════
#  Generic (Fallback) Handler
# ══════════════════════════════════════════════════════════════════

class GenericHandler(ContentHandler):
    """Handle unknown content type — click through and wait."""

    @staticmethod
    def can_handle(content_type: str) -> bool:
        return True  # Catch-all fallback — always last in dispatch order

    def handle(self, bot, chapter_num: int, section_num: int,
               task_count: int) -> str:
        log("    Handling generic content...")
        human_delay(5.0, 0.15)

        # Try scrolling to bottom
        js = """
        async (page) => {
            const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2'));
            if (iframe) {
                await iframe.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            }
            return 'done';
        }
        """
        pw_run_code(js)
        human_delay(3.0, 0.25)

        snap = pw_snapshot()
        return "completed" if _is_section_complete(snap) else "failed"
