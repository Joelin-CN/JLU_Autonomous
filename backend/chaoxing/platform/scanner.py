"""
Course and section discovery — scan Chaoxing course listing and chapter trees.

Navigates the Chaoxing website to discover:
    - Unfinished courses from the personal space course listing
    - Chapter/section structures with quiz vs content classification
    - Per-section task point counts and completion status

All scanning uses JS DOM injection for reliability (avoids snapshot-ref fragility).
"""

import json
import os
import re
import tempfile
import time

from ..constants import TMP_DIR
from ..config import cfg
from ..session import _get_active_session
from ..logging_setup import log
from ..browser.engine import pw_goto, pw_snapshot
from ..browser.js_runner import pw_run_code_file, pw_extract_result
from ..utils import human_delay
from .navigation import pw_goto_course


# ── Internal: Navigate to Course Listing ─────────────────────────

def _ensure_on_course_listing() -> bool:
    """Navigate to personal space and click 课程 to reach the course listing.

    Returns True if the course listing page (with mooc2 iframe) is loaded.
    Uses JS DOM click for reliability (avoids snapshot-ref fragility).
    """
    # 1. Ensure on personal space
    snap = pw_snapshot()
    if "个人空间" not in snap and "i.chaoxing.com/base" not in snap:
        pw_goto("https://i.chaoxing.com/base")
        human_delay(3.0, 0.25)
        snap = pw_snapshot()

    if "个人空间" not in snap:
        log("Cannot reach personal space", "ERROR")
        return False

    # 2. Check if course listing is already loaded
    js_check = """
    async (page) => {
        const cf = page.frames().find(f =>
            f !== page.mainFrame() &&
            (f.url().includes('visit/interaction') ||
             f.url().includes('mooc2-ans') || f.url().includes('courses'))
        );
        if (cf) {
            const bt = (await cf.locator('body').innerText() || '').substring(0, 500);
            if (bt.includes('我学的课') || bt.includes('课程已结束') || bt.includes('任务点进度')) {
                return JSON.stringify({alreadyThere: true});
            }
        }
        return JSON.stringify({alreadyThere: false});
    }
    """
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    tmp.write(js_check)
    tmp.close()
    try:
        raw = pw_run_code_file(tmp.name, timeout=10)
        check = json.loads(pw_extract_result(raw))
        if check.get("alreadyThere"):
            log("Already on course listing page")
            return True
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp.name)
        except:
            pass

    # 3. Click 课程 via JS
    log("Clicking 课程 in sidebar...")
    js_click = """
    async (page) => {
        const headings = await page.locator('heading').all();
        let courseMenuItem = null;
        for (const h of headings) {
            const text = (await h.textContent() || '').trim();
            if (text === '课程') {
                courseMenuItem = await h.evaluateHandle(el => {
                    let p = el;
                    for (let i = 0; i < 5; i++) {
                        if (!p) break;
                        const role = p.getAttribute && p.getAttribute('role');
                        if (role === 'menuitem' || p.tagName === 'A' || p.tagName === 'BUTTON') {
                            return p;
                        }
                        p = p.parentElement;
                    }
                    return el;
                });
                break;
            }
        }
        if (!courseMenuItem) {
            const menuItems = await page.locator('[role="menuitem"]').all();
            for (const mi of menuItems) {
                const text = (await mi.textContent() || '').trim();
                if (text.includes('课程')) {
                    courseMenuItem = mi; break;
                }
            }
        }
        if (!courseMenuItem) return 'no-course-menuitem';

        await courseMenuItem.click();
        await page.waitForTimeout(3000);
        return 'clicked';
    }
    """
    tmp2 = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    tmp2.write(js_click)
    tmp2.close()
    try:
        raw2 = pw_run_code_file(tmp2.name, timeout=15)
        click_result = pw_extract_result(raw2)
        log(f"  Click 课程 result: {click_result}")
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp2.name)
        except:
            pass

    human_delay(2.0, 0.25)
    snap = pw_snapshot()
    log(f"  Page has 我学的课: {'我学的课' in snap}")
    return True


# ── Public: Scan Courses ─────────────────────────────────────────

