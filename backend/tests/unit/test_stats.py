"""Tests for chaoxing.solvers.quiz.stats — QuizStats accuracy tracker."""
import json
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.solvers.quiz.stats import QuizStats


# ── Helpers ────────────────────────────────────────────────────

def _mock_path_ops():
    """Return mocks for Path operations used by QuizStats.__init__."""
    mocks = {
        "exists": MagicMock(return_value=False),
        "mkdir": MagicMock(),
        "read_text": MagicMock(),
        "write_text": MagicMock(),
    }
    return mocks


# ── Sanitize ───────────────────────────────────────────────────

class TestSanitize:
    """Tests for QuizStats._sanitize — course name filename sanitization."""

    def test_ascii_name_unchanged(self):
        """ASCII-only names should pass through unchanged."""
        assert QuizStats._sanitize("calculus") == "calculus"

    def test_chinese_name_unchanged(self):
        """Chinese names should pass through unchanged."""
        assert QuizStats._sanitize("概率论与数理统计") == "概率论与数理统计"

    def test_special_chars_replaced(self):
        """Special characters should be replaced with underscores."""
        result = QuizStats._sanitize("math:101/section")
        assert ":" not in result
        assert "/" not in result
        assert "_" in result

    def test_spaces_replaced(self):
        """Spaces should be replaced with underscores."""
        result = QuizStats._sanitize("my course name")
        assert " " not in result
        assert "_" in result

    def test_empty_string_returns_unknown(self):
        """Empty name should return 'unknown'."""
        assert QuizStats._sanitize("") == "unknown"

    def test_all_special_chars_returns_unknown(self):
        """Name with only special characters should return 'unknown'."""
        result = QuizStats._sanitize("!@#$%")
        assert result == "unknown"

    def test_mixed_alphanumeric_and_special(self):
        """Mixed alphanumeric and special characters should preserve alphanumeric."""
        result = QuizStats._sanitize("Course (2024)")
        assert "Course" in result
        assert "2024" in result

    def test_leading_trailing_underscores_stripped(self):
        """Leading and trailing underscores from replacement should be stripped."""
        result = QuizStats._sanitize("!!!test!!!")
        assert not result.startswith("_")
        assert not result.endswith("_")
        assert "test" in result

    def test_hyphen_preserved(self):
        """Hyphens should be preserved in the sanitized name."""
        result = QuizStats._sanitize("course-name-v2")
        assert "-" in result


# ── Answers Match ──────────────────────────────────────────────

class TestAnswersMatch:
    """Tests for QuizStats._answers_match — answer comparison logic."""

    def test_both_none_returns_none(self):
        """When both answers are None, should return None (unknown)."""
        assert QuizStats._answers_match(None, None) is None

    def test_ai_none_returns_none(self):
        """When AI answer is None, should return None regardless of expected."""
        assert QuizStats._answers_match(None, "A") is None

    def test_expected_none_returns_none(self):
        """When expected is None, should return None regardless of AI answer."""
        assert QuizStats._answers_match("A", None) is None

    def test_exact_string_match(self):
        """Exact string match should return True."""
        assert QuizStats._answers_match("A", "A") is True

    def test_string_mismatch(self):
        """String mismatch should return False."""
        assert QuizStats._answers_match("A", "B") is False

    def test_list_match_same_order(self):
        """Matching lists in same order should return True."""
        assert QuizStats._answers_match(["A", "B"], ["A", "B"]) is True

    def test_list_match_different_order(self):
        """Matching lists in different order should return True (set comparison)."""
        assert QuizStats._answers_match(["B", "A"], ["A", "B"]) is True

    def test_list_mismatch(self):
        """Non-matching lists should return False."""
        assert QuizStats._answers_match(["A", "B"], ["A", "C"]) is False

    def test_list_different_lengths(self):
        """Lists of different lengths should return False."""
        assert QuizStats._answers_match(["A", "B"], ["A", "B", "C"]) is False

    def test_string_vs_list(self):
        """String vs list comparison should return False."""
        assert QuizStats._answers_match("A", ["A"]) is False

    def test_boolean_true_vs_string(self):
        """Boolean values are not compared specially — should handle gracefully."""
        result = QuizStats._answers_match(True, "True")
        assert result is False


