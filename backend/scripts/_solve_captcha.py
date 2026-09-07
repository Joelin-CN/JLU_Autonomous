"""Auto-solve Chaoxing in-page CAPTCHA via DeepSeek image recognition."""
import sys
import os
import time

from chaoxing.browser.engine import pw
from chaoxing.browser.js_runner import pw_run_code_file, pw_extract_result
from chaoxing.constants import SCRIPT_DIR, TMP_DIR
from chaoxing.ai.deepseek import ask_deepseek_image, ensure_deepseek_image_ready


def detect_captcha():
    """Check if page (main or studentstudy iframe) contains a CAPTCHA. Returns is_present, captcha data."""
    js = """
    async (page) => {
        // Check main page first (e.g. antispiderShowVerify.ac), then iframe
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
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=str(TMP_DIR), encoding='utf-8')
    try:
        tmp.write(js)
        tmp.close()
        raw = pw_run_code_file(tmp.name, timeout=15)
        return pw_extract_result(raw)
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass


def solve_captcha():
    """Detect captcha, screenshot it, send to DeepSeek, fill answer."""
    import json

    # 1. Detect
    print("[Captcha] Checking for in-page CAPTCHA...")
    result_str = detect_captcha()
    print(f"[Captcha] Detection result: {result_str[:300]}")

    try:
        result = json.loads(result_str)
    except json.JSONDecodeError:
        print("[Captcha] Could not parse detection result, trying regex...")
        import re
        if '操作异常' in result_str or '验证码' in result_str:
            print("[Captcha] CAPTCHA text found but JSON parsing failed")
        return False

    if not result.get('captcha'):
        print("[Captcha] No CAPTCHA detected on page")
        return True  # Nothing to solve

    img_box = result.get('imgBox')
    if not img_box:
        print("[Captcha] CAPTCHA text found but no image box located")
        return False

    # 2. Extract CAPTCHA image — try DOM fetch first, fallback to screenshot
    from chaoxing.session import _get_active_session as _gs
    session = _gs()
    suffix = f"_{session}" if session and session != "chaoxing-chrome" else ""
    captcha_path = os.path.join(SCRIPT_DIR, f'_captcha_img{suffix}.png')
    for f in [captcha_path]:
        try:
            os.unlink(f)
        except:
            pass

    # Try DOM-based extraction (download img src directly — preserves original quality)
    # Check both main page and studentstudy iframe
    js_extract = """
    async (page) => {
        // Try main page first, then mooc iframe
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
        // Fallback: screenshot on main page
        return 'fallback';
    }
    """
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=str(TMP_DIR), encoding='utf-8')
    try:
        tmp.write(js_extract)
        tmp.close()
        raw_result = pw_run_code_file(tmp.name, timeout=15)
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass

    img_data = pw_extract_result(raw_result)
    if img_data and isinstance(img_data, str) and img_data.startswith('data:image/'):
        import base64 as _b64
        try:
            _, b64_data = img_data.split(',', 1)
            with open(captcha_path, 'wb') as f:
                f.write(_b64.b64decode(b64_data))
            print(f"[Captcha] DOM-extracted: {len(b64_data)} bytes base64 → {os.path.getsize(captcha_path)} bytes PNG")
        except Exception as e:
            print(f"[Captcha] Base64 decode failed: {e}")
    else:
        # Fallback: use old screenshot approach with known coordinates
        print(f"[Captcha] DOM extraction returned: {str(img_data)[:100]}, using screenshot fallback...")
        js_screenshot = f"""
        async (page) => {{
            await page.screenshot({{
                path: '{captcha_path.replace(chr(92), '/')}',
                clip: {{x: {img_box['x']}, y: {img_box['y']}, width: {img_box['width']}, height: {img_box['height']}}}
            }});
            return 'ok';
        }}
        """
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=str(TMP_DIR), encoding='utf-8')
        try:
            tmp.write(js_screenshot)
            tmp.close()
            pw_run_code_file(tmp.name, timeout=15)
        finally:
            try: os.unlink(tmp.name)
            except Exception: pass
        if os.path.exists(captcha_path):
            print(f"[Captcha] Screenshot saved: {os.path.getsize(captcha_path)} bytes")

    if not os.path.exists(captcha_path) or os.path.getsize(captcha_path) < 100:
        print("[Captcha] Failed to extract CAPTCHA image")
        return False

    # 3. Send to DeepSeek image mode for recognition
    print("[Captcha] Asking DeepSeek to read CAPTCHA text...")
    # ask_deepseek_image() already calls ensure_deepseek_image_ready() internally
    prompt = "请识别图片中的验证码文字。只返回验证码文字本身，不要其他任何内容。"
    raw_answer = ask_deepseek_image([captcha_path], prompt, timeout=120)
    print(f"[Captcha] DeepSeek raw: {raw_answer[:200]}")

    # 4. Extract the answer text — aggressively clean noise then regex
    import re as _re
    answer = None
    cleaned = raw_answer
    for noise in ['请识别图片中的文字', '只返回文字本身', '不要其他任何内容',
                  '请识别图片中的验证码文字', '识别', '识图模式',
                  '深度思考', '内容由 AI 生成，请仔细甄别']:
        cleaned = cleaned.replace(noise, '')
    cleaned = _re.sub(r'\s+', '', cleaned)

    # Longest-first to avoid truncation: {4} before {5} would match
    # "HpZ7z" as "HpZ7" and stop, never reaching the correct {5} pattern.
    captcha_patterns = [
        r'([A-Za-z0-9]{6})',   # 6-char
        r'([A-Za-z0-9]{5})',   # 5-char
        r'([A-Za-z0-9]{4})',   # 4-char
        r'([A-Za-z0-9]{3})',   # 3-char
    ]
    for pat in captcha_patterns:
        m = _re.search(pat, cleaned)
        if m:
            answer = m.group(1)
            break

    # Space-tolerant fallback (longer combos first to avoid truncation)
    if not answer:
        for pat in [r'([A-Za-z0-9]{2,3})\s*([A-Za-z0-9]{2,3})',
                    r'([A-Za-z0-9]{2})\s*([A-Za-z0-9]{1,2})',
                    r'([A-Za-z0-9]{1,2})\s*([A-Za-z0-9]{2,3})']:
            m = _re.search(pat, raw_answer)
            if m:
                answer = m.group(1) + m.group(2)
                break

    # Last resort
    if not answer:
        stripped = _re.sub(r'\s+', '', raw_answer.strip().strip('"').strip("'"))
        m2 = _re.search(r'[A-Za-z0-9]{3,6}', stripped)
        if m2:
            answer = m2.group(0)

    print(f"[Captcha] Extracted answer: '{answer}'")

    # 5. Fill the answer and submit (check main page first, then iframe)
    js_fill = f"""
    async (page) => {{
        // Try main page first, then mooc iframe
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
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, dir=str(TMP_DIR), encoding='utf-8')
    try:
        tmp.write(js_fill)
        tmp.close()
        raw_fill = pw_run_code_file(tmp.name, timeout=15)
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass
    fill_result = pw_extract_result(raw_fill)
    print(f"[Captcha] Fill result: {fill_result}")

    if 'solved' in str(fill_result):
        print("[Captcha] ✅ CAPTCHA solved!")
        return True
    else:
        print(f"[Captcha] ❌ CAPTCHA solve may have failed: {fill_result}")
        return False


if __name__ == '__main__':
    success = solve_captcha()
    sys.exit(0 if success else 1)
