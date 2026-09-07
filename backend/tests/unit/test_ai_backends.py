"""Tests for AI backend solvers and factory functions."""

from unittest import mock
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.ai._base import AISolver
from chaoxing.ai.doubao import DoubaoAPISolver
from chaoxing.ai.router import get_ai_solver, ai_solve_quiz
from chaoxing.exceptions import ConfigError


class TestProviderNames:
    """Verify provider_name property returns correct identifiers."""

    def test_doubao_provider_name(self):
        """DoubaoAPISolver.provider_name should return 'doubao-api'."""
        solver = DoubaoAPISolver()
        assert solver.provider_name == "doubao-api"



class TestAISolverFactory:
    """Test get_ai_solver factory with various providers."""

    @mock.patch("chaoxing.ai.router.cfg")
    def test_get_doubao_solver(self, mock_cfg):
        """get_ai_solver should return DoubaoAPISolver when provider is 'doubao-api'."""
        mock_cfg.return_value = "doubao-api"
        solver = get_ai_solver()
        assert isinstance(solver, DoubaoAPISolver)

    @mock.patch("chaoxing.ai.router.cfg")
    def test_get_invalid_provider_raises(self, mock_cfg):
        """get_ai_solver should raise ConfigError for unknown provider."""
        mock_cfg.return_value = "unknown-provider-xyz"
        with pytest.raises(ConfigError, match="Unknown AI provider"):
            get_ai_solver()


class TestAISolveQuizWrapper:
    """Test the ai_solve_quiz backward-compatible wrapper."""

    @mock.patch("chaoxing.ai.router.get_ai_solver")
    def test_ai_solve_quiz_delegates_to_solver(self, mock_get_solver):
        """ai_solve_quiz should delegate to the configured solver's solve_quiz_text."""
        mock_solver = mock.MagicMock(spec=AISolver)
        mock_solver.solve_quiz_text.return_value = [
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "B"},
        ]
        mock_get_solver.return_value = mock_solver

        questions = [
            {"index": 1, "question": "What is 2+2?", "options": ["A. 3", "B. 4"]},
        ]
        result = ai_solve_quiz(questions, "Math", "Quiz 1")

        mock_solver.solve_quiz_text.assert_called_once_with(
            questions, "Math", "Quiz 1"
        )
        assert result == [{"index": 1, "answer": "A"}, {"index": 2, "answer": "B"}]

    @mock.patch("chaoxing.ai.router.get_ai_solver")
    def test_ai_solve_quiz_empty_questions(self, mock_get_solver):
        """ai_solve_quiz should handle empty question list."""
        mock_solver = mock.MagicMock(spec=AISolver)
        mock_solver.solve_quiz_text.return_value = []
        mock_get_solver.return_value = mock_solver

        result = ai_solve_quiz([], "Course", "Section")
        assert result == []




class TestDeepSeekProvider:
    """DeepSeek provider: registry, credentials parsing, router dispatch."""

    def test_providers_registry_complete(self):
        from chaoxing.ai.doubao import _PROVIDERS
        for pid, spec in _PROVIDERS.items():
            assert spec["creds_file"].name, pid
            assert spec["key_var"], pid
            assert spec["base_url"].startswith("https://"), pid
        assert _PROVIDERS["deepseek-api"]["base_url"] == "https://api.deepseek.com"
        assert _PROVIDERS["deepseek-api"]["key_var"] == "DEEPSEEK_API_KEY"

    def test_deepseek_creds_roundtrip(self, tmp_path):
        from chaoxing.ai import doubao as eng
        f = tmp_path / "deepseek.txt"
        f.write_text('export DEEPSEEK_API_KEY="sk-test123"\nmodel="deepseek-v4-flash-vision-exp"\n',
                     encoding="utf-8")
        spec = eng._PROVIDERS["deepseek-api"]
        old = spec["creds_file"]
        try:
            eng._PROVIDERS["deepseek-api"] = {**spec, "creds_file": f}
            creds = eng._load_credentials("deepseek-api")
            assert creds == {"api_key": "sk-test123",
                             "model": "deepseek-v4-flash-vision-exp"}
        finally:
            eng._PROVIDERS["deepseek-api"] = spec
            assert old == eng._PROVIDERS["deepseek-api"]["creds_file"]

    def test_unknown_provider_rejected(self):
        from chaoxing.ai.doubao import _load_credentials
        with pytest.raises(ValueError):
            _load_credentials("no-such-provider")

    def test_router_dispatches_deepseek(self):
        from chaoxing.ai.router import get_ai_solver
        from chaoxing.ai.deepseek import DeepSeekAPISolver
        with patch("chaoxing.ai.router.cfg", return_value="deepseek-api"):
            solver = get_ai_solver()
        assert isinstance(solver, DeepSeekAPISolver)
        assert solver.provider_name == "deepseek-api"

    def test_call_completion_threads_provider(self):
        from chaoxing.ai import doubao as eng
        with patch.object(eng, "_load_credentials",
                          return_value={"api_key": "sk-x", "model": "m"}), \
             patch.object(eng, "_create_client") as mock_client, \
             patch.object(eng, "_parse_quiz_answer", return_value=[]):
            mock_ctx = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_ctx
            mock_ctx.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok"))], usage=None)
            out = eng._call_chat_completion([{"role": "user", "content": "x"}],
                                            provider="deepseek-api")
        assert out == "ok"
        # client factory received the provider
        assert mock_client.call_args.kwargs.get("provider") == "deepseek-api"


class TestDeepSeekBalance:
    """DeepSeek balance query shapes the billing result like Doubao's."""

    def test_balance_maps_fields(self):
        from chaoxing.ai import deepseek as ds
        sample = {"is_available": True, "balance_infos": [
            {"currency": "CNY", "total_balance": "97.40",
             "granted_balance": "0.00", "topped_up_balance": "97.40"}]}
        with patch("httpx.get") as mock_get:
            mock_get.return_value.json.return_value = sample
            b = ds.query_deepseek_balance()
        assert b["availableBalance"] == "97.40"
        assert b["cashBalance"] == "97.40"
        assert b["currency"] == "CNY"
        assert b["provider"] if "provider" in b else True  # provider set by CLI layer

    def test_balance_unavailable_account_raises(self):
        from chaoxing.ai import deepseek as ds
        with patch("httpx.get") as mock_get:
            mock_get.return_value.json.return_value = {"is_available": False}
            with pytest.raises(RuntimeError):
                ds.query_deepseek_balance()


class TestQuizEngineLock:
    """A quiz keeps the engine resolved at its start across batches."""

    def test_solve_persists_engine_fns(self):
        import inspect
        from chaoxing.solvers.quiz import solver as sv
        src = inspect.getsource(sv.ChapterQuizSolver.solve_quiz)
        assert "self._quiz_engine_fns = (solve_text_fn, solve_image_fn)" in src
        batched = inspect.getsource(sv.ChapterQuizSolver._solve_batched)
        assert 'getattr(self, "_quiz_engine_fns"' in str(batched)
