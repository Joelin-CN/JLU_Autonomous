"""Tests for chaoxing.platform.captcha — CAPTCHA detection and solving."""
import os
from unittest.mock import patch, MagicMock

from chaoxing.platform.captcha import (
    detect_captcha,
    solve_captcha,
    solve_captcha_image,
    captcha_paths_for_session,
    captcha_answer_path,
)


class TestCaptchaPaths:
    """Tests for the shared CAPTCHA path helpers (read/write side consistency)."""

    def test_default_session_no_suffix(self):
        """The single-account default session gets no per-account suffix."""
        img, ans = captcha_paths_for_session("chaoxing-chrome")
        assert img.endswith("_captcha_img.png")
        assert ans.endswith("_captcha_answer.txt")

    def test_multi_account_session_suffix(self):
        """Multi-account sessions get a _chaoxing-chrome-<N> suffix."""
        img, ans = captcha_paths_for_session("chaoxing-chrome-2")
        assert img.endswith("_captcha_img_chaoxing-chrome-2.png")
        assert ans.endswith("_captcha_answer_chaoxing-chrome-2.txt")

    def test_empty_session_treated_as_default(self):
        """An empty/None-ish session name falls back to no suffix."""
        img, ans = captcha_paths_for_session("")
        assert img.endswith("_captcha_img.png")
        assert ans.endswith("_captcha_answer.txt")

    def test_answer_path_matches_read_side(self):
        """captcha_answer_path(N) (write side) must equal the answer path the
        read side derives from session 'chaoxing-chrome-N' — the whole point of
        the shared helper is that these never drift apart."""
        for n in (0, 1, 7):
            write_path = captcha_answer_path(n)
            _, read_path = captcha_paths_for_session(f"chaoxing-chrome-{n}")
            assert write_path == read_path
            assert write_path.endswith(f"_captcha_answer_chaoxing-chrome-{n}.txt")


class TestSolveCaptchaImage:
    """Tests for solve_captcha_image — shared CAPTCHA OCR+extraction pipeline."""

    def test_returns_none_for_missing_image(self):
        """If the image file does not exist, should return None."""
        result = solve_captcha_image("/nonexistent/path/captcha.png")
        assert result is None

    def test_returns_none_for_too_small_image(self):
        """If the image file is too small (< 100 bytes), should return None."""
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=50):
            result = solve_captcha_image("/tmp/small.png")
            assert result is None

    def test_extracts_4char_answer(self):
        """When AI returns a clean 4-char answer, extract it properly."""
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("chaoxing.ai.doubao.doubao_ask_image") as mock_ask:
            mock_ask.return_value = "A3x9"
            result = solve_captcha_image("/tmp/captcha.png")
            assert result == "A3x9"

    def test_extracts_answer_with_noise(self):
        """Should clean noise markers and still extract the real answer."""
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("chaoxing.ai.doubao.doubao_ask_image") as mock_ask:
            mock_ask.return_value = (
                "识图模式\n深度思考\n验证码是: X7k2\n"
                "内容由 AI 生成，请仔细甄别"
            )
            result = solve_captcha_image("/tmp/captcha.png")
            assert result == "X7k2"

    def test_extracts_space_separated_answer(self):
        """Should handle space-separated alphanumeric answers (e.g. 'NS dn' -> 'NSdn')."""
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("chaoxing.ai.doubao.doubao_ask_image") as mock_ask:
            mock_ask.return_value = "NS dn"
            result = solve_captcha_image("/tmp/captcha.png")
            assert result == "NSdn"

    def test_4char_pattern_has_priority(self):
        """4-char pattern is checked first (most common CAPTCHA length)
        and will match before 5-char or 6-char patterns."""
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("chaoxing.ai.doubao.doubao_ask_image") as mock_ask:
            # "ABc12" has 5 chars but 4-char pattern matches "ABc1" first
            mock_ask.return_value = "ABc12"
            result = solve_captcha_image("/tmp/captcha.png")
            assert result == "ABc1"

    def test_extracts_3char_answer(self):
        """Should handle 3-character CAPTCHA answers (fallback)."""
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("chaoxing.ai.doubao.doubao_ask_image") as mock_ask:
            mock_ask.return_value = "x9Z"
            result = solve_captcha_image("/tmp/captcha.png")
            assert result == "x9Z"

    def test_last_resort_extraction(self):
        """Should return None when answer has no alphanumeric chars."""
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("chaoxing.ai.doubao.doubao_ask_image") as mock_ask:
            mock_ask.return_value = '"验证码"'
            result = solve_captcha_image("/tmp/captcha.png")
            assert result is None  # "验证码" has no alphanumeric

    def test_uses_format_captcha_prompt(self):
        """Should use the shared CAPTCHA prompt from chaoxing.ai.prompts."""
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("chaoxing.ai.doubao.doubao_ask_image") as mock_ask, \
             patch("chaoxing.platform.captcha.format_captcha_prompt") as mock_prompt:
            mock_prompt.return_value = (
                "请识别图片中的验证码文字。只返回验证码文字本身，不要其他任何内容。"
            )
            mock_ask.return_value = "ABCD"
            result = solve_captcha_image("/tmp/captcha.png")
            mock_prompt.assert_called_once()
            assert result == "ABCD"


