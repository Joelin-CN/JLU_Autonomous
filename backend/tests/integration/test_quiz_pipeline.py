"""
Integration tests for the quiz-solving pipeline.

Tests the full pipeline stages: extract -> solve -> fill -> submit -> grade,
with all browser and AI interactions mocked via unittest.mock.

Pipeline stages:
  1. Extractor   — parse quiz questions from YAML snapshot
  2. Solver/AI   — send questions to AI backend for answers
  3. Filler      — click options / fill blanks in DOM
  4. Submitter   — click submit button and confirm
  5. Grader      — capture filled state screenshots, grade via AI
  6. Retry       — re-attempt on low score, view correct answers
  7. Stats       — per-quiz accuracy tracking and reporting
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.solvers.quiz.extractor import (
    extract_questions_from_snapshot,
    count_questions_in_snapshot,
    _clean_snapshot,
)
from chaoxing.solvers.quiz.strategies import (
    FontDecryptTextStrategy,
    V2ScreenshotStrategy,
    V1ScreenshotStrategy,
    FullPageScreenshotStrategy,
    SnapshotTextStrategy,
    STRATEGY_CHAIN,
)
from chaoxing.solvers.quiz.grader import (
    _grade_batched,
    _parse_correct_answers,
    _parse_grade_answer,
)
from chaoxing.solvers.quiz.submitter import (
    _parse_score,
    _submit_quiz_native,
    _submit_quiz,
)
from chaoxing.solvers.quiz.filler import (
    _fill_answers,
    _is_unanswerable,
)


# ═══════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_tempfile():
    """Create a mock NamedTemporaryFile with a .name attribute.

    All browser-interaction functions in the quiz pipeline write JS code
    to a temp file, then execute it via pw_run_code_file(). This fixture
    replaces tempfile.NamedTemporaryFile so the mock can provide a
    predictable file path.
    """
    mock_file = MagicMock()
    mock_file.name = os.path.join(os.sep, "tmp", "mock_quiz_script.js")
    with patch("tempfile.NamedTemporaryFile", return_value=mock_file):
        yield mock_file


@pytest.fixture
def sample_snapshot():
    """Return a realistic YAML snapshot containing 3 quiz questions.

    Contains the structural noise (URLs, ref markers, box coordinates)
    that the extractor must strip, plus quiz content (questions, options).
    Also includes plain-text lines matching the count regex pattern
    (numbers directly after newline+whitespace).
    """
    return "\n".join([
        "- Page URL: https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/studentcourse",
        "  - generic [ref=e1]:",
        "    - text: 单选题",
        "    - generic [ref=e2] [box=10,20,800,600]:",
        "      - text: 1. What is the capital of France?",
        "      - radio \"A. London\"",
        "      - radio \"B. Paris\" [cursor=pointer]",
        "      - radio \"C. Berlin\"",
        "      - radio \"D. Madrid\"",
        "      - text: 2. Which number is prime? [checked]",
        "      - radio \"A. 4\"",
        "      - radio \"B. 7\" [cursor=pointer]",
        "      - radio \"C. 9\"",
        "      - radio \"D. 12\"",
        "      - text: 3. The Earth is round. (True/False)",
        "      - radio \"正确\"",
        "      - radio \"错误\"",
        # Count-compatible lines: numbers directly after newline+whitespace
        "    1. Paris is in France",
        "    2. The sky is blue",
        "    3. Water boils at 100C",
    ])


@pytest.fixture
def multi_question_snapshot():
    """Return a snapshot with 5 questions for large-pipeline tests."""
    lines = [
        "    1. Question number one",
        "    2. Question number two",
        "    3. Question number three",
        "    4. Question number four",
        "    5. Question number five",
    ]
    return "\n".join(lines)


@pytest.fixture
def single_question_snapshot():
    """Return a snapshot with exactly 1 question in count-compatible format."""
    return "    1. The sky is blue."


@pytest.fixture
def mock_ai_answers():
    """Return AI answers corresponding to the sample_snapshot fixture."""
    return [
        {"index": 1, "answer": "B"},
        {"index": 2, "answer": "B"},
        {"index": 3, "answer": "正确"},
    ]


# ═══════════════════════════════════════════════════════════════════
#  Stage 1: Question Extraction Tests
# ═══════════════════════════════════════════════════════════════════

class TestQuestionExtraction:
    """Verify that quiz questions are correctly extracted from YAML snapshots.

    The extractor must strip structural noise (URLs, ref markers, box
    coordinates, YAML prefixes) while preserving question text, option
    labels, and type markers (单选题, 判断题, etc.).
    """

    def test_extract_questions_from_snapshot_cleans_noise(self, sample_snapshot):
        """Full pipeline with mock AI: extract questions from snapshot.

        Verifies that structural noise is removed and quiz content preserved.
        """
        questions = extract_questions_from_snapshot(sample_snapshot)
        assert len(questions) == 1
        assert questions[0]["type"] == "quiz_full"
        text = questions[0]["text"]

        # Quiz content preserved
        assert "capital of France" in text
        assert "prime" in text or "Which number" in text
        assert "London" in text  # Option text preserved

        # Structural noise stripped
        assert "Page URL" not in text
        assert "generic [ref=" not in text
        assert "[box=" not in text
        assert "[cursor=pointer]" not in text

    def test_count_questions_in_snapshot(self, sample_snapshot):
        """Multiple questions pipeline: count questions correctly."""
        count = count_questions_in_snapshot(sample_snapshot)
        assert count == 3

    def test_count_questions_single(self, single_question_snapshot):
        """Single question pipeline: count returns 1."""
        count = count_questions_in_snapshot(single_question_snapshot)
        assert count == 1

    def test_count_questions_many(self, multi_question_snapshot):
        """Multiple questions (5) counted correctly."""
        count = count_questions_in_snapshot(multi_question_snapshot)
        assert count == 5

    def test_extract_empty_snapshot(self):
        """Extraction failure: empty snapshot returns minimal result.

        The extractor should degrade gracefully rather than crash.
        """
        questions = extract_questions_from_snapshot("")
        assert len(questions) == 1
        assert questions[0]["type"] == "quiz_full"
        assert questions[0]["text"] == ""

    def test_extract_no_quiz_content(self):
        """Extraction failure: snapshot with no quiz questions.

        When the page shows navigation menus but no quiz content,
        the extractor should return minimal output (empty text).
        """
        snap = (
            "- Page URL: https://example.com\n"
            "  - generic [ref=e1]:\n"
            "    - link \"首页\"\n"
            "    - link \"课程\"\n"
        )
        questions = extract_questions_from_snapshot(snap)
        assert questions[0]["type"] == "quiz_full"
        # Text should be minimal/empty since no quiz content present
        cleaned = _clean_snapshot(snap)
        assert len(cleaned) < 50 or "(" not in cleaned

    def test_extract_preserves_chinese_question_types(self):
        """Verify Chinese quiz type markers are preserved in extraction.

        单选题, 多选题, 判断题 should survive the cleaning process.
        """
        snap = (
            "- Page URL: https://test.com\n"
            "  - text: 单选题\n"
            "  - text: 1. 这是一个单选题？\n"
            "  - radio \"A. 选项A\"\n"
            "  - radio \"B. 选项B\"\n"
            "  - text: 判断题\n"
            "  - text: 2. 这是正确的吗？\n"
            "  - radio \"正确\"\n"
            "  - radio \"错误\"\n"
        )
        questions = extract_questions_from_snapshot(snap)
        text = questions[0]["text"]
        assert "单选" in text
        assert "判断" in text
        assert "选项A" in text


# ═══════════════════════════════════════════════════════════════════
#  Stage 2: Answer Filling Tests
# ═══════════════════════════════════════════════════════════════════

class TestAnswerFilling:
    """Verify that answers are correctly dispatched to fill operations.

    The filler must: detect question types, skip unanswerable questions,
    dispatch single-select to click_option, multi-select elements each
    option individually, and blank/essay to fill_blank.
    """

    def test_is_unanswerable_detects_markers(self):
        """_is_unanswerable should detect AI's 'cannot determine' markers."""
        assert _is_unanswerable("unanswerable") is True
        assert _is_unanswerable("无法判断") is True
        assert _is_unanswerable("无法确定") is True
        assert _is_unanswerable("信息不足") is True
        assert _is_unanswerable("data insufficient") is True
        assert _is_unanswerable("cannot determine") is True
        assert _is_unanswerable("not enough info") is True

    def test_is_unanswerable_empty_and_none(self):
        """Empty or None answers are considered unanswerable."""
        assert _is_unanswerable("") is True
        assert _is_unanswerable(None) is True

    def test_is_unanswerable_valid_answers(self):
        """Normal answers are not flagged as unanswerable."""
        assert _is_unanswerable("B") is False
        assert _is_unanswerable("正确") is False
        assert _is_unanswerable("The answer is B") is False

    def test_fill_answers_empty_list(self, mock_tempfile):
        """Filling zero answers returns 0 and does nothing."""
        with patch("chaoxing.solvers.quiz.filler._detect_question_types",
                   return_value=[]):
            result = _fill_answers([])
            assert result == 0

    def test_fill_answers_single_select(self, mock_tempfile):
        """Each single-select question triggers one _click_option call."""
        mock_types = [
            {"index": 1, "type": "single"},
            {"index": 2, "type": "single"},
        ]
        answers = [
            {"index": 1, "answer": "B"},
            {"index": 2, "answer": "C"},
        ]

        with patch(
            "chaoxing.solvers.quiz.filler._detect_question_types",
            return_value=mock_types
        ), patch(
            "chaoxing.solvers.quiz.filler._click_option"
        ) as mock_click, patch(
            "chaoxing.solvers.quiz.filler._fill_blank"
        ):
            result = _fill_answers(answers)
            assert result == 2
            assert mock_click.call_count == 2
            # First call: Q1, "B"; second: Q2, "C"
            mock_click.assert_any_call(1, "B")
            mock_click.assert_any_call(2, "C")

    def test_fill_answers_skips_unanswerable(self, mock_tempfile):
        """AI unanswerable markers cause questions to be skipped."""
        mock_types = [
            {"index": 1, "type": "single"},
            {"index": 2, "type": "single"},
        ]
        answers = [
            {"index": 1, "answer": "unanswerable"},
            {"index": 2, "answer": "C"},
        ]

        with patch(
            "chaoxing.solvers.quiz.filler._detect_question_types",
            return_value=mock_types
        ), patch(
            "chaoxing.solvers.quiz.filler._click_option"
        ) as mock_click, patch(
            "chaoxing.solvers.quiz.filler._fill_blank"
        ):
            result = _fill_answers(answers)
            # Q1 skipped (unanswerable), Q2 filled
            assert result == 1
            assert mock_click.call_count == 1
            mock_click.assert_called_once_with(2, "C")

    def test_fill_answers_multi_select(self, mock_tempfile):
        """Multi-select answers click each option individually."""
        mock_types = [{"index": 1, "type": "multi"}]
        answers = [{"index": 1, "answer": ["A", "C", "D"]}]

        with patch(
            "chaoxing.solvers.quiz.filler._detect_question_types",
            return_value=mock_types
        ), patch(
            "chaoxing.solvers.quiz.filler._click_option"
        ) as mock_click, patch(
            "chaoxing.solvers.quiz.filler._fill_blank"
        ):
            result = _fill_answers(answers)
            assert result == 1
            assert mock_click.call_count == 3

    def test_fill_answers_blank_type(self, mock_tempfile):
        """Fill-in-the-blank questions dispatch to _fill_blank."""
        mock_types = [{"index": 1, "type": "fill"}]
        answers = [{"index": 1, "answer": "Paris"}]

        with patch(
            "chaoxing.solvers.quiz.filler._detect_question_types",
            return_value=mock_types
        ), patch(
            "chaoxing.solvers.quiz.filler._click_option"
        ) as mock_click, patch(
            "chaoxing.solvers.quiz.filler._fill_blank"
        ) as mock_fill:
            mock_fill.return_value = True
            result = _fill_answers(answers)
            assert result == 1
            assert mock_fill.call_count == 1
            # _click_option should NOT be called for fill type (unless fallback)
            assert mock_click.call_count == 0

    def test_fill_answers_blank_fallback(self, mock_tempfile):
        """Fill failure: _fill_blank returns False, triggers _click_option fallback."""
        mock_types = [{"index": 1, "type": "fill"}]
        answers = [{"index": 1, "answer": "Paris"}]

        with patch(
            "chaoxing.solvers.quiz.filler._detect_question_types",
            return_value=mock_types
        ), patch(
            "chaoxing.solvers.quiz.filler._click_option"
        ) as mock_click, patch(
            "chaoxing.solvers.quiz.filler._fill_blank"
        ) as mock_fill:
            mock_fill.return_value = False  # Fill fails
            result = _fill_answers(answers)
            assert result == 1  # Still counted as filled (fallback attempted)
            assert mock_fill.call_count == 1
            assert mock_click.call_count == 1  # Fallback triggered

    def test_fill_answers_mixed_types(self, mock_tempfile):
        """Pipeline with mixed question types dispatches correctly."""
        mock_types = [
            {"index": 1, "type": "single"},
            {"index": 2, "type": "multi"},
            {"index": 3, "type": "judge"},
            {"index": 4, "type": "fill"},
        ]
        answers = [
            {"index": 1, "answer": "B"},
            {"index": 2, "answer": ["A", "B"]},
            {"index": 3, "answer": "正确"},
            {"index": 4, "answer": "text answer"},
        ]

        with patch(
            "chaoxing.solvers.quiz.filler._detect_question_types",
            return_value=mock_types
        ), patch(
            "chaoxing.solvers.quiz.filler._click_option"
        ) as mock_click, patch(
            "chaoxing.solvers.quiz.filler._fill_blank"
        ) as mock_fill:
            mock_fill.return_value = True
            result = _fill_answers(answers)
            assert result == 4
            # Q1 (single): 1 click, Q2 (multi): 2 clicks, Q3 (judge): 1 click,
            # Q4 (fill): 1 fill_blank, 0 clicks = total 4 click calls
            assert mock_click.call_count == 4
            assert mock_fill.call_count == 1


