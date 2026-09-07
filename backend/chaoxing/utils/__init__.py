"""Pure utility functions — snapshot parsing, text cleaning, shell helpers."""

import random
import re
import time
from typing import Optional


def human_delay(base_seconds: float, jitter_ratio: float = 0.25,
                min_seconds: float = 0.1) -> float:
    """Sleep for ``base_seconds`` with a human-like random jitter.

    Keeps the overall pace slightly irregular (e.g. 3s becomes roughly
    2.25–3.75s) so repeated operations do not look machine-uniform, while
    staying bounded so long waits cannot balloon out of control. Returns the
    actual number of seconds slept (useful for tests).
    """
    low = max(min_seconds, base_seconds * (1.0 - jitter_ratio))
    high = base_seconds * (1.0 + jitter_ratio)
    delay = random.uniform(low, high)
    time.sleep(delay)
    return delay


def find_ref_by_text(snapshot_text: str, text: str) -> Optional[str]:
    """Find a ref for an element containing specific text.

    Looks for patterns like: - link "章节" [ref=e38]
    """
    # Look for patterns like: - link "章节" [ref=e38]
    pattern = re.compile(rf'\[ref=(e\d+)\][^\n]*{re.escape(text)}', re.DOTALL)
    match = pattern.search(snapshot_text)
    if match:
        return match.group(1)

    # Fallback: search for any ref near the text
    lines = snapshot_text.split("\n")
    for i, line in enumerate(lines):
        if text in line:
            # Search nearby lines for ref=
            for j in range(max(0, i - 5), min(len(lines), i + 5)):
                ref_match = re.search(r"\[ref=(e\d+)\]", lines[j])
                if ref_match:
                    return ref_match.group(1)
    return None


def find_refs_by_pattern(snapshot_text: str, pattern: str) -> list[str]:
    """Find all refs matching a regex pattern in context."""
    refs = []
    for match in re.finditer(pattern, snapshot_text, re.DOTALL):
        ref_match = re.search(r"\[ref=(e\d+)\]", match.group(0))
        if ref_match:
            refs.append(ref_match.group(1))
    return refs


def parse_progress_from_snapshot(snapshot_text: str) -> tuple[int, int]:
    """Extract '已完成任务点: X/Y' from snapshot."""
    pattern = re.compile(r"已完成任务点:\s*(\d+)/(\d+)")
    match = pattern.search(snapshot_text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0
