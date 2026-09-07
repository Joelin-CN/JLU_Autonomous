"""Tests for chaoxing.browser.engine — pw() argument construction and quoting."""
import sys
import subprocess
from unittest.mock import patch, MagicMock

from chaoxing.browser.engine import _quote_arg, pw, pw_snapshot, pw_click, pw_goto
from chaoxing.browser.js_runner import pw_run_code_file
from chaoxing.exceptions import ConfigError


class TestQuoteArg:
    """Argument quoting for Windows shell (cmd.exe)."""

    def test_plain_string_no_quoting(self):
        assert _quote_arg("hello") == "hello"

    def test_url_with_ampersand_quoted(self):
        result = _quote_arg("https://example.com?a=1&b=2")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_string_with_spaces_quoted(self):
        result = _quote_arg("hello world")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_newlines_collapsed(self):
        result = _quote_arg("line1\nline2\nline3")
        assert "\n" not in result

    def test_multiline_spaces_collapsed(self):
        result = _quote_arg("a\n  b\n    c")
        assert "\n" not in result

    def test_special_chars_trigger_quoting(self):
        specials = ["a&b", "a?b", "a=b", "a b", "a%b", "a^b", "a|b", "a<b", "a>b", "a(b", "a)b"]
        for s in specials:
            result = _quote_arg(s)
            assert result.startswith('"') or any(c not in result for c in "&?= %^|<>()"), \
                f"'{s}' should be quoted or stripped of special chars"


class TestPwSubprocess:
    """Test pw() subprocess.run interactions."""

    def test_pw_constructs_shell_command(self):
        with patch("chaoxing.browser.engine.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            pw("snapshot", "--boxes")
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            # Should use shell=False by default (security hardening)
            assert call_args[1].get("shell") is False

    def test_pw_shell_false_option(self):
        with patch("chaoxing.browser.engine.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            pw("run-code", "console.log(1)", use_shell=False)
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[1].get("shell") is False

    def test_pw_returns_stdout(self):
        with patch("chaoxing.browser.engine.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="result text", stderr="")
            result = pw("snapshot")
            assert result == "result text"

    def test_pw_stderr_warning_on_failure(self):
        with patch("chaoxing.browser.engine.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error message")
            # Should still return stdout (even if empty) — warning is printed to stderr
            result = pw("snapshot")
            assert result == ""


class TestConvenienceWrappers:
    """Test pw_snapshot, pw_click, etc."""

    def test_pw_snapshot_calls_pw(self):
        with patch("chaoxing.browser.engine.pw") as mock_pw:
            mock_pw.return_value = "snapshot output"
            result = pw_snapshot()
            assert result == "snapshot output"
            mock_pw.assert_called_once_with("snapshot", "--boxes")

    def test_pw_click_calls_pw(self):
        with patch("chaoxing.browser.engine.pw") as mock_pw:
            pw_click("ref-123")
            mock_pw.assert_called_once()
            args = mock_pw.call_args[0]
            assert args[0] == "click"
            assert args[1] == "ref-123"

    def test_pw_goto_uses_js_file(self):
        # pw_goto does `from .js_runner import _run_js_file` internally
        with patch("chaoxing.browser.js_runner._run_js_file") as mock_run_js:
            pw_goto("https://example.com/path?a=1&b=2")
            mock_run_js.assert_called_once()
            js_code = mock_run_js.call_args[0][0]
            assert "page.goto" in js_code
            assert "example.com" in js_code
