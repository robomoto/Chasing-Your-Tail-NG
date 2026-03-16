"""TDD tests for Phase 5: FusionEngine cross-source correlation."""
import time
import pytest
from unittest.mock import patch

from scanners.base_scanner import DeviceAppearance, SourceType
from fusion_engine import CorrelationRule, FusionEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_appearance(
    device_id: str,
    source_type: SourceType,
    timestamp: float,
    location_id: str = "loc-A",
    **kwargs,
) -> DeviceAppearance:
    """Convenience factory for DeviceAppearance with sensible defaults."""
    return DeviceAppearance(
        device_id=device_id,
        source_type=source_type,
        timestamp=timestamp,
        location_id=location_id,
        **kwargs,
    )


NOW = 1_700_000_000.0  # fixed epoch for deterministic tests


# ---------------------------------------------------------------------------
# CorrelationRule tests
# ---------------------------------------------------------------------------


class TestCorrelationRule:
    """Tests for CorrelationRule creation and check logic."""

    def test_rule_creation(self):
        """Rule stores name, source_types, score_multiplier, time_window_s."""
        rule = CorrelationRule(
            name="wifi_ble",
            source_types=(SourceType.WIFI, SourceType.BLE),
            score_multiplier=1.5,
            time_window_s=30.0,
        )
        assert rule.name == "wifi_ble"
        assert rule.source_types == (SourceType.WIFI, SourceType.BLE)
        assert rule.score_multiplier == 1.5
        assert rule.time_window_s == 30.0

    def test_rule_check_matching(self):
        """Two appearances within time window from matching source types return True."""
        rule = CorrelationRule(
            name="wifi_ble",
            source_types=(SourceType.WIFI, SourceType.BLE),
            score_multiplier=1.5,
            time_window_s=30.0,
        )
        a = _make_appearance("dev-wifi-1", SourceType.WIFI, NOW)
        b = _make_appearance("dev-ble-1", SourceType.BLE, NOW + 10.0)
        assert rule.check(a, b) is True

    def test_rule_check_matching_reversed_order(self):
        """Rule check should match source types regardless of argument order."""
        rule = CorrelationRule(
            name="wifi_ble",
            source_types=(SourceType.WIFI, SourceType.BLE),
            score_multiplier=1.5,
            time_window_s=30.0,
        )
        a = _make_appearance("dev-ble-1", SourceType.BLE, NOW)
        b = _make_appearance("dev-wifi-1", SourceType.WIFI, NOW + 5.0)
        assert rule.check(a, b) is True

    def test_rule_check_wrong_sources(self):
        """Appearances from non-matching source types return False."""
        rule = CorrelationRule(
            name="wifi_ble",
            source_types=(SourceType.WIFI, SourceType.BLE),
            score_multiplier=1.5,
            time_window_s=30.0,
        )
        a = _make_appearance("dev-wifi-1", SourceType.WIFI, NOW)
        b = _make_appearance("dev-wifi-2", SourceType.WIFI, NOW + 5.0)
        assert rule.check(a, b) is False

    def test_rule_check_outside_time_window(self):
        """Appearances more than time_window_s apart return False."""
        rule = CorrelationRule(
            name="wifi_ble",
            source_types=(SourceType.WIFI, SourceType.BLE),
            score_multiplier=1.5,
            time_window_s=30.0,
        )
        a = _make_appearance("dev-wifi-1", SourceType.WIFI, NOW)
        b = _make_appearance("dev-ble-1", SourceType.BLE, NOW + 31.0)
        assert rule.check(a, b) is False


# ---------------------------------------------------------------------------
# FusionEngine tests
# ---------------------------------------------------------------------------


