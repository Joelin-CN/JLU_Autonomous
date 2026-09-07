"""
Quiz accuracy tracker — per-quiz stats, JSON persistence, summary reports.

Self-contained module: only imports from stdlib and chaoxing.constants/logging_setup.
Zero dependencies on other quiz modules.
"""

import json
import re
import time
import datetime
from pathlib import Path

from ...constants import TMP_DIR, OUTPUT_DIR
from ...logging_setup import log


class QuizStats:
    """Track per-quiz accuracy and persist cumulative stats to JSON.

    Records each attempt: AI answer, actual score, correct answers (if parsed),
    question type breakdown, retry count, and Doubao mode used.
    """

    def __init__(self, course_name: str):
        self.course_name = course_name
        self.started_at = datetime.datetime.now().isoformat()
        self.records: list[dict] = []
        self._stats_dir = Path(TMP_DIR)  # OUTPUT_DIR for persistent stats
        self._stats_file = Path(OUTPUT_DIR) / f"_quiz_stats_{self._sanitize(course_name)}.json"
        self._stats_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    @staticmethod
    def _sanitize(name: str) -> str:
        """Sanitize course name for filename."""
        return re.sub(r'[^\w一-鿿\-]', '_', name).strip('_') or "unknown"

    def record_attempt(self, section_key: str, total_questions: int,
                       ai_answers: list[dict], score: int | None,
                       correct_answers: list[dict] | None = None,
                       retry_count: int = 0, mode: str = "text",
                       ai_raw: str = ""):
        """Record one quiz attempt.

        Args:
            section_key: e.g. "1.6 章节测试1"
            total_questions: Number of questions in the quiz
            ai_answers: AI's answer list [{index, answer}, ...]
            score: Percentage score after submission (None if unknown)
            correct_answers: Parsed correct answers from answer view (if available)
            retry_count: How many retries were needed (0 = first try)
            mode: "text" or "image"
            ai_raw: Raw AI response (for debugging)
        """
        # Determine per-question correctness if we have both AI and correct answers
        per_question = []
        if correct_answers and ai_answers:
            correct_map = {a.get("index"): a.get("answer") for a in correct_answers}
            for ai in ai_answers:
                idx = ai.get("index")
                ai_ans = ai.get("answer")
                exp = correct_map.get(idx)
                is_correct = self._answers_match(ai_ans, exp)
                per_question.append({
                    "index": idx,
                    "ai_answer": ai_ans,
                    "expected": exp,
                    "correct": is_correct,
                })

        # Count question types if we can infer from answers
        q_types = self._infer_question_types(ai_answers)

        record = {
            "section": section_key,
            "total_questions": total_questions,
            "ai_answers": ai_answers,
            "score": score,
            "correct_answers": correct_answers,
            "retry_count": retry_count,
            "mode": mode,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "per_question": per_question,
            "question_types": q_types,
            "ai_raw_preview": ai_raw[:200] if ai_raw else "",
        }
        self.records.append(record)
        # Cap records to prevent unbounded memory growth across retries
        if len(self.records) > 200:
            self.records = self.records[-200:]
        self._save()
        log(f"  [Stats] Recorded {section_key}: score={score}%, "
            f"retries={retry_count}, mode={mode}")

    @staticmethod
    def _answers_match(ai, expected) -> bool | None:
        """Check if AI answer matches expected. Returns None if unknown."""
        if ai is None or expected is None:
            return None
        if ai == expected:
            return True
        if isinstance(ai, list) and isinstance(expected, list):
            return set(ai) == set(expected)
        return False

    @staticmethod
    def _infer_question_types(answers: list[dict]) -> dict:
        """Infer question types from answer format."""
        types = {"single": 0, "multi": 0, "judge": 0, "essay": 0, "fill": 0}
        for a in answers:
            ans = a.get("answer", "")
            if isinstance(ans, list) and len(ans) > 0:
                types["multi"] += 1
            elif isinstance(ans, str):
                if ans in ("正确", "错误", "对", "错", "True", "False", "true", "false"):
                    types["judge"] += 1
                elif len(ans) == 1 and ans.isalpha() and ans.isascii():
                    types["single"] += 1
                elif len(ans) > 20:
                    types["essay"] += 1
                else:
                    types["fill"] += 1
        return types

    def summary(self) -> dict:
        """Return cumulative accuracy summary."""
        total = len(self.records)
        # NOTE: do NOT early-return a minimal dict when total == 0. print_summary
        # (and callers) read total_questions, avg_score, perfect_sections,
        # total_retries, mode_usage, records, etc. unconditionally — a short dict
        # caused a KeyError (Issue C) whenever a course produced no successful
        # records (e.g. every quiz failed). Every aggregation below is guarded
        # for the empty case (`if scores else 0`, `if total else 0`,
        # `if q_total else 0`), so falling through yields a complete dict of
        # zeros and the full key set is always present.
        scores = [r["score"] for r in self.records if r["score"] is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        perfect = sum(1 for s in scores if s >= 100)
        passing = sum(1 for s in scores if s is not None and s >= 60)

        total_retries = sum(r["retry_count"] for r in self.records)
        total_questions = sum(r["total_questions"] for r in self.records)

        # Per-question accuracy (only available when correct_answers parsed)
        q_correct = 0
        q_total = 0
        for r in self.records:
            for pq in r.get("per_question", []):
                q_total += 1
                if pq.get("correct"):
                    q_correct += 1

        # Aggregate question types
        type_stats = {"single": 0, "multi": 0, "judge": 0, "essay": 0, "fill": 0}
        type_correct = dict(type_stats)
        for r in self.records:
            for pq in r.get("per_question", []):
                if not pq.get("correct"):
                    continue
                idx = pq.get("index")
                # Find the answer to determine type
                ai_ans = r.get("ai_answers", [])
                for a in ai_ans:
                    if a.get("index") == idx:
                        t = self._classify_answer(a.get("answer", ""))
                        type_stats[t] = type_stats.get(t, 0) + 1
                        type_correct[t] = type_correct.get(t, 0) + 1
                        break

        # Mode stats
        text_count = sum(1 for r in self.records if r.get("mode") == "text")
        image_count = sum(1 for r in self.records if r.get("mode") == "image")

        return {
            "course": self.course_name,
            "total_quizzes": total,
            "total_questions": total_questions,
            "avg_score": round(avg_score, 1),
            "perfect_sections": perfect,
            "passing_sections": passing,
            "total_retries": total_retries,
            "avg_retries": round(total_retries / total, 1) if total else 0,
            "per_question_accuracy": f"{q_correct}/{q_total}" if q_total else "N/A",
            "per_question_pct": round(q_correct / q_total * 100, 1) if q_total else 0,
            "question_types": type_stats,
            "question_types_correct": type_correct,
            "mode_usage": {"text": text_count, "image": image_count},
            "records": self.records,
        }

    @staticmethod
    def _classify_answer(answer) -> str:
        """Classify a single answer into a question type."""
        if isinstance(answer, list):
            return "multi"
        if isinstance(answer, str):
            if answer in ("正确", "错误", "对", "错"):
                return "judge"
            if len(answer) == 1 and answer.isalpha():
                return "single"
            if len(answer) > 20:
                return "essay"
            return "fill"
        return "unknown"

    def print_summary(self):
        """Print a formatted summary to the log."""
        s = self.summary()
        log(f"\n{'='*60}")
        log(f"ACCURACY REPORT: {s['course']}")
        log(f"{'='*60}")
        log(f"  Sections attempted:  {s['total_quizzes']}")
        log(f"  Total questions:     {s['total_questions']}")
        log(f"  Average score:       {s['avg_score']}%")
        log(f"  Perfect sections:    {s['perfect_sections']}/{s['total_quizzes']}")
        log(f"  Total retries:       {s['total_retries']} (avg {s['avg_retries']}/section)")
        if s['per_question_accuracy'] != "N/A":
            log(f"  Question accuracy:   {s['per_question_accuracy']} ({s['per_question_pct']}%)")
        log(f"  Mode usage:          text={s['mode_usage']['text']}, image={s['mode_usage']['image']}")

        # Per-question-type breakdown
        qtypes = s.get('question_types', {})
        qtypes_correct = s.get('question_types_correct', {})
        if any(qtypes.values()):
            log(f"  By question type:")
            for t in ["single", "multi", "judge", "fill", "essay"]:
                total_t = qtypes.get(t, 0)
                if total_t == 0:
                    continue
                correct_t = qtypes_correct.get(t, 0)
                log(f"    {t:8s}: {correct_t}/{total_t} correct")

        # Per-section breakdown
        log(f"\n  Per-section breakdown:")
        for r in s['records']:
            status = "✓" if (r.get('score') or 0) >= 100 else "✗"
            log(f"    {status} {r['section']}: {r['score']}% "
                f"(retries={r['retry_count']}, mode={r['mode']}, "
                f"q={r['total_questions']})")

        log(f"{'='*60}")

    def _load(self):
        """Load existing stats from JSON file."""
        if self._stats_file.exists():
            try:
                data = json.loads(self._stats_file.read_text(encoding="utf-8"))
                self.records = data.get("records", [])
                if data.get("course_name") == self.course_name:
                    log(f"  [Stats] Loaded {len(self.records)} existing records")
            except (json.JSONDecodeError, KeyError):
                self.records = []

    def _save(self):
        """Persist stats to JSON file."""
        data = {
            "course_name": self.course_name,
            "started_at": self.started_at,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "records": self.records,
        }
        self._stats_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
