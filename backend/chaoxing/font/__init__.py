"""Font decryption — Chaoxing font-cxsecret obfuscation handling.

Uses Typr.js + MD5 via JS injection to decrypt glyph-level text obfuscation,
backed by a 355 KB glyph-to-character mapping table (_table.json).
"""

import json as _json
import tempfile as _tmp
import os as _os

from ..constants import SCRIPT_DIR, TMP_DIR
from ..logging_setup import log
from ..session import _get_tls
from ..browser.js_runner import pw_run_code_file, pw_extract_result

# Cached table.json content (loaded once per process)
_TABLE_JSON: str = None


def _load_table_json() -> str:
    """Load the table.json glyph->character mapping (cached)."""
    global _TABLE_JSON
    if _TABLE_JSON is None:
        table_path = SCRIPT_DIR / "_table.json"
        if not table_path.exists():
            log("table.json not found at " + str(table_path), "WARN")
            return "{}"
        _TABLE_JSON = table_path.read_text(encoding="utf-8").strip()
        log(f"Loaded table.json: {len(_TABLE_JSON)} chars")
    return _TABLE_JSON


def ensure_font_decrypt_loaded() -> bool:
    """Inject the font-cxsecret decryption JS into the chaoxing page.

    Call once before using decrypt_font_cxsecret().
    Returns True if the JS was loaded successfully.
    """
    tls = _get_tls()
    if tls.font_decrypt_loaded:
        return True

    decrypt_js_path = SCRIPT_DIR / "_decrypt_font.js"
    if not decrypt_js_path.exists():
        log("_decrypt_font.js not found", "ERROR")
        return False

    # Run the JS file to inject Typr.js + md5 + decrypt into page context
    raw = pw_run_code_file(str(decrypt_js_path), timeout=30)
    _res = pw_extract_result(raw)
    # The JS file doesn't return anything meaningful; the function is on window
    tls.font_decrypt_loaded = True
    log("Font decryption JS loaded into page", "OK")
    return True


def decrypt_font_cxsecret(iframe_doc_js: str = None) -> dict:
    """Decrypt font-cxsecret obfuscation in the quiz iframe.

    Returns {ok: true, decrypted: N} or {ok: false, reason: "..."}.
    Call ensure_font_decrypt_loaded() first.
    """
    table_json_str = _load_table_json()
    if table_json_str == "{}":
        return {"ok": False, "reason": "no-table-json"}

    # Use JSON.stringify to avoid escaping issues
    table_json_escaped = _json.dumps(table_json_str)

    js = f"""
    async (page) => {{
        // Find quiz iframe with .font-cxsecret elements
        const candidates = page.frames().filter(f =>
            f !== page.mainFrame() &&
            (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
             f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
        );
        if (candidates.length === 0) return JSON.stringify({{ok: false, reason: 'no-quiz-iframe'}});

        let result = {{ok: false, reason: 'no-cxsecret-found'}};
        for (const iframe of candidates) {{
            try {{
                const hasCxsecret = await iframe.locator('.font-cxsecret').count();
                if (hasCxsecret > 0) {{
                    const tableJsonStr = {table_json_escaped};
                    result = await iframe.evaluate((tableJsonStr) => {{
                        if (typeof window._cxDecryptFont !== 'function') {{
                            return {{ok: false, reason: 'decrypt-func-not-loaded'}};
                        }}
                        return window._cxDecryptFont(document, tableJsonStr);
                    }}, tableJsonStr);
                    break;
                }}
            }} catch(e) {{
                result = {{ok: false, reason: 'error:' + e.message}};
            }}
        }}
        return JSON.stringify(result);
    }}
    """
    tmp = _tmp.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
    tmp.write(js)
    tmp.close()
    try:
        raw = pw_run_code_file(tmp.name, timeout=60)
        extracted = pw_extract_result(raw)
        return _json.loads(extracted)
    except Exception as e:
        return {"ok": False, "reason": f"error:{e}"}
    finally:
        try:
            _os.unlink(tmp.name)
        except Exception:
            pass


def get_decrypted_quiz_text() -> str:
    """Decrypt font obfuscation and return clean text from the quiz iframe.

    This enables Doubao TEXT mode (faster, cheaper) instead of image mode.
    Returns empty string on failure.
    """
    if not ensure_font_decrypt_loaded():
        return ""

    result = decrypt_font_cxsecret()
    if not result.get("ok"):
        log(f"Font decrypt failed: {result.get('reason', '?')}", "WARN")
        return ""

    decrypted_count = result.get("decrypted", 0)
    log(f"Font decrypted {decrypted_count} elements", "OK")

    # Now extract clean text from the page
    js = """
    async (page) => {
        const candidates = page.frames().filter(f =>
            f !== page.mainFrame() &&
            (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
             f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
        );
        if (candidates.length === 0) return '';
        // Return clean text from the first quiz iframe
        const bt = await candidates[0].locator('body').innerText();
        return bt;
    }
    """
    tmp = _tmp.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False, encoding='utf-8', dir=str(TMP_DIR))
    tmp.write(js)
    tmp.close()
    try:
        raw = pw_run_code_file(tmp.name, timeout=15)
        return pw_extract_result(raw)
    except Exception:
        return ""
    finally:
        try:
            _os.unlink(tmp.name)
        except Exception:
            pass
