"""Quick test for navigate_to_section JS."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import pw_run_code, pw_goto_course, pw_click, pw_snapshot, find_ref_by_text, load_config

config = load_config()
course = config["courses"][0]  # 概率论与数理统计

# Navigate to course
print("Navigating to course...")
pw_goto_course(course["courseid"], course["clazzid"], course.get("cpi", "415409200"))
time.sleep(3)

# Click 章节 tab
snap = pw_snapshot()
ref = find_ref_by_text(snap, "章节")
if ref:
    print(f"Clicking 章节 (ref={ref})...")
    pw_click(ref)
    time.sleep(3)

# Now test the JS
section_num = "1.6"
js = f"""
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
print(f"JS first 200 chars: {repr(js[:200])}")
print()
result = pw_run_code(js)
print(f"RESULT: {repr(result)}")