class TestDetectCaptcha:
    """Tests for detect_captcha — CAPTCHA presence detection."""

    def test_no_captcha_found(self):
        """When no CAPTCHA markers exist, returns JSON with captcha=False."""
        mock_tmp = MagicMock()
        with patch("tempfile.NamedTemporaryFile", return_value=mock_tmp), \
             patch("chaoxing.platform.captcha.pw_run_code_file") as mock_run, \
             patch("chaoxing.platform.captcha.pw_extract_result") as mock_extract:
            mock_run.return_value = "raw_result"
            mock_extract.return_value = '{"captcha":false,"reason":"not-found"}'
            result = detect_captcha()
            assert "captcha" in result.lower()
            assert "false" in result.lower()

    def test_captcha_found_with_img_box(self):
        """When CAPTCHA markers exist, returns JSON with captcha=True and imgBox."""
        mock_tmp = MagicMock()
        with patch("tempfile.NamedTemporaryFile", return_value=mock_tmp), \
             patch("chaoxing.platform.captcha.pw_run_code_file") as mock_run, \
             patch("chaoxing.platform.captcha.pw_extract_result") as mock_extract:
            mock_run.return_value = "raw_result"
            mock_extract.return_value = (
                '{"captcha":true,"imgBox":{"x":100,"y":200,"width":80,"height":30},'
                '"tbBox":{"x":120,"y":250,"width":60,"height":25},'
                '"btnBox":{"x":200,"y":250,"width":40,"height":25},'
                '"source":"main-page","snippet":"请填写验证码"}'
            )
            result = detect_captcha()
            assert "captcha" in result.lower()
            assert "true" in result.lower()
            assert "imgBox" in result


class TestSolveCaptcha:
    """Tests for solve_captcha — full detection + solve pipeline."""

    def test_no_captcha_returns_true(self):
        """When no CAPTCHA is detected, solve_captcha returns True immediately."""
        with patch("chaoxing.platform.captcha.detect_captcha") as mock_detect:
            mock_detect.return_value = '{"captcha":false,"reason":"not-found"}'
            result = solve_captcha()
            assert result is True

    def test_none_answer_rejected(self):
        """F4 fix: when solve_captcha_image returns None, return False instead
        of injecting the literal string "None" into the CAPTCHA fill JS."""
        mock_tmp_extract = MagicMock()
        mock_tmp_extract.name = "/tmp/extract.js"

        with patch("chaoxing.platform.captcha.detect_captcha") as mock_detect, \
             patch("chaoxing.platform.captcha.solve_captcha_image") as mock_solve_img, \
             patch("chaoxing.platform.captcha._get_active_session") as mock_session, \
             patch("chaoxing.platform.captcha.pw_run_code_file") as mock_run, \
             patch("chaoxing.platform.captcha.pw_extract_result") as mock_extract, \
             patch("tempfile.NamedTemporaryFile") as mock_tmpfile, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("builtins.open") as mock_open, \
             patch("base64.b64decode", return_value=b"fake_png_data"):
            mock_detect.return_value = (
                '{"captcha":true,"imgBox":{"x":100,"y":200,"width":80,"height":30}}'
            )
            mock_session.return_value = "test-session"
            mock_tmpfile.return_value = mock_tmp_extract
            mock_run.return_value = "raw"
            mock_extract.return_value = "data:image/png;base64,ZmFrZQ=="
            mock_solve_img.return_value = None  # Answer extraction failed!

            result = solve_captcha()
            assert result is False
            mock_solve_img.assert_called_once()

    def test_valid_answer_accepted(self):
        """When solve_captcha_image returns a valid answer, the fill pipeline runs."""
        mock_tmp_extract = MagicMock()
        mock_tmp_extract.name = "/tmp/extract.js"
        mock_tmp_fill = MagicMock()
        mock_tmp_fill.name = "/tmp/fill.js"

        with patch("chaoxing.platform.captcha.detect_captcha") as mock_detect, \
             patch("chaoxing.platform.captcha.solve_captcha_image") as mock_solve_img, \
             patch("chaoxing.platform.captcha._get_active_session") as mock_session, \
             patch("chaoxing.platform.captcha.pw_run_code_file") as mock_run, \
             patch("chaoxing.platform.captcha.pw_extract_result") as mock_extract, \
             patch("tempfile.NamedTemporaryFile") as mock_tmpfile, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("builtins.open") as mock_open, \
             patch("base64.b64decode", return_value=b"fake_png_data"), \
             patch("os.unlink") as mock_unlink:
            mock_detect.return_value = (
                '{"captcha":true,"imgBox":{"x":100,"y":200,"width":80,"height":30}}'
            )
            mock_session.return_value = "test-session"
            mock_solve_img.return_value = "A3x9"
            # Two tempfile calls: one for extract, one for fill
            mock_tmpfile.side_effect = [mock_tmp_extract, mock_tmp_fill]
            mock_run.side_effect = ["raw_extract", "raw_fill"]
            mock_extract.side_effect = [
                "data:image/png;base64,ZmFrZQ==",
                "solved:https://example.com/ok",
            ]

            result = solve_captcha()
            assert result is True
            mock_solve_img.assert_called_once()

    def test_no_img_box_returns_false(self):
        """When CAPTCHA text is found but no image box, return False."""
        with patch("chaoxing.platform.captcha.detect_captcha") as mock_detect:
            mock_detect.return_value = (
                '{"captcha":true,"imgBox":null,"snippet":"验证码错误"}'
            )
            result = solve_captcha()
            assert result is False

    def test_json_parse_failure_with_captcha_text(self):
        """When JSON parsing fails but CAPTCHA text is found, return False."""
        with patch("chaoxing.platform.captcha.detect_captcha") as mock_detect:
            mock_detect.return_value = 'some garbage 操作异常 here'
            result = solve_captcha()
            assert result is False
