"""Tests for chaoxing.solvers.quiz.grader — grading and answer parsing."""
import json
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.solvers.quiz.grader import (
    _parse_grade_answer,
    _parse_correct_answers,
    _grade_batched,
)


# ── _parse_grade_answer ──────────────────────────────────────────

VALID_GRADE_JSON = """[
    {"index": 1, "selected": "A", "is_correct": true,
     "correct_answer": "A", "explanation": "正确，概率取值在[0,1]区间"},
    {"index": 2, "selected": ["B", "D"], "is_correct": true,
     "correct_answer": ["B", "D"], "explanation": "泊松和几何分布都是离散的"},
    {"index": 3, "selected": "B", "is_correct": false,
     "correct_answer": "A", "explanation": "选错了，应该是A"}
]"""

VALID_GRADE_JSON_0BASED = """[
    {"index": 0, "selected": "A", "is_correct": true,
     "correct_answer": "A", "explanation": "Q1"},
    {"index": 1, "selected": "B", "is_correct": false,
     "correct_answer": "C", "explanation": "Q2"},
    {"index": 2, "selected": "D", "is_correct": true,
     "correct_answer": "D", "explanation": "Q3"}
]"""

VALID_GRADE_JSON_WITH_FENCE = """```json
[
    {"index": 1, "selected": "A", "is_correct": true,
     "correct_answer": "A", "explanation": "correct"}
]
```"""

INVALID_JSON = "这不是JSON格式的响应，AI可能返回了文本描述。"

PARTIAL_JSON = """前面的说明文字...
[
    {"index": 1, "selected": "A", "is_correct": true,
     "correct_answer": "A", "explanation": "正确"}
]
...后面的总结"""


class TestParseGradeAnswer:
    """Tests for _parse_grade_answer — extracting JSON grading arrays."""

    def test_parses_valid_json_array(self):
        """Should parse a clean JSON array of grading results."""
        result = _parse_grade_answer(VALID_GRADE_JSON)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["index"] == 1
        assert result[0]["is_correct"] is True
        assert result[1]["selected"] == ["B", "D"]

    def test_parses_json_with_markdown_fence(self):
        """Should strip markdown code fences before parsing."""
        result = _parse_grade_answer(VALID_GRADE_JSON_WITH_FENCE)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["index"] == 1

    def test_parses_json_embedded_in_text(self):
        """Should extract JSON array from surrounding text via bracket tracking."""
        result = _parse_grade_answer(PARTIAL_JSON)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["index"] == 1

    def test_invalid_json_returns_empty_list(self):
        """Should return empty list for unparseable text."""
        result = _parse_grade_answer(INVALID_JSON)
        assert result == []

    def test_empty_string_returns_empty_list(self):
        """Should return empty list for empty string."""
        result = _parse_grade_answer("")
        assert result == []

    def test_non_list_json_returns_empty(self):
        """Should return empty list if JSON is not a list."""
        result = _parse_grade_answer('{"key": "value"}')
        assert result == []

    def test_empty_json_list_returns_empty(self):
        """Should return empty list if JSON array is empty."""
        result = _parse_grade_answer("[]")
        assert result == []

    def test_list_of_non_dicts_returns_empty(self):
        """Should return empty list if JSON array contains non-dicts."""
        result = _parse_grade_answer('[1, 2, 3]')
        assert result == []

    def test_preserves_all_grading_fields(self):
        """Should keep is_correct, correct_answer, selected, explanation."""
        result = _parse_grade_answer(VALID_GRADE_JSON)
        first = result[0]
        assert "is_correct" in first
        assert "correct_answer" in first
        assert "selected" in first
        assert "explanation" in first

    def test_0_based_json_parsed_correctly(self):
        """Should also parse 0-based index JSON."""
        result = _parse_grade_answer(VALID_GRADE_JSON_0BASED)
        assert len(result) == 3
        assert result[0]["index"] == 0


# ── _parse_correct_answers ───────────────────────────────────────

SNAPSHOT_PATTERN1 = """- generic [ref=e1]:
  - text: 1. 正确答案：A
  - text: 选项解释内容
- generic [ref=e2]:
  - text: 2. 正确答案：B
- generic [ref=e3]:
  - text: 3. 正确答案：C
"""

SNAPSHOT_PATTERN2 = """- generic [ref=e1]:
  - radio "对" [checked]
  - radio "错"
- generic [ref=e2]:
  - radio "对"
  - radio "错" [checked]
"""

