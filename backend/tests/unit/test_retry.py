"""Tests for chaoxing.solvers.quiz.retry — retry loop logic."""
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.solvers.quiz.retry import _retry_quiz


# ── Mock setup helpers ───────────────────────────────────────────

def _make_mock_solver():
    """Create a mock ChapterQuizSolver with necessary attributes."""
    solver = MagicMock()
    solver.name = "测试课程"
    solver.tracker = MagicMock()
    solver.stats = {"solved": 0, "failed": 0, "retried": 0}
    solver.quiz_stats = MagicMock()
    solver._fill_and_submit.return_value = True
    solver.solve_quiz.return_value = True
    return solver


def _make_section():
    """Create a sample section dict."""
    return {"section": "1.1", "name": "章节测试1"}


def _set_find_ref_responses(mock, responses_by_text: dict):
    """Configure a find_ref_by_text mock to return values based on text searched."""
    def side_effect(snap, text):
        for key, value in responses_by_text.items():
            if key in text:
                return value
        return None
    mock.side_effect = side_effect


def _set_cfg_responses(mock, target_score=100, max_retries=3):
    """Configure a cfg mock to return different values per key."""
    def side_effect(key, default=None):
        if key == "retry.quiz_target_score":
            return target_score
        if key == "retry.quiz_max_retries":
            return max_retries
        return default
    mock.side_effect = side_effect


# ── _retry_quiz ──────────────────────────────────────────────────

class TestRetryQuiz:
    """Tests for _retry_quiz retry loop."""

    @patch("chaoxing.solvers.quiz.retry._parse_score")
    @patch("chaoxing.solvers.quiz.retry._parse_correct_answers")
    @patch("chaoxing.solvers.quiz.retry.pw_click")
    @patch("chaoxing.solvers.quiz.retry.pw_snapshot")
    @patch("chaoxing.solvers.quiz.retry.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.retry.cfg")
    def test_retry_with_correct_answers_and_pass(
        self, mock_cfg, mock_find_ref, mock_snapshot,
        mock_click, mock_parse_answers, mock_parse_score
    ):
        """Retry with correct answers from answer view -> submit -> pass."""
        _set_cfg_responses(mock_cfg, target_score=100, max_retries=5)
        solver = _make_mock_solver()
        section = _make_section()

        mock_snapshot.side_effect = ["snap1", "answer_snap", "result_snap"]

        _set_find_ref_responses(mock_find_ref, {
            "查看答案": "ref_ans",
            "重试": "ref_retry",
        })

        mock_parse_answers.return_value = [
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "B"},
        ]
        mock_parse_score.return_value = 100

        result = _retry_quiz(solver, section, retry_depth=0)

        assert result is True
        solver.tracker.mark_section_done.assert_called_once()
        solver._fill_and_submit.assert_called_once()

    @patch("chaoxing.solvers.quiz.retry._parse_score")
    @patch("chaoxing.solvers.quiz.retry._parse_correct_answers")
    @patch("chaoxing.solvers.quiz.retry.pw_click")
    @patch("chaoxing.solvers.quiz.retry.pw_snapshot")
    @patch("chaoxing.solvers.quiz.retry.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.retry.cfg")
    def test_retry_no_correct_answers_calls_solve_quiz(
        self, mock_cfg, mock_find_ref, mock_snapshot,
        mock_click, mock_parse_answers, mock_parse_score
    ):
        """When no correct answers but retry button found, calls solve_quiz."""
        _set_cfg_responses(mock_cfg, max_retries=5)
        solver = _make_mock_solver()
        section = _make_section()

        mock_snapshot.return_value = "snap1"

        _set_find_ref_responses(mock_find_ref, {
            "重试": "ref_retry",
        })

        mock_parse_answers.return_value = None

        result = _retry_quiz(solver, section, retry_depth=1)

        solver.solve_quiz.assert_called_once_with(section, 2)

    @patch("chaoxing.solvers.quiz.retry._parse_score")
    @patch("chaoxing.solvers.quiz.retry._parse_correct_answers")
    @patch("chaoxing.solvers.quiz.retry.pw_click")
    @patch("chaoxing.solvers.quiz.retry.pw_snapshot")
    @patch("chaoxing.solvers.quiz.retry.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.retry.cfg")
    def test_max_retries_exhausted(
        self, mock_cfg, mock_find_ref, mock_snapshot,
        mock_click, mock_parse_answers, mock_parse_score
    ):
        """Neither button found -> break -> return False."""
        _set_cfg_responses(mock_cfg, max_retries=5)
        solver = _make_mock_solver()
        section = _make_section()

        mock_snapshot.return_value = "snap_no_buttons"

        _set_find_ref_responses(mock_find_ref, {})

        result = _retry_quiz(solver, section, retry_depth=0)

        assert result is False

    @patch("chaoxing.solvers.quiz.retry._parse_score")
    @patch("chaoxing.solvers.quiz.retry._parse_correct_answers")
    @patch("chaoxing.solvers.quiz.retry.pw_click")
    @patch("chaoxing.solvers.quiz.retry.pw_snapshot")
    @patch("chaoxing.solvers.quiz.retry.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.retry.cfg")
    def test_retry_with_correct_answers_but_score_below_target(
        self, mock_cfg, mock_find_ref, mock_snapshot,
        mock_click, mock_parse_answers, mock_parse_score
    ):
        """Score below target -> continues loop -> eventually fails."""
        _set_cfg_responses(mock_cfg, target_score=100, max_retries=3)
        solver = _make_mock_solver()
        section = _make_section()

        # Each iteration with both buttons needs 3 snapshots (main, answer, result)
        mock_snapshot.side_effect = ["snap"] * 20

        _set_find_ref_responses(mock_find_ref, {
            "查看答案": "ref_ans",
            "重试": "ref_retry",
        })

        mock_parse_answers.return_value = [
            {"index": 1, "answer": "A"},
        ]
        mock_parse_score.return_value = 60  # Always below target

        result = _retry_quiz(solver, section, retry_depth=0)

        assert result is False

    @patch("chaoxing.solvers.quiz.retry._parse_score")
    @patch("chaoxing.solvers.quiz.retry._parse_correct_answers")
    @patch("chaoxing.solvers.quiz.retry.pw_click")
    @patch("chaoxing.solvers.quiz.retry.pw_snapshot")
    @patch("chaoxing.solvers.quiz.retry.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.retry.cfg")
    def test_correct_answers_reset_each_iteration(
        self, mock_cfg, mock_find_ref, mock_snapshot,
        mock_click, mock_parse_answers, mock_parse_score
    ):
        """E4 fix: correct_answers reset each iteration allows re-viewing."""
        _set_cfg_responses(mock_cfg, target_score=100, max_retries=5)
        solver = _make_mock_solver()
        section = _make_section()

        mock_snapshot.side_effect = [
            "snap1", "answer_snap1", "result_snap1",  # iter 1
            "snap2", "answer_snap2", "result_snap2",  # iter 2
        ]

        _set_find_ref_responses(mock_find_ref, {
            "查看答案": "ref_ans",
            "重试": "ref_retry",
        })

        mock_parse_answers.side_effect = [
            [{"index": 1, "answer": "B"}],       # iter 1: wrong
            [{"index": 1, "answer": "A"}],       # iter 2: correct
        ]
        mock_parse_score.side_effect = [50, 100]

        result = _retry_quiz(solver, section, retry_depth=0)

        assert result is True
        assert mock_parse_answers.call_count == 2, (
            "E4 fix: correct_answers should be reset each iteration"
        )

    @patch("chaoxing.solvers.quiz.retry._parse_score")
    @patch("chaoxing.solvers.quiz.retry._parse_correct_answers")
    @patch("chaoxing.solvers.quiz.retry.pw_click")
    @patch("chaoxing.solvers.quiz.retry.pw_snapshot")
    @patch("chaoxing.solvers.quiz.retry.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.retry.cfg")
    def test_direct_refill_with_stored_answers(
        self, mock_cfg, mock_find_ref, mock_snapshot,
        mock_click, mock_parse_answers, mock_parse_score
    ):
        """Priority 3: correct_answers but no retry button -> direct refill."""
        _set_cfg_responses(mock_cfg, target_score=100, max_retries=5)
        solver = _make_mock_solver()
        section = _make_section()

        mock_snapshot.side_effect = [
            "snap1", "answer_snap", "result_snap",
        ]

        _set_find_ref_responses(mock_find_ref, {
            "查看答案": "ref_ans",
        })

        mock_parse_answers.return_value = [
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "B"},
        ]
        mock_parse_score.return_value = 100

        result = _retry_quiz(solver, section, retry_depth=0)

        assert result is True
        solver._fill_and_submit.assert_called_once()
        solver.tracker.mark_section_done.assert_called_once()


