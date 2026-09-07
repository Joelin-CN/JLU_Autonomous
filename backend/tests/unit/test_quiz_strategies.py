"""Tests for chaoxing.solvers.quiz.strategies — 5-tier solving strategy chain."""
from chaoxing.solvers.quiz.strategies import (
    SolvingStrategy,
    FontDecryptTextStrategy,
    V2ScreenshotStrategy,
    V1ScreenshotStrategy,
    FullPageScreenshotStrategy,
    SnapshotTextStrategy,
)


class TestStrategyOrdering:
    """Verify the 5-tier strategy fallback chain is correctly ordered."""

    def test_all_strategies_have_unique_tiers(self):
        strategies = [
            FontDecryptTextStrategy(),
            V2ScreenshotStrategy(),
            V1ScreenshotStrategy(),
            FullPageScreenshotStrategy(),
            SnapshotTextStrategy(),
        ]
        tiers = [s.tier for s in strategies]
        # All tiers should be distinct
        assert len(tiers) == len(set(tiers)), f"Duplicate tiers: {tiers}"

    def test_font_decrypt_is_tier_1(self):
        s = FontDecryptTextStrategy()
        assert s.tier == 1
        assert s.name == "FontDecryptText"

    def test_v2_screenshot_after_font_decrypt(self):
        font = FontDecryptTextStrategy()
        v2 = V2ScreenshotStrategy()
        assert font.tier < v2.tier, "FontDecrypt should be tried before V2 screenshots"

    def test_snapshot_text_is_last_resort(self):
        strategies = [
            FontDecryptTextStrategy(),
            V2ScreenshotStrategy(),
            V1ScreenshotStrategy(),
            FullPageScreenshotStrategy(),
            SnapshotTextStrategy(),
        ]
        snapshot_tier = SnapshotTextStrategy().tier
        for s in strategies:
            if not isinstance(s, SnapshotTextStrategy):
                assert s.tier < snapshot_tier, \
                    f"{s.name} (tier {s.tier}) should be before SnapshotText (tier {snapshot_tier})"

    def test_strategies_are_abc(self):
        assert hasattr(SolvingStrategy, '__abstractmethods__')
        assert 'name' in SolvingStrategy.__abstractmethods__
        assert 'tier' in SolvingStrategy.__abstractmethods__
        assert 'try_solve' in SolvingStrategy.__abstractmethods__


class TestStrategyNames:
    """Verify each strategy has a descriptive name."""

    def test_all_strategies_have_non_empty_names(self):
        strategies = [
            FontDecryptTextStrategy(),
            V2ScreenshotStrategy(),
            V1ScreenshotStrategy(),
            FullPageScreenshotStrategy(),
            SnapshotTextStrategy(),
        ]
        for s in strategies:
            assert s.name, f"{s.__class__.__name__} has empty name"
            assert len(s.name) > 2, f"{s.__class__.__name__} name too short: '{s.name}'"


class TestStrategyTiers:
    """Verify tiers are in the expected 1-5 range."""

    def test_all_tiers_in_range(self):
        strategies = [
            FontDecryptTextStrategy(),
            V2ScreenshotStrategy(),
            V1ScreenshotStrategy(),
            FullPageScreenshotStrategy(),
            SnapshotTextStrategy(),
        ]
        for s in strategies:
            assert 1 <= s.tier <= 5, \
                f"{s.name} tier {s.tier} out of range (expected 1-5)"
