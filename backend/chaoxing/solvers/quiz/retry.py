"""
Retry logic — score checking, answer-view parsing, re-solving, capping.

Implements the retry loop: check score after submission, view correct answers
if available, click retry button, re-fill with best available answers, and
recurse into solve_quiz() as needed up to MAX_RETRY_DEPTH.
"""

import time

from ...config import cfg
from ...logging_setup import log
from ...browser.engine import pw_snapshot, pw_click
from ...utils import find_ref_by_text
from .submitter import _parse_score
from .grader import _parse_correct_answers


def _retry_quiz(solver, section: dict, retry_depth: int = 0) -> bool:
    """Retry a quiz after a failed attempt.

    Strategy (in order of preference):
    1. Click "查看答案" to see correct answers → parse them → click "重试" → fill correct answers
    2. Click "重试" directly → re-solve with AI
    3. Fall back with known correct answers if we parsed them

    Args:
        solver: The ChapterQuizSolver instance (for calling solve_quiz and _fill_and_submit).
        section: Section dict with 'section' and 'name' keys.
        retry_depth: Current recursion depth.
    """
    max_retries = cfg("retry.quiz_max_retries", 10)
    section_num = section["section"]
    section_name = section["name"]

    for attempt in range(1, max_retries + 1):
        correct_answers = None  # Fresh each iteration — reset across retry attempts
        log(f"  [{section_num}] Retry attempt {attempt}/{max_retries} (depth={retry_depth})")
        time.sleep(2)
        snap = pw_snapshot()

        # ── Priority 1: View correct answers, then retry with them ──
        view_answers_ref = (
            find_ref_by_text(snap, "查看答案") or
            find_ref_by_text(snap, "查看解析") or
            find_ref_by_text(snap, "参考答案")
        )
        if view_answers_ref and correct_answers is None:
            pw_click(view_answers_ref)
            time.sleep(3)
            answer_snap = pw_snapshot()
            correct_answers = _parse_correct_answers(answer_snap)
            if correct_answers:
                log(f"  [{section_num}] Parsed {len(correct_answers)} correct answers from answer view")
            else:
                log(f"  [{section_num}] Could not parse correct answers from answer view", "WARN")
            # Continue loop to find retry button

        # ── Priority 2: Click retry and fill with best available answers ──
        retry_ref = (
            find_ref_by_text(snap, "重试") or
            find_ref_by_text(snap, "再做一次") or
            find_ref_by_text(snap, "重新作答") or
            find_ref_by_text(snap, "再来一次") or
            find_ref_by_text(snap, "重新答题")
        )
        if retry_ref:
            pw_click(retry_ref)
            time.sleep(3)

            if correct_answers:
                # Use correct answers from answer view
                log(f"  [{section_num}] Filling with correct answers from answer view")
                if solver._fill_and_submit(correct_answers):
                    time.sleep(2)
                    result_snap = pw_snapshot()
                    score = _parse_score(result_snap)
                    log(f"  [{section_num}] Retry score (with correct answers): {score}%")
                    if score is not None and score >= cfg("retry.quiz_target_score", 100):
                        log(f"  [{section_num}] PASSED with correct answers!", "OK")
                        solver.tracker.mark_section_done(solver.name, f"{section_num} {section_name}")
                        solver.stats["solved"] += 1
                        solver.quiz_stats.record_attempt(
                            f"{section_num} {section_name}",
                            len(correct_answers), correct_answers, score,
                            correct_answers=correct_answers,
                            retry_count=retry_depth + attempt, mode="corrected")
                        return True
                    # If still failing, loop to try again
                    continue
            else:
                # No correct answers yet — re-solve with AI
                log(f"  [{section_num}] Re-solving with AI...")
                return solver.solve_quiz(section, retry_depth + 1)

        # ── Priority 3: If we have correct answers but no retry button ──
        # (e.g. the quiz might auto-reset after viewing answers)
        if correct_answers:
            # Look for a fresh quiz form directly
            if solver._fill_and_submit(correct_answers):
                time.sleep(2)
                result_snap = pw_snapshot()
                score = _parse_score(result_snap)
                if score is not None and score >= cfg("retry.quiz_target_score", 100):
                    log(f"  [{section_num}] PASSED on direct refill!", "OK")
                    solver.tracker.mark_section_done(solver.name, f"{section_num} {section_name}")
                    solver.stats["solved"] += 1
                    solver.quiz_stats.record_attempt(
                        f"{section_num} {section_name}",
                        len(correct_answers), correct_answers, score,
                        correct_answers=correct_answers,
                        retry_count=retry_depth + attempt, mode="corrected")
                    return True

        # No retry button and no correct answers to try — stuck
        if not retry_ref and not view_answers_ref:
            log(f"  [{section_num}] No retry or view-answers button found", "WARN")
            break

    solver.stats["failed"] += 1
    return False
