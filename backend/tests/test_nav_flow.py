"""Quick test v2: verify navigate_to_section and go_back with all fixes."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import (
    load_config, cfg, log,
    pw, pw_snapshot, pw_click, pw_goto_course, pw_run_code, pw_extract_result,
    find_ref_by_text, parse_progress_from_snapshot,
)

config = load_config()
course = config["courses"][1]  # 大学物理ABC（下）

log("=== Step 1: Open course and navigate to 章节 ===")
pw_goto_course(course["courseid"], course["clazzid"], course.get("cpi", "415409200"))
time.sleep(3)

snap = pw_snapshot()
chapter_ref = find_ref_by_text(snap, "章节")
if chapter_ref:
    log(f"Clicking 章节 (ref={chapter_ref})")
    pw_click(chapter_ref)
    time.sleep(3)
else:
    log("Could not find 章节!", "ERROR")
    sys.exit(1)

# Take snapshot to see what sections are visible
snap = pw_snapshot()
log(f"Chapter tree loaded, checking for section links...")

# Check for any link patterns in the snapshot
import re
links = re.findall(r'link\s+"([^"]+)"', snap)
log(f"Found {len(links)} links in snapshot: {links[:20]}")

# Check progress
done, total = parse_progress_from_snapshot(snap)
log(f"Progress: {done}/{total}")

# Try navigation with a different pattern
log(f"\n=== Step 2: Navigate to first section ===")
# Get all 'a' elements and their text
js = "async (page) => { const iframe = page.frames().find(f => f.url().includes('mooc2')); if (!iframe) return 'no-iframe'; const links = await iframe.locator('a').all(); const texts = []; for (const link of links) { const text = await link.textContent(); if (text && text.trim()) texts.push(text.trim()); } return texts.slice(0,30).join(' ||| '); }"
raw = pw_run_code(js)
result = pw_extract_result(raw)
log(f"Section links in iframe: {result[:500]}")

log(f"\n=== Test complete ===")
