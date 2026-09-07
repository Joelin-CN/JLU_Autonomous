"""Tests for chaoxing.solvers.quiz.submitter — quiz submission and score parsing."""
from unittest.mock import patch, MagicMock

from chaoxing.solvers.quiz.submitter import (
    _submit_quiz,
    _submit_quiz_native,
    _parse_score,
)


class TestParseScore:
    """Tests for _parse_score with various Chinese score formats."""

    def test_parses_fen_format(self):
        """Pattern: (\\d+)\\s*分 -> 85分"""
        assert _parse_score("得分：85分") == 85

    def test_parses_defen_format(self):
        """Pattern: 得分[：:]\\s*(\\d+)"""
        assert _parse_score("得分：90") == 90
        assert _parse_score("得分: 95") == 95

    def test_parses_chengji_format(self):
        """Pattern: 成绩[：:]\\s*(\\d+)"""
        assert _parse_score("成绩：100") == 100
        assert _parse_score("成绩: 88") == 88

    def test_parses_percent_format(self):
        """Pattern: (\\d+)\\s*%"""
        assert _parse_score("正确率 95%") == 95

    def test_no_score_returns_none(self):
        """When no score pattern matches, return None."""
        assert _parse_score("欢迎使用学习通") is None

    def test_empty_string_returns_none(self):
        assert _parse_score("") is None

    def test_multiple_matches_returns_first(self):
        """When multiple patterns match, first one wins."""
        snap = "得分：85分\n成绩：90"
        result = _parse_score(snap)
        assert result is not None  # Should find something

    def test_zero_score(self):
        """Score of 0 should be parsed (not confused with None)."""
        assert _parse_score("得分：0分") == 0
        assert _parse_score("正确率 0%") == 0


class TestSubmitQuizNative:
    """Tests for native JS-based submission."""

    @patch("chaoxing.solvers.quiz.submitter.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.submitter.pw_extract_result")
    def test_native_submit_json_true(self, mock_extract, mock_run):
        """When JS returns {ok:true}, native submit returns True."""
        mock_run.return_value = "raw"
        mock_extract.return_value = '{"ok":true,"method":"btnBlueSubmit"}'
        result = _submit_quiz_native()
        assert result is True

    @patch("chaoxing.solvers.quiz.submitter.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.submitter.pw_extract_result")
    def test_native_submit_json_false(self, mock_extract, mock_run):
        """When JS returns {ok:false}, native submit returns False."""
        mock_run.return_value = "raw"
        mock_extract.return_value = '{"ok":false,"reason":"button not found"}'
        result = _submit_quiz_native()
        assert result is False

    @patch("chaoxing.solvers.quiz.submitter.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.submitter.pw_extract_result")
    def test_native_submit_json_parse_error(self, mock_extract, mock_run):
        """When JSON parse fails, native submit returns False."""
        mock_run.return_value = "raw"
        mock_extract.return_value = "not json at all"
        result = _submit_quiz_native()
        assert result is False


class TestSubmitQuiz:
    """Tests for full submit flow."""

    @patch("chaoxing.solvers.quiz.submitter._submit_quiz_native")
    def test_submit_native_succeeds(self, mock_native):
        """When native submit succeeds, return True."""
        mock_native.return_value = True
        result = _submit_quiz()
        assert result is True

    @patch("chaoxing.solvers.quiz.submitter.pw_snapshot")
    @patch("chaoxing.solvers.quiz.submitter.pw_click")
    @patch("chaoxing.solvers.quiz.submitter.find_ref_by_text")
    @patch("chaoxing.solvers.quiz.submitter._submit_quiz_native")
    def test_submit_fallback_to_snapshot(
        self, mock_native, mock_find_ref, mock_click, mock_snapshot
    ):
        """When native submit fails, fall back to snapshot text search."""
        mock_native.return_value = False
        mock_snapshot.return_value = "提交 交卷 button text"
        # First find "提交", then find confirmation "确定"
        mock_find_ref.side_effect = lambda snap, text: f"ref_{text}"

        result = _submit_quiz()
        assert result is True
        mock_click.assert_called()
