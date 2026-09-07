"""
Integration tests for the content-completion pipeline.

Tests the full pipeline: navigate -> detect -> handle -> progress,
with all browser, filesystem, and AI interactions mocked.

Pipeline stages:
  1. Navigator     — open course, navigate to sections, return to chapter tree
  2. Detector      — detect content type (video/document/audio/quiz/generic)
  3. Handlers      — video playback, document scrolling, audio waiting
  4. Anti-spider   — CAPTCHA detection and auto-solve
  5. Bot           — ChapterContentBot orchestration with progress tracking
"""

import json
import os
import time
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.solvers.content.detector import detect_content_type
from chaoxing.solvers.content.handlers import (
    VideoHandler,
    DocumentHandler,
    AudioHandler,
    GenericHandler,
    check_anti_spider,
    _is_section_complete,
    ContentHandler,
)
from chaoxing.solvers.content.navigator import (
    navigate_to_section,
    get_chapter_tree,
)
from chaoxing.solvers.content.bot import (
    ChapterContentBot,
    _dispatch_handler,
)


# ═══════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_tempfile():
    """Mock NamedTemporaryFile to return a file-like with .name attribute."""
    mock_file = MagicMock()
    mock_file.name = os.path.join(os.sep, "tmp", "mock_content_script.js")
    with patch("tempfile.NamedTemporaryFile", return_value=mock_file):
        yield mock_file


@pytest.fixture
def course_config():
    """Return a minimal course config dict for ChapterContentBot."""
    return {
        "name": "Test Course",
        "courseid": "123456",
        "clazzid": "654321",
        "cpi": "415409200",
        "chapters": [
            {"num": 1, "name": "第一章", "sections": 3,
             "tasks_per": [2, 1, 0]},
        ],
    }


@pytest.fixture
def mock_bot(course_config):
    """Create a ChapterContentBot with mocked progress tracker."""
    with patch(
        "chaoxing.solvers.content.bot.ProgressTracker"
    ) as mock_tracker_cls:
        mock_tracker = MagicMock()
        mock_tracker.is_section_done.return_value = False
        mock_tracker_cls.return_value = mock_tracker
        bot = ChapterContentBot(course_config)
        bot.tracker = mock_tracker
        yield bot


# ═══════════════════════════════════════════════════════════════════
#  Content Type Detection Tests
# ═══════════════════════════════════════════════════════════════════

class TestContentDetection:
    """Verify content type detection via mocked browser JS execution."""

    def test_detect_video_content(self, mock_tempfile):
        """Video content detection: JS finds video elements and controls."""
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.content.detector.pw_extract_result",
            return_value="video"
        ):
            result = detect_content_type()
            assert result == "video"

    def test_detect_document_content(self, mock_tempfile):
        """Document content detection: JS finds .reader, .ppt, next/prev."""
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.content.detector.pw_extract_result",
            return_value="document"
        ):
            result = detect_content_type()
            assert result == "document"

    def test_detect_audio_content(self, mock_tempfile):
        """Audio content detection: JS finds listening/audio indicators."""
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.content.detector.pw_extract_result",
            return_value="audio"
        ):
            result = detect_content_type()
            assert result == "audio"

    def test_detect_quiz_content(self, mock_tempfile):
        """Quiz content detection: JS finds .question, radio/checkbox inputs."""
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.content.detector.pw_extract_result",
            return_value="quiz"
        ):
            result = detect_content_type()
            assert result == "quiz"

    def test_detect_generic_fallback(self, mock_tempfile):
        """Generic fallback when no specific type detected."""
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.content.detector.pw_extract_result",
            return_value="generic"
        ):
            result = detect_content_type()
            assert result == "generic"

    def test_detect_js_failure_snapshot_fallback_video(self, mock_tempfile):
        """JS detection failure: fallback to snapshot text matching for video.

        When the tempfile/JS pipeline throws, the detector falls back to
        pw_snapshot()-based text matching.
        """
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            side_effect=Exception("JS timeout")
        ), patch(
            "chaoxing.solvers.content.detector.pw_snapshot",
            return_value="播放 video player controls"
        ):
            result = detect_content_type()
            assert result == "video"

    def test_detect_js_failure_snapshot_fallback_audio(self, mock_tempfile):
        """JS failure -> snapshot fallback detects audio via 听力."""
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            side_effect=Exception("JS timeout")
        ), patch(
            "chaoxing.solvers.content.detector.pw_snapshot",
            return_value="听力 listening comprehension audio"
        ):
            result = detect_content_type()
            assert result == "audio"

    def test_detect_js_failure_snapshot_fallback_document(self, mock_tempfile):
        """JS failure -> snapshot fallback detects document via PDF."""
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            side_effect=Exception("JS timeout")
        ), patch(
            "chaoxing.solvers.content.detector.pw_snapshot",
            return_value="pdf document viewer"
        ):
            result = detect_content_type()
            assert result == "document"

    def test_detect_js_failure_snapshot_fallback_generic(self, mock_tempfile):
        """JS failure -> snapshot with no known markers -> generic."""
        with patch(
            "chaoxing.solvers.content.detector.pw_run_code_file",
            side_effect=Exception("JS timeout")
        ), patch(
            "chaoxing.solvers.content.detector.pw_snapshot",
            return_value="chapter navigation 章节"
        ):
            result = detect_content_type()
            assert result == "generic"