# ═══════════════════════════════════════════════════════════════════
#  Stage 3: Submission Tests
# ═══════════════════════════════════════════════════════════════════

class TestQuizSubmission:
    """Verify score parsing and submit behaviour with mocked browser."""

    def test_parse_score_chinese_format(self):
        """'得分：85' extracts 85."""
        assert _parse_score("得分：85\n题目完成") == 85

    def test_parse_score_percent_format(self):
        """'成绩: 95%' extracts 95."""
        assert _parse_score("成绩: 95%") == 95

    def test_parse_score_with_unit_suffix(self):
        """'100分' extracts 100."""
        assert _parse_score("最终得分 100分") == 100

    def test_parse_score_no_match(self):
        """Submit failure: no score in snapshot returns None."""
        assert _parse_score("提交成功，请查看结果") is None

    def test_parse_score_first_match_wins(self):
        """When multiple patterns match, the first one is used."""
        result = _parse_score("得分 60分 满分100")
        assert result == 60  # "60分" matched first via \d+\s*分

    def test_submit_quiz_native_success(self, mock_tempfile):
        """Native submit via btnBlueSubmit() succeeds."""
        with patch(
            "chaoxing.solvers.quiz.submitter.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.quiz.submitter.pw_extract_result"
        ) as mock_extract, patch(
            "chaoxing.solvers.quiz.submitter.pw_snapshot",
            return_value="no confirm dialog"
        ), patch(
            "chaoxing.solvers.quiz.submitter.find_ref_by_text",
            return_value=None
        ):
            mock_extract.return_value = '{"ok": true, "method": "btnBlueSubmit"}'
            assert _submit_quiz_native() is True

    def test_submit_quiz_native_failure(self, mock_tempfile):
        """Submit failure: no submit method found in JS returns False."""
        with patch(
            "chaoxing.solvers.quiz.submitter.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.quiz.submitter.pw_extract_result"
        ) as mock_extract:
            mock_extract.return_value = (
                '{"ok": false, "reason": "no-submit-method-found"}'
            )
            assert _submit_quiz_native() is False

    def test_submit_quiz_fallback_snapshot(self, mock_tempfile):
        """Submit: when native fails, falls back to snapshot text search.

        _submit_quiz scans snapshot for 提交/交卷/暂存 -> clicks -> then
        rescans for 确定/确认 confirmation dialog. The find_ref_by_text
        mock must return enough items for all lookups.
        """
        with patch(
            "chaoxing.solvers.quiz.submitter._submit_quiz_native",
            return_value=False
        ), patch(
            "chaoxing.solvers.quiz.submitter.pw_snapshot"
        ) as mock_snap, patch(
            "chaoxing.solvers.quiz.submitter.find_ref_by_text"
        ) as mock_find, patch(
            "chaoxing.solvers.quiz.submitter.pw_click"
        ) as mock_click:
            mock_snap.return_value = "提交 button text"
            # Calls: find "提交" -> "交卷"(skipped) -> "暂存"(skipped) ->
            #        snap again -> find "确定" -> find "确认"
            mock_find.side_effect = ["ref-submit", None, None]
            assert _submit_quiz() is True
            mock_click.assert_called_once_with("ref-submit")


