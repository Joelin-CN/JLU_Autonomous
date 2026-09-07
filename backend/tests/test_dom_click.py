"""
Quick test: Verify DOM-based option clicking works correctly.
Navigates to the quiz that's already open and tests clicking options
for Q1-Q3 without submitting.
"""
import sys
import time
import json
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import (
    set_active_session, log,
    pw_run_code_file, pw_extract_result,
    ensure_chaoxing_viewport,
)
from chapter_quiz_solver import ChapterQuizSolver


def test_dom_click():
    set_active_session("chaoxing-chrome")

    # Create a minimal solver instance just to test _click_option_dom
    course_config = {
        "name": "概率论与数理统计",
        "courseid": "255106367",
        "clazzid": "127207872",
        "cpi": "415409200",
    }
    solver = ChapterQuizSolver(course_config, dry_run=True)

    ensure_chaoxing_viewport(2048, 1152)

    # Test Q1: "单选题" — test clicking option A within Q1's Y range
    log("\n--- Test 1: DOM click Q1 option 'A' ---")
    result = solver._click_option_dom(1, "A", True)
    log(f"Result: {result}")

    # Test Q2: "单选题" — test clicking option B within Q2's Y range
    log("\n--- Test 2: DOM click Q2 option 'B' ---")
    result = solver._click_option_dom(2, "B", True)
    log(f"Result: {result}")

    # Test Q5: test with full text search
    log("\n--- Test 3: DOM click Q5 with option letter 'C' ---")
    result = solver._click_option_dom(5, "C", True)
    log(f"Result: {result}")

    # Test Q28 (多选题): test clicking multiple
    log("\n--- Test 4: DOM click Q28 (多选题) option 'A' ---")
    result = solver._click_option_dom(28, "A", True)
    log(f"Result: {result}")

    log("\n--- Test 5: DOM click Q28 (多选题) option 'B' ---")
    result = solver._click_option_dom(28, "B", True)
    log(f"Result: {result}")

    # Test Q30 (last question, 多选题)
    log("\n--- Test 6: DOM click Q30 (last Q, 多选题) option 'D' ---")
    result = solver._click_option_dom(30, "D", True)
    log(f"Result: {result}")

    log("\n=== All DOM click tests complete ===")


def test_fallback_click():
    """Test the full _click_option (which falls back to snapshot if DOM fails)."""
    set_active_session("chaoxing-chrome")

    course_config = {
        "name": "概率论与数理统计",
        "courseid": "255106367",
        "clazzid": "127207872",
        "cpi": "415409200",
    }
    solver = ChapterQuizSolver(course_config, dry_run=True)

    log("\n--- Test full _click_option on Q3 option 'A' ---")
    solver._click_option(3, "A")
    log("Done")


if __name__ == "__main__":
    log("=" * 60)
    log("DOM-BASED OPTION CLICK TEST")
    log("=" * 60)
    test_dom_click()
    log("\n")
    test_fallback_click()
    log("\nDone!")
