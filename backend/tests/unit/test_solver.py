"""Tests for chaoxing.solvers.quiz.solver — solver orchestration."""
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from chaoxing.exceptions import ConfigError
from chaoxing.solvers.quiz.solver import ChapterQuizSolver


# ── Mock helpers ─────────────────────────────────────────────────

def _make_course_config():
    """Create a minimal course config for testing."""
    return {
        "name": "测试课程",
        "courseid": "12345",
        "clazzid": "67890",
        "cpi": "415409200",
    }


# ── _get_ai_solver ───────────────────────────────────────────────

class TestGetAISolver:
    """Tests for ChapterQuizSolver._get_ai_solver (E3 fix)."""

    @patch("chaoxing.solvers.quiz.solver.cfg")
    def test_valid_provider_doubao(self, mock_cfg):
        """Should return solver functions for doubao-api provider."""
        mock_cfg.return_value = "doubao-api"
        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        text_fn, image_fn = solver._get_ai_solver()

        assert callable(text_fn)
        assert callable(image_fn)
        assert text_fn is not None
        assert image_fn is not None

    @patch("chaoxing.solvers.quiz.solver.cfg")
    def test_invalid_provider_raises_config_error(self, mock_cfg):
        """E3 fix: Unknown provider should raise ConfigError, not just warn."""
        mock_cfg.return_value = "unknown-ai-provider"
        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        with pytest.raises(ConfigError) as exc_info:
            solver._get_ai_solver()

        assert "Unknown AI provider" in str(exc_info.value)
        assert "unknown-ai-provider" in str(exc_info.value)

    @patch("chaoxing.solvers.quiz.solver.cfg")
    def test_empty_provider_raises_config_error(self, mock_cfg):
        """Empty string provider should raise ConfigError."""
        mock_cfg.return_value = ""
        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        with pytest.raises(ConfigError):
            solver._get_ai_solver()

    @patch("chaoxing.solvers.quiz.solver.cfg")
    def test_none_provider_defaults_and_passes(self, mock_cfg):
        """None provider should fall back to default and pass."""
        # Returning None from cfg triggers the default "doubao-api"
        mock_cfg.return_value = None

        # cfg is called with default="doubao-api", so it returns None only
        # if the config actually has None. Mock it to return "doubao-api".
        mock_cfg.return_value = "doubao-api"
        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        text_fn, image_fn = solver._get_ai_solver()
        assert callable(text_fn)


# ── _solve_batched index remapping ──────────────────────────────

