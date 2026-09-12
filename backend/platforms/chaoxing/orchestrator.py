"""
Chaoxing Auto-Course Orchestrator — multi-thread dispatch and course processing.

Top-level coordination layer:
    - Multi-account multi-threaded execution
    - Course discovery -> quiz solving -> content completion pipeline
    - Progress tracking, resume support, graceful shutdown

This is the canonical implementation. All real logic lives here.

Entry point: chaoxing/api.py (JSON-line protocol for frontend-backend communication).
"""
import time
import json
import threading
from pathlib import Path

from core.constants import OUTPUT_DIR, SHUTDOWN_FLAG, CHROME_PROFILES_DIR
from core.config import load_config, get_config
from core.session import set_active_session, _get_active_session
from core.logging_setup import (
    log, progress, check_signals, log_exception, phase, emit_memory,
)
from core import memory
from core.memory import (
    MemoryMonitor, MemorySamplerError, gate_open, measure_project_chrome_gb,
    PER_ACCOUNT_INITIAL_GB,
)
from core.browser.engine import pw_snapshot, pw_goto, pw_click
from .platform.navigation import pw_goto_course
from .platform.auth import (
    read_all_chaoxing_credentials,
    is_chaoxing_browser_open,
    chaoxing_login,
    close_chaoxing_browser,
)
from .platform.scanner import scan_courses, scan_course_sections
from core.utils import find_ref_by_text, parse_progress_from_snapshot, human_delay
from core.tracking import ProgressTracker
from .discover import (
    build_dynamic_course_config,
    discover_courses,
    save_discovered_state,
)
from .solvers.quiz.solver import ChapterQuizSolver
from .solvers.content.bot import ChapterContentBot


# ══════════════════════════════════════════════════════════════════
#  Session / Login helpers
# ══════════════════════════════════════════════════════════════════

# 泳道硬失败异常已上收到 core；再导出保持 chaoxing.orchestrator.AccountRunError 可用
from core.orchestrator import AccountRunError  # noqa: E402,F401  (re-export)


# ── core 编排机钩子（ModuleRunner 惰性读取；函数体在调用时解析全局，
#    因此对 chaoxing.orchestrator.* 的 monkeypatch 全部生效）─────────

def run_account(account_index, creds, config):
    return run_for_account(account_index, creds, config)


def config_cls(**kwargs):
    """RunConfig 工厂（core 编排机经此构建平台配置对象）。"""
    return RunConfig(**kwargs)


def read_credentials():
    return read_all_chaoxing_credentials()


def close_browser(account_index: int):
    close_chaoxing_browser(account_index)


def session_name(account_index: int) -> str:
    return f"chaoxing-chrome-{account_index}"


def thread_name(account_index: int) -> str:
    return f"chaoxing-account-{account_index}"


def max_concurrent_cfg():
    try:
        return get_config().max_concurrent
    except Exception:
        return None


def ensure_logged_in(account_index: int = 0) -> bool:
    """Verify the browser session is still on the Chaoxing personal space.
    If not logged in, attempt automatic login using stored credentials.

    account_index: which account from passwords/chaoxing.txt (0-based).

    Handles stale sessions: if a session exists but pw_snapshot() fails
    (dead tab, crashed renderer), the old session is discarded and a fresh
    one is created.
    """
    # 0. If no browser session exists at all, create one and login
    if not is_chaoxing_browser_open():
        log(f"No browser session found, attempting auto-login for account [{account_index}]...")
        return chaoxing_login(account_index)

    # 1. Take a snapshot — if it fails, the session is dead
    try:
        snap = pw_snapshot()
    except Exception as e:
        log(f"Browser session appears dead ({e}), re-creating...", "WARN")
        # The session may still be listed by playwright-cli, so close it
        # explicitly before login reopens a fresh one (stale-session fix).
        try:
            close_chaoxing_browser(account_index)
        except Exception:
            pass
        return chaoxing_login(account_index)

    # 2. Check what page we're on
    if "用户登录" in snap or "passport2.chaoxing.com" in snap:
        log("On login page, attempting auto-login...")
        return chaoxing_login(account_index)

    # 3. If we're already on the personal space, great
    # (could also be on a course page — try navigating to personal space)
    if "个人空间" in snap:
        return True

    # 4. Unknown page — try navigating to personal space
    log("Unknown page, navigating to personal space...", "WARN")
    pw_goto("https://i.chaoxing.com/")
    human_delay(3.0, 0.25)
    snap = pw_snapshot()
    if "用户登录" in snap or "passport2" in snap:
        return chaoxing_login(account_index)
    if "个人空间" in snap:
        return True
    return "个人空间" in snap


