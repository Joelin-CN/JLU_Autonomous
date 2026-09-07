"""
Question extraction — parse quiz questions from YAML snapshots.

Extracts quiz content from Playwright YAML snapshots by stripping structural
noise and keeping only question text, options, and type markers.
"""

import re

from ...logging_setup import log


def extract_questions_from_snapshot(snap: str) -> list[dict]:
    """Extract quiz questions from the iframe snapshot into a clean text prompt.

    The raw snapshot is cleaned (YAML noise removed) and questions are
    structured for Doubao to parse. Returns a single-element list with
    the full cleaned quiz text.
    """
    cleaned = _clean_snapshot(snap)
    return [{
        "type": "quiz_full",
        "text": cleaned,
    }]


def _clean_snapshot(snap: str) -> str:
    """Strip ALL YAML/playwright noise from snapshot.

    Keeps ONLY lines that look like quiz content:
    - Question type markers (单选题, 多选题, 判断题, etc.)
    - Numbered questions and their text
    - Option labels (A., A), A., etc.) and option text
    - Radio/checkbox indicators
    - 正确/错误 (true/false answers)

    Aggressively removes: page URLs, YAML structure, ref markers,
    box coordinates, generic/structural prefixes, empty and whitespace lines.
    """
    # Keywords that indicate a line is quiz content
    QUIZ_KEYWORDS = [
        "单选", "多选", "判断", "简答", "填空", "选择",
        "题目", "选项", "问题",
        "正确", "错误",
        "radio", "checkbox", "checked",
        "。", "？", "，", "！",  # Chinese punctuation = actual text
        ". ", "? ", "! ",  # English punctuation in content
    ]

    # Line prefixes that are ALWAYS structural (skip unconditionally)
    SKIP_PREFIXES = [
        "- /url:", "- Page URL:", "- generic [ref=",
        "  - generic [ref=", "    - generic [ref=",
        "- img ", "- button ", "- link ",
        "- textbox ", "- heading ",
        "- list ", "- listitem ",
    ]

    lines = snap.split("\n")
    cleaned = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip structural prefixes unconditionally
        if any(stripped.startswith(p) for p in SKIP_PREFIXES):
            continue

        # Skip lines that start with "- " followed by structural markers
        if stripped.startswith("- "):
            # Check if it has any quiz keyword
            has_quiz_kw = any(kw in stripped for kw in QUIZ_KEYWORDS)
            if not has_quiz_kw:
                continue

        # Skip indented structural lines without quiz content
        if stripped.startswith("  ") and not any(kw in stripped for kw in QUIZ_KEYWORDS):
            continue

        # Remove box coordinates
        line = re.sub(r"\[box=[^\]]+\]", "", line)
        # Remove ref markers
        line = re.sub(r"\[ref=[^\]]+\]", "", line)
        # Remove cursor pointers
        line = re.sub(r"\[cursor=pointer\]", "", line)
        # Remove aria attributes
        line = re.sub(r"\[aria[^\]]+\]", "", line)
        # Remove [active], [disabled], [checked] in their own brackets
        # (but keep the text "checked" inside quiz content)
        line = re.sub(r"\[checked\]", " [✓]", line)
        line = re.sub(r"\[active\]", "", line)
        line = re.sub(r"\[disabled\]", "", line)

        # Remove YAML prefixes: "- generic", "- text:", "- paragraph"
        line = re.sub(r"^(\s*)- (generic|text|paragraph|strong|emphasis)\s*", r"\1", line)

        # Collapse multiple spaces
        line = re.sub(r" {2,}", " ", line)

        stripped = line.strip()
        if stripped and not stripped.startswith("###"):
            # Only keep if it has meaningful content
            cleaned.append(stripped)

    result = "\n".join(cleaned)

    # Further dedup: if the result is mostly structural noise, do a regex extraction
    # Extract question blocks: lines with question numbers and their following content
    if len(result) < 100 or result.count("\n") < 3:
        # Fallback: regex-extract any text that looks like quiz content
        quiz_texts = re.findall(
            r'(?:单选题|多选题|判断题|简答题|填空题|第\d+题|\d+[\.、)])[^\n]*',
            snap
        )
        option_texts = re.findall(
            r'[A-D][\.、)][^\n]*',
            snap
        )
        all_texts = quiz_texts + option_texts
        if all_texts:
            result = "\n".join(all_texts[:50])  # Cap at 50 lines

    return result


def count_questions_in_text(text: str) -> int:
    """Count distinct question numbers in decrypted text."""
    markers = re.findall(r'(?:^|\n)\s*(\d+)[\.、)]', text)
    return len(set(markers)) if markers else 0


def count_questions_in_snapshot(snap: str) -> int:
    """Count distinct question numbers in snapshot text."""
    markers = re.findall(r'(?:^|\n)\s*(\d+)[\.、)]', snap)
    return len(set(markers)) if markers else 0