# ── Infer Question Types ───────────────────────────────────────

class TestInferQuestionTypes:
    """Tests for QuizStats._infer_question_types — type inference from answers."""

    def test_empty_answers_returns_zeros(self):
        """Empty answers list should return all-zero type counts."""
        result = QuizStats._infer_question_types([])
        assert result == {"single": 0, "multi": 0, "judge": 0, "essay": 0, "fill": 0}

    def test_single_choice_detected(self):
        """Single-letter ASCII answers should be classified as 'single'."""
        result = QuizStats._infer_question_types([{"answer": "A"}])
        assert result["single"] == 1
        assert result["multi"] == 0

    def test_multi_choice_detected(self):
        """List answers should be classified as 'multi'."""
        result = QuizStats._infer_question_types([{"answer": ["A", "B", "C"]}])
        assert result["multi"] == 1

    def test_judge_cn_correct(self):
        """Chinese '正确' should be classified as 'judge'."""
        result = QuizStats._infer_question_types([{"answer": "正确"}])
        assert result["judge"] == 1

    def test_judge_cn_wrong(self):
        """Chinese '错误' should be classified as 'judge'."""
        result = QuizStats._infer_question_types([{"answer": "错误"}])
        assert result["judge"] == 1

    def test_judge_cn_dui(self):
        """Chinese '对' should be classified as 'judge'."""
        result = QuizStats._infer_question_types([{"answer": "对"}])
        assert result["judge"] == 1

    def test_judge_cn_cuo(self):
        """Chinese '错' should be classified as 'judge'."""
        result = QuizStats._infer_question_types([{"answer": "错"}])
        assert result["judge"] == 1

    def test_judge_en_true(self):
        """English 'True' should be classified as 'judge'."""
        result = QuizStats._infer_question_types([{"answer": "True"}])
        assert result["judge"] == 1

    def test_judge_en_false(self):
        """English 'false' should be classified as 'judge'."""
        result = QuizStats._infer_question_types([{"answer": "false"}])
        assert result["judge"] == 1

    def test_essay_detected(self):
        """Long string answers (>20 chars) should be classified as 'essay'."""
        result = QuizStats._infer_question_types(
            [{"answer": "这是一个很长的答案，包含超过二十个字符的文本内容"}]
        )
        assert result["essay"] == 1

    def test_fill_detected(self):
        """Short non-letter, non-judge answers should be classified as 'fill'."""
        result = QuizStats._infer_question_types([{"answer": "0.5"}])
        assert result["fill"] == 1

    def test_mixed_question_types(self):
        """Multiple answers of different types should be counted correctly."""
        answers = [
            {"answer": "A"},
            {"answer": ["B", "C"]},
            {"answer": "正确"},
            {"answer": "这是一个需要详细论述的简答题答案内容所以要超过二十个字符"},
            {"answer": "42"},
        ]
        result = QuizStats._infer_question_types(answers)
        assert result["single"] == 1
        assert result["multi"] == 1
        assert result["judge"] == 1
        assert result["essay"] == 1
        assert result["fill"] == 1

    def test_answer_key_missing(self):
        """Answers without 'answer' key should default to empty string (classified as fill)."""
        result = QuizStats._infer_question_types([{"index": 1}])
        # Empty string falls through to 'fill' in the type classifier
        assert result["single"] == 0
        assert result["multi"] == 0
        assert result["judge"] == 0
        assert result["essay"] == 0
        assert result["fill"] == 1

    def test_empty_list_answer(self):
        """Empty list answer should NOT be counted as multi."""
        result = QuizStats._infer_question_types([{"answer": []}])
        assert result["multi"] == 0

    def test_two_char_string_is_fill(self):
        """A 2-char non-alpha string should be classified as fill."""
        result = QuizStats._infer_question_types([{"answer": "12"}])
        assert result["fill"] == 1


