"""
Chapter Quiz Auto-Solver — main facade that orchestrates the 5-tier fallback chain.

Handles: opening course, navigating to sections, extracting questions, solving via
AI (5 strategies), filling answers, submitting, retrying, grading, and stats.

Primary target: 概率论与数理统计 (16 quizzes, 100% target score each).
"""

import time
import math
import os
import random
from pathlib import Path

from core.constants import TMP_DIR
from core.config import load_config, cfg
from core.exceptions import ConfigError
from core.logging_setup import log, check_signals
from core.session import _get_active_session
from core.browser.engine import pw, pw_snapshot, pw_run_code
from core.browser.js_runner import pw_run_code_file, pw_extract_result
from core.browser.viewport import ensure_chaoxing_viewport
from ...platform.navigation import pw_goto_course
from ..content.navigator import _click_chapter_tab
from core.tracking import ProgressTracker
from core.ai.router import ai_solve_quiz, ai_solve_quiz_image
from ...font import get_decrypted_quiz_text
from core.utils import human_delay

from .stats import QuizStats
from .extractor import (
    extract_questions_from_snapshot,
    _clean_snapshot,
    count_questions_in_text,
    count_questions_in_snapshot,
)
from .strategies import (
    FontDecryptTextStrategy,
    V2ScreenshotStrategy,
    V1ScreenshotStrategy,
    FullPageScreenshotStrategy,
    SnapshotTextStrategy,
    STRATEGY_CHAIN,
)
from .filler import (
    _fill_answers,
    _click_option,
    _click_option_dom,
    _fill_blank,
    _is_unanswerable,
    _detect_question_types,
    UNANSWERABLE_MARKERS,
)
from .submitter import _submit_quiz, _submit_quiz_native, _parse_score
from .grader import (
    _capture_filled_screenshots_v2,
    _grade_batched,
    _parse_correct_answers,
)
from .retry import _retry_quiz


