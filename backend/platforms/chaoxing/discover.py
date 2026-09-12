"""
Course discovery — dynamic scanning and configuration building.

Scans the Chaoxing platform for unfinished courses, maps chapter trees,
and builds dynamic course config dicts for the orchestrator.

Extracted from scripts/chaoxing_orchestrator.py.
"""

import json
import threading
from pathlib import Path

from core.constants import OUTPUT_DIR
from core.config import load_config, cfg
from core.session import _get_active_session
from core.logging_setup import log, progress
from .platform.scanner import scan_courses, scan_course_sections


def _current_account_index() -> int:
    """Best-effort account index from the worker thread name.

    Threads are named ``chaoxing-account-{index}`` in
    orchestrator.run_multi_account. Falls back to 0 (single-account /
    main thread).
    """
    tname = threading.current_thread().name
    if tname.startswith("chaoxing-account-"):
        try:
            return int(tname.split("-")[-1])
        except ValueError:
            pass
    return 0


def course_matches_filter(course: dict, filter_tokens: list[str],
                          account_index: int) -> bool:
    """Whether a discovered course matches any filter token.

    Token forms (the frontend sends ``Course.id`` = ``"N:courseid"``):
      - ``"N:courseid"`` — account-prefixed id. Matches only when
        ``N == account_index`` AND ``courseid == course['courseid']``.
        The account check matters: a courseid is course-level on Chaoxing,
        so two accounts enrolled in the same course share it — without the
        prefix check, account 2 would wrongly pick up account 1's selection.
      - ``"courseid"`` — bare courseid, exact match (legacy / no prefix).
      - ``"<name substring>"`` — legacy course-name substring match.
    """
    cid = str(course.get("courseid", ""))
    name = course.get("name", "")
    for tok in filter_tokens:
        if ":" in tok:
            prefix, _, rest = tok.partition(":")
            if prefix.isdigit():
                if int(prefix) == account_index and rest == cid:
                    return True
                # prefixed token for a different account — skip, don't
                # fall through to the name/courseid match below.
                continue
        if tok == cid or (tok and tok in name) or tok == name:
            return True
    return False


def _split_filter(course_filter: str) -> list[str]:
    """Split a comma-joined --courses filter into trimmed tokens."""
    return [t.strip() for t in course_filter.split(",") if t.strip()]


def build_dynamic_course_config(course_info: dict, sections: dict) -> dict:
    """Build a course config dict from dynamic scan results.

    Args:
        course_info: from scan_courses() — {name, courseid, clazzid, cpi, done, total, percent, teacher}
        sections:    from scan_course_sections() — {done, total, quiz_sections, content_sections, chapters}

    Returns:
        A dict compatible with ChapterQuizSolver and ChapterContentBot.
    """
    ch_list = sections.get("chapters", [])

    # Build chapters in ContentBot-compatible format
    chapters_for_bot = []
    for ch in ch_list:
        tasks_per = [s.get("tasks", 0) for s in ch.get("sections", [])]
        chapters_for_bot.append({
            "num": ch.get("num"),
            "name": ch.get("name", ""),
            "sections": ch.get("sections_count", len(ch.get("sections", []))),
            "tasks_per": tasks_per,
        })

    # Drop already-completed quizzes from the work list. The scanner flags each
    # section's is_complete (catalog_state contains icon_yiwanc); a completed
    # quiz serves Chaoxing's 已批阅 (selectWorkQuestionYiPiYue) review template,
    # whose option DOM the filler can't act on — navigating to it just wastes
    # time and logs spurious DOM misses. The content side already skips via
    # tasks=0; this is the quiz-side equivalent. A submitted quiz has nothing to
    # do regardless of run mode, so this filter is unconditional.
    all_quiz = sections.get("quiz_sections", [])
    remaining_quiz = [s for s in all_quiz if not s.get("is_complete")]
    skipped_quiz = len(all_quiz) - len(remaining_quiz)
    if skipped_quiz:
        log(f"  Skipping {skipped_quiz} already-completed quiz section(s); "
            f"{len(remaining_quiz)} remain")

    return {
        "name": course_info["name"],
        "courseid": course_info["courseid"],
        "clazzid": course_info["clazzid"],
        "cpi": course_info.get("cpi", "415409200"),
        "current_progress": sections.get("done", course_info.get("done", 0)),
        "total_tasks": sections.get("total", course_info.get("total", 0)),
        "remaining_quiz_sections": remaining_quiz,
        "remaining_content_sections": sections.get("content_sections", []),
        "chapters": chapters_for_bot,
    }


