"""Debug: what happens after history.back() in the iframe?"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import (
    load_config, log,
    pw_snapshot, pw_click, pw_goto_course, pw_run_code, pw_extract_result,
    find_ref_by_text, parse_progress_from_snapshot,
)

config = load_config()
course = config["courses"][1]  # 大学物理ABC（下）

# Open course, click 章节
log("=== 1. Setup ===")
pw_goto_course(course["courseid"], course["clazzid"], course.get("cpi", "415409200"))
time.sleep(3)
snap = pw_snapshot()
ref = find_ref_by_text(snap, "章节")
pw_click(ref)
time.sleep(3)

# Navigate to 1.1
log("=== 2. Navigate to 1.1 ===")
js_nav = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); for (const link of links) { const text = await link.textContent(); if (text && text.trim().startsWith('1.1')) { await link.click(); await page.waitForTimeout(1000); return 'clicked:' + text.trim(); } } return 'not-found'; }"
raw = pw_run_code(js_nav)
result = pw_extract_result(raw)
log(f"Nav 1.1: {result}")
time.sleep(2)

# Check iframe URL after navigation
js_url = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); return iframe ? iframe.url().substring(0,100) : 'no-iframe'; }"
raw = pw_run_code(js_url)
log(f"After nav - iframe URL: {pw_extract_result(raw)}")

# Go back
log("=== 3. Go back ===")
js_back = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (iframe) { await iframe.evaluate(() => { window.history.back(); }); return 'back-ok'; } return 'no-iframe'; }"
raw = pw_run_code(js_back)
result = pw_extract_result(raw)
log(f"GoBack: {result}")
time.sleep(3)

# Check iframe URL after goback
raw = pw_run_code(js_url)
log(f"After back - iframe URL: {pw_extract_result(raw)}")

# Check available links in the iframe
js_links = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); const texts = []; for (const link of links) { const t = (await link.textContent() || '').trim(); if (t && /^\\d+\\.\\d+/.test(t)) texts.push(t); } return texts.join(' | ') || 'no-section-links'; }"
raw = pw_run_code(js_links)
result = pw_extract_result(raw)
log(f"Section links after back: {result[:300]}")

# Try clicking 章节 again
log("=== 4. Re-click 章节 ===")
snap = pw_snapshot()
ref = find_ref_by_text(snap, "章节")
if ref:
    pw_click(ref)
    time.sleep(3)
    raw = pw_run_code(js_links)
    result = pw_extract_result(raw)
    log(f"Section links after re-clicking 章节: {result[:300]}")
else:
    log("Could not find 章节 ref")

# Try navigating to 1.2
log("=== 5. Navigate to 1.2 ===")
js_nav2 = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); for (const link of links) { const text = await link.textContent(); if (text && text.trim().startsWith('1.2')) { await link.click(); await page.waitForTimeout(1000); return 'clicked:' + text.trim(); } } return 'not-found'; }"
raw = pw_run_code(js_nav2)
result = pw_extract_result(raw)
log(f"Nav 1.2: {result}")