# ═══════════════════════════════════════════════════════════════════
#  Stage 4: Grading Tests
# ═══════════════════════════════════════════════════════════════════

class TestGradeCalculation:
    """Verify AI-based grading produces correct accuracy statistics."""

    def test_grade_batched_all_correct(self):
        """Grade calculation: all correct = 100% accuracy, passed."""
        filled_infos = [
            {"index": 1, "path": "/tmp/filled_q1.png", "qid": "123", "qtype": "single"},
            {"index": 2, "path": "/tmp/filled_q2.png", "qid": "456", "qtype": "single"},
        ]
        ai_answers = [
            {"index": 1, "answer": "B"},
            {"index": 2, "answer": "C"},
        ]
        mock_result = json.dumps([
            {"index": 1, "selected": "B", "is_correct": True,
             "correct_answer": "B", "explanation": "Correct"},
            {"index": 2, "selected": "C", "is_correct": True,
             "correct_answer": "C", "explanation": "Correct"},
        ])

        with patch(
            "chaoxing.solvers.quiz.grader.ai_grade_quiz_image",
            return_value=mock_result
        ):
            result = _grade_batched(filled_infos, ai_answers,
                                    batch_size=5, section_key="1.1")
            assert result["accuracy"] == 100.0
            assert result["correct"] == 2
            assert result["incorrect"] == 0
            assert result["uncertain"] == 0
            assert result["passed"] is True

    def test_grade_batched_mixed(self):
        """Grade calculation: correct/incorrect count with mixed results."""
        filled_infos = [
            {"index": 1, "path": "/tmp/filled_q1.png", "qid": "123", "qtype": "single"},
            {"index": 2, "path": "/tmp/filled_q2.png", "qid": "456", "qtype": "multi"},
            {"index": 3, "path": "/tmp/filled_q3.png", "qid": "789", "qtype": "judge"},
        ]
        ai_answers = [
            {"index": 1, "answer": "B"},
            {"index": 2, "answer": ["A", "C"]},
            {"index": 3, "answer": "正确"},
        ]
        mock_result = json.dumps([
            {"index": 1, "selected": "B", "is_correct": True,
             "correct_answer": "B", "explanation": "OK"},
            {"index": 2, "selected": "A", "is_correct": False,
             "correct_answer": "ACD", "explanation": "Missing D"},
            {"index": 3, "selected": "正确", "is_correct": None,
             "correct_answer": None, "explanation": "看不清"},
        ])

        with patch(
            "chaoxing.solvers.quiz.grader.ai_grade_quiz_image",
            return_value=mock_result
        ):
            result = _grade_batched(filled_infos, ai_answers,
                                    batch_size=5, section_key="1.1")
            assert result["accuracy"] == 50.0  # 1/2 graded
            assert result["correct"] == 1
            assert result["incorrect"] == 1
            assert result["uncertain"] == 1
            assert result["total"] == 3
            assert result["passed"] is False  # 50% < 80% threshold

    def test_grade_batched_all_uncertain(self):
        """Grade: all uncertain = 0% accuracy, not passed."""
        filled_infos = [
            {"index": 1, "path": "/tmp/filled_q1.png", "qid": "123", "qtype": "single"},
        ]
        ai_answers = [{"index": 1, "answer": "B"}]
        mock_result = json.dumps([
            {"index": 1, "selected": "unclear", "is_correct": None,
             "correct_answer": None, "explanation": "Image blurry"},
        ])

        with patch(
            "chaoxing.solvers.quiz.grader.ai_grade_quiz_image",
            return_value=mock_result
        ):
            result = _grade_batched(filled_infos, ai_answers,
                                    batch_size=5, section_key="1.1")
            assert result["correct"] == 0
            assert result["incorrect"] == 0
            assert result["uncertain"] == 1
            assert result["passed"] is False

    def test_grade_batched_empty_result_retries(self):
        """Grade: empty AI response triggers retry with short prompt."""
        filled_infos = [
            {"index": 1, "path": "/tmp/filled_q1.png", "qid": "123", "qtype": "single"},
        ]
        ai_answers = [{"index": 1, "answer": "B"}]

        mock_grade_result = json.dumps([
            {"index": 1, "selected": "B", "is_correct": True,
             "correct_answer": "B", "explanation": "OK"},
        ])

        with patch(
            "chaoxing.solvers.quiz.grader.ai_grade_quiz_image"
        ) as mock_grade, patch(
            "chaoxing.solvers.quiz.grader.time.sleep"
        ):
            # First call returns empty, second succeeds
            mock_grade.side_effect = ["", mock_grade_result]
            result = _grade_batched(filled_infos, ai_answers,
                                    batch_size=5, section_key="1.1")
            assert mock_grade.call_count == 2
            assert result["accuracy"] == 100.0

    def test_parse_grade_answer_json(self):
        """_parse_grade_answer parses valid JSON array."""
        text = json.dumps([
            {"index": 1, "is_correct": True, "correct_answer": "B"},
        ])
        result = _parse_grade_answer(text)
        assert len(result) == 1
        assert result[0]["is_correct"] is True

    def test_parse_grade_answer_markdown_fence(self):
        """_parse_grade_answer strips markdown code fences."""
        text = "```json\n[{\"index\":1,\"is_correct\":true}]\n```"
        result = _parse_grade_answer(text)
        assert len(result) == 1
        assert result[0]["is_correct"] is True

    def test_parse_correct_answers_from_snapshot(self):
        """_parse_correct_answers extracts answers from 查看答案 view."""
        snap = (
            "1. 正确答案：A\n"
            "2. 正确答案：B\n"
            "3. 正确答案：C\n"
        )
        result = _parse_correct_answers(snap)
        assert result is not None
        assert len(result) == 3
        assert result[0] == {"index": 1, "answer": "A"}
        assert result[1] == {"index": 2, "answer": "B"}
        assert result[2] == {"index": 3, "answer": "C"}

    def test_parse_correct_answers_no_match(self):
        """_parse_correct_answers returns None when no answers found."""
        assert _parse_correct_answers("No answers here") is None