SNAPSHOT_PATTERN3 = """- generic [ref=e1]:
  - text: 1-5：ABCDB
"""

SNAPSHOT_PATTERN4 = """- generic [ref=e1]:
  - text: 第1题 正确答案：D
  - text: 第2题 正确答案：B
"""


class TestParseCorrectAnswers:
    """Tests for _parse_correct_answers — parsing answer-view snapshots."""

    def test_parses_pattern1_correct_answer_colon(self):
        """Should parse '1. 正确答案：A' pattern."""
        result = _parse_correct_answers(SNAPSHOT_PATTERN1)
        assert result is not None
        assert len(result) == 3
        assert result[0] == {"index": 1, "answer": "A"}
        assert result[1] == {"index": 2, "answer": "B"}
        assert result[2] == {"index": 3, "answer": "C"}

    def test_parses_pattern2_checked_radios(self):
        """Should parse checked radio buttons."""
        result = _parse_correct_answers(SNAPSHOT_PATTERN2)
        assert result is not None
        assert len(result) == 2
        assert result[0] == {"index": 1, "answer": "对"}
        assert result[1] == {"index": 2, "answer": "错"}

    def test_parses_pattern3_sequence(self):
        """Should parse '1-5：ABCDB' range pattern."""
        result = _parse_correct_answers(SNAPSHOT_PATTERN3)
        assert result is not None
        assert len(result) == 5
        assert result[0] == {"index": 1, "answer": "A"}
        assert result[1] == {"index": 2, "answer": "B"}
        assert result[4] == {"index": 5, "answer": "B"}

    def test_parses_pattern4_di_ti(self):
        """Should parse '第1题 正确答案：D' pattern."""
        result = _parse_correct_answers(SNAPSHOT_PATTERN4)
        assert result is not None
        assert len(result) == 2
        assert result[0]["index"] == 1
        assert result[0]["answer"] == "D"
        assert result[1]["index"] == 2
        assert result[1]["answer"] == "B"

    def test_no_match_returns_none(self):
        """Should return None when no patterns match."""
        result = _parse_correct_answers("这是普通的页面文本，没有答案信息")
        assert result is None

    def test_empty_snapshot_returns_none(self):
        """Should return None for empty snapshot."""
        result = _parse_correct_answers("")
        assert result is None

    def test_result_is_list_of_dicts(self):
        """Result should be a list of dicts with 'index' and 'answer' keys."""
        result = _parse_correct_answers(SNAPSHOT_PATTERN1)
        assert isinstance(result, list)
        for item in result:
            assert "index" in item
            assert "answer" in item
            assert isinstance(item["index"], int)


# ── _grade_batched index remapping ───────────────────────────────