# ══════════════════════════════════════════════════════════════════
#  Course processing
# ══════════════════════════════════════════════════════════════════

def process_course(course: dict, dry_run: bool = False,
                   quiz_only: bool = False, content_only: bool = False,
                   grade_only: bool = False):
    """Process a single course through appropriate bots.

    quiz_only:    skip content phase (for solve-quiz command)
    content_only: skip quiz phase (for complete-content command)
    grade_only:   "simulation" mode — quizzes are solved, answers filled and
                  screenshotted, then AI-graded WITHOUT submitting; content
                  sections navigate + detect type but are not completed. Used
                  by the frontend "模拟运行" toggle. Distinct from dry_run
                  (which is a pure skip).
    """
    name = course["name"]
    mode_tag = ""
    if grade_only:
        mode_tag = " [GRADE-ONLY/模拟]"
    elif quiz_only:
        mode_tag = " [QUIZ-ONLY]"
    elif content_only:
        mode_tag = " [CONTENT-ONLY]"

    log(f"\n{'#'*60}")
    log(f"# Processing: {name}{mode_tag}")
    log(f"{'#'*60}")

    # Honor a STOP that arrived while the previous course was running so the
    # thread's finally-block (browser close) runs promptly instead of waiting
    # for the parent's SIGTERM escalation.
    check_signals()

    # Check if course is already completed in progress tracker
    tracker = ProgressTracker()
    if tracker.state["completed_courses"] and name in tracker.state["completed_courses"]:
        log(f"Course {name} already marked complete in tracker, skipping")
        return

    has_quizzes = bool(course.get("remaining_quiz_sections"))
    has_content = bool(course.get("chapters"))

    # Phase 1: Solve quizzes (skip if content-only)
    if has_quizzes and not content_only:
        log(f"\n--- Phase 1: Solving quizzes for {name} ---")
        # grade_only routes to the solver's "fill + screenshot + AI-grade, no
        # submit" path; dry_run (pure skip) is kept separate.
        solver = ChapterQuizSolver(course, dry_run=dry_run, grade_only=grade_only)
        solver.run()
    elif has_quizzes and content_only:
        log(f"\n--- Phase 1: SKIPPED (content-only mode) — "
            f"{len(course.get('remaining_quiz_sections', []))} quiz sections ignored ---")

    check_signals()

    # Phase 2: Complete content sections (skip if quiz-only)
    if has_content and not quiz_only:
        log(f"\n--- Phase 2: Completing content for {name} ---")
        bot = ChapterContentBot(course, dry_run=dry_run, grade_only=grade_only)
        bot.run()
    elif has_content and quiz_only:
        log(f"\n--- Phase 2: SKIPPED (quiz-only mode) — "
            f"{len(course.get('chapters', []))} chapters ignored ---")

    # Check if course reached 100% (skip for dry_run and grade_only — neither
    # actually submits, so a 100% check would always fail and waste time).
    if not dry_run and not grade_only:
        log(f"Verifying final progress for {name}...")
        pw_goto_course(course["courseid"], course["clazzid"],
                       course.get("cpi", "415409200"))
        time.sleep(3)

        # Click 章节
        snap = pw_snapshot()
        chapter_ref = find_ref_by_text(snap, "章节")
        if chapter_ref:
            pw_click(chapter_ref)
            time.sleep(2)

        snap = pw_snapshot()
        done, total = parse_progress_from_snapshot(snap)
        log(f"Final progress: {done}/{total}")

        if done >= total and total > 0:
            log(f"[DONE] Course {name} COMPLETED!", "OK")
            tracker.mark_course_done(name)


# ══════════════════════════════════════════════════════════════════
#  Per-account orchestration
# ══════════════════════════════════════════════════════════════════