# ═══════════════════════════════════════════════════════════════════
#  Stage 5: Strategy Chain Tests
# ═══════════════════════════════════════════════════════════════════

class TestStrategyChain:
    """Verify the 5-tier solving strategy chain and fallback behaviour."""

    def test_chain_order(self):
        """Strategies must be ordered tier 1..5, best to worst."""
        tiers = [s.tier for s in STRATEGY_CHAIN]
        assert tiers == [1, 2, 3, 4, 5]
        names = [s.name for s in STRATEGY_CHAIN]
        assert names == [
            "FontDecryptText", "V2Screenshot", "V1Screenshot",
            "FullPageScreenshot", "SnapshotText",
        ]

    def test_snapshot_strategy_already_done(self):
        """Strategy returns already_done marker when page shows completion.

        When the snapshot contains '暂无' or '已完成', the strategy short-circuits
        and tells the caller to mark the section done without solving.
        The strategy uses local imports inside try_solve(); patch at source.
        """
        strategy = SnapshotTextStrategy()
        mock_solver = MagicMock()
        mock_solver._get_ai_solver.return_value = (MagicMock(), MagicMock())

        with patch(
            "chaoxing.browser.engine.pw_snapshot",
            return_value="暂无任务点 已完成"
        ), patch(
            "chaoxing.solvers.quiz.extractor.extract_questions_from_snapshot",
            return_value=[{"type": "quiz_full", "text": ""}]
        ):
            result = strategy.try_solve(mock_solver)
            assert result is not None
            assert result.get("already_done") is True

    def test_snapshot_strategy_solves_with_ai(self):
        """SnapshotTextStrategy sends extracted text to AI and returns answers."""
        strategy = SnapshotTextStrategy()
        mock_solver = MagicMock()
        mock_solve_text = MagicMock(return_value=[
            {"index": 1, "answer": "B"},
            {"index": 2, "answer": "C"},
        ])
        mock_solver._get_ai_solver.return_value = (mock_solve_text, MagicMock())

        with patch(
            "chaoxing.browser.engine.pw_snapshot",
            return_value="1. 问题一 2. 问题二"
        ), patch(
            "chaoxing.solvers.quiz.extractor.extract_questions_from_snapshot",
            return_value=[{"type": "quiz_full", "text": "1. 问题一\n2. 问题二"}]
        ), patch(
            "chaoxing.solvers.quiz.extractor.count_questions_in_snapshot",
            return_value=2
        ):
            result = strategy.try_solve(mock_solver)
            assert result is not None
            assert len(result["answers"]) == 2
            assert result["mode"] == "text"
            assert result["q_count"] == 2
            mock_solve_text.assert_called_once()

    def test_snapshot_strategy_ai_exception(self):
        """AI solving failure: exception in AI call returns None.

        The strategy chain continues to the next strategy on failure.
        """
        strategy = SnapshotTextStrategy()
        mock_solver = MagicMock()
        mock_solve_text = MagicMock(side_effect=Exception("AI timeout"))
        mock_solver._get_ai_solver.return_value = (mock_solve_text, MagicMock())

        with patch(
            "chaoxing.browser.engine.pw_snapshot",
            return_value="1. 问题一"
        ), patch(
            "chaoxing.solvers.quiz.extractor.extract_questions_from_snapshot",
            return_value=[{"type": "quiz_full", "text": "1. 问题一"}]
        ):
            result = strategy.try_solve(mock_solver)
            assert result is None

    def test_font_decrypt_empty_text(self):
        """FontDecryptTextStrategy returns None when decryption produces empty text.

        FontDecryptTextStrategy does a local import of get_decrypted_quiz_text
        inside try_solve(); we patch at the source module chaoxing.font.
        """
        strategy = FontDecryptTextStrategy()
        mock_solver = MagicMock()
        mock_solver._get_ai_solver.return_value = (MagicMock(), MagicMock())

        with patch(
            "chaoxing.font.get_decrypted_quiz_text",
            return_value=""
        ):
            assert strategy.try_solve(mock_solver) is None

    def test_font_decrypt_too_short(self):
        """FontDecryptTextStrategy returns None when text <= 50 chars."""
        strategy = FontDecryptTextStrategy()
        mock_solver = MagicMock()
        mock_solver._get_ai_solver.return_value = (MagicMock(), MagicMock())

        with patch(
            "chaoxing.font.get_decrypted_quiz_text",
            return_value="short"
        ):
            assert strategy.try_solve(mock_solver) is None

    def test_chain_fallback_pattern(self):
        """AI solving failure -> strategy fallback: Tier 1 fails, Tier 2 succeeds.

        Simulates the solver's loop over STRATEGY_CHAIN: each strategy is tried
        in order; None results cause fallback to the next; the first non-None
        result is accepted.
        """
        # Simulate: Tier 1 returns None, Tier 2 succeeds
        results = []
        for strategy in STRATEGY_CHAIN:
            if isinstance(strategy, FontDecryptTextStrategy):
                results.append(None)  # Tier 1 failed
            elif isinstance(strategy, V2ScreenshotStrategy):
                results.append({
                    "answers": [{"index": 1, "answer": "A"}],
                    "q_count": 1,
                    "mode": "image",
                    "q_infos": [],
                })
                break
            else:
                results.append(None)

        assert results[0] is None  # Tier 1 failed
        assert results[1] is not None  # Tier 2 picked up
        assert len(results) == 2  # Only 2 strategies tried