# ── Edge cases ───────────────────────────────────────────────────

class TestRetryQuizEdgeCases:
    """Edge case tests for _retry_quiz."""

    @patch("chaoxing.solvers.quiz.retry._parse_score")
    @patch("chaoxing.solvers.quiz.retry._parse_correct_answers")
    @patch("chaoxing.solvers.quiz.retry.pw_click")
    @patch("chaoxing.solvers.quiz.retry.pw_snapshot")
    @patch("chaoxing.solvers.quiz.retry.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.retry.cfg")
    def test_fill_and_submit_failure_handled(
        self, mock_cfg, mock_find_ref, mock_snapshot,
        mock_click, mock_parse_answers, mock_parse_score
    ):
        """When _fill_and_submit returns False, should exhaust and fail."""
        _set_cfg_responses(mock_cfg, max_retries=3)
        solver = _make_mock_solver()
        solver._fill_and_submit.return_value = False
        section = _make_section()

        # Each iteration needs 3 snapshots, 3 iterations = 9 entries
        mock_snapshot.side_effect = ["snap"] * 20

        _set_find_ref_responses(mock_find_ref, {
            "查看答案": "ref_ans",
            "重试": "ref_retry",
        })

        mock_parse_answers.return_value = [
            {"index": 1, "answer": "A"},
        ]
        mock_parse_score.return_value = 100

        result = _retry_quiz(solver, section, retry_depth=0)
        assert result is False

    @patch("chaoxing.solvers.quiz.retry._parse_score")
    @patch("chaoxing.solvers.quiz.retry._parse_correct_answers")
    @patch("chaoxing.solvers.quiz.retry.pw_click")
    @patch("chaoxing.solvers.quiz.retry.pw_snapshot")
    @patch("chaoxing.solvers.quiz.retry.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.retry.cfg")
    def test_score_none_triggers_continue(
        self, mock_cfg, mock_find_ref, mock_snapshot,
        mock_click, mock_parse_answers, mock_parse_score
    ):
        """When score is None, should continue loop."""
        _set_cfg_responses(mock_cfg, max_retries=3)
        solver = _make_mock_solver()
        section = _make_section()

        mock_snapshot.side_effect = ["snap"] * 20

        _set_find_ref_responses(mock_find_ref, {
            "查看答案": "ref_ans",
            "重试": "ref_retry",
        })

        mock_parse_answers.return_value = [
            {"index": 1, "answer": "A"},
        ]
        mock_parse_score.return_value = None

        result = _retry_quiz(solver, section, retry_depth=0)
        assert result is False
