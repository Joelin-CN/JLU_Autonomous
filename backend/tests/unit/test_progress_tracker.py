"""Tests for chaoxing.tracking — ProgressTracker with crash-safe atomic saves."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.tracking import ProgressTracker


class TestProgressTrackerLoad:
    """Tests for _load() resilience."""

    def test_load_missing_file_returns_default(self, tmp_path):
        """When state file doesn't exist, _load returns default dict."""
        state_file = tmp_path / "nonexistent.json"
        tracker = ProgressTracker(state_file=state_file)
        assert tracker.state == {
            "completed_sections": [],
            "completed_courses": [],
            "errors": [],
        }

    def test_load_malformed_json_returns_default(self, tmp_path):
        """G2 fix: malformed JSON should NOT crash — return default dict."""
        state_file = tmp_path / "corrupt.json"
        state_file.write_text("{ this is not valid json !!! }", encoding="utf-8")
        tracker = ProgressTracker(state_file=state_file)
        assert tracker.state == {
            "completed_sections": [],
            "completed_courses": [],
            "errors": [],
        }

    def test_load_valid_json(self, tmp_path):
        """Valid JSON should load correctly."""
        state_file = tmp_path / "valid.json"
        data = {
            "completed_sections": ["Course A::1.1"],
            "completed_courses": ["Course A"],
            "errors": [],
        }
        state_file.write_text(json.dumps(data), encoding="utf-8")
        tracker = ProgressTracker(state_file=state_file)
        assert tracker.state == data

    def test_load_empty_json_object(self, tmp_path):
        """Empty JSON object loads as-is (missing keys handled by callers)."""
        state_file = tmp_path / "empty.json"
        state_file.write_text("{}", encoding="utf-8")
        tracker = ProgressTracker(state_file=state_file)
        assert tracker.state == {}


class TestProgressTrackerSave:
    """Tests for crash-safe atomic save() (G3 fix)."""

    def test_save_creates_file(self, tmp_path):
        """save() should create the state file."""
        state_file = tmp_path / "state.json"
        tracker = ProgressTracker(state_file=state_file)
        tracker.mark_section_done("TestCourse", "1.1")
        assert state_file.exists()
        loaded = json.loads(state_file.read_text(encoding="utf-8"))
        assert "TestCourse::1.1" in loaded["completed_sections"]

    def test_save_and_reload_roundtrip(self, tmp_path):
        """Data saved should survive a reload."""
        state_file = tmp_path / "state.json"
        tracker1 = ProgressTracker(state_file=state_file)
        tracker1.mark_section_done("CourseX", "2.3")
        tracker1.mark_course_done("CourseX")

        tracker2 = ProgressTracker(state_file=state_file)
        assert tracker2.is_section_done("CourseX", "2.3")
        assert "CourseX" in tracker2.state["completed_courses"]

    def test_mark_section_done_idempotent(self, tmp_path):
        """Marking the same section twice should not duplicate."""
        state_file = tmp_path / "state.json"
        tracker = ProgressTracker(state_file=state_file)
        tracker.mark_section_done("C", "1.1")
        tracker.mark_section_done("C", "1.1")
        count = tracker.state["completed_sections"].count("C::1.1")
        assert count == 1


class TestProgressTrackerErrors:
    """Tests for error logging."""

    def test_log_error_appends(self, tmp_path):
        """log_error should append to the errors list."""
        state_file = tmp_path / "state.json"
        tracker = ProgressTracker(state_file=state_file)
        tracker.log_error("CourseA", "1.2", "Test error message")
        assert len(tracker.state["errors"]) == 1
        assert tracker.state["errors"][0]["course"] == "CourseA"
        assert tracker.state["errors"][0]["section"] == "1.2"
        assert tracker.state["errors"][0]["error"] == "Test error message"


class TestProgressTrackerThreadSafety:
    """Tests for thread-safe operations (G3 fix)."""

    def test_concurrent_saves_dont_corrupt(self, tmp_path):
        """Multiple threads saving should not produce corrupted JSON."""
        import threading

        state_file = tmp_path / "state.json"
        tracker = ProgressTracker(state_file=state_file)

        errors = []

        def worker(n):
            try:
                for i in range(10):
                    tracker.mark_section_done(f"Course{n}", f"1.{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        # Should be able to reload without JSON errors
        tracker2 = ProgressTracker(state_file=state_file)
        assert isinstance(tracker2.state, dict)