# ═══════════════════════════════════════════════════════════════════
#  Stage 6: Retry Tests
# ═══════════════════════════════════════════════════════════════════

class TestRetryLogic:
    """Verify the retry loop exhausts correctly."""

    def test_retry_exhaust_all_buttons_missing(self):
        """Retry exhaust: no retry buttons found, loop breaks and fails.

        When the post-submit snapshot has neither '重试' nor '查看答案'
        buttons, the retry loop stops after scanning all snapshots.
        """
        from chaoxing.solvers.quiz.retry import _retry_quiz

        mock_solver = MagicMock()
        mock_solver.stats = {"solved": 0, "failed": 0, "retried": 0}
        section = {"section": "1.6", "name": "章节测试1"}

        with patch(
            "chaoxing.solvers.quiz.retry.pw_snapshot",
            return_value="No retry buttons available"
        ), patch(
            "chaoxing.solvers.quiz.retry.find_ref_by_text",
            return_value=None
        ), patch(
            "chaoxing.solvers.quiz.retry.cfg",
            return_value=3
        ), patch(
            "chaoxing.solvers.quiz.retry.time.sleep"
        ):
            result = _retry_quiz(mock_solver, section, retry_depth=0)
            assert result is False
            assert mock_solver.stats["failed"] == 1

    def test_retry_with_correct_answers_and_retry_button(self):
        """Retry: parse correct answers, click retry, fill with correct answers.

        Best-case retry path: view answers -> parse them -> retry -> fill correct.
        """
        from chaoxing.solvers.quiz.retry import _retry_quiz

        mock_solver = MagicMock()
        mock_solver.stats = {"solved": 0, "failed": 0, "retried": 0}
        mock_solver.tracker = MagicMock()
        mock_solver.quiz_stats = MagicMock()
        section = {"section": "1.6", "name": "章节测试1"}

        # _fill_and_submit returns True, then snapshot with perfect score
        mock_solver._fill_and_submit.return_value = True

        with patch(
            "chaoxing.solvers.quiz.retry.pw_snapshot"
        ) as mock_snap, patch(
            "chaoxing.solvers.quiz.retry.find_ref_by_text"
        ) as mock_find, patch(
            "chaoxing.solvers.quiz.retry.pw_click"
        ), patch(
            "chaoxing.solvers.quiz.retry.cfg",
            return_value=100
        ), patch(
            "chaoxing.solvers.quiz.retry.time.sleep"
        ), patch(
            "chaoxing.solvers.quiz.retry._parse_correct_answers"
        ) as mock_parse_answers, patch(
            "chaoxing.solvers.quiz.retry._parse_score"
        ) as mock_parse_score:
            # Snap 1: has 查看答案 and 重试
            # After viewing answers: parse correct answers
            mock_parse_answers.return_value = [
                {"index": 1, "answer": "B"},
                {"index": 2, "answer": "C"},
            ]
            # After fill+submit: parse score
            mock_parse_score.return_value = 100

            mock_find.side_effect = [
                "ref-view-answers",  # 查看答案 button
                "ref-retry",         # 重试 button
            ]

            result = _retry_quiz(mock_solver, section, retry_depth=0)
            assert result is True
            assert mock_solver.stats["solved"] == 1
            mock_solver.tracker.mark_section_done.assert_called()