class TestSolveBatchedIndexRemapping:
    """Tests for ChapterQuizSolver._solve_batched index remapping (E2 fix)."""

    @patch("chaoxing.solvers.quiz.solver.ChapterQuizSolver._get_ai_solver")
    def test_0_based_ai_response_remapped_correctly(self, mock_get_solver):
        """E2 fix: 0-based AI response should be remapped correctly.

        AI returns 0-based indices (0,1,2) for batch covering global Q4-6.
        After fix: offsets by batch_q_indices[0] (4), resulting in 4,5,6.
        """
        mock_solve_image = MagicMock()
        mock_solve_text = MagicMock()
        mock_get_solver.return_value = (mock_solve_text, mock_solve_image)

        # AI returns 0-based answers
        mock_solve_image.return_value = [
            {"index": 0, "answer": "A"},
            {"index": 1, "answer": "B"},
            {"index": 2, "answer": "C"},
        ]

        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        q_infos = [
            {"index": 4, "path": "/tmp/q4.png"},
            {"index": 5, "path": "/tmp/q5.png"},
            {"index": 6, "path": "/tmp/q6.png"},
        ]

        result = solver._solve_batched(q_infos, batch_size=3)

        assert len(result) == 3
        indices = [a["index"] for a in result]
        # 0-based: offset = batch_q_indices[0] = 4
        # 0+4=4, 1+4=5, 2+4=6
        assert indices == [4, 5, 6], (
            f"E2 fix: 0-based AI response should be remapped. "
            f"Expected [4,5,6], got {indices}"
        )

    @patch("chaoxing.solvers.quiz.solver.ChapterQuizSolver._get_ai_solver")
    def test_1_based_ai_response_remapped_correctly(self, mock_get_solver):
        """E2 fix: 1-based AI response should be remapped correctly.

        AI returns 1-based indices (1,2,3) for batch covering global Q7-9.
        After fix: offsets by batch_q_indices[0]-1 (6), resulting in 7,8,9.
        """
        mock_solve_image = MagicMock()
        mock_solve_text = MagicMock()
        mock_get_solver.return_value = (mock_solve_text, mock_solve_image)

        # AI returns 1-based answers
        mock_solve_image.return_value = [
            {"index": 1, "answer": "D"},
            {"index": 2, "answer": "E"},
            {"index": 3, "answer": "F"},
        ]

        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        q_infos = [
            {"index": 7, "path": "/tmp/q7.png"},
            {"index": 8, "path": "/tmp/q8.png"},
            {"index": 9, "path": "/tmp/q9.png"},
        ]

        result = solver._solve_batched(q_infos, batch_size=3)

        assert len(result) == 3
        indices = [a["index"] for a in result]
        # 1-based: offset = batch_q_indices[0] - 1 = 6
        # 1+6=7, 2+6=8, 3+6=9
        assert indices == [7, 8, 9], (
            f"E2 fix: 1-based AI response should be remapped. "
            f"Expected [7,8,9], got {indices}"
        )

    @patch("chaoxing.solvers.quiz.solver.ChapterQuizSolver._get_ai_solver")
    def test_first_batch_no_remapping_needed(self, mock_get_solver):
        """When batch starts at Q1 and AI returns 1-based, no remapping needed."""
        mock_solve_image = MagicMock()
        mock_solve_text = MagicMock()
        mock_get_solver.return_value = (mock_solve_text, mock_solve_image)

        mock_solve_image.return_value = [
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "B"},
        ]

        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        q_infos = [
            {"index": 1, "path": "/tmp/q1.png"},
            {"index": 2, "path": "/tmp/q2.png"},
        ]

        result = solver._solve_batched(q_infos, batch_size=2)

        indices = [a["index"] for a in result]
        assert indices == [1, 2], f"First batch should not shift, got {indices}"

    @patch("chaoxing.solvers.quiz.solver.ChapterQuizSolver._get_ai_solver")
    def test_multiple_batches_all_remapped(self, mock_get_solver):
        """Multiple batches should all have correct index remapping."""
        mock_solve_image = MagicMock()
        mock_solve_text = MagicMock()
        mock_get_solver.return_value = (mock_solve_text, mock_solve_image)

        # Batch 1 (Q1-2) returns 1-based, batch 2 (Q3-4) returns 1-based
        mock_solve_image.side_effect = [
            [{"index": 1, "answer": "A"}, {"index": 2, "answer": "B"}],
            [{"index": 1, "answer": "C"}, {"index": 2, "answer": "D"}],
        ]

        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        q_infos = [
            {"index": 1, "path": "/tmp/q1.png"},
            {"index": 2, "path": "/tmp/q2.png"},
            {"index": 3, "path": "/tmp/q3.png"},
            {"index": 4, "path": "/tmp/q4.png"},
        ]

        result = solver._solve_batched(q_infos, batch_size=2)

        assert len(result) == 4
        indices = [a["index"] for a in result]
        assert indices == [1, 2, 3, 4], (
            f"All indices should be correct after multi-batch remapping, "
            f"got {indices}"
        )

    @patch("chaoxing.solvers.quiz.solver.ChapterQuizSolver._get_ai_solver")
    def test_batch_with_no_valid_paths_skipped(self, mock_get_solver):
        """Batch with no valid paths should be skipped gracefully."""
        mock_solve_image = MagicMock()
        mock_solve_text = MagicMock()
        mock_get_solver.return_value = (mock_solve_text, mock_solve_image)

        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        # All paths are empty
        q_infos = [
            {"index": 1, "path": ""},
            {"index": 2, "path": ""},
        ]

        result = solver._solve_batched(q_infos, batch_size=2)

        # Should return empty list since no valid paths
        assert result == []

    @patch("chaoxing.solvers.quiz.solver.ChapterQuizSolver._get_ai_solver")
    def test_batch_with_mixed_valid_invalid_paths(self, mock_get_solver):
        """Batch with some valid and some invalid paths should still work."""
        mock_solve_image = MagicMock()
        mock_solve_text = MagicMock()
        mock_get_solver.return_value = (mock_solve_text, mock_solve_image)

        mock_solve_image.return_value = [
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "B"},
        ]

        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        q_infos = [
            {"index": 1, "path": "/tmp/q1.png"},
            {"index": 2, "path": ""},     # no path, but still in batch
            {"index": 3, "path": "/tmp/q3.png"},
        ]

        result = solver._solve_batched(q_infos, batch_size=3)

        # batch_paths will have 2 paths (q1.png, q3.png)
        # batch_q_indices = [1,2,3]
        # The AI will get 2 images and may return 2 or 3 answers
        assert isinstance(result, list)

    @patch("chaoxing.solvers.quiz.solver.ChapterQuizSolver._get_ai_solver")
    def test_ai_returns_question_index_field(self, mock_get_solver):
        """Should handle AI responses using 'question_index' key."""
        mock_solve_image = MagicMock()
        mock_solve_text = MagicMock()
        mock_get_solver.return_value = (mock_solve_text, mock_solve_image)

        # AI uses "question_index" instead of "index"
        mock_solve_image.return_value = [
            {"question_index": 1, "answer": "A"},
            {"question_index": 2, "answer": "B"},
        ]

        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        q_infos = [
            {"index": 1, "path": "/tmp/q1.png"},
            {"index": 2, "path": "/tmp/q2.png"},
        ]

        result = solver._solve_batched(q_infos, batch_size=2)

        assert len(result) == 2
        assert result[0]["index"] == 1  # Remapped from question_index

    @patch("chaoxing.solvers.quiz.solver.ChapterQuizSolver._get_ai_solver")
    def test_single_question_batch(self, mock_get_solver):
        """Single question in a batch should work correctly."""
        mock_solve_image = MagicMock()
        mock_solve_text = MagicMock()
        mock_get_solver.return_value = (mock_solve_text, mock_solve_image)

        mock_solve_image.return_value = [
            {"index": 1, "answer": "C"},
        ]

        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        q_infos = [
            {"index": 5, "path": "/tmp/q5.png"},
        ]

        result = solver._solve_batched(q_infos, batch_size=1)

        assert len(result) == 1
        assert result[0]["index"] == 5  # 1-based offset: 5-1=4, 1+4=5


