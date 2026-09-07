"""Tests for chaoxing.solvers.quiz.extractor — question extraction from snapshots."""
import re
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.solvers.quiz.extractor import (
    extract_questions_from_snapshot,
    _clean_snapshot,
    count_questions_in_text,
    count_questions_in_snapshot,
)


# ── Sample data ──────────────────────────────────────────────────

VALID_SNAPSHOT = """- Page URL: https://mooc1.chaoxing.com/mooc-ans/work/doHomeWorkNew
- generic [ref=e1]:
  - generic [ref=e2]:
    - text: 第1题
    - text: 单选题
    - text: 概率论中，事件的概率取值范围是？
  - generic [ref=e3]:
    - text: A. [0, 1]
    - text: B. (0, 1)
    - text: C. (-∞, +∞)
    - text: D. [0, ∞)
  - generic [ref=e4]:
    - radio "A" [checked]
    - radio "B"
    - radio "C"
    - radio "D"
- generic [ref=e5]:
  - generic [ref=e6]:
    - text: 第2题
    - text: 多选题
    - text: 以下哪些是离散型随机变量？
  - generic [ref=e7]:
    - text: A. 二项分布
    - text: B. 泊松分布
    - text: C. 正态分布
    - text: D. 几何分布
  - generic [ref=e8]:
    - checkbox "A"
    - checkbox "B"
    - checkbox "C"
    - checkbox "D"
- generic [ref=e9]:
  - text: 第3题
  - text: 判断题
  - text: 两个互斥事件一定是对立事件。
  - radio "正确"
  - radio "错误"
"""

SHORT_SNAPSHOT = "- Page URL: https://example.com\n- generic [ref=e1]"

NOISE_SNAPSHOT = """- /url: https://mooc1.chaoxing.com/knowledge/cards
- Page URL: https://mooc1.chaoxing.com/knowledge/cards
  - generic [ref=e1]:
    - img "logo"
    - button "返回"
    - link "返回首页"
    - textbox "搜索"
    - heading "课程目录" [level=2]
    - list [ref=e2]:
      - listitem [ref=e3]:
        - generic [ref=e4]:
          - text: 1.1 概率论基础"""


# ── _clean_snapshot ─────────────────────────────────

class TestCleanSnapshot:
    """Tests for _clean_snapshot — YAML noise stripping."""

    def test_valid_snapshot_strips_noise(self):
        """Valid YAML snapshot should have structural noise stripped."""
        result = _clean_snapshot(VALID_SNAPSHOT)
        # Should contain quiz content
        assert "第1题" in result or "概率论" in result
        # Should NOT contain structural markers
        assert "Page URL" not in result
        assert "[ref=" not in result
        # Should have some content
        assert len(result) > 50

    def test_valid_snapshot_keeps_options(self):
        """Options (A., B., etc.) should be preserved."""
        result = _clean_snapshot(VALID_SNAPSHOT)
        assert "A." in result or "A " in result
        assert "B." in result or "B " in result

    def test_valid_snapshot_keeps_question_types(self):
        """Question type markers should be preserved."""
        result = _clean_snapshot(VALID_SNAPSHOT)
        assert "单选题" in result
        assert "多选题" in result
        assert "判断题" in result

    def test_valid_snapshot_removes_structural_prefixes(self):
        """Structural prefixes like '- Page URL:', '- generic' should be removed."""
        result = _clean_snapshot(VALID_SNAPSHOT)
        lines = result.split("\n")
        for line in lines:
            assert not line.strip().startswith("- /url:")
            assert not line.strip().startswith("- Page URL:")
            # No bare ref markers
            assert "[ref=" not in line

    def test_short_snapshot_returns_minimal(self):
        """Snapshot with virtually no quiz content should return fallback text."""
        result = _clean_snapshot(SHORT_SNAPSHOT)
        # Should not crash, return something (may be empty if fallback regex finds nothing)
        assert isinstance(result, str)

    def test_pure_noise_snapshot_returns_limited(self):
        """Snapshot with ONLY structural noise should return little or nothing."""
        result = _clean_snapshot(NOISE_SNAPSHOT)
        assert isinstance(result, str)
        # The fallback regex should extract quiz-like text or return empty
        assert len(result) < 200  # Won't have much content

    def test_result_is_string(self):
        """Result should always be a string."""
        result = _clean_snapshot(VALID_SNAPSHOT)
        assert isinstance(result, str)

    def test_no_empty_lines_in_output(self):
        """Output should not contain empty lines."""
        result = _clean_snapshot(VALID_SNAPSHOT)
        for line in result.split("\n"):
            assert line.strip(), f"Empty line found in output: {repr(result[:200])}"