def run_for_account(account_index: int, creds: dict, args):
    """Run the full orchestrator for a single Chaoxing account.

    Sets the active session to chaoxing-chrome-N, logs in, discovers and
    processes courses. All state is isolated per-session.
    """
    session_name = f"chaoxing-chrome-{account_index}"
    set_active_session(session_name)
    log(f"\n{'='*60}")
    log(f"ACCOUNT [{account_index}]: {creds['account'][:3]}***"
        f"  session={session_name}")
    log(f"{'='*60}")

    # ── Step 1: Ensure logged in ──
    progress(account_index, "Logging in...")
    log(f"[Account {account_index}] Checking browser session...")
    if not ensure_logged_in(account_index):
        if args.dry_run or args.scan_only:
            log(f"[Account {account_index}] Session not ready "
                f"(continuing in dry/scan mode)", "WARN")
        else:
            log(f"[Account {account_index}] Auto-login failed.", "ERROR")
            progress(account_index, "LOGIN FAILED")
            return False
    progress(account_index, "Logged in ✓")

    # ── Step 2: Discover courses ──
    phase("scan_courses")
    if args.resume:
        output_dir = OUTPUT_DIR
        suffix = f"_{session_name}" if session_name != "chaoxing-chrome" else ""
        state_path = output_dir / f"discovered_courses{suffix}.json"
        if state_path.exists():
            with open(state_path, "r", encoding="utf-8") as f:
                dynamic_courses = json.load(f)
            log(f"[Account {account_index}] Resumed with "
                f"{len(dynamic_courses)} courses from {state_path}")
            if args.course:
                from .discover import course_matches_filter, _split_filter
                tokens = _split_filter(args.course)
                dynamic_courses = [
                    c for c in dynamic_courses
                    if course_matches_filter(c, tokens, account_index)
                ]
        else:
            log(f"[Account {account_index}] No saved discovery state, "
                f"scanning fresh...", "WARN")
            dynamic_courses = discover_courses(args.course)
    else:
        dynamic_courses = discover_courses(args.course)

    if not dynamic_courses:
        log(f"[Account {account_index}] No courses to process", "WARN")
        progress(account_index, "No courses (all complete or none found)")
        return

    if args.scan_only:
        log(f"\n{'='*60}")
        log(f"[Account {account_index}] SCAN-ONLY — "
            f"{len(dynamic_courses)} course(s) discovered")
        log(f"{'='*60}")
        for i, c in enumerate(dynamic_courses):
            q_count = len(c.get("remaining_quiz_sections", []))
            ch_count = len(c.get("chapters", []))
            prog = f"{c.get('current_progress', '?')}/{c.get('total_tasks', '?')}"
            tags = []
            if q_count > 0:
                tags.append(f"Quiz×{q_count}")
            if ch_count > 0:
                tags.append(f"Ch×{ch_count}")
            tag_str = f"  [{', '.join(tags)}]" if tags else ""
            log(f"  [{i+1}] {c['name']}: {prog}{tag_str}")
        save_discovered_state(dynamic_courses, merge=bool(args.course))
        progress(account_index, f"DONE — {len(dynamic_courses)} courses",
                 len(dynamic_courses), len(dynamic_courses))
        return True

    # Save discovered state for resume support
    save_discovered_state(dynamic_courses, merge=bool(args.course))

    # ── Step 3: Process courses ──
    total_courses = len(dynamic_courses)
    log(f"\n[Account {account_index}] {'='*60}")
    log(f"[Account {account_index}] Courses to process ({total_courses}):")
    for c in dynamic_courses:
        prog = c.get("current_progress", "?")
        total = c.get("total_tasks", "?")
        has_quiz = "[Quiz]" if c.get("remaining_quiz_sections") else ""
        has_content = "[Content]" if c.get("chapters") else ""
        log(f"  {c['name']}: {prog}/{total} {has_quiz} {has_content}")
    log(f"[Account {account_index}] {'='*60}")

    if args.dry_run:
        log("\n[!] DRY RUN MODE — no actual submissions will be made\n")
    if getattr(args, "grade_only", False):
        log("\n[!] 模拟运行 (GRADE-ONLY) — 做题/填答案/AI 评分,但不提交\n")

    # ── Step 3: Process courses ──
    phase("solve_quiz" if getattr(args, "quiz_only", False) else "process_sections")
    start_time = time.time()
    for i, course in enumerate(dynamic_courses):
        if SHUTDOWN_FLAG.is_set():
            log("Shutdown flag detected, stopping course processing", "WARN")
            save_discovered_state(dynamic_courses, merge=bool(args.course))
            break
        # Pause/stop/RAM-guard yield point (blocks while paused, raises on stop).
        try:
            check_signals()
        except KeyboardInterrupt:
            log("Stop/RAM signal at course boundary. Progress saved.", "WARN")
            save_discovered_state(dynamic_courses, merge=bool(args.course))
            break
        name = course.get("name", "?")
        progress(account_index, f"Processing: {name}", i + 1, total_courses)
        try:
            process_course(course, dry_run=args.dry_run,
                           quiz_only=getattr(args, 'quiz_only', False),
                           content_only=getattr(args, 'content_only', False),
                           grade_only=getattr(args, 'grade_only', False))
            progress(account_index, f"Completed: {name}", i + 1, total_courses)
        except KeyboardInterrupt:
            log("\n[!] Interrupted by user. Progress saved.", "WARN")
            save_discovered_state(dynamic_courses, merge=bool(args.course))
            break
        except Exception as e:
            log(f"Fatal error processing {course['name']}: {e}", "ERROR")
            progress(account_index, f"FAILED: {name}", i + 1, total_courses)
            log_exception(f"Account {account_index}: course '{name}'", exc=e)

    elapsed = time.time() - start_time
    log(f"\n[Account {account_index}] {'='*60}")
    log(f"[Account {account_index}] Finished in {elapsed/60:.1f} minutes")
    log(f"[Account {account_index}] {'='*60}")
    progress(account_index, f"DONE — {total_courses} courses",
             total_courses, total_courses)
    return True