# ── Classify Answer ────────────────────────────────────────────

class TestClassifyAnswer:
    """Tests for QuizStats._classify_answer — single answer type classification."""

    def test_list_is_multi(self):
        """List answer should be 'multi'."""
        assert QuizStats._classify_answer(["A", "B"]) == "multi"

    def test_judge_zh_correct(self):
        """Chinese '正确' should be 'judge'."""
        assert QuizStats._classify_answer("正确") == "judge"

    def test_judge_zh_wrong(self):
        """Chinese '错误' should be 'judge'."""
        assert QuizStats._classify_answer("错误") == "judge"

    def test_single_letter(self):
        """Single ASCII letter should be 'single'."""
        assert QuizStats._classify_answer("A") == "single"
        assert QuizStats._classify_answer("D") == "single"

    def test_long_text_is_essay(self):
        """Text longer than 20 chars should be 'essay'."""
        assert QuizStats._classify_answer("A" * 21) == "essay"

    def test_short_text_is_fill(self):
        """Short non-letter text should be 'fill'."""
        assert QuizStats._classify_answer("3.14") == "fill"

    def test_non_string_non_list_is_unknown(self):
        """Non-string, non-list values should be 'unknown'."""
        assert QuizStats._classify_answer(42) == "unknown"
        assert QuizStats._classify_answer(None) == "unknown"


# ── Record Attempt ─────────────────────────────────────────────

class TestRecordAttempt:
    """Tests for QuizStats.record_attempt — recording and persistence."""

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_record_basic_attempt(self, mock_mkdir, mock_save, mock_load):
        """Should record a basic attempt with score and increment records."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            section_key="1.1 章节测试",
            total_questions=10,
            ai_answers=[{"index": 1, "answer": "A"}, {"index": 2, "answer": "B"}],
            score=80,
        )
        assert len(stats.records) == 1
        assert stats.records[0]["section"] == "1.1 章节测试"
        assert stats.records[0]["total_questions"] == 10
        assert stats.records[0]["score"] == 80
        assert stats.records[0]["mode"] == "text"
        assert stats.records[0]["retry_count"] == 0
        assert mock_save.called

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_record_with_correct_answers(self, mock_mkdir, mock_save, mock_load):
        """Should compute per_question correctness when correct_answers provided."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            section_key="1.1",
            total_questions=3,
            ai_answers=[
                {"index": 1, "answer": "A"},
                {"index": 2, "answer": "B"},
                {"index": 3, "answer": "C"},
            ],
            score=67,
            correct_answers=[
                {"index": 1, "answer": "A"},
                {"index": 2, "answer": "D"},
                {"index": 3, "answer": "C"},
            ],
        )
        record = stats.records[0]
        assert len(record["per_question"]) == 3
        assert record["per_question"][0]["correct"] is True   # A == A
        assert record["per_question"][1]["correct"] is False  # B != D
        assert record["per_question"][2]["correct"] is True   # C == C

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_record_with_retry_count(self, mock_mkdir, mock_save, mock_load):
        """Should track retry_count per attempt."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            section_key="1.2",
            total_questions=5,
            ai_answers=[],
            score=100,
            retry_count=3,
        )
        assert stats.records[0]["retry_count"] == 3

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_record_image_mode(self, mock_mkdir, mock_save, mock_load):
        """Should track mode='image' when specified."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            section_key="1.3",
            total_questions=5,
            ai_answers=[],
            score=90,
            mode="image",
        )
        assert stats.records[0]["mode"] == "image"

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_ai_raw_preview_truncated(self, mock_mkdir, mock_save, mock_load):
        """AI raw response should be truncated to 200 chars."""
        stats = QuizStats("TestCourse")
        long_response = "x" * 500
        stats.record_attempt(
            section_key="1.1",
            total_questions=1,
            ai_answers=[],
            score=None,
            ai_raw=long_response,
        )
        preview = stats.records[0]["ai_raw_preview"]
        assert len(preview) == 200

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_empty_ai_raw(self, mock_mkdir, mock_save, mock_load):
        """Empty AI raw should result in empty preview string."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            section_key="1.1",
            total_questions=1,
            ai_answers=[],
            score=None,
            ai_raw="",
        )
        assert stats.records[0]["ai_raw_preview"] == ""

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_score_none_accepted(self, mock_mkdir, mock_save, mock_load):
        """Score=None should be accepted (unknown score)."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            section_key="1.1",
            total_questions=5,
            ai_answers=[],
            score=None,
        )
        assert stats.records[0]["score"] is None

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_timestamp_is_set(self, mock_mkdir, mock_save, mock_load):
        """Each record should have a timestamp."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            section_key="1.1",
            total_questions=1,
            ai_answers=[],
            score=100,
        )
        assert "timestamp" in stats.records[0]
        assert stats.records[0]["timestamp"]  # non-empty

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_no_correct_answers_no_per_question(self, mock_mkdir, mock_save, mock_load):
        """Without correct_answers, per_question should be empty list."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            section_key="1.1",
            total_questions=3,
            ai_answers=[{"index": 1, "answer": "A"}],
            score=100,
        )
        assert stats.records[0]["per_question"] == []