class TestGradeBatchedIndexRemapping:
    """Tests for _grade_batched index remapping logic (E5 fix)."""

    @patch("chaoxing.solvers.quiz.grader.ai_grade_quiz_image")
    @patch("chaoxing.solvers.quiz.grader._parse_grade_answer")
    def test_0_based_remapping(
        self, mock_parse, mock_ai_grade
    ):
        """0-based AI responses should be remapped correctly.

        Batch covers global questions 3-5. AI returns indices 0,1,2.
        After remapping: 3,4,5.
        """
        filled_infos = [
            {"index": 3, "path": "/tmp/q3.png", "qid": "123", "qtype": "single"},
            {"index": 4, "path": "/tmp/q4.png", "qid": "124", "qtype": "single"},
            {"index": 5, "path": "/tmp/q5.png", "qid": "125", "qtype": "single"},
        ]
        ai_answers = [
            {"index": 3, "answer": "A"},
            {"index": 4, "answer": "B"},
            {"index": 5, "answer": "C"},
        ]

        # AI returns 0-based indices: 0, 1, 2 for batch positions
        grade_response = [
            {"index": 0, "selected": "A", "is_correct": True,
             "correct_answer": "A", "explanation": "ok"},
            {"index": 1, "selected": "B", "is_correct": True,
             "correct_answer": "B", "explanation": "ok"},
            {"index": 2, "selected": "C", "is_correct": True,
             "correct_answer": "C", "explanation": "ok"},
        ]

        mock_ai_grade.return_value = json.dumps(grade_response)
        mock_parse.return_value = [dict(g) for g in grade_response]  # Deep copy

        result = _grade_batched(filled_infos, ai_answers, batch_size=3,
                                section_key="1.1")

        assert result["accuracy"] == 100.0
        # Check that indices were remapped: 0->3, 1->4, 2->5
        per_q = result["per_question"]
        indices = [q["index"] for q in per_q]
        assert indices == [3, 4, 5], f"Expected [3,4,5], got {indices}"

    @patch("chaoxing.solvers.quiz.grader.ai_grade_quiz_image")
    @patch("chaoxing.solvers.quiz.grader._parse_grade_answer")
    def test_1_based_remapping(
        self, mock_parse, mock_ai_grade
    ):
        """1-based AI responses should be remapped correctly.

        Batch covers global questions 6-8. AI returns indices 1,2,3.
        After remapping: 6,7,8 (offset = 6 - 1 = 5).
        """
        filled_infos = [
            {"index": 6, "path": "/tmp/q6.png", "qid": "126", "qtype": "single"},
            {"index": 7, "path": "/tmp/q7.png", "qid": "127", "qtype": "single"},
            {"index": 8, "path": "/tmp/q8.png", "qid": "128", "qtype": "single"},
        ]
        ai_answers = [
            {"index": 6, "answer": "A"},
            {"index": 7, "answer": "B"},
            {"index": 8, "answer": "C"},
        ]

        # AI returns 1-based indices: 1, 2, 3 for batch positions
        grade_response = [
            {"index": 1, "selected": "D", "is_correct": False,
             "correct_answer": "A", "explanation": "wrong"},
            {"index": 2, "selected": "B", "is_correct": True,
             "correct_answer": "B", "explanation": "ok"},
            {"index": 3, "selected": "C", "is_correct": True,
             "correct_answer": "C", "explanation": "ok"},
        ]

        mock_ai_grade.return_value = json.dumps(grade_response)
        mock_parse.return_value = [dict(g) for g in grade_response]

        result = _grade_batched(filled_infos, ai_answers, batch_size=3,
                                section_key="1.2")

        # Accuracy: 2/3 = 66.7%
        assert result["accuracy"] == pytest.approx(66.7, abs=0.1)
        assert result["correct"] == 2
        assert result["incorrect"] == 1

        # Check that indices were remapped: 1->6, 2->7, 3->8
        per_q = result["per_question"]
        indices = [q["index"] for q in per_q]
        assert indices == [6, 7, 8], f"Expected [6,7,8], got {indices}"

    @patch("chaoxing.solvers.quiz.grader.ai_grade_quiz_image")
    @patch("chaoxing.solvers.quiz.grader._parse_grade_answer")
    def test_first_batch_no_remapping_needed(
        self, mock_parse, mock_ai_grade
    ):
        """When batch starts at index 1 with 1-based AI response, no remapping."""
        filled_infos = [
            {"index": 1, "path": "/tmp/q1.png", "qid": "1", "qtype": "single"},
            {"index": 2, "path": "/tmp/q2.png", "qid": "2", "qtype": "single"},
        ]
        ai_answers = [
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "B"},
        ]

        grade_response = [
            {"index": 1, "selected": "A", "is_correct": True,
             "correct_answer": "A", "explanation": "ok"},
            {"index": 2, "selected": "B", "is_correct": True,
             "correct_answer": "B", "explanation": "ok"},
        ]

        mock_ai_grade.return_value = json.dumps(grade_response)
        mock_parse.return_value = [dict(g) for g in grade_response]

        result = _grade_batched(filled_infos, ai_answers, batch_size=2,
                                section_key="1.1")

        # Indices should remain 1, 2 (no remapping needed)
        per_q = result["per_question"]
        indices = [q["index"] for q in per_q]
        assert indices == [1, 2], f"Expected [1,2], got {indices}"

    @patch("chaoxing.solvers.quiz.grader.ai_grade_quiz_image")
    @patch("chaoxing.solvers.quiz.grader._parse_grade_answer")
    def test_empty_parse_returns_zero_accuracy(
        self, mock_parse, mock_ai_grade
    ):
        """When _parse_grade_answer returns empty, accuracy should be 0."""
        filled_infos = [
            {"index": 1, "path": "/tmp/q1.png", "qid": "1", "qtype": "single"},
        ]
        ai_answers = [
            {"index": 1, "answer": "A"},
        ]

        mock_ai_grade.return_value = "invalid response"
        mock_parse.return_value = []

        result = _grade_batched(filled_infos, ai_answers, batch_size=1,
                                section_key="1.1")

        assert result["accuracy"] == 0.0
        assert result["correct"] == 0
        assert result["incorrect"] == 0
        assert result["passed"] is False

    @patch("chaoxing.solvers.quiz.grader.ai_grade_quiz_image")
    @patch("chaoxing.solvers.quiz.grader._parse_grade_answer")
    def test_no_valid_paths_returns_zero_accuracy(
        self, mock_parse, mock_ai_grade
    ):
        """When no screenshots have valid paths, should return 0 accuracy."""
        filled_infos = [
            {"index": 1, "path": "", "qid": "1", "qtype": "single"},
        ]
        ai_answers = []

        result = _grade_batched(filled_infos, ai_answers, batch_size=1,
                                section_key="1.1")

        assert result["accuracy"] == 0.0
        assert result["total"] == 1

    @patch("chaoxing.solvers.quiz.grader.ai_grade_quiz_image")
    @patch("chaoxing.solvers.quiz.grader._parse_grade_answer")
    def test_ai_exception_does_not_crash(
        self, mock_parse, mock_ai_grade
    ):
        """AI exception should be caught and not crash the grader."""
        filled_infos = [
            {"index": 1, "path": "/tmp/q1.png", "qid": "1", "qtype": "single"},
        ]
        ai_answers = [
            {"index": 1, "answer": "A"},
        ]

        mock_ai_grade.side_effect = Exception("Network timeout")

        # Should not raise
        result = _grade_batched(filled_infos, ai_answers, batch_size=1,
                                section_key="1.1")

        assert result["accuracy"] == 0.0
        assert result["total"] == 1

    @patch("chaoxing.solvers.quiz.grader.ai_grade_quiz_image")
    @patch("chaoxing.solvers.quiz.grader._parse_grade_answer")
    def test_all_uncertain_returns_zero_accuracy(
        self, mock_parse, mock_ai_grade
    ):
        """When all answers are uncertain (is_correct=None), accuracy = 0."""
        filled_infos = [
            {"index": 1, "path": "/tmp/q1.png", "qid": "1", "qtype": "single"},
            {"index": 2, "path": "/tmp/q2.png", "qid": "2", "qtype": "single"},
        ]
        ai_answers = [
            {"index": 1, "answer": "?"},
            {"index": 2, "answer": "?"},
        ]

        grade_response = [
            {"index": 1, "selected": "unclear", "is_correct": None,
             "correct_answer": "?", "explanation": "看不清"},
            {"index": 2, "selected": "unclear", "is_correct": None,
             "correct_answer": "?", "explanation": "图片模糊"},
        ]

        mock_ai_grade.return_value = json.dumps(grade_response)
        mock_parse.return_value = [dict(g) for g in grade_response]

        result = _grade_batched(filled_infos, ai_answers, batch_size=2,
                                section_key="1.1")

        assert result["accuracy"] == 0.0
        assert result["correct"] == 0
        assert result["incorrect"] == 0
        assert result["uncertain"] == 2


