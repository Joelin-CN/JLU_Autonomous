"""Batch test navigation helper — invoked by chaoxing_cli.ps1 Invoke-BatchTest.

Usage: python _batch_nav.py <session> <courseid> <clazzid> <cpi> <section>

Prints diagnostics to stdout; PS parses CODI: and NAV_OK: lines.
"""
import sys, os, time, json, re, tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

from chaoxing.session import set_active_session
from chaoxing.logging_setup import log
from chaoxing.browser.engine import pw_snapshot
from chaoxing.browser.js_runner import pw_run_code_file, pw_extract_result
from chaoxing.utils import find_ref_by_text
from chaoxing.solvers.quiz.solver import ChapterQuizSolver


def main():
    if len(sys.argv) < 6:
        print("Usage: _batch_nav.py <session> <courseid> <clazzid> <cpi> <section>")
        sys.exit(1)

    session = sys.argv[1]
    courseid = sys.argv[2]
    clazzid = sys.argv[3]
    cpi = sys.argv[4]
    section = sys.argv[5]

    set_active_session(session)

    course_cfg = {
        'name': '概率论与数理统计',
        'courseid': courseid,
        'clazzid': clazzid,
        'cpi': cpi,
    }

    solver = ChapterQuizSolver(course_cfg, dry_run=False, grade_only=True)

    # ── Navigate to course + chapter tab ──
    solver.open_course()
    time.sleep(4)

    # ── Check if chapter tree loaded ──
    # The chapter tree loads in a studentcourse iframe after clicking 章节
    # Use JS to check for actual iframe presence (snapshot text check unreliable)
    js_check_iframe = """
    async (page) => {
        const frames = page.frames();
        for (const f of frames) {
            if (f.url().includes('studentcourse')) return 'found';
        }
        return 'not-found';
    }
    """
    ck_tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(SCRIPT_DIR), encoding='utf-8')
    ck_tmp.write(js_check_iframe)
    ck_tmp.close()
    try:
        raw = pw_run_code_file(ck_tmp.name, timeout=10)
        iframe_check = pw_extract_result(raw)
        log(f'Chapter tree check: {iframe_check}')
    finally:
        os.unlink(ck_tmp.name)

    # ── Retry if chapter tree not loaded ──
    if iframe_check != 'found':
        log('Chapter tree not detected, retrying open_course...')
        solver.open_course()
        time.sleep(4)

    # ── Navigate to section ──
    ok = solver.navigate_to_section(section)
    time.sleep(5)

    # Wait for quiz iframe to load (nested iframes inside studentstudy page)
    js_wait_quiz = """
    async (page) => {
        // Wait up to 10s for quiz content to appear in any frame
        for (let i = 0; i < 20; i++) {
            for (const f of page.frames()) {
                try {
                    const cnt = await f.locator('.TiMu').count();
                    if (cnt > 0) return 'quiz-found:' + cnt;
                } catch(e) {}
            }
            await page.waitForTimeout(500);
        }
        return 'quiz-not-found';
    }
    """
    wt_tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(SCRIPT_DIR), encoding='utf-8')
    wt_tmp.write(js_wait_quiz)
    wt_tmp.close()
    try:
        raw_w = pw_run_code_file(wt_tmp.name, timeout=20)
        quiz_wait = pw_extract_result(raw_w)
        log(f'Quiz wait result: {quiz_wait}')
    finally:
        os.unlink(wt_tmp.name)

    # ── Diagnostics ──
    snap_final = pw_snapshot()
    has_iframe = 'studentcourse' in snap_final or 'mooc2-ans' in snap_final
    has_timu = '.TiMu' in snap_final or 'question' in snap_final.lower() or quiz_wait.startswith('quiz-found')
    print(f'NAV_OK:{ok}|has_iframe={has_iframe}|has_quiz={has_timu}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
