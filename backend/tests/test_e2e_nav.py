"""End-to-end test: navigate to section, go back, navigate to another."""
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

# Step 1: Open course and click 章节
log("=== 1. Open course and click 章节 ===")
pw_goto_course(course["courseid"], course["clazzid"], course.get("cpi", "415409200"))
time.sleep(3)
snap = pw_snapshot()
ref = find_ref_by_text(snap, "章节")
if ref:
    pw_click(ref)
    time.sleep(3)
else:
    log("ERROR: 章节 not found"); sys.exit(1)

done, total = parse_progress_from_snapshot(pw_snapshot())
log(f"Initial progress: {done}/{total}")

# Step 2: Navigate to section 1.1 (single-line JS via pw_extract_result)
log("\n=== 2. Navigate to section 1.1 ===")
js_nav = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); for (const link of links) { const text = await link.textContent(); if (text && text.trim().startsWith('1.1')) { await link.click(); page.waitForTimeout(1000); return 'clicked:' + text.trim(); } } return 'not-found'; }"
raw = pw_run_code(js_nav)
result = pw_extract_result(raw)
log(f"Navigate to 1.1: {result}")

if not result.startswith("clicked:"):
    log(f"FAIL: Could not navigate to 1.1 (got: {result})")
    sys.exit(1)

time.sleep(3)
log("Navigated to section 1.1 successfully!")

# Step 3: Go back via history.back()
log("\n=== 3. Go back to chapter tree ===")
js_back = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (iframe) { await iframe.evaluate(() => { window.history.back(); }); return 'back-ok'; } return 'no-iframe'; }"
raw = pw_run_code(js_back)
result = pw_extract_result(raw)
log(f"Go back result: {result}")
time.sleep(2)

# Step 4: Verify we're back and navigate to section 1.2
log("\n=== 4. Navigate to section 1.2 (verify chapter tree is back) ===")
js_nav2 = "async (page) => { const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); for (const link of links) { const text = await link.textContent(); if (text && text.trim().startsWith('1.2')) { await link.click(); page.waitForTimeout(1000); return 'clicked:' + text.trim(); } } return 'not-found'; }"
raw = pw_run_code(js_nav2)
result = pw_extract_result(raw)
log(f"Navigate to 1.2: {result}")

if result.startswith("clicked:"):
    log("\n✅ ALL TESTS PASSED!")
else:
    log(f"\n❌ FAIL: Could not navigate to 1.2 after goBack (got: {result})")