# ── Grade result structure ───────────────────────────────────────

class TestGradeResultStructure:
    """Verify _grade_batched returns the expected dict structure."""

    @patch("chaoxing.solvers.quiz.grader.ai_grade_quiz_image")
    @patch("chaoxing.solvers.quiz.grader._parse_grade_answer")
    def test_result_has_all_required_keys(
        self, mock_parse, mock_ai_grade
    ):
        """Result dict should contain all expected keys."""
        filled_infos = [
            {"index": 1, "path": "/tmp/q1.png", "qid": "1", "qtype": "single"},
        ]
        ai_answers = [{"index": 1, "answer": "A"}]

        grade_response = [
            {"index": 1, "selected": "A", "is_correct": True,
             "correct_answer": "A", "explanation": "ok"},
        ]
        mock_ai_grade.return_value = json.dumps(grade_response)
        mock_parse.return_value = [dict(g) for g in grade_response]

        result = _grade_batched(filled_infos, ai_answers, batch_size=1,
                                section_key="1.1")

        assert "accuracy" in result
        assert "total" in result
        assert "correct" in result
        assert "incorrect" in result
        assert "uncertain" in result
        assert "per_question" in result
        assert "passed" in result
        assert isinstance(result["accuracy"], (int, float))
        assert isinstance(result["passed"], bool)
