"""Progress tracking — runtime state persistence and progress reporting."""

import json
import os
import threading
import tempfile
import time
from pathlib import Path

from ..constants import OUTPUT_DIR
from ..session import _get_active_session


class ProgressTracker:
    """Track automation progress with resume capability.

    Automatically uses per-session state files when set_active_session() is used.
    E.g. session "chaoxing-chrome-0" -> output/progress_state_chaoxing-chrome-0.json

    Thread-safe: all save() calls acquire a lock.
    Crash-safe: writes to temp file + atomic rename.
    """

    def __init__(self, state_file: Path = None, session_name: str = None):
        self._lock = threading.Lock()
        if state_file:
            self.state_file = state_file
        else:
            # Auto-detect session for per-account isolation
            session = session_name or _get_active_session()
            suffix = f"_{session}" if session and session != "chaoxing-chrome" else ""
            self.state_file = OUTPUT_DIR / f"progress_state{suffix}.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                # Malformed or unreadable state — start fresh
                pass
        return {"completed_sections": [], "completed_courses": [], "errors": []}

    def save(self):
        """Atomically save state — crash-safe via temp file + rename."""
        with self._lock:
            try:
                tmp_fd, tmp_path = tempfile.mkstemp(
                    suffix=".json", prefix=".progress_",
                    dir=str(self.state_file.parent)
                )
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(self.state, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.state_file)
            except Exception:
                pass  # Best-effort persistence; don't crash on I/O error

    def mark_section_done(self, course_name: str, section: str):
        key = f"{course_name}::{section}"
        if key not in self.state["completed_sections"]:
            self.state["completed_sections"].append(key)
            self.save()

    def mark_course_done(self, course_name: str):
        if course_name not in self.state["completed_courses"]:
            self.state["completed_courses"].append(course_name)
            self.save()

    def is_section_done(self, course_name: str, section: str) -> bool:
        return f"{course_name}::{section}" in self.state["completed_sections"]

    def log_error(self, course: str, section: str, error: str):
        self.state["errors"].append({
            "course": course,
            "section": section,
            "error": error,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        # Cap errors to prevent unbounded memory growth in long sessions
        if len(self.state["errors"]) > 50:
            self.state["errors"] = self.state["errors"][-50:]
        self.save()
