"""Phase B partial E2E test: V2 screenshot + batched solving (no submission).

The quiz has expired so we cannot submit, but we can test:
  1. _capture_question_screenshots_v2() on all 30 questions
  2. _solve_batched() sending to AI Tab1
  3. Answer quality analysis

Usage:
    python _test_phase_b.py
"""
import sys
import json
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import log
from chapter_quiz_solver import ChapterQuizSolver


def main():
    config_path = Path(__file__).parent / "chaoxing_config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    course_cfg = cfg["courses"][0]  # 概率论与数理统计
    print(f"Course: {course_cfg['name']}")
    print(f"CourseID: {course_cfg['courseid']}")

    solver = ChapterQuizSolver(course_cfg, dry_run=False)

    # ── Step A: Capture all 30 question screenshots ──
    print("\n" + "=" * 60)
    print("Step A: _capture_question_screenshots_v2()")
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
    print(f"\nCapture completed in {t1 - t0:.1f}s")
    print(f"Total questions: {len(q_infos)}")

    # Summarize metadata
    success = [q for q in q_infos if q.get("path") and os.path.exists(q["path"])]
    failed = [q for q in q_infos if not q.get("path") or not os.path.exists(q["path"])]
    print(f"Screenshots captured: {len(success)}/{len(q_infos)}")

    if failed:
        print("Failed questions:")
        for q in failed:
            print(f"  Q{q['index']}: {q.get('error', 'no path')}")

    # Show image distribution
    img_counts = [q.get("img_count", 0) for q in q_infos]
    print(f"Image counts per question: {img_counts}")
    print(f"Total images: {sum(img_counts)}")
    print(f"Questions with images: {sum(1 for c in img_counts if c > 0)}")

    # Show qtype distribution
    from collections import Counter
    qtypes = Counter(q.get("qtype", "unknown") for q in q_infos)
    print(f"Question types: {dict(qtypes)}")

    # Show text previews (first 5)
    print("\nText previews (first 5):")
    for q in q_infos[:5]:
        print(f"  Q{q['index']}: [{q['qtype']}] qid={q['qid']} imgs={q['img_count']} "
              f"text={q['text_preview'][:80] if q['text_preview'] else '(no text)'}")

    if not success:
        print("\nNo screenshots to solve — aborting")
        return

    # ── Step B: Batch solve via AI Tab1 ──
    print("\n" + "=" * 60)
    print("Step B: _solve_batched() → AI Tab1")
    print("=" * 60)
    t2 = time.time()

    section_key = "1.6 章节测试1"
    try:
        answers = solver._solve_batched(q_infos, batch_size=5, section_key=section_key)
    except Exception as e:
        print(f"SOLVE EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

        # Clean up screenshots
        for q in q_infos:
            p = q.get("path", "")
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except:
                    pass
        return

    t3 = time.time()
    print(f"\nSolving completed in {t3 - t2:.1f}s")
    print(f"Total answers: {len(answers)}")

    # ── Step C: Report answers ──
    print("\n" + "=" * 60)
    print("Answers:")
    print("=" * 60)
    for a in answers:
        idx = a.get("index", a.get("question_index", "?"))
        ans = a.get("answer", "?")
        qtype = qtypes.get(idx, "unknown") if isinstance(idx, int) else "?"
        print(f"  Q{idx:2d} [{qtype:7s}]: {ans}")

    # Summary statistics
    letter_answers = sum(1 for a in answers
                        if isinstance(a.get("answer"), str) and len(a.get("answer", "")) == 1)
    multi_answers = sum(1 for a in answers
                       if isinstance(a.get("answer"), list))
    unknown_answers = sum(1 for a in answers
                         if a.get("answer") == "?" or a.get("answer") is None)
    print(f"\nAnswer types: {letter_answers} single-letter, {multi_answers} multi, "
          f"{unknown_answers} unknown")

    # Save answers for future reference
    output_path = Path(__file__).parent / f"_phase_b_answers_{int(time.time())}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "course": course_cfg["name"],
            "section": section_key,
            "total_questions": len(q_infos),
            "capture_time_s": round(t1 - t0, 1),
            "solve_time_s": round(t3 - t2, 1),
            "total_time_s": round(t3 - t0, 1),
            "q_metadata": q_infos,
            "answers": answers,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}")

    # ── Clean up screenshots ──
    print("\nCleaning up screenshots...")
    for q in q_infos:
        p = q.get("path", "")
        if p and os.path.exists(p):
            try:
                os.unlink(p)
            except:
                pass
    print("Done.")


if __name__ == "__main__":
    main()