def scan_courses() -> list[dict]:
    """Scan the Chaoxing personal space course listing for unfinished courses.

    Prerequisites: Browser session open and logged in (chaoxing_login).

    Navigates to the course listing (个人空间→课程), scrolls the mooc2 iframe,
    and extracts course cards via JS DOM traversal.

    Returns list sorted by progress (highest first):
        [{name, courseid, clazzid, cpi, done, total, percent, teacher}]
    Only returns courses where: percent < 95, not ended, total > 0.
    Returns empty list on failure.
    """
    # 1. Navigate to course listing
    if not _ensure_on_course_listing():
        log("Failed to reach course listing page", "ERROR")
        return []

    human_delay(2.0, 0.25)

    # 2. JS extraction: find course links, walk up to cards, parse text
    scan_js = r"""
    async (page) => {
        const iframe = page.frames().find(f =>
            f !== page.mainFrame() &&
            f.url().includes('visit/interaction')
        );
        if (!iframe) return JSON.stringify({ok: false, reason: 'no-courses-iframe'});

        // The course list lazy-loads cards while scrolling. Scroll + wait
        // until the rendered card count stabilizes so a fast first paint does
        // not leave most courses undiscovered (observed: 11 courses → 1).
        let stableCardCount = 0;
        for (let pass = 0; pass < 5; pass++) {
            await iframe.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            await page.waitForTimeout(700 + Math.floor(Math.random() * 500));
            await iframe.evaluate(() => window.scrollTo(0, 0));
            await page.waitForTimeout(400 + Math.floor(Math.random() * 300));
            const rendered = await iframe.locator('div.course.learnCourse[id^="c_"]').count();
            if (rendered > stableCardCount) {
                stableCardCount = rendered;
            } else if (rendered === stableCardCount && rendered > 0) {
                break;
            }
        }

        const cardDivs = await iframe.locator(
            'div.course.learnCourse[id^="c_"]'
        ).all();

        const courses = [];

        for (const card of cardDivs) {
            try {
                const cardId = (await card.getAttribute('id') || '').trim();
                const info = (await card.getAttribute('info') || '').trim();

                if (!cardId || !info) continue;

                const courseid = cardId.replace('c_', '');
                const infoParts = info.split('_');
                const clazzid = infoParts[0];
                const cpi = infoParts[1] || '415409200';

                if (!courseid || !clazzid) continue;

                const cardText = ((await card.innerText()) || '')
                    .replace(/\s+/g, ' ').trim();

                let name = '';
                const links = await card.locator(
                    'a[href*="courseid"]'
                ).all();
                for (const link of links) {
                    const linkText = (
                        await link.textContent() || ''
                    ).trim();
                    if (linkText && linkText !== '课程已结束'
                        && linkText.length >= 2) {
                        name = linkText;
                        break;
                    }
                }
                if (!name) continue;

                const progM = cardText.match(
                    /任务点进度[：:]\s*(\d+)\s*\/\s*(\d+)/
                );
                const pctM = cardText.match(/(\d{1,3})\s*%/);
                const done = progM ? parseInt(progM[1]) : 0;
                const total = progM ? parseInt(progM[2]) : 0;
                const percent = pctM ? parseInt(pctM[1])
                              : (total > 0
                                 ? Math.round(done * 100 / total) : 0);

                const isEnded = (
                    cardText.includes('课程已结束') ||
                    cardText.includes('已结束')
                );

                let teacher = '';
                const tM = cardText.match(
                    /(?:教师|老师|讲师)[：:]\s*(\S+)/
                );
                if (tM) teacher = tM[1].trim();

                courses.push({
                    name, courseid, clazzid, cpi,
                    done, total, percent,
                    is_ended: isEnded,
                    teacher,
                });
            } catch(e) {
                // skip individual card errors
            }
        }

        const COMPLETION_THRESHOLD = 95;

        let unfinished = courses.filter(
            c => c.percent < COMPLETION_THRESHOLD && !c.is_ended && c.total > 0
        );
        let noProgress = courses.filter(
            c => c.total === 0 && !c.is_ended
        );
        unfinished.sort((a, b) => b.percent - a.percent);
        noProgress.sort((a, b) => a.name.localeCompare(b.name, 'zh'));
        let all = unfinished.concat(noProgress);

        // Deduplicate by courseid
        const seenIds = new Set();
        all = all.filter(c => {
            if (seenIds.has(c.courseid)) return false;
            seenIds.add(c.courseid);
            return true;
        });

        return JSON.stringify({
            ok: true,
            total_on_page: courses.length,
            unfinished_count: all.length,
            courses: all,
        });
    }
    """

    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    tmp.write(scan_js)
    tmp.close()

    try:
        raw = pw_run_code_file(tmp.name, timeout=25)
        result_str = pw_extract_result(raw)
        result = json.loads(result_str)
    except Exception as e:
        log(f"scan_courses JS failed: {e}", "ERROR")
        return []
    finally:
        try:
            os.unlink(tmp.name)
        except:
            pass

    if not result.get("ok"):
        log(f"scan_courses error: {result.get('reason', '?')}", "WARN")
        return []

    courses = result.get("courses", [])
    log(f"scan_courses: {result.get('unfinished_count', 0)} unfinished / "
        f"{result.get('total_on_page', 0)} total on page")
    return courses