# ── Summary ────────────────────────────────────────────────────

class TestSummary:
    """Tests for QuizStats.summary — cumulative accuracy reporting."""

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_empty_records_summary(self, mock_mkdir, mock_save, mock_load):
        """Empty records should return total_quizzes=0."""
        stats = QuizStats("TestCourse")
        result = stats.summary()
        assert result["course"] == "TestCourse"
        assert result["total_quizzes"] == 0

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_avg_score_calculation(self, mock_mkdir, mock_save, mock_load):
        """Should correctly calculate average score."""
        stats = QuizStats("TestCourse")
        stats.record_attempt("s1", 10, [], score=80)
        stats.record_attempt("s2", 10, [], score=100)
        result = stats.summary()
        assert result["avg_score"] == 90.0

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_perfect_sections_count(self, mock_mkdir, mock_save, mock_load):
        """Should count sections with score >= 100 as perfect."""
        stats = QuizStats("TestCourse")
        stats.record_attempt("s1", 10, [], score=100)
        stats.record_attempt("s2", 10, [], score=80)
        stats.record_attempt("s3", 10, [], score=100)
        result = stats.summary()
        assert result["perfect_sections"] == 2

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_passing_sections_count(self, mock_mkdir, mock_save, mock_load):
        """Should count sections with score >= 60 as passing."""
        stats = QuizStats("TestCourse")
        stats.record_attempt("s1", 10, [], score=59)
        stats.record_attempt("s2", 10, [], score=60)
        stats.record_attempt("s3", 10, [], score=90)
        result = stats.summary()
        assert result["passing_sections"] == 2  # s2 and s3

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_total_retries_sum(self, mock_mkdir, mock_save, mock_load):
        """Should sum retries across all records."""
        stats = QuizStats("TestCourse")
        stats.record_attempt("s1", 10, [], score=80, retry_count=2)
        stats.record_attempt("s2", 10, [], score=90, retry_count=1)
        result = stats.summary()
        assert result["total_retries"] == 3
        assert result["avg_retries"] == 1.5

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_total_questions_sum(self, mock_mkdir, mock_save, mock_load):
        """Should sum total questions across all records."""
        stats = QuizStats("TestCourse")
        stats.record_attempt("s1", 10, [], score=80)
        stats.record_attempt("s2", 5, [], score=90)
        result = stats.summary()
        assert result["total_questions"] == 15

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_per_question_accuracy_none_when_no_data(self, mock_mkdir, mock_save, mock_load):
        """Without correct_answers, per_question_accuracy should be 'N/A'."""
        stats = QuizStats("TestCourse")
        stats.record_attempt("s1", 10, [], score=80)
        result = stats.summary()
        assert result["per_question_accuracy"] == "N/A"
        assert result["per_question_pct"] == 0

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_per_question_accuracy_calculation(self, mock_mkdir, mock_save, mock_load):
        """Should compute per-question accuracy from correct_answers."""
        stats = QuizStats("TestCourse")
        stats.record_attempt(
            "s1", 3,
            ai_answers=[
                {"index": 1, "answer": "A"},
                {"index": 2, "answer": "B"},
                {"index": 3, "answer": "C"},
            ],
            score=67,
            correct_answers=[
                {"index": 1, "answer": "A"},
                {"index": 2, "answer": "D"},
                {"index": 3, "answer": "C"},
            ],
        )
        result = stats.summary()
        assert result["per_question_accuracy"] == "2/3"
        assert result["per_question_pct"] == pytest.approx(66.7, abs=0.1)

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_mode_usage_stats(self, mock_mkdir, mock_save, mock_load):
        """Should count text vs image mode usage."""
        stats = QuizStats("TestCourse")
        stats.record_attempt("s1", 10, [], score=80, mode="text")
        stats.record_attempt("s2", 10, [], score=90, mode="image")
        stats.record_attempt("s3", 10, [], score=70, mode="text")
        result = stats.summary()
        assert result["mode_usage"]["text"] == 2
        assert result["mode_usage"]["image"] == 1

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_none_scores_excluded_from_avg(self, mock_mkdir, mock_save, mock_load):
        """Scores that are None should be excluded from average calculation."""
        stats = QuizStats("TestCourse")
        stats.record_attempt("s1", 10, [], score=None)
        stats.record_attempt("s2", 10, [], score=100)
        result = stats.summary()
        assert result["avg_score"] == 100.0

    @patch("chaoxing.solvers.quiz.stats.QuizStats._load")
    @patch("chaoxing.solvers.quiz.stats.QuizStats._save")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_question_type_breakdown_in_summary(self, mock_mkdir, mock_save, mock_load):
        """Summary should include question_types and question_types_correct when records exist."""
        stats = QuizStats("TestCourse")
        stats.records = [{
            "section": "s1",
            "score": 100,
            "total_questions": 1,
            "retry_count": 0,
            "mode": "text",
            "per_question": [],
        }]
        result = stats.summary()
        assert "question_types" in result
        assert "question_types_correct" in result
        for t in ["single", "multi", "judge", "essay", "fill"]:
            assert t in result["question_types"]


