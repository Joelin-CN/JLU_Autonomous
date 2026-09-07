"""
CAPTCHA auto-detection and solving via AI image recognition (Doubao).

Detects in-page CAPTCHA (antispiderShowVerify.ac), screenshots the
challenge image, sends it to Doubao for OCR, extracts the answer
via regex, and auto-fills/submits the form.
"""

import json
import os
import re
import base64
import tempfile
import time

from ..constants import SCRIPT_DIR, TMP_DIR
from ..browser.js_runner import pw_run_code_file, pw_extract_result
from ..session import _get_active_session
from ..ai.prompts import format_captcha_prompt
from ..logging_setup import log


def _session_suffix(session: str) -> str:
    """Return the per-account filename suffix for a session name.

    Multi-account threads use sessions named ``chaoxing-chrome-<N>`` and get
    a ``_chaoxing-chrome-<N>`` suffix; the single-account default session
    ``chaoxing-chrome`` gets no suffix. This is the single source of truth
    for the suffix rule — both the CAPTCHA read side (check_anti_spider)
    and the answer write side (StdinController) derive paths from it so the
    filenames can never drift apart.
    """
    return f"_{session}" if session and session != "chaoxing-chrome" else ""


def captcha_paths_for_session(session: str) -> tuple:
    """Return ``(captcha_img_path, captcha_answer_path)`` for a session name.

    Both paths live under ``TMP_DIR`` with the per-account suffix applied.
    Used by check_anti_spider() (read side) to keep the image/answer file
    names consistent with the writer.

    Args:
        session: Active session name (e.g. "chaoxing-chrome" or
                 "chaoxing-chrome-2").

    Returns:
        Tuple of (image PNG absolute path, answer TXT absolute path).
    """
    suffix = _session_suffix(session)
    img = os.path.join(str(TMP_DIR), f'_captcha_img{suffix}.png')
    answer = os.path.join(str(TMP_DIR), f'_captcha_answer{suffix}.txt')
    return img, answer


def captcha_answer_path(account_index: int) -> str:
    """Return the answer-file path for a zero-based account index.

    The write side (StdinController, which only knows the frontend's
    ``accountId``) uses this to target the same file the read side polls.
    Reconstructs the multi-account session name ``chaoxing-chrome-<N>`` so
    the suffix matches :func:`captcha_paths_for_session` exactly.

    Args:
        account_index: Zero-based account index from the RESOLVE_TICKET payload.

    Returns:
        Absolute path to ``_captcha_answer_chaoxing-chrome-<N>.txt``.
    """
    session = f"chaoxing-chrome-{account_index}"
    _, answer = captcha_paths_for_session(session)
    return answer


