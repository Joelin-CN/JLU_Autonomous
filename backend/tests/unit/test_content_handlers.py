"""Tests for chaoxing.solvers.content.handlers — content handlers and helpers."""
from unittest.mock import patch, MagicMock

from chaoxing.solvers.content.handlers import (
    _is_section_complete,
    VideoHandler,
    DocumentHandler,
    AudioHandler,
    GenericHandler,
)


class TestIsSectionComplete:
    """Tests for _is_section_complete — checks if a section is marked done."""

    def test_chinese_task_complete(self):
        """Should detect '任务点完成' in snapshot."""
        snap = "任务点完成  章节1.1"
        assert _is_section_complete(snap) is True

    def test_chinese_completed(self):
        """Should detect '已完成' in snapshot."""
        snap = "已完成  100%"
        assert _is_section_complete(snap) is True

    def test_chinese_study_complete(self):
        """Should detect '学习完成' in snapshot."""
        snap = "学习完成！恭喜"
        assert _is_section_complete(snap) is True

    def test_green_check(self):
        """Should detect 'green_check' in snapshot."""
        snap = "status: green_check icon"
        assert _is_section_complete(snap) is True

    def test_english_completed(self):
        """Should detect 'completed' in snapshot."""
        snap = "Task completed successfully"
        assert _is_section_complete(snap) is True

    def test_not_complete(self):
        """Should return False when no indicators are present."""
        snap = "未完成  待学习  继续"
        assert _is_section_complete(snap) is False

    def test_empty_snapshot(self):
        """Should return False for empty snapshot."""
        assert _is_section_complete("") is False


class TestVideoHandler:
    """Tests for VideoHandler.can_handle."""

    def test_can_handle_video(self):
        handler = VideoHandler()
        assert handler.can_handle("video") is True

    def test_cannot_handle_document(self):
        handler = VideoHandler()
        assert handler.can_handle("document") is False

    def test_cannot_handle_audio(self):
        handler = VideoHandler()
        assert handler.can_handle("audio") is False

    def test_cannot_handle_unknown(self):
        handler = VideoHandler()
        assert handler.can_handle("unknown-type") is False

    def test_cannot_handle_empty(self):
        handler = VideoHandler()
        assert handler.can_handle("") is False


class TestDocumentHandler:
    """Tests for DocumentHandler.can_handle."""

    def test_can_handle_document(self):
        handler = DocumentHandler()
        assert handler.can_handle("document") is True

    def test_cannot_handle_video(self):
        handler = DocumentHandler()
        assert handler.can_handle("video") is False

    def test_cannot_handle_audio(self):
        handler = DocumentHandler()
        assert handler.can_handle("audio") is False


class TestAudioHandler:
    """Tests for AudioHandler.can_handle."""

    def test_can_handle_audio(self):
        handler = AudioHandler()
        assert handler.can_handle("audio") is True

    def test_cannot_handle_video(self):
        handler = AudioHandler()
        assert handler.can_handle("video") is False

    def test_cannot_handle_document(self):
        handler = AudioHandler()
        assert handler.can_handle("document") is False


class TestGenericHandler:
    """Tests for GenericHandler.can_handle — always returns True."""

    def test_can_handle_any_type(self):
        handler = GenericHandler()
        assert handler.can_handle("video") is True
        assert handler.can_handle("document") is True
        assert handler.can_handle("audio") is True
        assert handler.can_handle("unknown-type") is True

    def test_can_handle_empty_string(self):
        handler = GenericHandler()
        assert handler.can_handle("") is True

    def test_can_handle_none(self):
        handler = GenericHandler()
        # Even None should work (used as catch-all)
        assert handler.can_handle(None) is True