def discover_courses(course_filter: str = None) -> list[dict]:
    """Discover unfinished courses dynamically.

    1. scan_courses() — find all unfinished courses
    2. For each course, scan_course_sections() — map the chapter tree
    3. Build dynamic config dicts for the orchestrator

    Args:
        course_filter: Optional course name substring to filter by.

    Returns:
        List of course config dicts ready for process_course().
    """
    log("=" * 60)
    log("Phase 0: Discovering unfinished courses...")
    log("=" * 60)

    course_infos = scan_courses()
    if not course_infos:
        log("No unfinished courses found!", "WARN")
        return []

    acct_idx = _current_account_index()

    if course_filter:
        tokens = _split_filter(course_filter)
        filtered = [
            c for c in course_infos
            if course_matches_filter(c, tokens, acct_idx)
        ]
        if not filtered:
            log(f"No course matching '{course_filter}' in discovered list", "WARN")
            log(f"Available: {[c['name'] for c in course_infos]}")
            return []
        course_infos = filtered

    log(f"\nFound {len(course_infos)} unfinished course(s):")
    for i, c in enumerate(course_infos):
        pct_str = f"{c['percent']}%" if c['total'] > 0 else "0/0 (no tasks)"
        log(f"  [{i+1}] {c['name']}: {c['done']}/{c['total']} ({pct_str})"
            f"  teacher={c.get('teacher', '?')}")

    # Determine account index from thread name for progress reporting
    _acct_idx = acct_idx

    dynamic_courses = []
    for i, info in enumerate(course_infos):
        # The listing card's "任务点进度" is unreliable: 0/0 can mean
        # "no tasks", "fully completed", or "has tasks but the card failed to
        # render progress". Only a real chapter-tree scan can tell them apart,
        # so scan 0/0 courses too instead of assuming they are empty.
        is_zero_listing = info.get("total", 0) == 0
        if is_zero_listing:
            log(f"[{i+1}/{len(course_infos)}] {info['name']}: 0/0 on listing "
                f"— scanning sections to determine real state")

        progress(_acct_idx, f"Scanning: {info['name']}", i + 1, len(course_infos))
        log(f"[{i+1}/{len(course_infos)}] Scanning sections: {info['name']}...")
        sections = scan_course_sections(
            info["courseid"], info["clazzid"], info.get("cpi", "415409200")
        )
        if not sections.get("ok", True):
            log(f"  Failed to scan sections: {sections.get('reason', '?')}", "ERROR")
            if is_zero_listing:
                # Keep a placeholder so the course stays visible/retryable.
                dynamic_courses.append(build_dynamic_course_config(info, {
                    "ok": True, "done": 0, "total": 0,
                    "quiz_sections": [], "content_sections": [],
                    "chapters": [],
                }))
            continue

        done = sections.get("done", 0)
        total = sections.get("total", 0)
        if is_zero_listing and total > 0 and done >= total:
            log(f"  -> actually completed ({done}/{total}), "
                f"excluding from work list")
            continue

        config_dict = build_dynamic_course_config(info, sections)

        q_count = len(sections.get("quiz_sections", []))
        c_count = len(sections.get("content_sections", []))
        ch_count = len(sections.get("chapters", []))
        log(f"  -> {ch_count} chapters, {q_count} quiz + {c_count} content sections")

        dynamic_courses.append(config_dict)

    return dynamic_courses


def save_discovered_state(courses: list[dict], *, merge: bool = False):
    """Save dynamically discovered courses for --resume support.

    Uses per-session file when multi-account is active.

    merge=True keeps courses from a previous full scan that the current run
    did not touch. A course-filtered run (user picked specific courses, or a
    retry subset) otherwise overwrites the file with its subset and the
    untouched courses silently vanish from the atlas until the next full
    scan — real data loss from the user's perspective.
    """
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    session = _get_active_session()
    suffix = f"_{session}" if session and session != "chaoxing-chrome" else ""
    state_path = output_dir / f"discovered_courses{suffix}.json"
    if merge and state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            by_id = {c.get("courseid"): c for c in existing if isinstance(c, dict)}
            for c in courses:
                by_id[c.get("courseid")] = c
            courses = list(by_id.values())
        except Exception as e:
            log(f"Merging discovery state failed ({e}) — overwriting instead",
                "WARN")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)
    log(f"Saved {len(courses)} discovered courses to {state_path}")