def detect_captcha() -> str:
    """Check if the page contains a CAPTCHA challenge.

    Searches both the main page and any mooc iframe for CAPTCHA text
    markers ("操作异常", "验证码", "9010"). Also locates the CAPTCHA
    image box, text input, and submit button for use by solve_captcha().

    Returns:
        JSON string: {"captcha": true/false, ...} with bounding box data
        if a CAPTCHA is found.
    """
    js = """
    async (page) => {
        const targets = [page];
        const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc'));
        if (iframe) targets.push(iframe);

        for (const target of targets) {
            const bodyText = await target.locator('body').innerText();
            if (bodyText.includes('操作异常') || bodyText.includes('验证码') || bodyText.includes('9010')) {
                const imgs = await target.locator('img').all();
                let imgBox = null;
                for (const img of imgs) {
                    const box = await img.boundingBox();
                    if (box && box.width > 50 && box.height > 20) {
                        imgBox = {x: box.x, y: box.y, width: box.width, height: box.height};
                        break;
                    }
                }
                const tb = await target.locator('input[type="text"], textbox, input').first();
                const tbBox = tb ? await tb.boundingBox() : null;
                const btn = await target.locator('button').filter({hasText: '提交'}).first();
                const btnBox = btn ? await btn.boundingBox() : null;

                return JSON.stringify({
                    captcha: true,
                    imgBox,
                    tbBox,
                    btnBox,
                    source: target === page ? 'main-page' : 'iframe',
                    snippet: bodyText.substring(0, 200)
                });
            }
        }
        return JSON.stringify({captcha: false, reason: 'not-found'});
    }
    """
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=str(TMP_DIR), encoding='utf-8')
    try:
        tmp.write(js)
        tmp.close()
        raw = pw_run_code_file(tmp.name, timeout=15)
        return pw_extract_result(raw)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def solve_captcha_image(captcha_img_path: str) -> str or None:
    """Send a CAPTCHA image to AI for OCR and extract the answer text.

    Shared pipeline used by both solve_captcha() (platform layer) and
    check_anti_spider() (content-handler layer) to avoid ~500 lines of
    duplicated OCR + regex extraction logic.

    Args:
        captcha_img_path: Absolute path to the CAPTCHA screenshot PNG.

    Returns:
        The extracted answer string (e.g. "A3x9"), or None if extraction
        failed.
    """
    if not os.path.exists(captcha_img_path) or os.path.getsize(captcha_img_path) < 100:
        log(f"[Captcha] Image missing or too small: {captcha_img_path}")
        return None

    # Deferred import to avoid circular dependency at module load time
    from ..ai.doubao import doubao_ask_image

    prompt_text = format_captcha_prompt()
    raw_answer = doubao_ask_image([captcha_img_path], prompt_text, timeout=120)

    # ── Clean and extract answer ──
    answer = None
    cleaned = raw_answer
    for noise in ['请识别图片中的文字', '只返回文字本身', '不要其他任何内容',
                  '请识别图片中的验证码文字', '识别', '识图模式',
                  '深度思考', '内容由 AI 生成，请仔细甄别']:
        cleaned = cleaned.replace(noise, '')
    cleaned = re.sub(r'\s+', '', cleaned)

    # Longest-first to avoid truncation (4-char first since it's most common)
    captcha_patterns = [
        r'([A-Za-z0-9]{4})',
        r'([A-Za-z0-9]{5})',
        r'([A-Za-z0-9]{6})',
        r'([A-Za-z0-9]{3})',
    ]
    for pat in captcha_patterns:
        m = re.search(pat, cleaned)
        if m:
            answer = m.group(1)
            break

    # Space-tolerant fallback
    if not answer:
        for pat in [r'([A-Za-z0-9]{2})\s*([A-Za-z0-9]{2,3})',
                    r'([A-Za-z0-9]{1,2})\s*([A-Za-z0-9]{2,3})']:
            m = re.search(pat, raw_answer)
            if m:
                answer = m.group(1) + m.group(2)
                break

    # Last resort
    if not answer:
        stripped = re.sub(r'\s+', '', raw_answer.strip().strip('"').strip("'"))
        m2 = re.search(r'[A-Za-z0-9]{3,6}', stripped)
        if m2:
            answer = m2.group(0)

    return answer