# ── Public: Scan Course Sections ─────────────────────────────────

def scan_course_sections(courseid: str, clazzid: str,
                         cpi: str = "415409200") -> dict:
    """Scan the chapter tree for a specific course.

    Navigates to the course page, clicks 章节 tab, and extracts all
    chapter/section information from the mooc2-ans iframe.

    Returns: {
        "ok": bool,
        "course_name": str,
        "done": int, "total": int,
        "quiz_sections": [{chapter, section, name, tasks}],
        "content_sections": [{chapter, section, name, tasks}],
        "chapters": [{num, name, sections_count,
                       sections: [{section, name, tasks, type}]}],
    }
    On failure, returns {"ok": false, "reason": "..."}.
    """
    # 1. Navigate to course page
    log(f"  Navigating to course (id={courseid})...")
    pw_goto_course(courseid, clazzid, cpi)
    human_delay(3.0, 0.25)

    # 2. Click 章节 tab via JS
    js_click_chapter = r"""
    async (page) => {
        const links = await page.locator('a').all();
        for (const link of links) {
            const text = (await link.textContent() || '').trim();
            if (text === '章节') {
                await link.click();
                await page.waitForTimeout(2500 + Math.floor(Math.random() * 1200));
                return 'clicked';
            }
        }
        try {
            await page.getByRole('link', { name: '章节' }).click();
            await page.waitForTimeout(2500 + Math.floor(Math.random() * 1200));
            return 'clicked-via-role';
        } catch(e) {
            return 'not-found';
        }
    }
    """
    tmp_click = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    tmp_click.write(js_click_chapter)
    tmp_click.close()
    try:
        raw_click = pw_run_code_file(tmp_click.name, timeout=20)
        click_result = pw_extract_result(raw_click)
        log(f"  Click 章节: {click_result}")
    except Exception as e:
        log(f"  Click 章节 failed: {e}", "WARN")
    finally:
        try:
            os.unlink(tmp_click.name)
        except:
            pass

    # 3. DOM-based extraction from chapter tree iframe
    scan_js = r"""
    async (page) => {
        const iframe = page.frames().find(f =>
            f !== page.mainFrame() &&
            f.url().includes('mooc2-ans') &&
            (f.url().includes('studentcourse') || f.url().includes('mycourse'))
        );
        if (!iframe) return JSON.stringify({ok: false, reason: 'no-chapter-iframe'});

        await page.waitForTimeout(400 + Math.floor(Math.random() * 300));

        const bodyText = (await iframe.locator('body').innerText()) || '';
        const progM = bodyText.match(
            /已完成任务点[：:]\s*(\d+)\s*\/\s*(\d+)/
        );
        const done = progM ? parseInt(progM[1]) : 0;
        const total = progM ? parseInt(progM[2]) : 0;

        let courseName = '';
        try { courseName = await page.title(); } catch(e) {}

        const result = await iframe.evaluate(() => {
            const chapters = [];
            const quizSections = [];
            const contentSections = [];
            let currentChapter = null;

            const items = document.querySelectorAll('div.chapter_item');

            items.forEach((item) => {
                const catalogTitle = item.querySelector('.catalog_title');
                if (!catalogTitle) return;

                // Chapter header?
                const catalogNum = catalogTitle.querySelector('.catalog_num em');
                if (catalogNum) {
                    const chNum = parseInt((catalogNum.textContent || '').trim());
                    if (isNaN(chNum)) return;

                    const nameSpan = catalogTitle.querySelector('.catalog_name a.clicktitle span');
                    let chName = '';
                    if (nameSpan) {
                        chName = (nameSpan.textContent || '').trim();
                    }
                    if (!chName) {
                        const clickLink = catalogTitle.querySelector('.catalog_name a.clicktitle');
                        if (clickLink) {
                            chName = (clickLink.textContent || '').trim();
                        }
                    }

                    currentChapter = { num: chNum, name: chName, sections: [] };
                    if (!chapters.find(c => c.num === chNum)) {
                        chapters.push(currentChapter);
                    } else {
                        currentChapter = chapters.find(c => c.num === chNum);
                    }
                    return;
                }

                // Section item?
                const itemId = item.id || '';
                if (!itemId.startsWith('cur')) return;

                const contentId = itemId.replace('cur', '');
                const sbar = catalogTitle.querySelector('.catalog_sbar');
                if (!sbar) return;

                const sectionNum = (sbar.textContent || '').trim();
                if (!/^\d+\.\d+$/.test(sectionNum)) return;

                const clickLink = catalogTitle.querySelector('a.clicktitle');
                let sectionName = '';
                if (clickLink) {
                    sectionName = (clickLink.textContent || '').trim();
                    sectionName = sectionName.replace(/^\d+\.\d+\s*/, '').trim();
                }
                if (!sectionName) {
                    sectionName = item.getAttribute('title') || '';
                }

                const stateDiv = catalogTitle.querySelector('.catalog_state');
                const stateClass = stateDiv ? (stateDiv.className || '') : '';
                const isComplete = stateClass.includes('icon_yiwanc');
                const tasks = isComplete ? 0 : 1;

                const chNum = parseInt(sectionNum.split('.')[0]);
                if (!currentChapter || currentChapter.num !== chNum) {
                    let ch = chapters.find(c => c.num === chNum);
                    if (!ch) {
                        ch = { num: chNum, name: '', sections: [] };
                        chapters.push(ch);
                    }
                    currentChapter = ch;
                }

                const isQuiz = /测试|测验|作业|考试|Test|Quiz|Exam/i
                    .test(sectionName);

                const sec = {
                    chapter: currentChapter.num,
                    section: sectionNum,
                    name: sectionName,
                    contentid: contentId,
                    tasks,
                    type: isQuiz ? 'quiz' : 'content',
                    is_complete: isComplete,
                };
                currentChapter.sections.push(sec);

                if (isQuiz) quizSections.push(sec);
                else contentSections.push(sec);
            });

            chapters.sort((a, b) => a.num - b.num);
            for (const ch of chapters) {
                ch.sections_count = ch.sections.length;
            }

            return { chapters, quizSections, contentSections };
        });

        return JSON.stringify({
            ok: true,
            course_name: courseName,
            done, total,
            chapters: result.chapters,
            quiz_sections: result.quizSections,
            content_sections: result.contentSections,
        });
    }
    """

    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    tmp.write(scan_js)
    tmp.close()

    try:
        raw = pw_run_code_file(tmp.name, timeout=25)
        result_str = pw_extract_result(raw)
        result = json.loads(result_str)
    except Exception as e:
        log(f"  scan_course_sections JS failed: {e}", "ERROR")
        return {"ok": False, "reason": f"js-error:{e}"}
    finally:
        try:
            os.unlink(tmp.name)
        except:
            pass

    if result.get("ok"):
        q_count = len(result.get("quiz_sections", []))
        c_count = len(result.get("content_sections", []))
        d = result.get("done", 0)
        t = result.get("total", 0)
        log(f"  Sections: {q_count} quizzes + {c_count} content, "
            f"progress: {d}/{t}")
    else:
        log(f"  scan_course_sections error: {result.get('reason', '?')}", "WARN")

    return result
