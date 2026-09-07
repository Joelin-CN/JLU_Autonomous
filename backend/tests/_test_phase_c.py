"""Phase C E2E Test: V2 Screenshot + Batched Solving + Fill + AI Grading.

Tests the complete grading pipeline on a single quiz:
  1. Navigate to the quiz section
  2. V2 element.screenshot() capture
  3. Batched AI Tab1 solving
  4. Fill answers into form (no submit)
  5. Screenshot filled state (showing selected answers)
  6. Send filled screenshots to AI for grading
  7. Calculate accuracy, pass if > 80%

Usage:
    python _test_phase_c.py                          # targets first quiz in config
    python _test_phase_c.py --section "1.7"           # target specific section
    python _test_phase_c.py --skip-navigation          # skip nav (already on quiz page)
"""

import sys
import json
import time
import os
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import log, load_config, set_active_session
from chapter_quiz_solver import ChapterQuizSolver


def main():
    parser = argparse.ArgumentParser(description="Phase C E2E Test")
    parser.add_argument("--section", default="1.7",
                        help="Section number to test (default: 1.7)")
    parser.add_argument("--skip-navigation", action="store_true",
                        help="Skip navigation (quiz page already loaded)")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Questions per AI batch (default: 5)")
    parser.add_argument("--session", default=None,
                        help="Playwright session name (e.g. chaoxing-chrome-1)")
    args = parser.parse_args()

    # Set active Playwright session for multi-account support
    if args.session:
        set_active_session(args.session)
        print(f"Session: {args.session}")

    config = load_config()
    course_cfg = config["courses"][0]  # 概率论与数理统计
    print(f"Course: {course_cfg['name']}")
    print(f"Target section: {args.section}")

    solver = ChapterQuizSolver(course_cfg, dry_run=False, grade_only=True)

    # Find the target section
    quizzes = course_cfg.get("remaining_quiz_sections", [])
    target = None
    for q in quizzes:
        if q["section"] == args.section:
            target = q
            break

    if not target:
        print(f"Section {args.section} not found in config quizzes:")
        for q in quizzes:
            print(f"  {q['section']} {q['name']}")
        return

    section_key = f"{target['section']} {target['name']}"
    print(f"Target: {section_key}")

    # ── Step 0: Navigate to course + section ──
    if not args.skip_navigation:
        print("\n" + "=" * 60)
        print("Step 0: Navigate to course and section")
        print("=" * 60)
        solver.open_course()
        time.sleep(2)

        if not solver.navigate_to_section(target["section"]):
            print(f"FAILED: Cannot navigate to section {target['section']}")
            return
        time.sleep(3)

    # ── Step 1: V2 Screenshot Capture ──
    print("\n" + "=" * 60)
    print("Step 1: V2 Screenshot Capture (.TiMu containers)")
    print("=" * 60)
    t0 = time.time()
    try:
        q_infos = solver._capture_question_screenshots_v2()
    except Exception as e:
        print(f"CAPTURE EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return

    t1 = time.time()
    print(f"Capture completed in {t1 - t0:.1f}s")
    print(f"Total questions: {len(q_infos)}")

    success = [q for q in q_infos if q.get("path") and os.path.exists(q["path"])]
    failed = [q for q in q_infos if not q.get("path") or not os.path.exists(q["path"])]
    print(f"Screenshots: {len(success)}/{len(q_infos)}")

    if failed:
        print("Failed questions:")
        for q in failed:
            print(f"  Q{q['index']}: {q.get('error', 'no path')}")

    # Show metadata summary
    from collections import Counter
    qtypes = Counter(q.get("qtype", "unknown") for q in q_infos)
    print(f"Question types: {dict(qtypes)}")

    img_counts = [q.get("img_count", 0) for q in q_infos]
    print(f"Images per question: {img_counts}")
    print(f"Total embedded images: {sum(img_counts)}")

    if not success:
        print("\nNo screenshots to solve — aborting")
        return

    # ── Step 2: Batched AI Solving ──
    print("\n" + "=" * 60)
    print("Step 2: Batched AI Tab1 Solving")
    print("=" * 60)
    t2 = time.time()

    try:
        answers = solver._solve_batched(q_infos, batch_size=args.batch_size,
                                        section_key=section_key)
    except Exception as e:
        print(f"SOLVE EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        # Clean up screenshots
        for q in q_infos:
            p = q.get("path", "")
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass
        return

    t3 = time.time()
    print(f"Solving completed in {t3 - t2:.1f}s")
    print(f"Total answers: {len(answers)}")

    # Print answers
    print("\nAnswers from solving pass:")
    for a in answers:
        idx = a.get("index", a.get("question_index", "?"))
        ans = a.get("answer", "?")
        print(f"  Q{idx:2d}: {ans}")

    # Clean up V2 screenshots (no longer needed)
    for q in q_infos:
        p = q.get("path", "")
        if p and os.path.exists(p):
            try: os.unlink(p)
            except: pass

    # ── Step 3: Fill Answers ──
    print("\n" + "=" * 60)
    print("Step 3: Fill Answers into Form")
    print("=" * 60)
    t4 = time.time()

    try:
        filled_count = solver._fill_answers(answers)
    except Exception as e:
        print(f"FILL EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return

    t5 = time.time()
    print(f"Fill completed in {t5 - t4:.1f}s")
    print(f"Questions filled: {filled_count}/{len(answers)}")

    # Brief pause for DOM to settle after clicks
    time.sleep(1)

    # ── Step 4: Capture Filled State ──
    print("\n" + "=" * 60)
    print("Step 4: Capture Filled State Screenshots")
    print("=" * 60)
    t6 = time.time()

    try:
        filled_infos = solver._capture_filled_screenshots_v2()
    except Exception as e:
        print(f"FILLED CAPTURE EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return

    t7 = time.time()
    print(f"Filled capture completed in {t7 - t6:.1f}s")

    filled_success = [q for q in filled_infos if q.get("path") and os.path.exists(q["path"])]
    print(f"Filled screenshots: {len(filled_success)}/{len(filled_infos)}")

    # Show answer values extracted from hidden inputs
    answered = [q for q in filled_infos if q.get("answer_value", "")]
    print(f"Questions with answer values: {len(answered)}")
    for q in filled_infos[:5]:
        print(f"  Q{q['index']}: answer_value={q.get('answer_value', 'N/A')[:40]} "
              f"indicators={q.get('selected_indicators', 0)}")

    if not filled_success:
        print("\nNo filled screenshots — aborting")
        return

    # ── Step 5: AI Grading ──
    print("\n" + "=" * 60)
    print("Step 5: AI Grading (filled screenshots → accuracy)")
    print("=" * 60)
    t8 = time.time()

    try:
        grade_result = solver._grade_batched(
            filled_infos, answers, batch_size=args.batch_size,
            section_key=section_key)
    except Exception as e:
        print(f"GRADE EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        # Clean up
        for q in filled_infos:
            p = q.get("path", "")
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass
        return

    t9 = time.time()
    print(f"Grading completed in {t9 - t8:.1f}s")

    # ── Step 6: Report ──
    print("\n" + "=" * 60)
    print("GRADE REPORT")
    print("=" * 60)
    print(f"Accuracy:    {grade_result['accuracy']}%")
    print(f"Correct:     {grade_result['correct']}")
    print(f"Incorrect:   {grade_result['incorrect']}")
    print(f"Uncertain:   {grade_result['uncertain']}")
    print(f"Total:       {grade_result['total']}")

    print(f"\nPer-question breakdown:")
    for g in grade_result.get("per_question", []):
        status = "✓" if g.get("is_correct") else ("✗" if g.get("is_correct") is False else "?")
        print(f"  {status} Q{g.get('index', '?')}: selected={g.get('selected', '?')} "
              f"correct={g.get('correct_answer', '?')} "
              f"| {g.get('explanation', '')[:60]}")

    passed = grade_result['accuracy'] >= 80
    print(f"\n{'PASSED!' if passed else 'FAILED'} "
          f"({grade_result['accuracy']}% {'>=' if passed else '<'} 80%)")

    # ── Timing Summary ──
    print(f"\nTiming:")
    print(f"  Capture (blank):  {t1 - t0:.1f}s")
    print(f"  Solve (AI): {t3 - t2:.1f}s")
    print(f"  Fill:             {t5 - t4:.1f}s")
    print(f"  Capture (filled): {t7 - t6:.1f}s")
    print(f"  Grade (AI): {t9 - t8:.1f}s")
    print(f"  TOTAL:            {t9 - t0:.1f}s")

    # ── Save Results ──
    output_dir = Path(__file__).parent / "phase_c_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"_phase_c_grade_{int(time.time())}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "course": course_cfg["name"],
            "section": section_key,
            "total_questions": len(answers),
            "ai_answers": answers,
            "grade_result": {
                "accuracy": grade_result["accuracy"],
                "correct": grade_result["correct"],
                "incorrect": grade_result["incorrect"],
                "uncertain": grade_result["uncertain"],
                "per_question": grade_result.get("per_question", []),
            },
            "timing": {
                "capture_s": round(t1 - t0, 1),
                "solve_s": round(t3 - t2, 1),
                "fill_s": round(t5 - t4, 1),
                "capture_filled_s": round(t7 - t6, 1),
                "grade_s": round(t9 - t8, 1),
                "total_s": round(t9 - t0, 1),
            },
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "passed": passed,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}")

    # ── Clean up filled screenshots ──
    print("\nCleaning up filled screenshots...")
    for q in filled_infos:
        p = q.get("path", "")
        if p and os.path.exists(p):
            try: os.unlink(p)
            except: pass
    print("Done.")

    return grade_result


if __name__ == "__main__":
    main()