# ── Load / Save ────────────────────────────────────────────────

class TestPersistence:
    """Tests for QuizStats._load and QuizStats._save."""

    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_load_non_existent_file(self, mock_mkdir):
        """When JSON file does not exist, records should stay as-is."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False

        stats = QuizStats("TestCourse")
        stats._stats_file = mock_path
        stats.records = []
        stats._load()
        assert stats.records == []

    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_load_valid_json(self, mock_mkdir):
        """Should load existing records from a valid JSON file."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        existing_data = {
            "course_name": "TestCourse",
            "records": [
                {"section": "s1", "score": 100},
            ],
        }
        mock_path.read_text.return_value = json.dumps(existing_data, ensure_ascii=False)

        stats = QuizStats("TestCourse")
        stats._stats_file = mock_path
        stats.records = []
        stats._load()
        assert len(stats.records) == 1
        assert stats.records[0]["score"] == 100

    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_load_invalid_json(self, mock_mkdir):
        """Invalid JSON should result in empty records."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "not valid json {{{"

        stats = QuizStats("TestCourse")
        stats._stats_file = mock_path
        stats.records = [{"old": "data"}]
        stats._load()
        assert stats.records == []  # Cleared on JSON error

    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_save_writes_json(self, mock_mkdir):
        """_save should write serialized records to the JSON file."""
        mock_path = MagicMock()

        stats = QuizStats("TestCourse")
        stats._stats_file = mock_path
        stats.records = [{"section": "s1", "score": 90}]
        stats._save()
        mock_path.write_text.assert_called_once()
        written_text = mock_path.write_text.call_args[0][0]
        data = json.loads(written_text)
        assert data["course_name"] == "TestCourse"
        assert len(data["records"]) == 1
        assert data["records"][0]["score"] == 90

    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_started_at_and_updated_at_in_save(self, mock_mkdir):
        """_save should include started_at and updated_at fields."""
        mock_path = MagicMock()

        stats = QuizStats("TestCourse")
        stats._stats_file = mock_path
        stats.records = []
        stats._save()
        written_text = mock_path.write_text.call_args[0][0]
        data = json.loads(written_text)
        assert "started_at" in data
        assert "updated_at" in data

    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_load_mismatched_course_name(self, mock_mkdir):
        """When JSON course_name differs, records are still loaded (log is skipped)."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        existing_data = {
            "course_name": "DifferentCourse",
            "records": [{"section": "s1", "score": 50}],
        }
        mock_path.read_text.return_value = json.dumps(existing_data, ensure_ascii=False)

        stats = QuizStats("TestCourse")
        stats._stats_file = mock_path
        stats.records = [{"original": "data"}]
        stats._load()
        # Records are loaded from file regardless of course_name match
        assert len(stats.records) == 1
        assert stats.records[0]["section"] == "s1"


