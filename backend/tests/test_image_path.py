"""
Diagnostic v4: verify multi-iframe iteration works.
"""
import sys, os, time, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from utils import (load_config, log, pw_snapshot, pw_click, pw_goto_course,
                   pw_run_code_file, pw_extract_result, find_ref_by_text)

def run_js(js: str) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False,
                                       dir=os.path.dirname(__file__), encoding="utf-8")
    try:
        tmp.write(js)
        tmp.close()
        return pw_extract_result(pw_run_code_file(tmp.name, timeout=20))
    finally:
        try: os.unlink(tmp.name)
        except: pass

def main():
    config = load_config()
    course = next(c for c in config["courses"] if c["name"] == "概率论与数理统计")
    section = course["remaining_quiz_sections"][0]

    log(f"=== Diagnostic v4: {section['section']} {section['name']} ===")

    pw_goto_course(course["courseid"], course["clazzid"], course.get("cpi", "415409200"))
    time.sleep(3)
    ref = find_ref_by_text(pw_snapshot(), "章节")
    if ref: pw_click(ref); time.sleep(2)

    result = run_js(f"""
async (page) => {{
    const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2'));
    if (!iframe) return 'no-iframe';
    const links = await iframe.locator('a').all();
    for (const link of links) {{
        const text = await link.textContent();
        if (text && text.includes('{section["section"]}')) {{
            await link.click();
            return 'clicked:' + text.trim();
        }}
    }}
    return 'not-found';
}}
""")
    log(f"  Navigate: {result}")
    if not result.startswith("clicked:"): return
    time.sleep(4)

    # Use the FIXED multi-iframe logic
    find_js = """
async (page) => {
    const candidates = page.frames().filter(f =>
        f !== page.mainFrame() &&
        (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
         f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
    );
    if (candidates.length === 0) return JSON.stringify({error: 'no-iframe'});

    // PRIMARY: find 题号 elements (.newZy_TItle / .Zy_TItle) as question boundaries
    let titleBoxes = [];
    let contentBottom = 0;
    let usedIframe = '';

    for (const iframe of candidates) {
        const urlShort = iframe.url().substring(0, 100);
        try {
            const titleEls = iframe.locator('.newZy_TItle, .Zy_TItle');
            const titleCount = await titleEls.count();
            if (titleCount >= 1) {
                for (let i = 0; i < titleCount; i++) {
                    try {
                        const box = await titleEls.nth(i).boundingBox();
                        if (box && box.width > 30 && box.height > 10) {
                            titleBoxes.push({
                                y: Math.round(box.y), h: Math.round(box.height),
                                x: Math.round(box.x), w: Math.round(box.width),
                            });
                        }
                    } catch(e) {}
                }
                if (titleBoxes.length > 0) usedIframe = urlShort;
            }
        } catch(e) {}
        // Content bottom for last question
        try {
            const bottomEls = iframe.locator('.Zy_ulTop, .TiMu, .newTiMu');
            const bc = await bottomEls.count();
            if (bc > 0) {
                const lb = await bottomEls.nth(bc - 1).boundingBox();
                if (lb) contentBottom = Math.round(lb.y + lb.height);
            }
        } catch(e) {}
        if (titleBoxes.length > 0) break;
    }

    // Fallback: container selectors
    if (titleBoxes.length === 0) {
        for (const iframe of candidates) {
            for (const sel of ['.Zy_ulTop', '.TiMu', '.newTiMu', '.questionDiv']) {
                try {
                    const els = iframe.locator(sel);
                    const c = await els.count();
                    if (c >= 1) {
                        for (let i = 0; i < c; i++) {
                            const box = await els.nth(i).boundingBox();
                            if (box && box.width > 100 && box.height > 30) {
                                titleBoxes.push({
                                    y: Math.round(box.y), h: Math.round(box.height),
                                    x: Math.round(box.x), w: Math.round(box.width),
                                });
                            }
                        }
                        if (titleBoxes.length > 0) { usedIframe = iframe.url().substring(0, 100); break; }
                    }
                } catch(e) {}
            }
            if (titleBoxes.length > 0) break;
        }
    }

    if (titleBoxes.length === 0) return JSON.stringify({error: 'no-questions-found'});

    titleBoxes.sort((a, b) => a.y - b.y);

    // Deduplicate by Y position: elements within 10px vertically belong to same question
    let merged = [];
    for (const tb of titleBoxes) {
        const last = merged[merged.length - 1];
        if (last && Math.abs(tb.y - last.y) <= 10) {
            // Same question — keep the one with smaller Y (higher up)
            if (tb.y < last.y) { last.y = tb.y; last.x = tb.x; last.w = tb.w; last.h = tb.h; }
        } else {
            merged.push({...tb});
        }
    }
    titleBoxes = merged;

    // Build question boundaries
    let questions = [];
    for (let i = 0; i < titleBoxes.length; i++) {
        const startY = titleBoxes[i].y;
        const endY = (i + 1 < titleBoxes.length) ? titleBoxes[i + 1].y - 4
                     : Math.max(startY + 200, contentBottom + 12);
        questions.push({index: i+1, startY, endY});
    }

    return JSON.stringify({
        ok: true, count: questions.length, iframe: usedIframe,
        sampleQ: questions[0],
        totalQ: questions.length,
    });
}
"""
    result2 = run_js(find_js)
    log(f"  Finder: {result2[:600]}")

    try:
        parsed = json.loads(result2)
        if parsed.get("ok"):
            log(f"  ✅ Found {parsed['count']} questions in iframe: {parsed.get('iframe','?')}", "OK")
            if parsed.get("sampleQ"):
                sq = parsed["sampleQ"]
                log(f"    Sample Q{sq['index']}: startY={sq['startY']}, endY={sq['endY']}")

            # Screenshot Q1 using 题号-based clip — write JS to temp file to avoid f-string escaping
            q_path = os.path.join(os.path.dirname(__file__), '_test_q1.png')
            ss_js = """async (page) => {
                const candidates = page.frames().filter(f =>
                    f !== page.mainFrame() &&
                    (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
                     f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
                );
                if (candidates.length === 0) return 'no-candidates';

                // Find quiz iframe and title elements
                let titleBoxes = [];
                let quizIframe = null;
                for (const iframe of candidates) {
                    try {
                        const els = iframe.locator('.newZy_TItle, .Zy_TItle');
                        const c = await els.count();
                        if (c > 0) {
                            for (let i = 0; i < c; i++) {
                                const b = await els.nth(i).boundingBox();
                                if (b && b.width > 30) {
                                    titleBoxes.push({y: b.y, x: b.x, w: b.width, h: b.height});
                                }
                            }
                            quizIframe = iframe;
                            break;
                        }
                    } catch(e) {}
                }
                if (titleBoxes.length === 0) return 'no-title-elements';

                // Deduplicate by Y position
                titleBoxes.sort((a, b) => a.y - b.y);
                let merged = [];
                for (const tb of titleBoxes) {
                    const last = merged[merged.length - 1];
                    if (last && Math.abs(tb.y - last.y) <= 10) {
                        if (tb.y < last.y) { last.y = tb.y; last.x = tb.x; last.w = tb.w; last.h = tb.h; }
                    } else {
                        merged.push({y: tb.y, x: tb.x, w: tb.w, h: tb.h});
                    }
                }
                titleBoxes = merged;

                // Determine boundaries
                const startY = titleBoxes[0].y;
                const endY = titleBoxes.length > 1 ? (titleBoxes[1].y - 4) : (startY + 600);

                // Scroll the quiz's first title into view
                const titleEls = quizIframe.locator('.newZy_TItle, .Zy_TItle');
                const titleCount = await titleEls.count();
                if (titleCount === 0) return 'no-title-after';
                await titleEls.nth(0).scrollIntoViewIfNeeded();
                await page.waitForTimeout(300);

                // Get fresh bounding box
                const sb = await titleEls.nth(0).boundingBox();
                if (!sb) return 'null-bbox';
                if (!sb.height) return 'zero-height';

                // viewportSize() returns null for headed persistent Chrome — use window dimensions instead
                const vw = (await page.evaluate(() => window.innerWidth)) || 1280;
                const vh = (await page.evaluate(() => window.innerHeight)) || 900;
                const pad = 10;
                const clipY = Math.max(0, sb.y - pad);
                const clipH = Math.min(endY - sb.y + pad * 2, vh - clipY);
                const clip = {
                    x: Math.max(0, sb.x - pad),
                    y: clipY,
                    width: Math.min(vw - sb.x + pad, sb.width + pad * 2 + 200),
                    height: clipH
                };
                const outPath = """ + json.dumps(q_path) + """;
                await page.screenshot({path: outPath, clip});
                return 'ok';
            }"""
            ss_result = run_js(ss_js)
            if os.path.exists(q_path):
                log(f"  ✅ Q1 screenshot saved: {os.path.getsize(q_path)/1024:.1f} KB", "OK")
                log(f"     Check _test_q1.png — it should show the FULL question (题号+题型+题目+所有选项)")
            else:
                log(f"  Screenshot failed: {ss_result}", "WARN")
        else:
            log(f"  ❌ {parsed.get('error')}", "ERROR")
    except json.JSONDecodeError:
        log(f"  ❌ Parse error: {result2[:200]}", "ERROR")

if __name__ == "__main__":
    main()