class TestCheckAntiSpider:
    """Tests for check_anti_spider — CAPTCHA guard used by content bot."""

    def test_no_captcha_returns_true(self):
        """When no CAPTCHA is present, returns True (all clear)."""
        from chaoxing.solvers.content.handlers import check_anti_spider

        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/check.js"

        with patch("chaoxing.solvers.content.handlers.pw_run_code") as mock_run_code, \
             patch("chaoxing.solvers.content.handlers.pw_extract_result") as mock_extract, \
             patch("tempfile.NamedTemporaryFile", return_value=mock_tmp), \
             patch("os.unlink") as mock_unlink:
            mock_run_code.return_value = "url_raw"
            mock_extract.side_effect = [
                "https://mooc1.chaoxing.com/mycourse/studentstudy",
                '{"captcha":false}',
            ]

            result = check_anti_spider()
            assert result is True

    def test_captcha_solved_via_shared_solver(self):
        """When CAPTCHA is detected and image exists, uses solve_captcha_image
        (shared deduplicated pipeline) and auto-fills on success."""
        from chaoxing.solvers.content.handlers import check_anti_spider

        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/check.js"

        # Call sequence for full solve path:
        # pw_run_code: 1 (URL check)
        # pw_extract_result: 4 (URL, iframe JSON, image extract, fill result)
        # pw_run_code_file: 3 (iframe check, image extract, fill inject)
        with patch("chaoxing.solvers.content.handlers.pw_run_code") as mock_run_code, \
             patch("chaoxing.solvers.content.handlers.pw_extract_result") as mock_extract, \
             patch("chaoxing.solvers.content.handlers.pw_run_code_file") as mock_run_file, \
             patch("chaoxing.solvers.content.handlers.solve_captcha_image") as mock_solve_img, \
             patch("tempfile.NamedTemporaryFile", return_value=mock_tmp), \
             patch("os.unlink") as mock_unlink, \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("builtins.open") as mock_open:
            mock_run_code.return_value = "url_raw"
            mock_run_file.return_value = "raw_output"
            mock_solve_img.return_value = "A3x9"
            # 4 extract_result calls: URL | iframe JSON | image extract | fill
            mock_extract.side_effect = [
                "https://mooc1.chaoxing.com/antispider?key=xyz",
                '{"captcha":true,"text":"操作异常","inAntispiderFrame":true}',
                "ok-80x30",
                "solved",
            ]

            result = check_anti_spider()
            assert result is True
            # Key assertion: shared solver was called (dedup proof)
            mock_solve_img.assert_called_once()

    # ── Manual-intervention TICKET chain ──────────────────────────

    def _run_fallback(self, *, answer_file_content=None, answer_file_exists,
                      extract_after_setup):
        """Drive check_anti_spider() into the manual-fallback loop.

        Sets up the common mocks so that a CAPTCHA is detected, the AI solver
        returns None (forcing the fallback loop), then lets the caller control
        the answer-file presence/content and the iframe-recheck verdict.

        Args:
            answer_file_content: String returned when the answer file is read.
            answer_file_exists: Whether os.path.exists() reports the answer file.
            extract_after_setup: Value returned by pw_extract_result for every
                call after the 3 setup calls (URL / iframe / image-extract) —
                used for the iframe re-check and/or the fill result.

        Returns:
            (result, ticket_calls) — the function return value and the list of
            ticket dicts emitted.
        """
        from chaoxing.solvers.content import handlers

        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/check.js"

        call = {"n": 0}

        def extract_side(_raw):
            call["n"] += 1
            if call["n"] == 1:
                return "https://mooc1.chaoxing.com/antispider?key=xyz"
            if call["n"] == 2:
                return '{"captcha":true,"text":"操作异常","inAntispiderFrame":true}'
            if call["n"] == 3:
                return "ok-80x30"  # image extract (not a data: URL)
            return extract_after_setup

        def exists_side(path):
            if "answer" in str(path):
                return answer_file_exists
            return True  # image always "exists" for base64 + size checks

        def open_side(path, mode="r", *a, **k):
            m = MagicMock()
            handle = m.__enter__.return_value
            if "b" in mode:
                handle.read.return_value = b"\x89PNG" + b"x" * 200
            else:
                handle.read.return_value = answer_file_content
            return m

        ticket_calls = []

        with patch.object(handlers, "pw_run_code", return_value="raw"), \
             patch.object(handlers, "pw_extract_result", side_effect=extract_side), \
             patch.object(handlers, "pw_run_code_file", return_value="raw"), \
             patch.object(handlers, "solve_captcha_image", return_value=None), \
             patch.object(handlers, "_get_active_session",
                          return_value="chaoxing-chrome-0"), \
             patch.object(handlers, "ticket",
                          side_effect=lambda d: ticket_calls.append(d)), \
             patch("tempfile.NamedTemporaryFile", return_value=mock_tmp), \
             patch("os.unlink"), \
             patch("os.path.exists", side_effect=exists_side), \
             patch("os.path.getsize", return_value=500), \
             patch("time.sleep"), \
             patch("builtins.open", side_effect=open_side):
            result = handlers.check_anti_spider()
        return result, ticket_calls

    def test_fallback_emits_unresolved_ticket(self):
        """Entering the manual-fallback loop emits a resolved:false captcha
        ticket carrying accountId, options, and a base64 image."""
        # Answer file solves on the first poll so the loop exits fast.
        result, tickets = self._run_fallback(
            answer_file_content="A3x9",
            answer_file_exists=True,
            extract_after_setup="solved",
        )
        assert result is True
        # First ticket is the unresolved intervention request.
        first = tickets[0]
        assert first["type"] == "captcha"
        assert first["resolved"] is False
        assert first["accountId"] == 0
        assert first["id"].startswith("captcha_0_")
        assert first["options"] == ["输入验证码", "跳过此课程"]
        assert first["imageBase64"].startswith("data:image/png;base64,")
        # Last ticket voids it as solved.
        assert tickets[-1]["resolved"] is True
        assert tickets[-1]["resolution"] == "solved"

    def test_fallback_skip_sentinel_returns_false(self):
        """A __SKIP__ answer makes check_anti_spider() return False (skip the
        course) and emit a resolved:true 'skipped' ticket."""
        result, tickets = self._run_fallback(
            answer_file_content="__SKIP__",
            answer_file_exists=True,
            extract_after_setup="irrelevant",
        )
        assert result is False
        assert tickets[0]["resolved"] is False  # initial request
        assert tickets[-1]["resolved"] is True
        assert tickets[-1]["resolution"] == "skipped"

    def test_fallback_timeout_emits_void_ticket(self):
        """When no answer arrives and the CAPTCHA never clears, the loop times
        out, returns False, and emits a resolved:true 'timeout' ticket."""
        # Answer file never present; iframe re-check always reports captcha.
        result, tickets = self._run_fallback(
            answer_file_content=None,
            answer_file_exists=False,
            extract_after_setup='{"captcha":true}',
        )
        assert result is False
        assert tickets[0]["resolved"] is False
        assert tickets[-1]["resolved"] is True
        assert tickets[-1]["resolution"] == "timeout"

    def test_fallback_wrong_answer_refreshes_same_ticket(self):
        """A wrong answer must NOT be re-submitted on the next poll: the answer
        file is deleted after reading (bug fix), and the backend re-grabs a
        refreshed CAPTCHA image and re-emits the SAME ticket id with the
        ORIGINAL createdAt (resolved:false) so the frontend reopens its input
        and its 10-min countdown continues uninterrupted."""
        from chaoxing.solvers.content import handlers

        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/check.js"

        # extract_result call sequence:
        #   1 URL | 2 iframe JSON | 3 initial image-extract
        #   poll 1: 4 fill="still-captcha" (wrong) | 5 re-extract image
        #           | 6 iframe re-check -> captcha gone -> solved & return
        call = {"n": 0}

        def extract_side(_raw):
            call["n"] += 1
            seq = {
                1: "https://mooc1.chaoxing.com/antispider?key=xyz",
                2: '{"captcha":true,"text":"操作异常","inAntispiderFrame":true}',
                3: "ok-80x30",
                4: "still-captcha",          # wrong answer submitted
                5: "ok-90x30",               # refreshed image re-extracted
                6: '{"captcha":false}',      # solved manually in Chrome -> end
            }
            return seq.get(call["n"], '{"captcha":false}')

        unlinked = []

        def unlink_side(path):
            unlinked.append(str(path))

        def open_side(path, mode="r", *a, **k):
            m = MagicMock()
            handle = m.__enter__.return_value
            if "b" in mode:
                handle.read.return_value = b"\x89PNG" + b"x" * 200
            else:
                handle.read.return_value = "WRONG"  # the wrong answer
            return m

        ticket_calls = []

        with patch.object(handlers, "pw_run_code", return_value="raw"), \
             patch.object(handlers, "pw_extract_result", side_effect=extract_side), \
             patch.object(handlers, "pw_run_code_file", return_value="raw"), \
             patch.object(handlers, "solve_captcha_image", return_value=None), \
             patch.object(handlers, "_get_active_session",
                          return_value="chaoxing-chrome-0"), \
             patch.object(handlers, "ticket",
                          side_effect=lambda d: ticket_calls.append(d)), \
             patch("tempfile.NamedTemporaryFile", return_value=mock_tmp), \
             patch("os.unlink", side_effect=unlink_side), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=500), \
             patch("time.sleep"), \
             patch("builtins.open", side_effect=open_side):
            result = handlers.check_anti_spider()

        assert result is True
        # The answer file was deleted after being read (bug fix) — no stale
        # wrong answer left on disk to be re-submitted next poll.
        assert any("answer" in p for p in unlinked)

        initial = ticket_calls[0]
        # A retry ticket: same id, still unresolved, ORIGINAL createdAt preserved.
        retry = next(t for t in ticket_calls[1:]
                     if t.get("resolved") is False)
        assert retry["id"] == initial["id"]
        assert retry["createdAt"] == initial["createdAt"]   # countdown continuity
        assert retry["imageBase64"].startswith("data:image/png;base64,")
        assert "有误" in retry["message"]
        # Terminal event still closes the same ticket.
        assert ticket_calls[-1]["resolved"] is True
        assert ticket_calls[-1]["resolution"] == "solved"
        assert ticket_calls[-1]["createdAt"] == initial["createdAt"]

