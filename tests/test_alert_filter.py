"""TDD tests for AlertFilter — false-positive suppression layer.

These tests define the acceptance criteria for alert_filter.py.
"""
import json
import pytest
from dataclasses import dataclass
from typing import List, Optional

from alert_filter import AlertFilter, FamiliarDeviceStore


# ---------------------------------------------------------------------------
# Mock device
# ---------------------------------------------------------------------------

@dataclass
class MockDevice:
    """Minimal mock matching SuspiciousDevice's relevant attributes."""
    mac: str
    persistence_score: float
    device_id: Optional[str] = None

    def __post_init__(self):
        if self.device_id is None:
            self.device_id = self.mac


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def familiar_path(tmp_path):
    return str(tmp_path / "familiar_devices.json")


@pytest.fixture
def base_config(familiar_path):
    return {
        "alert_filter": {
            "min_score": 0.7,
            "require_corroboration": False,
            "familiar_devices_path": familiar_path,
        }
    }


@pytest.fixture
def af(base_config):
    return AlertFilter(config=base_config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAlertFilter:

    def test_below_threshold_suppressed(self, af):
        """Score below min_score is suppressed."""
        device = MockDevice(mac="AA:BB:CC:DD:EE:01", persistence_score=0.5)
        surface, reason = af.should_surface(device)
        assert surface is False
        assert "below threshold" in reason.lower()

    def test_above_threshold_surfaced(self, af):
        """Score above min_score is surfaced."""
        device = MockDevice(mac="AA:BB:CC:DD:EE:02", persistence_score=0.8)
        surface, reason = af.should_surface(device)
        assert surface is True
        assert reason == ""

    def test_familiar_device_suppressed(self, af):
        """A device marked familiar (location 'all') is suppressed."""
        af.mark_familiar("AA:BB:CC:DD:EE:03", location_context="all")
        device = MockDevice(mac="AA:BB:CC:DD:EE:03", persistence_score=0.9)
        surface, reason = af.should_surface(device)
        assert surface is False
        assert "familiar device" in reason.lower()

    def test_familiar_wrong_location_not_suppressed(self, af):
        """Device marked familiar at 'home' is NOT suppressed when seen at 'work'."""
        af.mark_familiar("AA:BB:CC:DD:EE:04", location_context="home")
        device = MockDevice(mac="AA:BB:CC:DD:EE:04", persistence_score=0.8)
        # Simulate current_location being 'work' by passing it through should_surface
        surface, reason = af.should_surface(device, current_location="work")
        assert surface is True
        assert reason == ""

    def test_mark_and_unmark_familiar(self, af):
        """Mark, verify familiar, unmark, verify not familiar."""
        af.mark_familiar("AA:BB:CC:DD:EE:05")
        device = MockDevice(mac="AA:BB:CC:DD:EE:05", persistence_score=0.9)

        surface1, _ = af.should_surface(device)
        assert surface1 is False  # familiar -> suppressed

        af.unmark_familiar("AA:BB:CC:DD:EE:05")
        surface2, reason2 = af.should_surface(device)
        assert surface2 is True
        assert reason2 == ""

    def test_familiar_store_persistence(self, familiar_path):
        """Familiar device persists across store instances (backed by file)."""
        store1 = FamiliarDeviceStore(path=familiar_path)
        store1.add("AA:BB:CC:DD:EE:06", location_context="all", label="my phone")

        # Create a new store from the same file
        store2 = FamiliarDeviceStore(path=familiar_path)
        assert store2.is_familiar("AA:BB:CC:DD:EE:06") is True

    def test_corroboration_required_single_source(self, familiar_path):
        """When require_corroboration=True, a device with no fusion group is suppressed."""
        config = {
            "alert_filter": {
                "min_score": 0.7,
                "require_corroboration": True,
                "familiar_devices_path": familiar_path,
            }
        }

        # Mock fusion engine that reports no group for the device
        class MockFusion:
            def get_correlated_groups(self):
                return {}

        af = AlertFilter(config=config, fusion_engine=MockFusion())
        device = MockDevice(mac="AA:BB:CC:DD:EE:07", persistence_score=0.8)
        surface, reason = af.should_surface(device)
        assert surface is False
        assert "corroboration" in reason.lower()

    def test_get_familiar_devices(self, af):
        """get_familiar_devices returns list of marked devices."""
        af.mark_familiar("AA:BB:CC:DD:EE:08", location_context="home")
        af.mark_familiar("AA:BB:CC:DD:EE:09", location_context="all")

        devices = af.get_familiar_devices()
        assert len(devices) == 2
        ids = [d["device_id"] for d in devices]
        assert "AA:BB:CC:DD:EE:08" in ids
        assert "AA:BB:CC:DD:EE:09" in ids