# ── Print Summary ──────────────────────────────────────────────

class TestPrintSummary:
    """Tests for QuizStats.print_summary — formatted output."""

    @patch("chaoxing.solvers.quiz.stats.log")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_print_summary_calls_log(self, mock_mkdir, mock_log):
        """print_summary should call log() multiple times."""
        stats = QuizStats("TestCourse")
        stats.records = [{
            "section": "s1",
            "score": 100,
            "total_questions": 1,
            "retry_count": 0,
            "mode": "text",
            "per_question": [],
        }]
        stats.print_summary()
        assert mock_log.call_count >= 2  # At least header lines

    @patch("chaoxing.solvers.quiz.stats.log")
    @patch("chaoxing.solvers.quiz.stats.Path.mkdir")
    def test_print_summary_with_records(self, mock_mkdir, mock_log):
        """print_summary with records should log per-section breakdown."""
        stats = QuizStats("TestCourse")
        stats.records = [{
            "section": "1.1",
            "score": 90,
            "total_questions": 10,
            "retry_count": 1,
            "mode": "text",
        }]
        stats.print_summary()
        # Should include section breakdown
        found_section = False
        for call in mock_log.call_args_list:
            if "1.1" in str(call):
                found_section = True
                break
        assert found_section, "print_summary should log per-section breakdown"


# ── Initialization ─────────────────────────────────────────────

class TestInitialization:
    """Tests for QuizStats.__init__ — constructor behavior."""

    def test_course_name_stored(self):
        """course_name should be stored on the instance."""
        with patch("chaoxing.solvers.quiz.stats.Path.mkdir"):
            with patch.object(QuizStats, "_load", return_value=None):
                with patch.object(QuizStats, "_save", return_value=None):
                    stats = QuizStats("概率论")
                    assert stats.course_name == "概率论"

    def test_started_at_set(self):
        """started_at should be an ISO format datetime string."""
        with patch("chaoxing.solvers.quiz.stats.Path.mkdir"):
            with patch.object(QuizStats, "_load", return_value=None):
                with patch.object(QuizStats, "_save", return_value=None):
                    stats = QuizStats("Test")
                    assert stats.started_at
                    assert "T" in stats.started_at  # ISO format

    def test_records_initialized_empty(self):
        """records should start as an empty list (when no file exists)."""
        with patch("chaoxing.solvers.quiz.stats.Path.mkdir"):
            with patch.object(QuizStats, "_load", return_value=None):
                with patch.object(QuizStats, "_save", return_value=None):
                    stats = QuizStats("Test")
                    assert stats.records == []

    def test_stats_dir_created(self):
        """_stats_dir should be created on init."""
        mock_mkdir = MagicMock()
        with patch("chaoxing.solvers.quiz.stats.Path.mkdir", mock_mkdir):
            with patch.object(QuizStats, "_load", return_value=None):
                with patch.object(QuizStats, "_save", return_value=None):
                    QuizStats("Test")
                    assert mock_mkdir.called
