"""Tests for chaoxing.utils — pure utility functions."""

from chaoxing.utils import (
    find_ref_by_text,
    find_refs_by_pattern,
    parse_progress_from_snapshot,
)


class TestFindRefByText:
    """Test find_ref_by_text for locating ref markers in snapshots."""

    def test_finds_ref_on_same_line(self):
        """Should find ref when text and [ref=eNNN] are on the same line."""
        snapshot = '- link "章节" [ref=e38]'
        result = find_ref_by_text(snapshot, "章节")
        assert result == "e38"

    def test_finds_ref_near_text(self):
        """Should find ref within 5 lines of matching text (fallback strategy)."""
        snapshot = (
            'some line\n'
            'another line\n'
            '- link "章节" [ref=e42]\n'
            'more content\n'
            'target text is here: 章节\n'
        )
        result = find_ref_by_text(snapshot, "章节")
        assert result == "e42"

    def test_returns_none_for_no_match(self):
        """Should return None when text is not found anywhere."""
        snapshot = '- link "其他" [ref=e10]\n- button "确认" [ref=e11]'
        result = find_ref_by_text(snapshot, "不存在")
        assert result is None

    def test_returns_none_for_no_ref_nearby(self):
        """Should return None when text is found but no ref is nearby."""
        snapshot = 'just some text with 章节 but no ref marker at all'
        result = find_ref_by_text(snapshot, "章节")
        assert result is None

    def test_escapes_special_regex_chars(self):
        """Should properly escape special regex characters in the search text."""
        snapshot = '- link "测试 (重要)" [ref=e99]'
        result = find_ref_by_text(snapshot, "测试 (重要)")
        assert result == "e99"


class TestFindRefsByPattern:
    """Test find_refs_by_pattern for extracting refs via regex."""

    def test_finds_multiple_refs(self):
        """Should return all refs matching the given pattern."""
        snapshot = (
            'item1 [ref=e1] text1\n'
            'item2 [ref=e2] text2\n'
            'item3 [ref=e3] text3\n'
        )
        # Use non-greedy .*? and end-of-line anchor to avoid matching
        # across lines (the function uses re.DOTALL internally).
        result = find_refs_by_pattern(snapshot, r"item\d.*?(?=\n|$)")
        assert result == ["e1", "e2", "e3"]

    def test_returns_empty_list_for_no_match(self):
        """Should return empty list when pattern matches nothing."""
        snapshot = "no items here [ref=e1]"
        result = find_refs_by_pattern(snapshot, r"nonexistent_pattern_xyz")
        assert result == []

    def test_returns_empty_list_when_no_ref_in_match(self):
        """Should skip matches that don't contain a ref marker."""
        snapshot = "some text without ref markers"
        result = find_refs_by_pattern(snapshot, r"some text")
        assert result == []

    def test_finds_refs_with_video_pattern(self):
        """Should find refs matching a video-related pattern."""
        snapshot = (
            '- video "讲座1" [ref=e10]\n'
            '- video "讲座2" [ref=e11]\n'
            '- document "PDF" [ref=e12]\n'
        )
        # Use non-greedy .*? and end-of-line anchor to avoid matching
        # across lines (the function uses re.DOTALL internally).
        result = find_refs_by_pattern(snapshot, r"video.*?(?=\n|$)")
        assert result == ["e10", "e11"]


class TestParseProgressFromSnapshot:
    """Test parse_progress_from_snapshot for extracting completion progress."""

    def test_parses_standard_format(self):
        """Should parse '已完成任务点: 3/10' correctly."""
        snapshot = "已完成任务点: 3/10"
        done, total = parse_progress_from_snapshot(snapshot)
        assert done == 3
        assert total == 10

    def test_parses_with_whitespace(self):
        """Should handle extra whitespace around the colon."""
        snapshot = "已完成任务点:   5/20"
        done, total = parse_progress_from_snapshot(snapshot)
        assert done == 5
        assert total == 20

    def test_returns_zeros_for_no_match(self):
        """Should return (0, 0) when no progress info is present."""
        snapshot = "No progress information here"
        done, total = parse_progress_from_snapshot(snapshot)
        assert done == 0
        assert total == 0

    def test_parses_from_large_snapshot(self):
        """Should extract progress from within a larger snapshot text."""
        snapshot = (
            "Course: Math 101\n"
            "Section: Chapter 3\n"
            "已完成任务点: 7/15\n"
            "Status: In Progress\n"
        )
        done, total = parse_progress_from_snapshot(snapshot)
        assert done == 7
        assert total == 15

    def test_parses_complete_progress(self):
        """Should parse fully completed progress (e.g. 10/10)."""
        snapshot = "已完成任务点: 10/10"
        done, total = parse_progress_from_snapshot(snapshot)
        assert done == 10
        assert total == 10

    def test_parses_zero_progress(self):
        """Should parse zero progress (e.g. 0/10)."""
        snapshot = "已完成任务点: 0/10"
        done, total = parse_progress_from_snapshot(snapshot)
        assert done == 0
        assert total == 10
