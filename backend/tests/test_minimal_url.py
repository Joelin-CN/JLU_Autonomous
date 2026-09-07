"""Test: minimal studentcourse URL works for reloading chapter tree."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import (
    load_config, log,
    pw_snapshot, pw_click, pw_goto_course, pw_run_code, pw_extract_result,
    find_ref_by_text,
)

config = load_config()
course = config["courses"][1]
courseid = course["courseid"]
clazzid = course["clazzid"]
cpi = course.get("cpi", "415409200")

# Setup: open course, click 章节, navigate to 1.1
log("=== Setup ===")
pw_goto_course(courseid, clazzid, cpi)
time.sleep(3)
snap = pw_snapshot()
pw_click(find_ref_by_text(snap, "章节"))
time.sleep(3)

js_nav = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); for (const link of links) { const text = await link.textContent(); if (text && text.trim().startsWith('1.1')) { await link.click(); await page.waitForTimeout(1500); return 'clicked:' + text.trim(); } } return 'not-found'; }"
raw = pw_run_code(js_nav)
log(f"Nav 1.1: {pw_extract_result(raw)}")
time.sleep(2)

# Test minimal URL
log("\n=== Test: iframe.goto with minimal URL ===")
minimal_url = f"https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse?courseid={courseid}&clazzid={clazzid}&cpi={cpi}&pageHeader=0"
js_goto = f"async (page) => {{ const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; await iframe.goto('{minimal_url}'); return 'goto-ok'; }}"
raw = pw_run_code(js_goto)
result = pw_extract_result(raw)
log(f"iframe.goto: {result}")
time.sleep(3)

# Check section links
js_links = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); const texts = []; for (const link of links) { const t = (await link.textContent() || '').trim(); if (t && /^\\d+\\.\\d+/.test(t)) texts.push(t); } return texts.slice(0,5).join(' | ') || 'no-section-links'; }"
raw = pw_run_code(js_links)
result = pw_extract_result(raw)
log(f"Section links: {result}")

if "no-section-links" in result or not result:
    log("FAIL: Minimal URL didn't load chapter tree!", "ERROR")
else:
    log("SUCCESS: Minimal URL works for reloading chapter tree!", "OK")