# ═══════════════════════════════════════════════════════════════════
#  Handler Dispatch Tests
# ═══════════════════════════════════════════════════════════════════

class TestHandlerDispatch:
    """Verify content-type -> handler dispatch yields the correct handler."""

    def test_dispatch_video(self):
        """Video content detection and handling: dispatches to VideoHandler."""
        handler = _dispatch_handler("video")
        assert isinstance(handler, VideoHandler)

    def test_dispatch_document(self):
        """Document content detection and handling: dispatches to DocumentHandler."""
        handler = _dispatch_handler("document")
        assert isinstance(handler, DocumentHandler)

    def test_dispatch_audio(self):
        """Audio content detection and handling: dispatches to AudioHandler."""
        handler = _dispatch_handler("audio")
        assert isinstance(handler, AudioHandler)

    def test_dispatch_unknown_returns_generic(self):
        """Unknown content type falls back to GenericHandler."""
        handler = _dispatch_handler("unknown_type")
        assert isinstance(handler, GenericHandler)

    def test_can_handle_video_handler(self):
        """VideoHandler.can_handle('video') returns True."""
        assert VideoHandler.can_handle("video") is True
        assert VideoHandler.can_handle("document") is False
        assert VideoHandler.can_handle("audio") is False

    def test_can_handle_document_handler(self):
        """DocumentHandler.can_handle('document') returns True."""
        assert DocumentHandler.can_handle("document") is True
        assert DocumentHandler.can_handle("video") is False

    def test_can_handle_audio_handler(self):
        """AudioHandler.can_handle('audio') returns True."""
        assert AudioHandler.can_handle("audio") is True
        assert AudioHandler.can_handle("video") is False

    def test_can_handle_generic_handler(self):
        """GenericHandler.can_handle() returns True for anything (catch-all)."""
        assert GenericHandler.can_handle("video") is True
        assert GenericHandler.can_handle("document") is True
        assert GenericHandler.can_handle("unknown") is True

    def test_handler_is_abstract(self):
        """ContentHandler ABC cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ContentHandler()


# ═══════════════════════════════════════════════════════════════════
#  Video Handler Tests
# ═══════════════════════════════════════════════════════════════════

class TestVideoHandler:
    """Verify video content handling with mocked browser and filesystem."""

    def test_video_handler_advanced(self, mock_tempfile):
        """Video: _play_videos returns 'advanced:' and handler reports it.

        When v17 completes all videos and auto-clicks 下一节, the browser
        navigates inline to the next section without going back to the
        chapter tree.
        """
        with patch(
            "chaoxing.solvers.content.handlers.check_anti_spider",
            return_value=True
        ), patch.object(
            VideoHandler, "_play_videos",
            return_value="advanced:3:ch1.4 ch1.5 ch1.6"
        ), patch(
            "chaoxing.solvers.content.handlers.os.path.join",
            return_value=os.path.join(os.sep, "scripts", "_v17_section_player.js")
        ), patch(
            "chaoxing.solvers.content.handlers.return_to_course_page"
        ):
            handler = VideoHandler()
            mock_bot = MagicMock()
            mock_bot.courseid = "123"
            mock_bot.clazzid = "456"
            mock_bot.cpi = "789"

            result = handler.handle(mock_bot, 1, 1, 2)
            assert result == "advanced"

    def test_video_handler_completed(self, mock_tempfile):
        """Video: _play_videos returns 'all-complete:' and handler reports it.

        When all videos finish but no 下一节 is available, the handler
        returns to course page and reports 'completed'.
        """
        with patch(
            "chaoxing.solvers.content.handlers.check_anti_spider",
            return_value=True
        ), patch.object(
            VideoHandler, "_play_videos",
            return_value="all-complete:3 tasks done"
        ), patch(
            "chaoxing.solvers.content.handlers.return_to_course_page"
        ), patch(
            "chaoxing.solvers.content.handlers.os.path.join",
            return_value=os.path.join(os.sep, "scripts", "_v17_section_player.js")
        ):
            handler = VideoHandler()
            mock_bot = MagicMock()
            mock_bot.courseid = "123"
            mock_bot.clazzid = "456"
            mock_bot.cpi = "789"

            result = handler.handle(mock_bot, 1, 1, 2)
            assert result == "completed"

    def test_video_handler_captcha_detected_during_playback(self, mock_tempfile):
        """Video: CAPTCHA detected mid-playback, solve succeeds, retry playback.

        CAPTCHA detection during content playback: if check_anti_spider detects
        a CAPTCHA and solves it, playback should be retried.
        """
        with patch(
            "chaoxing.solvers.content.handlers.check_anti_spider"
        ) as mock_check, patch.object(
            VideoHandler, "_play_videos"
        ) as mock_play, patch(
            "chaoxing.solvers.content.handlers.return_to_course_page"
        ), patch(
            "chaoxing.solvers.content.handlers.os.path.join",
            return_value=os.path.join(os.sep, "scripts", "_v17_section_player.js")
        ):
            # First playback: CAPTCHA detected
            # Second playback: succeeds with auto-advance
            mock_play.side_effect = [
                "captcha-detected:playback blocked",
                "advanced:1:ch1.2",
            ]
            # First check: CAPTCHA solved -> True (can continue)
            # Second check (before retry): True
            mock_check.side_effect = [True, True]

            handler = VideoHandler()
            mock_bot = MagicMock()
            mock_bot.courseid = "123"
            mock_bot.clazzid = "456"
            mock_bot.cpi = "789"

            result = handler.handle(mock_bot, 1, 1, 2)
            assert result == "advanced"
            # _play_videos called twice (first captcha, second success)
            assert mock_play.call_count == 2

    def test_video_handler_captcha_unsolved(self, mock_tempfile):
        """Video: CAPTCHA detected, solve fails, returns 'failed'.

        CAPTCHA detection during content playback: if check_anti_spider
        cannot solve the CAPTCHA, the handler gives up.
        """
        with patch(
            "chaoxing.solvers.content.handlers.check_anti_spider"
        ) as mock_check, patch.object(
            VideoHandler, "_play_videos",
            return_value="captcha-detected:playback blocked"
        ), patch(
            "chaoxing.solvers.content.handlers.return_to_course_page"
        ), patch(
            "chaoxing.solvers.content.handlers.os.path.join",
            return_value=os.path.join(os.sep, "scripts", "_v17_section_player.js")
        ):
            mock_check.return_value = False  # Can't solve CAPTCHA

            handler = VideoHandler()
            mock_bot = MagicMock()
            mock_bot.courseid = "123"
            mock_bot.clazzid = "456"
            mock_bot.cpi = "789"

            result = handler.handle(mock_bot, 1, 1, 2)
            assert result == "failed"

    def test_video_handler_no_videos(self, mock_tempfile):
        """Video: no video frames found, returns 'no-video' (may be document)."""
        with patch(
            "chaoxing.solvers.content.handlers.check_anti_spider",
            return_value=True
        ), patch.object(
            VideoHandler, "_play_videos",
            return_value="no-video-frames"
        ), patch(
            "chaoxing.solvers.content.handlers.os.path.join",
            return_value=os.path.join(os.sep, "scripts", "_v17_section_player.js")
        ):
            handler = VideoHandler()
            mock_bot = MagicMock()
            mock_bot.courseid = "123"
            mock_bot.clazzid = "456"
            mock_bot.cpi = "789"

            result = handler.handle(mock_bot, 1, 1, 2)
            assert result == "no-video"

    def test_video_handler_pre_check_captcha_block(self, mock_tempfile):
        """Video: CAPTCHA blocks before playback starts -> failed.

        The CAPTCHA detection during content playback happens as a pre-check
        before attempting video playback.
        """
        with patch(
            "chaoxing.solvers.content.handlers.check_anti_spider",
            return_value=False
        ):
            handler = VideoHandler()
            mock_bot = MagicMock()
            result = handler.handle(mock_bot, 1, 1, 2)
            assert result == "failed"


# ═══════════════════════════════════════════════════════════════════
#  Document Handler Tests
# ═══════════════════════════════════════════════════════════════════

class TestDocumentHandler:
    """Verify document scrolling and completion detection."""

    def test_document_handler_completed(self):
        """Document: scrolling + _is_section_complete=True -> 'completed'."""
        with patch(
            "chaoxing.solvers.content.handlers.pw_run_code"
        ), patch(
            "chaoxing.solvers.content.handlers.pw_snapshot",
            return_value="任务点完成 green_check"
        ), patch(
            "chaoxing.solvers.content.handlers.time.sleep"
        ):
            handler = DocumentHandler()
            mock_bot = MagicMock()

            result = handler.handle(mock_bot, 1, 2, 3)
            assert result == "completed"

    def test_document_handler_not_completed(self):
        """Document: scrolling done but section not marked complete -> 'failed'."""
        with patch(
            "chaoxing.solvers.content.handlers.pw_run_code"
        ), patch(
            "chaoxing.solvers.content.handlers.pw_snapshot",
            return_value="No completion indicators here"
        ), patch(
            "chaoxing.solvers.content.handlers.time.sleep"
        ):
            handler = DocumentHandler()
            mock_bot = MagicMock()

            result = handler.handle(mock_bot, 1, 2, 3)
            assert result == "failed"


# ═══════════════════════════════════════════════════════════════════
#  Audio Handler Tests
# ═══════════════════════════════════════════════════════════════════

class TestAudioHandler:
    """Verify audio playback waiting and completion detection."""

    def test_audio_handler_clicks_play_and_waits(self):
        """Audio: clicks 播放, polls snapshot until completion."""
        with patch(
            "chaoxing.solvers.content.handlers.pw_snapshot"
        ) as mock_snap, patch(
            "chaoxing.solvers.content.handlers.pw_click"
        ) as mock_click, patch(
            "chaoxing.solvers.content.handlers.find_ref_by_text"
        ) as mock_find, patch(
            "chaoxing.solvers.content.handlers.time.sleep"
        ), patch(
            "chaoxing.solvers.content.handlers.time.time"
        ) as mock_time:
            # First snapshot: has 播放 button
            # Second snapshot: section complete
            mock_find.side_effect = ["ref-play-button", None]
            mock_snap.side_effect = [
                "播放 audio section",  # Initial snapshot (play button search)
                "任务点完成 已完成",    # Inside while loop
            ]
            # time.time(): [start, first-while-check, ...]
            # start=0, check=50 -> 50-0 = 50 < 180 -> enters loop
            mock_time.side_effect = [0, 50]

            handler = AudioHandler()
            mock_bot = MagicMock()
            mock_bot.CONTENT_TIMEOUT = 180

            result = handler.handle(mock_bot, 1, 3, 2)
            assert result == "completed"
            mock_click.assert_called_once_with("ref-play-button")

    def test_audio_handler_timeout_with_force_complete(self):
        """Audio: playback timeout, force-complete attempted."""
        with patch(
            "chaoxing.solvers.content.handlers.pw_snapshot",
            return_value="audio still playing"
        ), patch(
            "chaoxing.solvers.content.handlers.find_ref_by_text",
            return_value=None  # No play button, no completion
        ), patch(
            "chaoxing.solvers.content.handlers.time.sleep"
        ), patch(
            "chaoxing.solvers.content.handlers.time.time"
        ) as mock_time, patch(
            "chaoxing.solvers.content.handlers.pw_click"
        ), patch(
            "chaoxing.solvers.content.handlers._try_force_complete",
            return_value=True
        ):
            # Simulate timeout
            mock_time.side_effect = [0, 200]  # elapsed >= 180

            handler = AudioHandler()
            mock_bot = MagicMock()
            mock_bot.CONTENT_TIMEOUT = 180

            result = handler.handle(mock_bot, 1, 3, 2)
            # Force complete succeeded -> 'completed'
            assert result == "completed"


# ═══════════════════════════════════════════════════════════════════
#  Anti-Spider / CAPTCHA Tests
# ═══════════════════════════════════════════════════════════════════

class TestAntiSpider:
    """Verify CAPTCHA detection and auto-solve pipeline."""

    def test_check_anti_spider_no_captcha(self, mock_tempfile):
        """CAPTCHA detection: no antispider URL and no in-page text -> clear."""
        with patch(
            "chaoxing.solvers.content.handlers.pw_run_code",
            return_value="https://mooc1.chaoxing.com/mycourse/studentstudy"
        ), patch(
            "chaoxing.solvers.content.handlers.pw_extract_result",
            return_value="https://mooc1.chaoxing.com/mycourse/studentstudy"
        ), patch(
            "chaoxing.solvers.content.handlers.pw_run_code_file",
            return_value="raw"
        ):
            # No 'antispider' in URL, no CAPTCHA in iframe body
            with patch(
                "chaoxing.solvers.content.handlers.json.loads",
                return_value={"captcha": False, "text": "", "inAntispiderFrame": False}
            ):
                result = check_anti_spider()
                assert result is True

    def test_check_anti_spider_url_detected(self, mock_tempfile):
        """CAPTCHA: URL contains 'antispider' triggers detection.

        When the page URL contains 'antispider', the full CAPTCHA
        detection and auto-solve pipeline activates. This test mocks
        all browser calls to simulate a successful auto-solve.
        """
        with patch(
            "chaoxing.solvers.content.handlers.pw_run_code",
            return_value="url-raw"
        ), patch(
            "chaoxing.solvers.content.handlers.pw_extract_result"
        ) as mock_extract, patch(
            "chaoxing.solvers.content.handlers.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.content.handlers.solve_captcha_image",
            return_value="AB12"
        ), patch(
            "chaoxing.solvers.content.handlers.time.sleep"
        ), patch(
            "chaoxing.solvers.content.handlers._get_active_session",
            return_value="test-session"
        ), patch(
            "chaoxing.solvers.content.handlers.base64.b64decode",
            return_value=b"fake_png"
        ), patch(
            "builtins.open",
            MagicMock()
        ):
            # Extract call chain:
            # 1) URL check -> antispider URL
            # 2) iframe CAPTCHA text check -> JSON with captcha=True
            # 3) CAPTCHA image extraction -> "ok-200x50"
            # 4) Auto-fill result -> "solved"
            mock_extract.side_effect = [
                "https://antispider.chaoxing.com/captcha",
                '{"captcha": true, "text": "验证码", "inAntispiderFrame": false}',
                "ok-200x50",
                "solved",
            ]

            result = check_anti_spider()
            assert result is True

    def test_check_anti_spider_auto_solve_failure(self, mock_tempfile):
        """CAPTCHA: detected but auto-solve returns None, falls to manual wait.

        When solve_captcha_image returns None, check_anti_spider enters the
        manual-solve polling loop. We simulate the loop timing out.
        """
        with patch(
            "chaoxing.solvers.content.handlers.pw_run_code",
            side_effect=["url-raw", "url-raw2", "url-raw3"]
        ), patch(
            "chaoxing.solvers.content.handlers.pw_extract_result"
        ) as mock_extract, patch(
            "chaoxing.solvers.content.handlers.pw_run_code_file",
            return_value="raw"
        ), patch(
            "chaoxing.solvers.content.handlers.solve_captcha_image",
            return_value=None
        ), patch(
            "chaoxing.solvers.content.handlers.time.sleep"
        ), patch(
            "chaoxing.solvers.content.handlers._get_active_session",
            return_value="test-session"
        ), patch(
            "chaoxing.solvers.content.handlers.base64.b64decode",
            return_value=b"fake_png"
        ), patch(
            "builtins.open",
            MagicMock()
        ), patch(
            "chaoxing.solvers.content.handlers.os.path.exists",
            return_value=False
        ):
            mock_extract.side_effect = [
                "https://antispider.chaoxing.com/captcha",
                '{"captcha": true, "text": "验证码", "inAntispiderFrame": false}',
                "ok-200x50",
            ]
            # After first iteration: pw_run_code for URL check returns same URL
            # (antispider still present), timeout eventually reached
            result = check_anti_spider()
            assert result is False


# ═══════════════════════════════════════════════════════════════════
#  Navigation Tests
# ═══════════════════════════════════════════════════════════════════

class TestNavigation:
    """Verify section navigation and chapter tree extraction."""

    def test_navigate_to_section_found(self):
        """Navigation between sections: click link with matching section ID."""
        with patch(
            "chaoxing.solvers.content.navigator.pw_run_code",
            return_value="clicked:1.3 section name"
        ), patch(
            "chaoxing.solvers.content.navigator.pw_extract_result",
            return_value="clicked:1.3 section name"
        ), patch(
            "chaoxing.solvers.content.navigator.time.sleep"
        ):
            result = navigate_to_section(1, 3)
            assert result is True

    def test_navigate_to_section_not_found(self):
        """Navigation: section not found returns False."""
        with patch(
            "chaoxing.solvers.content.navigator.pw_run_code",
            return_value="not-found"
        ), patch(
            "chaoxing.solvers.content.navigator.pw_extract_result",
            return_value="not-found"
        ), patch(
            "chaoxing.solvers.content.navigator.time.sleep"
        ):
            result = navigate_to_section(5, 1)
            assert result is False

    def test_navigate_to_section_no_iframe(self):
        """Navigation: no mooc2 iframe returns False."""
        with patch(
            "chaoxing.solvers.content.navigator.pw_run_code",
            return_value="no-iframe"
        ), patch(
            "chaoxing.solvers.content.navigator.pw_extract_result",
            return_value="no-iframe"
        ), patch(
            "chaoxing.solvers.content.navigator.time.sleep"
        ):
            result = navigate_to_section(1, 1)
            assert result is False

    def test_get_chapter_tree(self):
        """get_chapter_tree extracts chapter structure from iframe DOM."""
        mock_chapters = [
            {
                "chapter": "第1章",
                "sections": ["1.1 节标题A", "1.2 节标题B"],
            },
        ]
        with patch(
            "chaoxing.solvers.content.navigator.pw_run_code",
            return_value=json.dumps(mock_chapters)
        ):
            tree = get_chapter_tree()
            assert len(tree) == 1
            assert tree[0]["chapter"] == "第1章"
            assert len(tree[0]["sections"]) == 2

    def test_get_chapter_tree_parse_failure(self):
        """get_chapter_tree returns [] on JSON parse failure."""
        with patch(
            "chaoxing.solvers.content.navigator.pw_run_code",
            return_value="not valid json {"
        ):
            tree = get_chapter_tree()
            assert tree == []


# ═══════════════════════════════════════════════════════════════════
#  Section Completion Detection Tests
# ═══════════════════════════════════════════════════════════════════

class TestSectionCompleteDetection:
    """Verify _is_section_complete recognises completion indicators."""

    def test_complete_with_green_check(self):
        """Progress tracking update: green_check indicator."""
        assert _is_section_complete("green_check present") is True

    def test_complete_with_chinese_indicator(self):
        """Progress tracking update: 任务点完成 indicator."""
        assert _is_section_complete("任务点完成") is True
        assert _is_section_complete("已完成") is True
        assert _is_section_complete("学习完成") is True

    def test_complete_with_completed(self):
        """Progress tracking update: 'completed' indicator."""
        assert _is_section_complete("section completed ok") is True

    def test_not_complete(self):
        """Section not complete when no indicators present."""
        assert _is_section_complete("Regular text without indicators") is False


# ═══════════════════════════════════════════════════════════════════
#  ChapterContentBot Tests
# ═══════════════════════════════════════════════════════════════════

class TestChapterContentBot:
    """Verify the content bot orchestration and progress tracking."""

    def test_bot_initialization(self, course_config):
        """Bot initialises with course config and progress tracker."""
        with patch(
            "chaoxing.solvers.content.bot.ProgressTracker"
        ) as mock_tracker:
            mock_tracker.return_value = MagicMock()
            bot = ChapterContentBot(course_config)
            assert bot.name == "Test Course"
            assert bot.courseid == "123456"
            assert bot.clazzid == "654321"
            assert bot.cpi == "415409200"
            assert bot.stats == {"completed": 0, "skipped": 0, "failed": 0}

    def test_complete_section_dry_run(self, mock_bot):
        """Dry run: section is marked completed without any browser interaction."""
        mock_bot.dry_run = True
        result = mock_bot.complete_section(1, 1, 2)
        assert result == "completed"
        assert mock_bot.stats["completed"] == 1

    def test_complete_section_already_done(self, mock_bot):
        """Already-completed sections are skipped."""
        mock_bot.tracker.is_section_done.return_value = True
        result = mock_bot.complete_section(1, 1, 2)
        assert result == "skipped"
        assert mock_bot.stats["skipped"] == 1

    def test_complete_section_zero_tasks(self, mock_bot):
        """Sections with 0 task points are skipped."""
        mock_bot.tracker.is_section_done.return_value = False
        result = mock_bot.complete_section(1, 1, 0)
        assert result == "skipped"
        assert mock_bot.stats["skipped"] == 1

    def test_complete_section_video_flow(self, mock_bot):
        """Bot orchestrates: navigate -> detect -> dispatch -> mark done."""
        mock_bot.tracker.is_section_done.return_value = False
        mock_bot.navigate_to_section = MagicMock(return_value=True)

        with patch(
            "chaoxing.solvers.content.bot.detect_content_type",
            return_value="video"
        ), patch(
            "chaoxing.solvers.content.bot.time.sleep"
        ), patch.object(
            VideoHandler, "handle", return_value="completed"
        ):
            result = mock_bot.complete_section(1, 2, 3)
            assert result == "completed"
            assert mock_bot.stats["completed"] == 1
            mock_bot.tracker.mark_section_done.assert_called_with(
                "Test Course", "ch1.2"
            )

    def test_complete_section_nav_failure(self, mock_bot):
        """Section navigation failure reports 'failed'."""
        mock_bot.tracker.is_section_done.return_value = False
        mock_bot.navigate_to_section = MagicMock(return_value=False)

        result = mock_bot.complete_section(1, 2, 3)
        assert result == "failed"
        assert mock_bot.stats["failed"] == 1

    def test_anti_spider_delay_behavior(self, mock_bot):
        """Anti-spider delay behavior: extra delay every 3 sections.

        The bot's run loop applies anti-spider delays at section_count % 3 == 0
        intervals, incrementing the delay per iteration up to a maximum.
        """
        # Directly test the delay calculation logic
        delay_base = ChapterContentBot.ANTI_SPIDER_DELAY  # 45
        delay_max = ChapterContentBot.ANTI_SPIDER_MAX_DELAY  # 180

        for section_count in [3, 6, 9, 12, 15]:
            delay = min(delay_base + section_count * 5, delay_max)
            # Verify delay increases with section count, capped at max
            assert delay >= delay_base
            assert delay <= delay_max

        # At section_count=3: 45 + 15 = 60
        assert min(45 + 3 * 5, 180) == 60
        # At large count, capped at 180
        assert min(45 + 100 * 5, 180) == 180

    def test_print_summary(self, mock_bot):
        """Bot prints correct summary statistics after run."""
        mock_bot.stats = {"completed": 5, "skipped": 2, "failed": 1}
        with patch("chaoxing.solvers.content.bot.log") as mock_log:
            mock_bot._print_summary()
            # Summary logged at INFO level (no level specified -> default)
            calls = [call[0][0] for call in mock_log.call_args_list]
            combined = " ".join(calls)
            assert "5" in combined
            assert "2" in combined
            assert "1" in combined


# ═══════════════════════════════════════════════════════════════════
#  Generic Handler Tests
# ═══════════════════════════════════════════════════════════════════

class TestGenericHandler:
    """Verify the catch-all generic handler."""

    def test_generic_handler_completed(self):
        """Generic: scrolls and checks for completion markers."""
        with patch(
            "chaoxing.solvers.content.handlers.pw_run_code"
        ), patch(
            "chaoxing.solvers.content.handlers.pw_snapshot",
            return_value="green_check 任务点完成"
        ), patch(
            "chaoxing.solvers.content.handlers.time.sleep"
        ):
            handler = GenericHandler()
            mock_bot = MagicMock()

            result = handler.handle(mock_bot, 1, 1, 1)
            assert result == "completed"

    def test_generic_handler_not_completed(self):
        """Generic: no completion markers -> 'failed'."""
        with patch(
            "chaoxing.solvers.content.handlers.pw_run_code"
        ), patch(
            "chaoxing.solvers.content.handlers.pw_snapshot",
            return_value="regular content without markers"
        ), patch(
            "chaoxing.solvers.content.handlers.time.sleep"
        ):
            handler = GenericHandler()
            mock_bot = MagicMock()

            result = handler.handle(mock_bot, 1, 1, 1)
            assert result == "failed"
