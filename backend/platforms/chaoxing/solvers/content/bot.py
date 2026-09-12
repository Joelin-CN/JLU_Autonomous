"""
ChapterContentBot — orchestrates the content completion flow.

Iterates through all chapters and sections of a course, auto-completing
videos, documents, audio, and other content types. Uses v17 inline
chaining for seamless section-to-section video advancement.

Usage:
    from chaoxing.solvers.content.bot import ChapterContentBot

    bot = ChapterContentBot(course_config)
    bot.run(start_chapter=1, start_section=1)
"""

import time
import os
from typing import Optional

from core.constants import OUTPUT_DIR
from core.logging_setup import log, check_signals
from core.browser.engine import pw_snapshot
from core.utils import human_delay
from .navigator import (
    open_course_chapters,
    go_back_to_chapter_tree,
    navigate_to_section,
    get_chapter_tree,
    parse_progress_from_snapshot,
)
from .detector import detect_content_type
from .handlers import (
    VideoHandler,
    DocumentHandler,
    AudioHandler,
    GenericHandler,
    check_anti_spider,
)

from core.tracking import ProgressTracker  # canonical location


# ══════════════════════════════════════════════════════════════════
#  Content Handler Dispatch
# ══════════════════════════════════════════════════════════════════

# Ordered from most-specific to least-specific (GenericHandler is catch-all)
_HANDLER_CLASSES = [VideoHandler, DocumentHandler, AudioHandler, GenericHandler]


def _dispatch_handler(content_type: str):
    """Return an instantiated handler for the given content type."""
    for handler_cls in _HANDLER_CLASSES:
        if handler_cls.can_handle(content_type):
            return handler_cls()
    # Should never happen (GenericHandler returns True for everything)
    return GenericHandler()


# ══════════════════════════════════════════════════════════════════
#  ChapterContentBot
# ══════════════════════════════════════════════════════════════════