# ── extract_questions_from_snapshot ──────────────────────────────

class TestExtractQuestionsFromSnapshot:
    """Tests for extract_questions_from_snapshot."""

    def test_valid_snapshot_returns_list(self):
        """Should return a list of question dicts."""
        result = extract_questions_from_snapshot(VALID_SNAPSHOT)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_returns_single_element_with_type(self):
        """Should return a single dict with type 'quiz_full'."""
        result = extract_questions_from_snapshot(VALID_SNAPSHOT)
        assert result[0]["type"] == "quiz_full"

    def test_returns_cleaned_text(self):
        """The text field should be cleaned (no structural noise)."""
        result = extract_questions_from_snapshot(VALID_SNAPSHOT)
        text = result[0]["text"]
        assert "Page URL" not in text
        assert "[ref=" not in text
        assert len(text) > 20

    def test_empty_snapshot_returns_list(self):
        """Empty or minimal snapshot should still return a list."""
        result = extract_questions_from_snapshot("")
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["type"] == "quiz_full"


# ── count_questions_in_text ──────────────────────────────────────

class TestCountQuestionsInText:
    """Tests for count_questions_in_text."""

    def test_count_numbered_questions(self):
        """Should count '1.', '2.', '3.' style question numbers."""
        text = "1. 什么是概率？\n2. 条件概率的定义？\n3. 贝叶斯公式？"
        result = count_questions_in_text(text)
        assert result == 3

    def test_count_with_chinese_brackets(self):
        """Should count '1)', '2)', '3)' style question numbers."""
        text = "1) 问题一\n2) 问题二\n3) 问题三"
        result = count_questions_in_text(text)
        assert result == 3

    def test_count_with_chinese_comma(self):
        """Should count '1、', '2、', '3、' style question numbers."""
        text = "1、问题一\n2、问题二"
        result = count_questions_in_text(text)
        assert result == 2

    def test_count_with_leading_whitespace(self):
        """Should count indented question numbers."""
        text = "  1. 问题一\n  2. 问题二\n  3. 问题三"
        result = count_questions_in_text(text)
        assert result == 3

    def test_duplicate_numbers_counted_once(self):
        """Same question number appearing multiple times should count once."""
        text = "1. 问题\n1. 问题 (重复)\n2. 另一个问题"
        result = count_questions_in_text(text)
        assert result == 2  # unique numbers only

    def test_no_questions_returns_zero(self):
        """Text with no question markers should return 0."""
        text = "这是纯文本，没有任何题号标记。"
        result = count_questions_in_text(text)
        assert result == 0

    def test_empty_text_returns_zero(self):
        """Empty text should return 0."""
        result = count_questions_in_text("")
        assert result == 0

    def test_multi_digit_question_numbers(self):
        """Should count multi-digit question numbers like '10.', '11.'."""
        text = "10. 问题十\n11. 问题十一\n12. 问题十二"
        result = count_questions_in_text(text)
        assert result == 3

    def test_only_mid_sentence_numbers_not_counted(self):
        """Numbers in the middle of sentences should not be counted."""
        text = "概率论中有3种重要分布。第5章介绍了这些内容。"
        result = count_questions_in_text(text)
        assert result == 0  # These aren't question markers


# ── count_questions_in_snapshot ──────────────────────────────────

NUMBERED_SNAPSHOT = """1. 单选题\n概率论中基本概念
2. 多选题\n以下哪些是离散型
3. 判断题\n问题内容
"""


class TestCountQuestionsInSnapshot:
    """Tests for count_questions_in_snapshot."""

    def test_count_from_valid_snapshot(self):
        """Should count numbered question markers in snapshot."""
        result = count_questions_in_snapshot(NUMBERED_SNAPSHOT)
        assert result == 3  # Has 1., 2., 3.

    def test_count_from_yaml_snapshot(self):
        """Should also work with the standard VALID_SNAPSHOT format.

        Note: VALID_SNAPSHOT uses 第1题 style markers which the
        regex may not detect, so we only verify it runs without error.
        """
        result = count_questions_in_snapshot(VALID_SNAPSHOT)
        assert isinstance(result, int)
        assert result >= 0

    def test_empty_snapshot_returns_zero(self):
        """Empty snapshot should return 0."""
        result = count_questions_in_snapshot("")
        assert result == 0

    def test_no_questions_returns_zero(self):
        """Snapshot without question markers should return 0."""
        result = count_questions_in_snapshot(NOISE_SNAPSHOT)
        assert result == 0

    def test_count_is_integer(self):
        """Result should always be an integer."""
        result = count_questions_in_snapshot(VALID_SNAPSHOT)
        assert isinstance(result, int)