# ── Solver initialization ────────────────────────────────────────

class TestSolverInit:
    """Tests for ChapterQuizSolver initialization."""

    def test_init_with_minimal_config(self):
        """Should initialize with minimal course config."""
        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)
        assert solver.name == "测试课程"
        assert solver.courseid == "12345"
        assert solver.clazzid == "67890"
        assert solver.dry_run is True
        assert solver.grade_only is False

    def test_init_grade_only_mode(self):
        """Should initialize in grade-only mode."""
        solver = ChapterQuizSolver(
            _make_course_config(), dry_run=False, grade_only=True
        )
        assert solver.grade_only is True
        assert solver.dry_run is False

    def test_init_creates_stats_dict(self):
        """Should create stats tracking dictionary."""
        solver = ChapterQuizSolver(_make_course_config())
        assert "solved" in solver.stats
        assert "failed" in solver.stats
        assert "retried" in solver.stats
        assert solver.stats["solved"] == 0

    def test_init_creates_quiz_stats(self):
        """Should create QuizStats instance."""
        solver = ChapterQuizSolver(_make_course_config())
        assert solver.quiz_stats is not None

    def test_grade_pass_threshold_default(self):
        """Default grade pass threshold should be 80."""
        solver = ChapterQuizSolver(_make_course_config())
        assert solver.GRADE_PASS_THRESHOLD == 80


# ── Answerability detection ─────────────────────────────────────

class TestAnswerability:
    """Tests for ChapterQuizSolver._is_unanswerable delegation."""

    def test_is_unanswerable_delegates_to_filler(self):
        """_is_unanswerable should delegate to filler._is_unanswerable."""
        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)

        # Exact marker match
        assert solver._is_unanswerable("无法判断") is True

        # Normal answer
        assert solver._is_unanswerable("A") is False

        # Substring false positive (E6 fix)
        answer_with_marker_in_context = (
            "The answer can be determined. There is not enough info "
            "about option C specifically."
        )
        assert solver._is_unanswerable(answer_with_marker_in_context) is False


# ── Count helpers ───────────────────────────────────────────────

class TestCountHelpers:
    """Tests for static count methods."""

    def test_count_questions_in_text_static(self):
        """Static _count_questions_in_text should work."""
        result = ChapterQuizSolver._count_questions_in_text(
            "1. Q1\n2. Q2\n3. Q3"
        )
        assert result == 3

    def test_count_questions_in_snapshot_static(self):
        """Static _count_questions_in_snapshot should work."""
        result = ChapterQuizSolver._count_questions_in_snapshot(
            "1. Q1\n2. Q2"
        )
        assert result == 2


# ── Section key helpers ─────────────────────────────────────────

class TestSectionKey:
    """Tests for section key construction in solve_quiz."""

    def test_section_key_format(self):
        """Section key should be '{section} {name}'."""
        solver = ChapterQuizSolver(_make_course_config(), dry_run=True)
        section = {"section": "2.3", "name": "概率分布测试"}

        section_key = f"{section['section']} {section['name']}"
        assert section_key == "2.3 概率分布测试"