class ChapterQuizSolver:
    """Automate solving chapter quizzes (章节测试) for a specific course."""

    # Phase C: accuracy threshold for grade-only pass/fail decision
    GRADE_PASS_THRESHOLD = 80  # Percentage

    # AI markers indicating an unanswerable question (skip filling, count as uncertain)
    UNANSWERABLE_MARKERS = UNANSWERABLE_MARKERS

    def __init__(self, course_config: dict, dry_run: bool = False,
                 grade_only: bool = False):
        self.course = course_config
        self.name = course_config["name"]
        self.courseid = course_config["courseid"]
        self.clazzid = course_config["clazzid"]
        self.cpi = course_config.get("cpi", "415409200")
        self.dry_run = dry_run
        self.grade_only = grade_only  # Phase C: fill answers, screenshot, grade via Doubao, skip submit
        self.tracker = ProgressTracker()
        self.stats = {"solved": 0, "failed": 0, "retried": 0}
        # Engine functions resolved at quiz start; see solve()._get_ai_solver.
        self._quiz_engine_fns = None
        self.quiz_stats = QuizStats(self.name)  # Accuracy tracking

    # ── AI Solver Provider Selector ──────────────────────────

    def _get_ai_solver(self):
        """Return (solve_text_fn, solve_image_fn) based on ai.provider config.

        Reads cfg("ai.provider") at each call -- no caching -- so runtime
        config changes take effect on the next quiz without restart.
        The router functions (ai_solve_quiz, ai_solve_quiz_image) internally
        dispatch to the configured provider, so we just return them directly.

        Returns:
            tuple of (text_solve_fn, image_solve_fn).
        """
        provider = cfg("ai.provider", "doubao-api")
        # Mirror the router's registry — the router is the single source of
        # truth for valid provider ids.
        from core.ai.doubao import _PROVIDERS
        if provider not in _PROVIDERS:
            raise ConfigError(f"Unknown AI provider: {provider}")
        return ai_solve_quiz, ai_solve_quiz_image

    # ── Navigation ────────────────────────────────────────

    def open_course(self):
        """Navigate to course page and click 章节 tab."""
        import tempfile as _tf2

        log(f"Opening course: {self.name}")
        pw_goto_course(self.courseid, self.clazzid, self.cpi)
        time.sleep(2)

        # Click 章节 in sidebar via JS (pw_click ref approach unreliable for this element)
        js_click_chapter = """
        async (page) => {
            const links = await page.locator('a, li, [role="tab"], [role="menuitem"]').all();
            let found = null;
            for (const link of links) {
                try {
                    const text = await link.textContent();
                    if (text && text.trim() === '章节') {
                        found = link;
                        break;
                    }
                } catch(e) {}
            }
            if (!found) {
                const el = page.locator('text=章节').first();
                if (await el.count() > 0) found = el;
            }
            if (!found) return 'no-chapter-element';
            await found.click();
            await page.waitForTimeout(3000);
            return 'clicked';
        }
        """
        _tf = _tf2.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False,
            dir=str(TMP_DIR), encoding="utf-8"
        )
        try:
            _tf.write(js_click_chapter)
            _tf.close()
            raw = pw_run_code_file(_tf.name, timeout=20)
            result = pw_extract_result(raw)
            log(f"  Click 章节: {result}")
        finally:
            try:
                os.unlink(_tf.name)
            except Exception:
                pass
        time.sleep(2)

    def navigate_to_section(self, section_num: str) -> bool:
        """Find and click a section link in the chapter tree.
        The section is identified by its number (e.g., '1.6').
        Returns True if the section link was found and clicked.
        """
        import tempfile as _tf

        # Use run-code to find and click the section link inside the iframe
        # The iframe contains the chapter tree with links like "1.6 章节测试1"
        js = f"""
        async (page) => {{
            const iframe = page.frames().find(f =>
                f !== page.mainFrame() &&
                (f.url().includes('mooc2') || f.url().includes('studentcourse'))
            );
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
        nav_file = _tf.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False,
            dir=str(TMP_DIR), encoding="utf-8"
        )
        try:
            nav_file.write(js)
            nav_file.close()
            raw = pw_run_code_file(nav_file.name, timeout=20)
        finally:
            try:
                os.unlink(nav_file.name)
            except Exception:
                pass
        result = pw_extract_result(raw)
        log(f"  Navigate to {section_num}: {result}")
        return result.startswith("clicked:")

    def go_back_to_chapter_tree(self) -> bool:
        """Return to the chapter tree after completing/failing a quiz section.

        After clicking a section link, the main page navigates away from
        the mooc2-ans course page to mooc1 studentstudy. We must navigate
        back to the course page and click 章节 to see the chapter tree again.
        """
        js_url = "async (page) => page.url()"
        raw = pw_run_code(js_url)
        current_url = pw_extract_result(raw)

        if "studentstudy" in current_url or "mooc1.chaoxing.com" in current_url:
            log("    Returning to course page from studentstudy...")
            pw_goto_course(self.courseid, self.clazzid, self.cpi)
            time.sleep(3)

            # Click 章节 tab — canonical proven strategy (getByRole fallback).
            # The old pw_snapshot+find_ref_by_text+pw_click clicked the wrong
            # element and never reloaded the chapter-tree iframe, so every
            # navigate_to_section after the first quiz saw 'no-iframe'.
            _click_chapter_tab()
            return True

        # Still on course page -- ensure 章节 tab is active and the chapter-tree
        # iframe is (re)loaded. _click_chapter_tab is what actually brings up the
        # .../studentcourse iframe; the iframe.goto below is a secondary refresh.
        _click_chapter_tab()

        # Use lightweight iframe.goto() to refresh chapter tree
        chapter_url = (
            "https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse"
            f"?courseid={self.courseid}&clazzid={self.clazzid}"
            f"&cpi={self.cpi}&pageHeader=0"
        )
        js_goto = (
            "async (page) => {"
            " const iframe = page.frames().find(f => f !== page.mainFrame() && f.url().includes('mooc2'));"
            f" if (iframe) {{ await iframe.goto('{chapter_url}'); return 'goto-ok'; }}"
            " return 'no-iframe'; }"
        )
        raw = pw_run_code(js_goto)
        result = pw_extract_result(raw)
        time.sleep(3)
        log(f"    iframe.goto result: {result}")
        return result == "goto-ok"

    # ── Question Extraction ──────────────────────────────

    def extract_questions_from_snapshot(self, snap: str) -> list[dict]:
        """Extract quiz questions from the iframe snapshot into a clean text prompt."""
        return extract_questions_from_snapshot(snap)

    def _clean_snapshot(self, snap: str) -> str:
        """Strip ALL YAML/playwright noise from snapshot."""
        return _clean_snapshot(snap)

    # ── Screenshot Capture Methods ───────────────────────

    def _capture_question_screenshots(self) -> list[str]:
        """Screenshot EACH question individually in the quiz iframe.

        Uses .newZy_TItle / .Zy_TItle (题号) elements as question boundaries.
        Each question's screenshot starts from its 题号 element and ends at
        the next question's 题号 (or the bottom of content for the last question).

        Returns list of absolute PNG paths (empty if failed).
        """
        import json as _json
        import tempfile
        import glob as _glob

        # Ensure viewport is large enough to show complete question content
        ensure_chaoxing_viewport(2048, 1152)

        # Remove stale files (session-namespaced)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        script_dir = str(TMP_DIR)
        session = _get_active_session()
        sfx = f"_{session}" if session and session != "chaoxing-chrome" else ""
        for old in _glob.glob(os.path.join(script_dir, f'_quiz_q*{sfx}.png')):
            try:
                os.unlink(old)
            except Exception:
                pass

        # ── Step 1: Find 题号 elements and build question boundaries ──
        find_js = r"""
        async (page) => {
            const candidates = page.frames().filter(f =>
                f !== page.mainFrame() &&
                (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
                 f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
            );
            if (candidates.length === 0) return JSON.stringify({error: 'no-iframe'});

            let titleBoxes = [];
            let usedIframe = '';
            let contentBottom = 0;

            for (const iframe of candidates) {
                const urlShort = iframe.url().substring(0, 100);

                // Find 题号 elements (.newZy_TItle or .Zy_TItle)
                try {
                    const titleEls = iframe.locator('.newZy_TItle, .Zy_TItle');
                    const titleCount = await titleEls.count();
                    if (titleCount >= 1) {
                        for (let i = 0; i < titleCount; i++) {
                            try {
                                const box = await titleEls.nth(i).boundingBox();
                                if (box && box.width > 30 && box.height > 10) {
                                    titleBoxes.push({
                                        y: Math.round(box.y),
                                        h: Math.round(box.height),
                                        x: Math.round(box.x),
                                        w: Math.round(box.width),
                                    });
                                }
                            } catch(e) {}
                        }
                        if (titleBoxes.length > 0) {
                            usedIframe = urlShort;
                        }
                    }
                } catch(e) {}

                // Also get the last content element's bottom for end boundary of last Q
                try {
                    const bottomEls = iframe.locator('.Zy_ulTop, .TiMu, .newTiMu');
                    const bottomCount = await bottomEls.count();
                    if (bottomCount > 0) {
                        const lastBox = await bottomEls.nth(bottomCount - 1).boundingBox();
                        if (lastBox) {
                            contentBottom = Math.round(lastBox.y + lastBox.height);
                        }
                    }
                } catch(e) {}

                if (titleBoxes.length > 0) break;
            }

            // Fallback: no 题号 elements -- try container selectors
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
                                if (titleBoxes.length > 0) {
                                    usedIframe = iframe.url().substring(0, 100);
                                    break;
                                }
                            }
                        } catch(e) {}
                    }
                    if (titleBoxes.length > 0) break;
                }
            }

            if (titleBoxes.length === 0) return JSON.stringify({error: 'no-questions-found'});

            // Sort top-to-bottom and deduplicate by Y position
            titleBoxes.sort((a, b) => a.y - b.y);
            let merged = [];
            for (const tb of titleBoxes) {
                const last = merged[merged.length - 1];
                if (last && Math.abs(tb.y - last.y) <= 10) {
                    if (tb.y < last.y) { last.y = tb.y; last.x = tb.x; last.w = tb.w; last.h = tb.h; }
                } else {
                    merged.push({...tb});
                }
            }
            titleBoxes = merged;

            // Build question boundaries: each Q spans from its 题号 top to next 题号 top
            let questions = [];
            for (let i = 0; i < titleBoxes.length; i++) {
                const startY = titleBoxes[i].y;
                let endY;
                if (i + 1 < titleBoxes.length) {
                    endY = titleBoxes[i + 1].y - 4;
                } else {
                    endY = Math.max(startY + 200, contentBottom + 12);
                }
                questions.push({
                    index: i + 1,
                    startY: startY,
                    endY: endY,
                    titleH: titleBoxes[i].h,
                });
            }

            return JSON.stringify({
                ok: true,
                count: questions.length,
                iframe: usedIframe,
                questions: questions,
            });
        }
        """
        find_js_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False,
            dir=str(TMP_DIR), encoding="utf-8"
        )
        try:
            find_js_file.write(find_js)
            find_js_file.close()
            raw = pw_run_code_file(find_js_file.name, timeout=25)
        finally:
            try:
                os.unlink(find_js_file.name)
            except Exception:
                pass
        result_str = pw_extract_result(raw)

        try:
            result = _json.loads(result_str)
        except _json.JSONDecodeError:
            log(f"  Failed to parse question boxes: {result_str[:100]}", "WARN")
            return []

        if not result.get("ok"):
            log(f"  No question boxes found: {result.get('error', 'unknown')}", "WARN")
            return []

        questions = result.get("questions", [])
        count = len(questions)
        log(f"  Found {count} question boundaries via 题号 elements")

        # ── Step 2: Screenshot each question using title-based clip ──
        paths = []
        screenshot_js_template = r"""
        async (page) => {{
            const candidates = page.frames().filter(f =>
                f !== page.mainFrame() &&
                (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
                 f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
            );
            if (candidates.length === 0) return 'no-iframe';

            // Find the Nth 题号 element and scroll it into view
            let titleEl = null;
            for (const iframe of candidates) {{
                try {{
                    const els = iframe.locator('.newZy_TItle, .Zy_TItle');
                    const c = await els.count();
                    if (c > Q_INDEX) {{
                        titleEl = els.nth(Q_INDEX);
                        break;
                    }}
                }} catch(e) {{}}
            }}

            // Fallback: use container selectors if no 题号 elements
            if (!titleEl) {{
                for (const iframe of candidates) {{
                    for (const sel of ['.Zy_ulTop', '.TiMu', '.newTiMu', '.questionDiv']) {{
                        try {{
                            const els = iframe.locator(sel);
                            const c = await els.count();
                            if (c > Q_INDEX) {{
                                titleEl = els.nth(Q_INDEX);
                                break;
                            }}
                        }} catch(e) {{}}
                    }}
                    if (titleEl) break;
                }}
            }}
            if (!titleEl) return 'no-element';

            // Scroll the 题号 to the top of the viewport
            await titleEl.scrollIntoViewIfNeeded();
            await page.waitForTimeout(350);

            // Get fresh bounding box for start position (after scroll)
            const startBox = await titleEl.boundingBox();
            if (!startBox || startBox.width < 20 || startBox.height < 5) return 'bad-start-box';

            // Determine end Y: try next 题号, or use configured endY
            let endY = Q_ENDY;
            if (Q_INDEX + 1 < 99) {{
                // Try to find next 题号 for dynamic end boundary
                for (const iframe of candidates) {{
                    try {{
                        const els = iframe.locator('.newZy_TItle, .Zy_TItle');
                        const c = await els.count();
                        if (c > Q_INDEX + 1) {{
                            const nextBox = await els.nth(Q_INDEX + 1).boundingBox();
                            if (nextBox && nextBox.y > startBox.y + 10) {{
                                endY = Math.round(nextBox.y - 6);
                            }}
                            break;
                        }}
                    }} catch(e) {{}}
                }}
            }}

            // If endY wasn't updated dynamically, compute from start + estimate
            if (endY <= startBox.y + 20) {{
                endY = Math.round(startBox.y + 500);
            }}

            const pad = 10;
            const vw = (await page.evaluate(() => window.innerWidth)) || 1280;
            const vh = (await page.evaluate(() => window.innerHeight)) || 900;
            const clipH = Math.min(endY - startBox.y + pad * 2,
                                  vh - startBox.y + pad);
            const clip = {{
                x: Math.max(0, startBox.x - pad),
                y: Math.max(0, startBox.y - pad),
                width: Math.min(vw - startBox.x + pad,
                                startBox.width + pad * 2 + 200),
                height: clipH
            }};
            await page.screenshot({{path: Q_PATH, clip}});
            return 'ok';
        }}
        """
        for i in range(count):
            q_info = questions[i]
            q_path = _json.dumps(os.path.join(script_dir, f'_quiz_q{i+1}{sfx}.png'))
            # Use the pre-computed endY from the finder as baseline
            end_y = q_info.get("endY", q_info["startY"] + 500)

            ss_js = (screenshot_js_template
                     .replace("Q_INDEX", str(i))
                     .replace("Q_PATH", q_path)
                     .replace("Q_ENDY", str(end_y)))

            ss_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", delete=False,
                dir=str(TMP_DIR), encoding="utf-8"
            )
            try:
                ss_file.write(ss_js)
                ss_file.close()
                raw2 = pw_run_code_file(ss_file.name, timeout=15)
            finally:
                try:
                    os.unlink(ss_file.name)
                except Exception:
                    pass
            ss_result = pw_extract_result(raw2)
            if "ok" in ss_result:
                paths.append(q_path.strip('"'))
                size_kb = os.path.getsize(q_path.strip('"')) / 1024 if os.path.exists(q_path.strip('"')) else 0
                log(f"  Q{i+1} screenshot: {size_kb:.1f} KB (y={q_info['startY']}..{end_y})")
            else:
                log(f"  Q{i+1} screenshot failed: {ss_result[:80]}", "WARN")

        log(f"  Captured {len(paths)}/{count} question screenshots")
        return paths

    def _capture_quiz_screenshot(self) -> str | None:
        """DEPRECATED: Use _capture_question_screenshots() instead.
        Kept as fallback for single-screenshot approach."""
        import json as _json
        import tempfile as _tempfile2

        session2 = _get_active_session()
        sfx2 = f"_{session2}" if session2 and session2 != "chaoxing-chrome" else ""
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        screenshot_path = os.path.join(
            str(TMP_DIR),
            f'_quiz_screenshot{sfx2}.png'
        )
        try:
            os.unlink(screenshot_path)
        except Exception:
            pass

        js = f"""
        async (page) => {{
            // Try ALL candidate iframes (not just first) -- quiz content may be nested
            const candidates = page.frames().filter(f =>
                f !== page.mainFrame() &&
                (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
                 f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
            );
            if (candidates.length === 0) return JSON.stringify({{error: 'no-iframe'}});

            // Find first iframe with non-empty body
            let bodyBox = null;
            for (const iframe of candidates) {{
                try {{
                    bodyBox = await iframe.locator('body').boundingBox();
                    if (bodyBox && bodyBox.width > 100 && bodyBox.height > 30) break;
                }} catch(e) {{}}
            }}

            if (!bodyBox) return JSON.stringify({{error: 'no-body'}});

            const pad = 12;
            const vw = (await page.evaluate(() => window.innerWidth)) || 1280;
            const vh = (await page.evaluate(() => window.innerHeight)) || 900;
            const clip = {{
                x: Math.max(0, bodyBox.x - pad),
                y: Math.max(0, bodyBox.y - pad),
                width: Math.min(vw - bodyBox.x,
                                bodyBox.width + pad * 2),
                height: Math.min(vh - bodyBox.y,
                                 bodyBox.height + pad * 2)
            }};
            await page.screenshot({{path: {_json.dumps(screenshot_path)}, clip}});
            return JSON.stringify({{ok: true, w: Math.round(bodyBox.width), h: Math.round(bodyBox.height)}});
        }}
        """
        js_file = _tempfile2.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False,
            dir=str(TMP_DIR), encoding="utf-8"
        )
        try:
            js_file.write(js)
            js_file.close()
            raw = pw_run_code_file(js_file.name, timeout=15)
        finally:
            try:
                os.unlink(js_file.name)
            except Exception:
                pass
        result = pw_extract_result(raw)
        try:
            parsed = _json.loads(result)
            if parsed.get("ok"):
                log(f"  Quiz screenshot saved: {parsed['w']}x{parsed['h']}px")
                return screenshot_path
        except Exception:
            pass
        return None

    # ── V2 Screenshot (Strategy A: element.screenshot) ──

    def _capture_question_screenshots_v2(self) -> list[dict]:
        """Strategy A: Screenshot each .TiMu container via element.screenshot().

        One-liner per question -- no scroll arithmetic, Y-coordinate tracking,
        or dedup needed. Also extracts per-question metadata.

        Returns:
            list of {index, path, has_images, img_count, text_preview, qid, qtype},
            empty list on failure.
        """
        import json as _json
        import tempfile
        import glob as _glob

        ensure_chaoxing_viewport(2048, 1152)

        # Clean stale screenshots (session-namespaced)
        script_dir = str(TMP_DIR)
        session = _get_active_session()
        sfx = f"_{session}" if session and session != "chaoxing-chrome" else ""
        for old in _glob.glob(os.path.join(script_dir, f'_quiz_q*v2{sfx}.png')):
            try:
                os.unlink(old)
            except Exception:
                pass

        # ── Single JS pass: find TiMu containers, screenshot each, extract metadata ──
        capture_js = r"""
        async (page) => {
            const candidates = page.frames().filter(f =>
                f !== page.mainFrame() &&
                (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
                 f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
            );
            if (candidates.length === 0) return JSON.stringify({error: 'no-iframe'});

            let questions = [];

            for (const iframe of candidates) {
                try {
                    const timuEls = iframe.locator('.TiMu');
                    const count = await timuEls.count();
                    if (count < 1) continue;

                    for (let i = 0; i < count; i++) {
                        const el = timuEls.nth(i);
                        try {
                            // Scroll element into view for accurate rendering
                            await el.scrollIntoViewIfNeeded();
                            await page.waitForTimeout(200);

                            // Screenshot the .TiMu container
                            const path = Q_DIR + '/_quiz_q' + (i + 1) + 'v2' + Q_SFX + '.png';
                            await el.screenshot({path});

                            // ── Extract metadata ──

                            // img count
                            let imgCount = 0;
                            try {
                                const imgs = el.locator('img');
                                imgCount = await imgs.count();
                            } catch(e) {}

                            // text preview (first 120 chars of innerText)
                            let textPreview = '';
                            try {
                                const fullText = await el.innerText();
                                textPreview = (fullText || '').replace(/\s+/g, ' ').trim().substring(0, 120);
                            } catch(e) {}

                            // qid: find input[id^="answer"] within container
                            let qid = '';
                            try {
                                const qidEl = el.locator('input[id^="answer"]');
                                const qidCount = await qidEl.count();
                                if (qidCount > 0) {
                                    const rawId = await qidEl.first().getAttribute('id');
                                    qid = (rawId || '').replace('answer', '');
                                }
                            } catch(e) {}

                            // qtype: detect from question title text
                            let qtype = 'unknown';
                            try {
                                const titleEl = el.locator('.newZy_TItle, .Zy_TItle, .Zy_TItle_before');
                                const titleCount = await titleEl.count();
                                if (titleCount > 0) {
                                    const titleText = (await titleEl.first().innerText() || '');
                                    if (/多选|不定项/.test(titleText)) qtype = 'multi';
                                    else if (/判断/.test(titleText)) qtype = 'judge';
                                    else if (/填空/.test(titleText)) qtype = 'fill';
                                    else if (/单选/.test(titleText) || /【/.test(titleText)) qtype = 'single';
                                }
                            } catch(e) {}
                            // Fallback qtype detection: check for radio vs checkbox
                            if (qtype === 'unknown') {
                                try {
                                    const radios = el.locator('input[type="radio"]');
                                    const checkboxes = el.locator('input[type="checkbox"]');
                                    const rc = await radios.count();
                                    const cc = await checkboxes.count();
                                    if (cc > 0 && rc === 0) qtype = 'multi';
                                    else if (rc > 0) qtype = 'single';
                                } catch(e) {}
                            }

                            questions.push({
                                index: i + 1,
                                path,
                                has_images: imgCount > 0,
                                img_count: imgCount,
                                text_preview: textPreview,
                                qid,
                                qtype,
                            });
                        } catch(e) {
                            questions.push({
                                index: i + 1,
                                path: '',
                                has_images: false,
                                img_count: 0,
                                text_preview: '',
                                qid: '',
                                qtype: 'unknown',
                                error: e.message,
                            });
                        }
                    }

                    return JSON.stringify({
                        ok: true,
                        count: questions.length,
                        iframe_url: iframe.url().substring(0, 80),
                        questions,
                    });
                } catch(e) {
                    return JSON.stringify({error: 'iframe-error: ' + e.message});
                }
            }

            return JSON.stringify({error: 'no-timu-found'});
        }
        """

        # Inject Q_DIR and Q_SFX into the JS
        sfx_json = _json.dumps(sfx)
        qdir_json = _json.dumps(script_dir.replace('\\', '/'))
        capture_js = capture_js.replace('Q_DIR', qdir_json).replace('Q_SFX', sfx_json)

        js_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False,
            dir=str(TMP_DIR), encoding="utf-8"
        )
        try:
            js_file.write(capture_js)
            js_file.close()
            raw = pw_run_code_file(js_file.name, timeout=90)
        finally:
            try:
                os.unlink(js_file.name)
            except Exception:
                pass

        result_str = pw_extract_result(raw)
        try:
            result = _json.loads(result_str)
        except _json.JSONDecodeError:
            log(f"  [V2] Failed to parse capture result: {result_str[:120]}", "WARN")
            return []

        if not result.get("ok"):
            log(f"  [V2] Screenshot capture failed: {result.get('error', 'unknown')}", "WARN")
            return []

        q_infos = result.get("questions", [])
        success_count = sum(1 for q in q_infos if q.get("path") and os.path.exists(q["path"]))
        log(f"  [V2] Captured {success_count}/{len(q_infos)} question screenshots "
            f"(img distribution: {[q.get('img_count',0) for q in q_infos[:10]]}...)")

        return q_infos

    # ── Batched Doubao Solving ────────────────────────

    def _solve_batched(self, q_infos: list[dict], batch_size: int = 5,
                       section_key: str = "") -> list[dict]:
        """Send question screenshots to AI in batches, merge results.

        Each batch uploads batch_size screenshots, gets answers via
        the configured image solver, then merges across all batches.
        Uses the engine resolved at quiz start (self._quiz_engine_fns) so a
        mid-quiz provider switch never swaps engines between batches.

        Returns: list of {index, answer} dicts (sorted by index).
        """
        engine_fns = getattr(self, "_quiz_engine_fns", None)             or self._get_ai_solver()
        _, solve_image_fn = engine_fns

        n = len(q_infos)
        total_batches = math.ceil(n / batch_size)
        all_answers = []
        failed_batches = 0

        log(f"  [Batched] {n} questions -> {total_batches} batch(es) of {batch_size}")

        for b in range(total_batches):
            start_idx = b * batch_size
            end_idx = min(start_idx + batch_size, n)
            batch_infos = q_infos[start_idx:end_idx]
            batch_q_indices = [q["index"] for q in batch_infos]
            batch_paths = [q["path"] for q in batch_infos if q.get("path")]

            if not batch_paths:
                log(f"  [Batched] Batch {b+1}/{total_batches}: no valid paths, skipping", "WARN")
                failed_batches += 1
                continue

            batch_label = f"{batch_q_indices[0]}-{batch_q_indices[-1]}"
            log(f"  [Batched] Batch {b+1}/{total_batches} (Q{batch_label}, {len(batch_paths)} images)...")

            try:
                batch_answers = solve_image_fn(
                    batch_paths, self.name,
                    f"{section_key} (batch {b+1}/{total_batches})"
                )
                if batch_answers:
                    # Remap batch-relative indices to absolute question numbers.
                    # Detect whether AI returns 0-based or 1-based indices via
                    # the minimum old_idx across all batch answers.
                    old_indices = [
                        ans.get("index", ans.get("question_index", 0))
                        for ans in batch_answers
                    ]
                    min_old = min(old_indices) if old_indices else 0
                    if min_old == 0:
                        # 0-based: answer index is offset from batch start
                        idx_offset = batch_q_indices[0]
                    else:
                        # 1-based: answer index is 1..batch_size within batch
                        idx_offset = batch_q_indices[0] - 1
                    for ans in batch_answers:
                        old_idx = ans.get("index", ans.get("question_index", 0))
                        ans["index"] = old_idx + idx_offset
                    all_answers.extend(batch_answers)
                    log(f"  [Batched] Batch {b+1}/{total_batches}: {len(batch_answers)} answers", "OK")
                else:
                    log(f"  [Batched] Batch {b+1}/{total_batches}: empty result", "WARN")
                    failed_batches += 1
            except Exception as e:
                log(f"  [Batched] Batch {b+1}/{total_batches} exception: {e}", "WARN")
                failed_batches += 1

        # Sort by index for consistent ordering
        all_answers.sort(key=lambda a: a.get("index", a.get("question_index", 0)))

        log(f"  [Batched] Total: {len(all_answers)} answers from {total_batches - failed_batches}/{total_batches} batches")
        return all_answers

    # ── Fill & Submit (delegates) ──────────────────────

    def _fill_answers(self, answers: list[dict]) -> int:
        """Fill in answers (no submit). Returns count of questions filled."""
        return _fill_answers(answers)

    def _click_option(self, q_index: int, answer: str):
        """Click a radio/checkbox for question q_index."""
        return _click_option(q_index, answer)

    def _click_option_dom(self, q_index: int, answer_str: str,
                          is_single_letter: bool) -> bool:
        """DOM-based option click using .TiMu / .questionLi container isolation."""
        return _click_option_dom(q_index, answer_str, is_single_letter)

    def _fill_blank(self, q_index: int, answer: str) -> bool:
        """Fill a textarea/blank question using UE editor or value assignment."""
        return _fill_blank(q_index, answer)

    def _is_unanswerable(self, answer) -> bool:
        """Check if the AI indicated the question cannot be answered."""
        return _is_unanswerable(answer)

    def _detect_question_types(self) -> list[dict]:
        """Inspect quiz DOM to determine each question's type."""
        return _detect_question_types()

    def _submit_quiz(self) -> bool:
        """Submit quiz using native function with snapshot fallback."""
        return _submit_quiz()

    def _submit_quiz_native(self) -> bool:
        """Submit quiz using page-native btnBlueSubmit() function."""
        return _submit_quiz_native()

    def _fill_and_submit(self, answers: list[dict]) -> bool:
        """Fill in answers and click submit button. (Delegates to _fill_answers + _submit_quiz)"""
        self._fill_answers(answers)
        return self._submit_quiz()

    # ── Score Parsing ──────────────────────────────────

    def _parse_score(self, snap: str) -> int | None:
        """Extract score percentage from result snapshot."""
        return _parse_score(snap)

    @staticmethod
    def _count_questions_in_text(text: str) -> int:
        """Count distinct question numbers in decrypted text."""
        return count_questions_in_text(text)

    @staticmethod
    def _count_questions_in_snapshot(snap: str) -> int:
        """Count distinct question numbers in snapshot text."""
        return count_questions_in_snapshot(snap)

    # ── Phase C: Grading ───────────────────────────────

    def _capture_filled_screenshots_v2(self) -> list[dict]:
        """Re-screenshot .TiMu containers AFTER filling answers."""
        return _capture_filled_screenshots_v2()

    def _grade_batched(self, filled_infos: list[dict], ai_answers: list[dict],
                       batch_size: int = 5, section_key: str = "") -> dict:
        """Send filled-state screenshots to Doubao Tab1 for grading."""
        return _grade_batched(filled_infos, ai_answers, batch_size, section_key,
                              self.GRADE_PASS_THRESHOLD)

    def _parse_correct_answers(self, snap: str) -> list[dict] | None:
        """Parse correct answers from the '查看答案' view snapshot."""
        return _parse_correct_answers(snap)

    # ── Retry ──────────────────────────────────────────

    def _retry_quiz(self, section: dict, retry_depth: int = 0) -> bool:
        """Retry a quiz after a failed attempt."""
        return _retry_quiz(self, section, retry_depth)

    # ── Main Solve Orchestrator ───────────────────────

    def _is_already_graded(self) -> bool:
        """Detect Chaoxing's 已批阅 (already-graded) quiz template.

        A submitted/graded quiz loads in an iframe whose URL contains
        'selectWorkQuestionYiPiYue' (vs 'doHomeWorkNew' for an answerable
        quiz). Its options render as ul.Zy_ulTop>li, which the filler's option
        selectors don't match — so without this guard every fill logs a DOM
        miss. Returns True when the graded template is detected; on any error
        returns False (fail open — better to attempt than wrongly skip).
        """
        js = r"""
        async (page) => {
            for (const f of page.frames()) {
                const u = f.url() || '';
                if (u.includes('selectWorkQuestionYiPiYue')) return 'graded';
            }
            return 'no';
        }
        """
        try:
            result = pw_extract_result(pw_run_code(js))
        except Exception:
            return False
        return str(result) == "graded"

    def _has_no_quiz_content(self) -> bool:
        """Detect an empty content node misclassified as a quiz (Issue A).

        Some sections whose name matches the quiz regex (e.g. "练习与测试",
        "test for superconductor") are actually empty content placeholders the
        instructor never populated. Navigating there renders the knowledge/cards
        frame with .nullpage ("暂无内容") and NO question DOM and NO work iframe
        — there is literally nothing to answer. Without this guard the solver
        screenshots a blank card, the AI hallucinates answers, and _fill_answers
        logs a `no-containers-and-no-titles` miss storm.

        FORTIFIED (Issue A, step 2) — borrows referrence_scripts2.txt's
        waitForQuestionsRenderAny polling design (NOT its hasActionableStudyContent
        union — see the note below on why generic inputs/editors are excluded):

          1. WAIT-THEN-JUDGE: a single-shot DOM probe races a real quiz's lazy
             iframe/question render and could wrongly flag a still-loading quiz
             as empty. Instead we POLL (400ms interval, ~6s deadline). The moment
             ANY actionable content appears we return 'has-content' early, so a
             real quiz costs almost nothing; only a genuinely empty node waits
             out the full deadline.
          2. REVERSE-EMPTY via QUIZ-SPECIFIC signals only: content is judged from
             the work iframe (doHomeWorkNew / mooc-ans/work / selectWorkQuestion)
             OR a question container (.TiMu/.questionLi/.newZy_TItle/.Zy_TItle/
             .subject_item/.examPaper_subject). A node counts as empty ONLY when,
             after the full wait, NEITHER exists AND an explicit empty marker
             (.nullpage / 暂无内容) is present.

        NOTE — why NOT generic inputs/editors: the reference's
        hasActionableStudyContent also counts textarea/[contenteditable]/ueditor.
        Empirically (account-1 9.4 probe) those are course-page CHROME present on
        EVERY section — the 讨论/评论 textareas (#discussTextArea,
        #toplevelTextCommentContent) and a note editor live even on an empty
        placeholder card, so counting them defeated the skip (they fired on the
        empty node and suppressed detection). A real answerable quiz ALWAYS loads
        a work iframe and/or question DOM, so those generic signals were redundant
        for real quizzes and harmful for empty ones — hence excluded. The work
        iframe + question containers are the quiz-specific, reliable signals.

        Conservative by design: 'empty' requires an explicit empty marker AND a
        complete absence of any work iframe / question container observed over the
        wait window. A real quiz returns 'has-content' the instant it renders and
        is never skipped. On any error returns False (fail open — better to
        attempt than wrongly skip).
        """
        js = r"""
        async (page) => {
            const DEADLINE_MS = 6000;
            const INTERVAL_MS = 400;
            const Q_SEL = '.TiMu, .questionLi, .newZy_TItle, .Zy_TItle, ' +
                '.subject_item, .examPaper_subject';
            const start = Date.now();
            let sawNullpage = false;
            while (Date.now() - start < DEADLINE_MS) {
                let hasWork = false, hasQuestions = false;
                sawNullpage = false;
                for (const f of page.frames()) {
                    const u = f.url() || '';
                    if (u.includes('doHomeWorkNew') ||
                        u.includes('mooc-ans/work') ||
                        u.includes('selectWorkQuestion')) hasWork = true;
                    try {
                        const r = await f.evaluate((qsel) => {
                            const q = document.querySelectorAll(qsel).length;
                            const np = !!document.querySelector('.nullpage') ||
                                !!(document.body &&
                                   document.body.innerText.indexOf('暂无内容') >= 0);
                            return { q: q, np: np };
                        }, Q_SEL);
                        if (r.q > 0) hasQuestions = true;
                        if (r.np) sawNullpage = true;
                    } catch (e) {}
                }
                if (hasWork || hasQuestions) return 'has-content';
                await page.waitForTimeout(INTERVAL_MS);
            }
            if (sawNullpage) return 'empty';
            return 'unknown';
        }
        """
        try:
            result = pw_extract_result(pw_run_code(js))
        except Exception:
            return False
        return str(result) == "empty"

    def solve_quiz(self, section: dict, retry_depth: int = 0) -> bool:
        """Complete one quiz section. Returns True on success.

        retry_depth guards against infinite recursion (max 5 nested retries).

        Solving pipeline (5-tier fallback):
          1. Font decrypt text mode (fast, but disabled until font encryption fixed)
          2. V2 Screenshot + Batched image mode (Strategy A)
          3. Legacy per-question screenshot + single-batch (fallback)
          4. Full-page screenshot (last resort image)
          5. Snapshot text mode (emergency fallback)
        """
        MAX_RETRY_DEPTH = 5
        section_num = section["section"]
        section_name = section["name"]
        section_key = f"{section_num} {section_name}"

        if self.tracker.is_section_done(self.name, section_key):
            log(f"  [{section_key}] Already completed, skipping", "SKIP")
            return True

        log(f"  [{section_key}] Starting quiz... (depth={retry_depth})")

        # ── Select AI solver based on config ──
        # Resolved ONCE per quiz: a mid-quiz provider switch (config edit /
        # settings panel) must not swap engines between batches of the same
        # quiz or between solve and retry — the switch takes effect on the
        # NEXT quiz.
        solve_text_fn, solve_image_fn = self._get_ai_solver()
        self._quiz_engine_fns = (solve_text_fn, solve_image_fn)
        provider = cfg("ai.provider", "doubao-api")
        log(f"  [{section_key}] AI provider: {provider}")

        # 0. DRY RUN: skip all navigation and submission
        if self.dry_run:
            log(f"  [{section_key}] DRY RUN: would navigate to section and solve quiz")
            return True

        # 1. Navigate to section (only on first attempt; retries are already on page)
        if retry_depth == 0:
            if not self.navigate_to_section(section_num):
                # The browser session may have been rebuilt mid-run (engine
                # recovers a dead daemon/Chrome by reopening about:blank), in
                # which case the course page — and with it the chapter-tree
                # iframe this navigation depends on — is gone. Re-enter the
                # course once before giving up on this section.
                log(f"  [{section_key}] Navigation failed — re-entering course page", "WARN")
                try:
                    self.open_course()
                except Exception as re_err:
                    log(f"  [{section_key}] Course re-entry failed: {re_err}", "ERROR")
                if not self.navigate_to_section(section_num):
                    log(f"  [{section_key}] Failed to navigate (after re-entry)", "ERROR")
                    self.stats["failed"] += 1
                    return False
            human_delay(3.0, 0.25)  # Wait for quiz to load

        # 2. Wait for quiz iframe to fully load
        human_delay(2.0, 0.25)

        # 2b. Already-graded guard. If the section was already submitted, Chaoxing
        # serves the 已批阅 review template (URL .../selectWorkQuestionYiPiYue),
        # whose option DOM (ul.Zy_ulTop>li) the filler can't act on — every fill
        # would log a spurious DOM miss. Discovery already filters is_complete
        # quizzes; this is the runtime backstop for stale resume files or quizzes
        # graded since the scan. Mark done and skip.
        if self._is_already_graded():
            log(f"  [{section_key}] Already graded (已批阅) — marking done, skipping")
            self.tracker.mark_section_done(self.name, section_key)
            self.stats["solved"] += 1
            return True

        # 2c. Empty-content guard (Issue A). A section whose name matches the
        # quiz regex but is actually an unpopulated content placeholder renders
        # an empty card (.nullpage / 暂无内容) with no question DOM and no work
        # iframe. There is nothing to answer — screenshotting it would feed a
        # blank card to the AI and produce a `no-containers-and-no-titles` miss
        # storm. Mark done and skip. (Conservative: skips only when an empty
        # marker is present and no question/work content exists.)
        if self._has_no_quiz_content():
            log(f"  [{section_key}] No quiz content (empty placeholder, 暂无内容) "
                f"— marking done, skipping")
            self.tracker.mark_section_done(self.name, section_key)
            self.stats["solved"] += 1
            return True

        # 3. Run strategies in order
        answers = None
        solve_mode = "text"
        q_count = 0

        for strategy in STRATEGY_CHAIN:
            log(f"  [{section_key}] Trying {strategy.name} (Tier {strategy.tier})...")
            result = strategy.try_solve(self)
            if result is not None:
                if result.get("already_done"):
                    log(f"  [{section_key}] Quiz already completed or empty, marking done")
                    self.tracker.mark_section_done(self.name, section_key)
                    return True
                answers = result.get("answers")
                q_count = result.get("q_count", 0)
                solve_mode = result.get("mode", "text")
                if answers is not None:
                    log(f"  [{section_key}] {strategy.name} returned {len(answers)} answers", "OK")
                    break
                else:
                    log(f"  [{section_key}] {strategy.name} returned no answers, trying next...", "WARN")
                    answers = None
            else:
                log(f"  [{section_key}] {strategy.name} failed, trying next...", "WARN")

        if not answers:
            log(f"  [{section_key}] AI returned no answers", "WARN")
            self.stats["failed"] += 1
            return False

        # 8. Fill answers
        self._fill_answers(answers)

        # ── Phase C: Grade-only mode ────────────────────
        # Capture filled state screenshots, send to Doubao for grading.
        # No submission -- accuracy derived from Doubao's independent re-evaluation.
        if self.grade_only:
            log(f"  [{section_key}] GRADE-ONLY: capturing filled state -> Doubao grading...")
            filled_infos = self._capture_filled_screenshots_v2()

            if not filled_infos:
                log(f"  [{section_key}] Failed to capture filled screenshots", "WARN")
                self.stats["failed"] += 1
                return False

            if q_count == 0:
                q_count = len(answers)

            # Grade via Doubao
            grade_result = self._grade_batched(
                filled_infos, answers, batch_size=5, section_key=section_key)

            # Clean up filled screenshots
            for qi in filled_infos:
                p = qi.get("path", "")
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

            accuracy = grade_result.get("accuracy", 0)
            passed = grade_result.get("passed", accuracy >= self.GRADE_PASS_THRESHOLD)
            log(f"  [{section_key}] GRADE RESULT: {accuracy}% "
                f"({grade_result.get('correct', 0)}✓ / {grade_result.get('incorrect', 0)}✗ "
                f"/ {grade_result.get('uncertain', 0)}?) -- {'PASSED' if passed else 'FAILED'}")

            # Record stats with Doubao grading as score
            self.quiz_stats.record_attempt(
                section_key, q_count, answers, accuracy,
                retry_count=retry_depth, mode=f"image+grade")

            # Pass threshold check
            if passed:
                log(f"  [{section_key}] GRADE PASSED! ({accuracy}% >= {self.GRADE_PASS_THRESHOLD}%)", "OK")
                self.tracker.mark_section_done(self.name, section_key)
                self.stats["solved"] += 1
                return True
            else:
                # Grade-only: don't retry aggressively -- AI can't improve much
                if self.grade_only and retry_depth >= 1:
                    log(f"  [{section_key}] GRADE FAILED after retry ({accuracy}% < {self.GRADE_PASS_THRESHOLD}%), giving up", "WARN")
                    self.stats["failed"] += 1
                    return False
                log(f"  [{section_key}] GRADE FAILED ({accuracy}% < {self.GRADE_PASS_THRESHOLD}%)", "WARN")
                self.stats["failed"] += 1
                return False
        # ── End grade-only ──────────────────────────────

        # 9. Submit (normal mode)
        if not self._submit_quiz():
            log(f"  [{section_key}] Submit failed, will retry", "WARN")
            if retry_depth >= MAX_RETRY_DEPTH:
                log(f"  [{section_key}] Max retry depth reached, giving up", "ERROR")
                self.stats["failed"] += 1
                return False
            self.stats["retried"] += 1
            return self._retry_quiz(section, retry_depth)

        # 10. Check score
        time.sleep(2)
        result_snap = pw_snapshot()
        score = self._parse_score(result_snap)
        log(f"  [{section_key}] Score: {score}%")

        # ── Record stats ──
        if q_count == 0:
            q_count = len(answers)

        if score is not None and score >= cfg("retry.quiz_target_score", 100):
            log(f"  [{section_key}] PASSED!", "OK")
            self.tracker.mark_section_done(self.name, section_key)
            self.stats["solved"] += 1
            self.quiz_stats.record_attempt(
                section_key, q_count, answers, score,
                retry_count=retry_depth, mode=solve_mode)
            return True
        else:
            log(f"  [{section_key}] Score below target ({score}%), retrying...", "WARN")
            if retry_depth >= MAX_RETRY_DEPTH:
                log(f"  [{section_key}] Max retry depth reached, accepting current score", "WARN")
                if score is not None and score >= 60:
                    self.tracker.mark_section_done(self.name, section_key)
                    self.stats["solved"] += 1
                    self.quiz_stats.record_attempt(
                        section_key, q_count, answers, score,
                        retry_count=retry_depth, mode=solve_mode)
                    return True
                self.stats["failed"] += 1
                self.quiz_stats.record_attempt(
                    section_key, q_count, answers, score or 0,
                    retry_count=retry_depth, mode=solve_mode)
                return False
            # Record first attempt before retry
            self.quiz_stats.record_attempt(
                section_key, q_count, answers, score,
                retry_count=retry_depth, mode=solve_mode)
            self.stats["retried"] += 1
            return self._retry_quiz(section, retry_depth)

    # ── Main Loop ──────────────────────────────────────

    def run(self):
        """Main execution loop for the course."""
        log(f"{'='*60}")
        log(f"Quiz Solver: {self.name}")
        log(f"{'='*60}")

        self.open_course()

        quizzes = self.course.get("remaining_quiz_sections", [])
        if not quizzes:
            log("No quiz sections configured for this course")
            return

        log(f"Total quizzes to solve: {len(quizzes)}")

        for i, section in enumerate(quizzes):
            # Pause/stop/RAM-guard yield point (blocks while paused, raises on stop).
            check_signals()
            log(f"\n--- Quiz {i+1}/{len(quizzes)}: {section['section']} {section['name']} ---")
            try:
                self.solve_quiz(section)
            except Exception as e:
                log(f"  Unexpected error: {e}", "ERROR")
                self.tracker.log_error(self.name, section["section"], str(e))
                self.stats["failed"] += 1

            # Return to chapter tree for next section navigation
            self.go_back_to_chapter_tree()

            # Human-like pacing between real quiz submissions. dry_run and
            # grade_only never submit, so they skip the pause. A 60–120s
            # irregular gap between sections keeps the submission rhythm
            # natural and reduces verification prompts.
            if (not self.dry_run and not self.grade_only
                    and i < len(quizzes) - 1):
                pacing = random.uniform(60, 120)
                log(f"    Pacing before next quiz: {pacing:.0f}s...")
                check_signals()
                time.sleep(pacing)

        # Summary
        log(f"\n{'='*60}")
        log(f"Quiz Solver Summary: {self.name}")
        log(f"  Solved: {self.stats['solved']}")
        log(f"  Failed: {self.stats['failed']}")
        log(f"  Retried: {self.stats['retried']}")
        log(f"{'='*60}")

        # Accuracy report
        self.quiz_stats.print_summary()


# Standalone entry point removed — use chaoxing.api or chaoxing.orchestrator instead.