class TestFusionEngine:
    """Tests for FusionEngine correlation and scoring."""

    @pytest.fixture()
    def fusion_config(self):
        """Minimal fusion engine config."""
        return {
            "time_window_s": 30.0,
        }

    @pytest.fixture()
    def engine(self, fusion_config):
        """FusionEngine with a default WiFi+BLE correlation rule."""
        eng = FusionEngine(config=fusion_config)
        eng.add_rule(CorrelationRule(
            name="wifi_ble",
            source_types=(SourceType.WIFI, SourceType.BLE),
            score_multiplier=1.5,
            time_window_s=30.0,
        ))
        return eng

    def test_engine_creation(self, fusion_config):
        """Engine stores config and starts with empty state."""
        eng = FusionEngine(config=fusion_config)
        assert eng.correlation_count == 0
        assert eng.get_correlated_groups() == {}

    def test_add_rule(self, fusion_config):
        """Rule is registered and accessible."""
        eng = FusionEngine(config=fusion_config)
        rule = CorrelationRule(
            name="wifi_ble",
            source_types=(SourceType.WIFI, SourceType.BLE),
            score_multiplier=1.5,
        )
        eng.add_rule(rule)
        # Engine should have at least one rule; exact API may vary,
        # but processing should now be able to use the rule.
        # We verify indirectly: a correlated pair should be detected.
        a = _make_appearance("phone-mac-1", SourceType.WIFI, NOW)
        b = _make_appearance("ble-tracker-1", SourceType.BLE, NOW + 5.0)
        eng.process_appearance(a)
        correlations = eng.process_appearance(b)
        assert len(correlations) > 0

    def test_process_single_appearance(self, engine):
        """One appearance alone produces no correlations."""
        a = _make_appearance("phone-mac-1", SourceType.WIFI, NOW)
        correlations = engine.process_appearance(a)
        assert correlations == []

    def test_process_correlated_pair(self, engine):
        """WiFi then BLE within 30s triggers a correlation."""
        a = _make_appearance("phone-mac-1", SourceType.WIFI, NOW)
        b = _make_appearance("ble-tracker-1", SourceType.BLE, NOW + 10.0)

        engine.process_appearance(a)
        correlations = engine.process_appearance(b)

        assert len(correlations) == 1
        corr = correlations[0]
        # Correlation info should reference both device_ids and the rule name
        assert "phone-mac-1" in (corr["device_id_a"], corr["device_id_b"])
        assert "ble-tracker-1" in (corr["device_id_a"], corr["device_id_b"])
        assert corr["rule_name"] == "wifi_ble"

    def test_process_uncorrelated_pair(self, engine):
        """Two WiFi appearances (same source type) produce no correlation."""
        a = _make_appearance("phone-mac-1", SourceType.WIFI, NOW)
        b = _make_appearance("phone-mac-2", SourceType.WIFI, NOW + 5.0)

        engine.process_appearance(a)
        correlations = engine.process_appearance(b)

        assert correlations == []

    def test_score_multiplier_for_correlated_device(self, engine):
        """After correlation, get_score_multiplier returns the rule's multiplier."""
        a = _make_appearance("phone-mac-1", SourceType.WIFI, NOW)
        b = _make_appearance("ble-tracker-1", SourceType.BLE, NOW + 5.0)

        engine.process_appearance(a)
        engine.process_appearance(b)

        assert engine.get_score_multiplier("phone-mac-1") == 1.5
        assert engine.get_score_multiplier("ble-tracker-1") == 1.5

    def test_score_multiplier_for_uncorrelated_device(self, engine):
        """Uncorrelated device returns 1.0 (no boost)."""
        a = _make_appearance("phone-mac-1", SourceType.WIFI, NOW)
        engine.process_appearance(a)

        assert engine.get_score_multiplier("phone-mac-1") == 1.0
        assert engine.get_score_multiplier("never-seen-device") == 1.0

    def test_get_correlated_groups(self, engine):
        """Returns dict mapping group_id to list of device_ids."""
        a = _make_appearance("phone-mac-1", SourceType.WIFI, NOW)
        b = _make_appearance("ble-tracker-1", SourceType.BLE, NOW + 5.0)

        engine.process_appearance(a)
        engine.process_appearance(b)

        groups = engine.get_correlated_groups()
        assert len(groups) == 1

        group_id = next(iter(groups))
        members = sorted(groups[group_id])
        assert members == ["ble-tracker-1", "phone-mac-1"]

    def test_correlation_count(self, engine):
        """correlation_count tracks number of correlations found."""
        assert engine.correlation_count == 0

        a = _make_appearance("phone-mac-1", SourceType.WIFI, NOW)
        b = _make_appearance("ble-tracker-1", SourceType.BLE, NOW + 5.0)
        engine.process_appearance(a)
        engine.process_appearance(b)

        assert engine.correlation_count == 1

        # A second correlated pair — use timestamps far enough from the first
        # pair that they don't cross-correlate (>30s window)
        c = _make_appearance("phone-mac-2", SourceType.WIFI, NOW + 60.0)
        d = _make_appearance("ble-tracker-2", SourceType.BLE, NOW + 65.0)
        engine.process_appearance(c)
        engine.process_appearance(d)

        assert engine.correlation_count == 2

    def test_window_expiry(self, engine):
        """Appearances older than time_window_s are pruned from the sliding window."""
        old = _make_appearance("phone-mac-old", SourceType.WIFI, NOW)
        engine.process_appearance(old)

        # New appearance arrives 31s later -- the old one should have expired
        fresh = _make_appearance("ble-tracker-fresh", SourceType.BLE, NOW + 31.0)
        correlations = engine.process_appearance(fresh)

        # Old WiFi appearance is outside the 30s window, so no correlation
        assert correlations == []

    def test_tpms_wifi_correlation(self, fusion_config):
        """TPMS sensor ID + WiFi phone MAC appearing together get 2.0x multiplier."""
        eng = FusionEngine(config=fusion_config)
        eng.add_rule(CorrelationRule(
            name="tpms_wifi",
            source_types=(SourceType.SUBGHZ, SourceType.WIFI),
            score_multiplier=2.0,
            time_window_s=30.0,
        ))

        tpms = _make_appearance(
            "tpms:0x1A2B3C4D",
            SourceType.SUBGHZ,
            NOW,
            frequency_mhz=433.92,
        )
        phone = _make_appearance("AA:BB:CC:DD:EE:FF", SourceType.WIFI, NOW + 3.0)

        eng.process_appearance(tpms)
        correlations = eng.process_appearance(phone)

        assert len(correlations) == 1
        assert correlations[0]["rule_name"] == "tpms_wifi"
        assert eng.get_score_multiplier("tpms:0x1A2B3C4D") == 2.0
        assert eng.get_score_multiplier("AA:BB:CC:DD:EE:FF") == 2.0
