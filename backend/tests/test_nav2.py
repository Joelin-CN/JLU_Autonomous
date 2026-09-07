"""Test if stripping newlines fixes the JS syntax error."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import pw, pw_click, pw_snapshot, find_ref_by_text, cfg

section_num = "1.6"

# Multi-line version (original - expected to fail)
js_multiline = f"""
async (page) => {{
    const iframe = page.frames().find(f => f.url().includes('mooc2'));
    if (!iframe) return 'no-iframe';
    const links = await iframe.locator('a').all();
    for (const link of links) {{
        const text = await link.textContent();
        if (text && text.includes('{section_num}')) {{
            await link.click();
            return 'clicked:' + text.trim();
        }}
    }}
    return 'not-found';
}}
"""

# Single-line version
js_single = f"async (page) => {{ const iframe = page.frames().find(f => f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); for (const link of links) {{ const text = await link.textContent(); if (text && text.includes('{section_num}')) {{ await link.click(); return 'clicked:' + text.trim(); }} }} return 'not-found'; }}"

print("=== Test 1: Multi-line JS ===")
print(f"JS repr (first 200): {repr(js_multiline[:200])}")
result = pw("run-code", js_multiline, timeout=20)
print(f"RESULT: {repr(result[:200])}")

print()
print("=== Test 2: Single-line JS ===")
print(f"JS repr (first 200): {repr(js_single[:200])}")
result = pw("run-code", js_single, timeout=20)
print(f"RESULT: {repr(result[:200])}")