class ChapterContentBot:
    """Automate completing content sections (videos, documents, listening).

    Orchestrates the content completion flow:
      1. Open course -> navigate to chapter tree
      2. Iterate through configured chapters/sections
      3. For each section: navigate, detect content type, dispatch to handler
      4. Track progress with per-session state files (resume-safe)
    """

    CONTENT_TIMEOUT = 180       # Max seconds to wait for a section to complete
    ANTI_SPIDER_DELAY = 45      # Seconds between sections to avoid detection
    ANTI_SPIDER_MAX_DELAY = 180 # Maximum seconds for anti-spider delay

    def __init__(self, course_config: dict, dry_run: bool = False,
                 grade_only: bool = False):
        self.course = course_config
        self.name = course_config["name"]
        self.courseid = course_config["courseid"]
        self.clazzid = course_config["clazzid"]
        self.cpi = course_config.get("cpi", "415409200")
        self.dry_run = dry_run
        # grade_only ("模拟运行"): navigate to each section and detect its
        # content type for inspection, but do NOT actually complete it (no
        # video playback, no task-point fulfilment). Content has no "submit"
        # to skip the way quizzes do, so this is the closest analogue.
        self.grade_only = grade_only
        self.tracker = ProgressTracker()
        self.stats = {"completed": 0, "skipped": 0, "failed": 0}

    # ── Navigation (delegates to navigator module) ──────────────

    def open_course_chapters(self):
        """Open course and navigate to 章节 tab (full reload — use once only)."""
        open_course_chapters(self.courseid, self.clazzid, self.cpi, self.name)

    def go_back_to_chapter_tree(self) -> bool:
        """Navigate back to the chapter tree after completing a section.

        Three strategies, tried in order:
        1. If on studentstudy, navigate directly to course page
        2. If on course page, use lightweight iframe.goto() refresh
        3. (Caller should fall back to open_course_chapters() on failure)

        Returns True on success.
        """
        return go_back_to_chapter_tree(self.courseid, self.clazzid, self.cpi)

    def get_chapter_tree(self) -> list:
        """Extract the chapter directory tree from the current page."""
        return get_chapter_tree()

    def navigate_to_section(self, chapter_num: int, section_num: int) -> bool:
        """Click a specific section in the chapter tree."""
        return navigate_to_section(chapter_num, section_num)

    # ── Section Completion ──────────────────────────────────────

    def complete_section(self, chapter_num: int, section_num: int,
                         task_count: int) -> str:
        """Complete one content section.

        Flow:
          1. Check progress tracker (skip if already done)
          2. Skip if no task points or dry_run
          3. Navigate to section in chapter tree
          4. Detect content type (video/document/audio/generic)
          5. Dispatch to the appropriate ContentHandler
          6. Update stats and return result

        Returns:
          "advanced"   — section done, page auto-advanced to next section inline
          "completed"  — section done, returned to course page (caller should go_back)
          "skipped"    — already done or no tasks
          "failed"     — failed to complete
        """
        section_key = f"ch{chapter_num}.{section_num}"

        if self.tracker.is_section_done(self.name, section_key):
            log("    Already done, skipping")
            self.stats["skipped"] += 1
            return "skipped"

        if task_count == 0:
            log("    No task points, skipping")
            self.stats["skipped"] += 1
            return "skipped"

        if self.dry_run:
            log(f"    [DRY RUN] Would complete section with {task_count} task points")
            self.stats["completed"] += 1
            return "completed"

        # Navigate to the section
        if not self.navigate_to_section(chapter_num, section_num):
            # A mid-run session rebuild (engine recovers a dead daemon/Chrome
            # by reopening about:blank) loses the course page this navigation
            # depends on. Re-enter the course once before failing the section.
            log("    Navigation failed — re-entering course page", "WARN")
            try:
                self.open_course_chapters()
            except Exception as re_err:
                log(f"    Course re-entry failed: {re_err}", "ERROR")
            if not self.navigate_to_section(chapter_num, section_num):
                log("    Failed to navigate to section (after re-entry)", "ERROR")
                self.stats["failed"] += 1
                return "failed"

        # Wait for content to load
        human_delay(3.0, 0.25)

        # Detect content type and dispatch to handler
        content_type = detect_content_type()
        log(f"    Content type: {content_type}")

        # grade_only ("模拟运行"): we navigated and detected the content type,
        # but stop here — no handler dispatch, no completion, no mark-done.
        # This verifies the navigation + detection path without doing the work.
        if self.grade_only:
            log(f"    [模拟] {content_type} section reached "
                f"({task_count} task points) — not completing", "OK")
            self.stats["skipped"] += 1
            return "skipped"

        handler = _dispatch_handler(content_type)
        result = handler.handle(self, chapter_num, section_num, task_count)

        if result in ("advanced", "completed"):
            log(f"    Section done! (result={result})", "OK")
            self.tracker.mark_section_done(self.name, section_key)
            self.stats["completed"] += 1
        else:
            log(f"    Section may not have completed properly (result={result})", "WARN")
            self.stats["failed"] += 1

        return result

    # ── Progress ────────────────────────────────────────────────

    def check_progress(self) -> tuple:
        """Check current task progress from the 章节 header.

        Returns:
            (done, total) tuple of ints.
        """
        snap = pw_snapshot()
        return parse_progress_from_snapshot(snap)

    # ── Main Loop ───────────────────────────────────────────────

    def run(self, start_chapter: int = 1, start_section: int = 1):
        """Iterate through all chapters and sections.

        Uses v17 inline section chaining: when a section's video completes,
        v17 auto-clicks "下一节" to navigate to the next section without
        going back to the chapter tree. This is faster and looks more
        natural (reference script approach).

        Falls back to chapter-tree navigation when inline advance is not
        available.

        Args:
            start_chapter: Chapter number to start from (1-indexed).
            start_section: Section number within start_chapter to start from.
        """
        log(f"{'='*60}")
        log(f"Content Bot: {self.name}")
        log(f"{'='*60}")

        self.open_course_chapters()

        # Check current progress
        done, total = self.check_progress()
        log(f"Current progress: {done}/{total}")

        chapters = self.course.get("chapters", [])
        if not chapters:
            log("No chapters configured for this course!")
            return

        section_count = 0   # Count sections processed for delay timing
        inline_chain = False  # True when v17 auto-advanced to the next section

        for ch in chapters:
            ch_num = ch["num"]
            if ch_num < start_chapter:
                continue

            ch_name = ch["name"]
            sections_count = ch["sections"]
            tasks_per = ch.get("tasks_per", [])

            log(f"\n--- Chapter {ch_num}: {ch_name} ({sections_count} sections) ---")

            for sec_idx in range(sections_count):
                sec_num = sec_idx + 1
                if ch_num == start_chapter and sec_num < start_section:
                    continue

                # Pause/stop/RAM-guard yield point. Raises KeyboardInterrupt on
                # stop or RAM-critical, which propagates past the per-section
                # `except Exception` below up to run_for_account's handler.
                check_signals()

                tasks = tasks_per[sec_idx] if sec_idx < len(tasks_per) else 0
                log(f"  Section {ch_num}.{sec_num} (tasks: {tasks})")

                try:
                    # Determine if we need to navigate to this section
                    # (skip navigation if v17 already advanced us here inline)
                    will_navigate = (
                        tasks > 0
                        and not self.dry_run
                        and not self.tracker.is_section_done(self.name, f"ch{ch_num}.{sec_num}")
                        and not inline_chain  # Already on this section from auto-advance
                    )

                    # Anti-spider check before navigating to a new section
                    if will_navigate and section_count > 0 and section_count % 3 == 0:
                        if not check_anti_spider():
                            log("Cannot continue due to anti-spider block", "ERROR")
                            self._print_summary()
                            return
                        # Extra delay every 3 sections
                        delay = min(self.ANTI_SPIDER_DELAY + section_count * 5, self.ANTI_SPIDER_MAX_DELAY)
                        log(f"    Anti-spider delay: {delay}s...")
                        human_delay(delay, 0.15)

                    result = self.complete_section(ch_num, sec_num, tasks)
                    section_count += 1

                    if result == "advanced":
                        # v17 auto-clicked "下一节" — we're now on the next section!
                        # Set flag so next iteration skips navigate_to_section()
                        inline_chain = True
                        log("    Inline chaining to next section (no chapter-tree round-trip)")
                    elif result in ("completed", "skipped"):
                        inline_chain = False
                        if will_navigate or (
                            tasks > 0 and not self.dry_run
                            and not self.tracker.is_section_done(self.name, f"ch{ch_num}.{sec_num}")
                        ):
                            # Check for anti-spider before returning to chapter tree
                            check_anti_spider()
                            # Go back to chapter tree for next section navigation
                            if not self.go_back_to_chapter_tree():
                                log("    go_back failed, falling back to full reload", "WARN")
                                self.open_course_chapters()
                    else:
                        # Failed — reset inline chain and go back
                        inline_chain = False
                        check_anti_spider()
                        if not self.go_back_to_chapter_tree():
                            self.open_course_chapters()

                except Exception as e:
                    log(f"    Error: {e}", "ERROR")
                    self.tracker.log_error(self.name, f"ch{ch_num}.{sec_num}", str(e))
                    self.stats["failed"] += 1
                    inline_chain = False

                # Periodic progress check (only when on chapter tree page)
                if not inline_chain:
                    done, total = self.check_progress()
                    log(f"  Overall progress: {done}/{total}")

        # Summary
        self._print_summary()

    def _print_summary(self):
        """Print completion statistics."""
        log(f"\n{'='*60}")
        log(f"Content Bot Summary: {self.name}")
        log(f"  Completed: {self.stats['completed']}")
        log(f"  Skipped:   {self.stats['skipped']}")
        log(f"  Failed:    {self.stats['failed']}")
        log(f"{'='*60}")


# Standalone entry point removed — use chaoxing.api or chaoxing.orchestrator instead.