# ══════════════════════════════════════════════════════════════════
#  Multi-threading
# ══════════════════════════════════════════════════════════════════

_GATE_RETRY_SECONDS = 5
_THREAD_STAGGER_SECONDS = 0.5


def _run_account_in_thread(account_index: int, creds: dict, args, semaphore,
                           monitor, budget_gb, initial_estimate_gb,
                           results: list = None, results_lock=None):
    """Compat wrapper（旧签名）— 实现在 core.orchestrator.run_account_in_thread。"""
    import sys as _sys
    from core.orchestrator import ModuleRunner, run_account_in_thread as _core_impl
    _core_impl(ModuleRunner(_sys.modules[__name__]), account_index, creds, args,
               semaphore, monitor, budget_gb, initial_estimate_gb,
               results, results_lock)


class RunConfig:
    """Configuration for a single orchestrator run.

    Replaces the old argparse Namespace. Constructed by api.py from
    CLI args and passed to run_for_account().
    """
    def __init__(self, *, course=None, dry_run=False, resume=False,
                 scan_only=False, quiz_only=False, content_only=False,
                 grade_only=False, yes=True):
        self.course = course
        self.dry_run = dry_run
        self.resume = resume
        self.scan_only = scan_only
        self.quiz_only = quiz_only
        self.content_only = content_only
        self.grade_only = grade_only
        self.yes = yes


def run_multi_account(account_indices: list[int], mode: str = "full",
                      course: str = None, grade_only: bool = False,
                      content_only: bool = False, dry_run: bool = False,
                      resume: bool = False, max_concurrent: int = None,
                      budget_gb: float = None, system_limit_gb: float = None,
                      per_account_estimate_gb: float = None):
    """Run orchestrator for multiple accounts in parallel threads.

    多账号并发/内存门/泳道结果机制已上收到 core.orchestrator
    （run_multi_account_generic）；本模块提供平台钩子（登录/课程处理/
    会话命名）。测试对 chaoxing.orchestrator.* 的 monkeypatch 经
    ModuleRunner 的调用时解析依然生效。
    """
    import sys as _sys
    from core.orchestrator import ModuleRunner, run_multi_account_generic
    runner = ModuleRunner(_sys.modules[__name__])
    return run_multi_account_generic(
        runner, account_indices, mode=mode, course=course,
        grade_only=grade_only, content_only=content_only, dry_run=dry_run,
        resume=resume, max_concurrent=max_concurrent, budget_gb=budget_gb,
        system_limit_gb=system_limit_gb,
        per_account_estimate_gb=per_account_estimate_gb)