def solve_captcha() -> bool:
    """Detect, screenshot, OCR, and submit CAPTCHA challenge.

    Full pipeline:
        1. detect_captcha() — locate challenge on page
        2. Extract CAPTCHA image (DOM fetch → fallback screenshot)
        3. Send to Doubao image mode for OCR
        4. Regex-extract answer (longest-first patterns)
        5. Auto-fill and submit

    Returns:
        True if CAPTCHA was solved or no CAPTCHA was present.
        False if solving failed.
    """
    # ── 1. Detect ──────────────────────────────────────────────
    log("[Captcha] Checking for in-page CAPTCHA...")
    result_str = detect_captcha()
    log(f"[Captcha] Detection result: {result_str[:300]}")

    try:
        result = json.loads(result_str)
    except json.JSONDecodeError:
        log("[Captcha] Could not parse detection result, trying regex...")
        if '操作异常' in result_str or '验证码' in result_str:
            log("[Captcha] CAPTCHA text found but JSON parsing failed")
        return False

    if not result.get('captcha'):
        log("[Captcha] No CAPTCHA detected on page")
        return True  # Nothing to solve

    img_box = result.get('imgBox')
    if not img_box:
        log("[Captcha] CAPTCHA text found but no image box located")
        return False

    # ── 2. Extract CAPTCHA image ───────────────────────────────
    session = _get_active_session()
    captcha_path, _ = captcha_paths_for_session(session)
    try:
        os.unlink(captcha_path)
    except OSError:
        pass

    # Try DOM-based extraction first (preserves original quality)
    js_extract = """
    async (page) => {
        const targets = [page];
        const mf = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc'));
        if (mf) targets.push(mf);

        for (const targetFrame of targets) {
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
            } catch(e) {}
        }
        return 'fallback';
    }
    """
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=str(TMP_DIR), encoding='utf-8')
    try:
        tmp.write(js_extract)
        tmp.close()
        raw_result = pw_run_code_file(tmp.name, timeout=15)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    img_data = pw_extract_result(raw_result)
    if img_data and isinstance(img_data, str) and img_data.startswith('data:image/'):
        try:
            _, b64_data = img_data.split(',', 1)
            with open(captcha_path, 'wb') as f:
                f.write(base64.b64decode(b64_data))
            log(f"[Captcha] DOM-extracted: {len(b64_data)} bytes base64 → {os.path.getsize(captcha_path)} bytes PNG")
        except Exception as e:
            log(f"[Captcha] Base64 decode failed: {e}")
    else:
        # Fallback: screenshot with known coordinates
        log(f"[Captcha] DOM extraction returned: {str(img_data)[:100]}, using screenshot fallback...")
        js_screenshot = f"""
        async (page) => {{
            await page.screenshot({{
                path: '{captcha_path.replace(chr(92), '/')}',
                clip: {{x: {img_box['x']}, y: {img_box['y']}, width: {img_box['width']}, height: {img_box['height']}}}
            }});
            return 'ok';
        }}
        """
        tmp2 = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=str(TMP_DIR), encoding='utf-8')
        try:
            tmp2.write(js_screenshot)
            tmp2.close()
            pw_run_code_file(tmp2.name, timeout=15)
        finally:
            try:
                os.unlink(tmp2.name)
            except Exception:
                pass
        if os.path.exists(captcha_path):
            log(f"[Captcha] Screenshot saved: {os.path.getsize(captcha_path)} bytes")

    if not os.path.exists(captcha_path) or os.path.getsize(captcha_path) < 100:
        log("[Captcha] Failed to extract CAPTCHA image")
        return False

    # ── 3. Ask Doubao to read CAPTCHA via shared solver ───────
    answer = solve_captcha_image(captcha_path)
    log(f"[Captcha] Extracted answer: '{answer}'")

    # ── 4. Validate answer before injecting into JS ──────────────
    if answer is None:
        log("[Captcha] CAPTCHA answer extraction failed")
        return False

    # ── 5. Fill and submit ─────────────────────────────────────
    js_fill = f"""
    async (page) => {{
        const targets = [page];
        const mf = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc'));
        if (mf) targets.push(mf);

        for (const target of targets) {{
            const tb = target.locator('input[type="text"], textbox, input').first();
            if (await tb.count() === 0) continue;

            await tb.fill('{answer}');
            await page.waitForTimeout(500);

            const btn = target.locator('button').filter({{hasText: '提交'}}).first();
            if (await btn.count() === 0) continue;

            await btn.click();
            await page.waitForTimeout(3000);

            const newUrl = page.url();
            const bodyText = await target.locator('body').innerText();
            const stillCaptcha = bodyText.includes('操作异常') || bodyText.includes('验证码');
            return stillCaptcha ? 'still-captcha' : 'solved:' + newUrl.substring(0, 80);
        }}
        return 'no-textbox-or-btn';
    }}
    """
    tmp3 = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=str(TMP_DIR), encoding='utf-8')
    try:
        tmp3.write(js_fill)
        tmp3.close()
        raw_fill = pw_run_code_file(tmp3.name, timeout=15)
    finally:
        try:
            os.unlink(tmp3.name)
        except Exception:
            pass
    fill_result = pw_extract_result(raw_fill)
    log(f"[Captcha] Fill result: {fill_result}")

    if 'solved' in str(fill_result):
        log("[Captcha] ✅ CAPTCHA solved!")
        return True
    else:
        log(f"[Captcha] ❌ CAPTCHA solve may have failed: {fill_result}")
        return False