# ═══════════════════════════════════════════════════════════════════
#  Stage 7: Stats Tests
# ═══════════════════════════════════════════════════════════════════

class TestQuizStatsTracking:
    """Verify QuizStats records attempts and computes summaries correctly."""

    def test_record_attempt_basic(self):
        """Stats: recording an attempt populates the records list."""
        from chaoxing.solvers.quiz.stats import QuizStats

        with patch("chaoxing.solvers.quiz.stats.Path.exists", return_value=False), \
             patch("chaoxing.solvers.quiz.stats.Path.mkdir"), \
             patch("chaoxing.solvers.quiz.stats.Path.write_text"), \
             patch("chaoxing.solvers.quiz.stats.Path.read_text", return_value="{}"):
            stats = QuizStats("Test Course")
            stats.record_attempt(
                section_key="1.1 测试",
                total_questions=3,
                ai_answers=[
                    {"index": 1, "answer": "B"},
                    {"index": 2, "answer": "C"},
                ],
                score=100,
                correct_answers=[
                    {"index": 1, "answer": "B"},
                    {"index": 2, "answer": "C"},
                ],
                retry_count=0,
                mode="text",
            )
            assert len(stats.records) == 1
            record = stats.records[0]
            assert record["score"] == 100
            assert record["total_questions"] == 3
            assert record["retry_count"] == 0

    def test_summary_aggregates_multiple_attempts(self):
        """Stats: summary correctly averages across multiple quizzes."""
        from chaoxing.solvers.quiz.stats import QuizStats

        with patch("chaoxing.solvers.quiz.stats.Path.exists", return_value=False), \
             patch("chaoxing.solvers.quiz.stats.Path.mkdir"), \
             patch("chaoxing.solvers.quiz.stats.Path.write_text"), \
             patch("chaoxing.solvers.quiz.stats.Path.read_text", return_value="{}"):
            stats = QuizStats("Test Course")
            stats.record_attempt("1.1", 3, [], 100, None, 0, "text")
            stats.record_attempt("1.2", 3, [], 80, None, 1, "image")

            summary = stats.summary()
            assert summary["total_quizzes"] == 2
            assert summary["avg_score"] == 90.0
            assert summary["perfect_sections"] == 1
            assert summary["passing_sections"] == 2
            assert summary["total_retries"] == 1

    def test_per_question_accuracy(self):
        """Stats: per-question accuracy computed from correct_answers."""
        from chaoxing.solvers.quiz.stats import QuizStats

        with patch("chaoxing.solvers.quiz.stats.Path.exists", return_value=False), \
             patch("chaoxing.solvers.quiz.stats.Path.mkdir"), \
             patch("chaoxing.solvers.quiz.stats.Path.write_text"), \
             patch("chaoxing.solvers.quiz.stats.Path.read_text", return_value="{}"):
            stats = QuizStats("Test Course")
            stats.record_attempt(
                "1.1", 3,
                ai_answers=[
                    {"index": 1, "answer": "B"},
                    {"index": 2, "answer": "C"},
                    {"index": 3, "answer": "D"},
                ],
                score=67,
                correct_answers=[
                    {"index": 1, "answer": "B"},
                    {"index": 2, "answer": "X"},  # AI was wrong here
                    {"index": 3, "answer": "D"},
                ],
                retry_count=0,
                mode="text",
            )
            summary = stats.summary()
            # Q1: B==B correct, Q2: C!=X incorrect, Q3: D==D correct
            assert summary["per_question_accuracy"] == "2/3"
            assert summary["per_question_pct"] == pytest.approx(66.7, abs=0.1)

    def test_empty_stats(self):
        """Stats: empty course returns zero counts."""
        from chaoxing.solvers.quiz.stats import QuizStats

        with patch("chaoxing.solvers.quiz.stats.Path.exists", return_value=False), \
             patch("chaoxing.solvers.quiz.stats.Path.mkdir"), \
             patch("chaoxing.solvers.quiz.stats.Path.write_text"):
            stats = QuizStats("Empty Course")
            summary = stats.summary()
            assert summary["total_quizzes"] == 0
