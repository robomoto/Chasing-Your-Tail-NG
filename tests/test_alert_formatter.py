"""TDD tests for alert_formatter module."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from response_guidance import AlertTier
from alert_formatter import AlertFormatter, AlertMessage
from surveillance_detector import SuspiciousDevice, DeviceAppearance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(
    mac: str = "AA:BB:CC:DD:EE:FF",
    persistence_score: float = 0.5,
    locations_seen: list = None,
    first_seen: datetime = None,
    last_seen: datetime = None,
    reasons: list = None,
    appearances: list = None,
) -> SuspiciousDevice:
    """Create a mock SuspiciousDevice with controlled fields."""
    now = datetime.now()
    if locations_seen is None:
        locations_seen = ["loc-A", "loc-B"]
    if first_seen is None:
        first_seen = now - timedelta(hours=3)
    if last_seen is None:
        last_seen = now
    if reasons is None:
        reasons = ["repeated appearance"]
    if appearances is None:
        appearances = []
    return SuspiciousDevice(
        mac=mac,
        persistence_score=persistence_score,
        appearances=appearances,
        reasons=reasons,
        first_seen=first_seen,
        last_seen=last_seen,
        total_appearances=len(appearances) if appearances else len(locations_seen),
        locations_seen=locations_seen,
    )


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------


class TestClassify:
    """Tests for score-to-tier classification."""

    def test_classify_silent(self):
        """score=0.2 -> AlertTier.SILENT."""
        fmt = AlertFormatter()
        assert fmt.classify(0.2) == AlertTier.SILENT

    def test_classify_informational(self):
        """score=0.4 -> AlertTier.INFORMATIONAL."""
        fmt = AlertFormatter()
        assert fmt.classify(0.4) == AlertTier.INFORMATIONAL

    def test_classify_notable(self):
        """score=0.6 -> AlertTier.NOTABLE."""
        fmt = AlertFormatter()
        assert fmt.classify(0.6) == AlertTier.NOTABLE

    def test_classify_elevated(self):
        """score=0.75 -> AlertTier.ELEVATED."""
        fmt = AlertFormatter()
        assert fmt.classify(0.75) == AlertTier.ELEVATED

    def test_classify_review(self):
        """score=0.9 -> AlertTier.REVIEW."""
        fmt = AlertFormatter()
        assert fmt.classify(0.9) == AlertTier.REVIEW


# ---------------------------------------------------------------------------
# Format alert tests
# ---------------------------------------------------------------------------


class TestFormatAlert:
    """Tests for alert message formatting."""

    def test_format_alert_silent_returns_none(self):
        """score=0.2 -> format_alert returns None."""
        fmt = AlertFormatter()
        device = _make_device(persistence_score=0.2)
        result = fmt.format_alert(device)
        assert result is None

    def test_format_alert_notable_content(self):
        """score=0.6, 3 locations -> headline mentions '3 of your locations'."""
        fmt = AlertFormatter()
        device = _make_device(
            persistence_score=0.6,
            locations_seen=["loc-A", "loc-B", "loc-C"],
        )
        result = fmt.format_alert(device)
        assert result is not None
        assert "3" in result.headline
        assert "locations" in result.headline.lower()
        # No forbidden words
        for word in AlertFormatter.FORBIDDEN_WORDS:
            assert word not in result.headline
            assert word not in result.detail

    def test_format_alert_elevated_content(self):
        """score=0.75, 4 locs, 6h -> headline mentions 'multiple locations over 6 hours'."""
        fmt = AlertFormatter()
        now = datetime.now()
        device = _make_device(
            persistence_score=0.75,
            locations_seen=["loc-A", "loc-B", "loc-C", "loc-D"],
            first_seen=now - timedelta(hours=6),
            last_seen=now,
        )
        result = fmt.format_alert(device)
        assert result is not None
        assert "multiple locations" in result.headline.lower()
        assert "6" in result.headline

    def test_no_forbidden_words_any_tier(self):
        """For scores [0.4, 0.6, 0.75, 0.9], verify no forbidden words in headline or detail."""
        fmt = AlertFormatter()
        for score in [0.4, 0.6, 0.75, 0.9]:
            device = _make_device(persistence_score=score)
            result = fmt.format_alert(device)
            assert result is not None, f"Expected alert for score={score}"
            for word in AlertFormatter.FORBIDDEN_WORDS:
                assert word not in result.headline, (
                    f"Forbidden word '{word}' in headline for score={score}"
                )
                assert word not in result.detail, (
                    f"Forbidden word '{word}' in detail for score={score}"
                )

    def test_single_source_caveat(self):
        """tier=ELEVATED, corroborated=False -> detail contains 'single sensor type'."""
        fmt = AlertFormatter()
        device = _make_device(persistence_score=0.75)
        # No fusion engine -> not corroborated
        result = fmt.format_alert(device, fusion_engine=None)
        assert result is not None
        assert not result.corroborated
        assert "single sensor type" in result.detail.lower()

    def test_format_alert_includes_guidance(self):
        """Alert message has non-empty guidance field."""
        fmt = AlertFormatter()
        device = _make_device(persistence_score=0.6)
        result = fmt.format_alert(device)
        assert result is not None
        assert result.guidance is not None
        # At least one of do_items or summary should be populated
        assert result.guidance.do_items or result.guidance.summary
