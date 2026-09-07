"""Test: navigate iframe directly to chapter tree URL."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import (
    load_config, log,
    pw_snapshot, pw_click, pw_goto_course, pw_run_code, pw_extract_result,
    find_ref_by_text,
)

config = load_config()
course = config["courses"][1]  # 大学物理ABC（下）
courseid = course["courseid"]
clazzid = course["clazzid"]

# Step 1: Open course, note initial iframe URL
log("=== 1. Open course (before clicking 章节) ===")
pw_goto_course(courseid, clazzid, course.get("cpi", "415409200"))
time.sleep(3)

js_url = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); return iframe ? iframe.url() : 'no-iframe'; }"
raw = pw_run_code(js_url)
initial_url = pw_extract_result(raw)
log(f"Initial iframe URL: {initial_url[:150]}")

# Step 2: Click 章节, note the chapter tree URL
log("\n=== 2. Click 章节 ===")
snap = pw_snapshot()
ref = find_ref_by_text(snap, "章节")
pw_click(ref)
time.sleep(4)

raw = pw_run_code(js_url)
chapter_url = pw_extract_result(raw)
log(f"Chapter tree iframe URL: {chapter_url[:150]}")

# Step 3: Navigate to section 1.1
log("\n=== 3. Navigate to section 1.1 ===")
js_nav = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); for (const link of links) { const text = await link.textContent(); if (text && text.trim().startsWith('1.1')) { await link.click(); await page.waitForTimeout(1500); return 'clicked:' + text.trim(); } } return 'not-found'; }"
raw = pw_run_code(js_nav)
result = pw_extract_result(raw)
log(f"Nav to 1.1: {result}")
time.sleep(2)

raw = pw_run_code(js_url)
after_nav_url = pw_extract_result(raw)
log(f"Section iframe URL: {after_nav_url[:150]}")

# Step 4: Navigate iframe back to chapter tree URL using iframe.goto()
log("\n=== 4. iframe.goto(chapter_tree_url) ===")
# Extract the studentcourse base URL from the chapter_url
# The chapter_url is something like: https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse?courseid=...&...
# Build the URL from courseid/clazzid
chapter_base_url = f"https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse?courseid={courseid}&clazzid={clazzid}&pageHeader=0"
js_goto = f"async (page) => {{ const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; await iframe.goto('{chapter_base_url}'); return 'goto-ok'; }}"
raw = pw_run_code(js_goto)
result = pw_extract_result(raw)
log(f"iframe.goto: {result}")
time.sleep(4)

# Check if section links are back
js_links = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); const texts = []; for (const link of links) { const t = (await link.textContent() || '').trim(); if (t && /^\\d+\\.\\d+/.test(t)) texts.push(t); } return texts.join(' | ') || 'no-section-links'; }"
raw = pw_run_code(js_links)
result = pw_extract_result(raw)
log(f"Section links: {result[:300]}")

# Step 5: Navigate to 1.2
log("\n=== 5. Navigate to 1.2 ===")
js_nav2 = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); for (const link of links) { const text = await link.textContent(); if (text && text.trim().startsWith('1.2')) { await link.click(); await page.waitForTimeout(1500); return 'clicked:' + text.trim(); } } return 'not-found'; }"
raw = pw_run_code(js_nav2)
result = pw_extract_result(raw)
log(f"Nav to 1.2: {result}")
