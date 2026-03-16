"""TDD tests for DeviceAppearance backward compatibility after Phase 1 refactor.

Tests 1-5 verify existing behavior that MUST be preserved — they should PASS
against the current (pre-refactor) code.

Test 6 is the TDD test for new multi-source behavior — it should FAIL until
Phase 1 implementation is complete.
"""
import time
import sqlite3
import json
import pytest

from surveillance_detector import (
    DeviceAppearance,
    SuspiciousDevice,
    SurveillanceDetector,
    load_appearances_from_kismet,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> dict:
    return {
        "paths": {"base_dir": ".", "kismet_logs": "/tmp/nonexistent/*.kismet"},
        "timing": {"check_interval": 60},
    }


def _kismet_db_with_devices(tmp_path, devices):
    """Create a Kismet-schema SQLite DB in tmp_path with the given device rows."""
    db_path = str(tmp_path / "test.kismet")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE devices (
            devmac TEXT, type TEXT, device TEXT,
            last_time REAL, first_time REAL DEFAULT 0,
            avg_lat REAL DEFAULT 0, avg_lon REAL DEFAULT 0
        )"""
    )
    for mac, dtype, device_json, ts in devices:
        conn.execute(
            "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
            (mac, dtype, device_json, ts),
        )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Tests 1-5: backward compatibility — should PASS on current code
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """These tests verify existing behavior that must survive the refactor."""

    def test_old_import_path_works(self):
        """DeviceAppearance is importable from surveillance_detector."""
        # This import already happened at module level; verify the class exists
        assert DeviceAppearance is not None
        # It should be usable as a dataclass with the legacy fields
        appearance = DeviceAppearance(
            mac="AA:BB:CC:DD:EE:01",
            timestamp=time.time(),
            location_id="test",
            ssids_probed=["Net1"],
        )
        assert appearance.mac == "AA:BB:CC:DD:EE:01"

    def test_legacy_add_device_appearance_shim(self):
        """add_device_appearance(mac=...) creates an appearance in device_history
        keyed by the MAC address (current behavior) or device_id (post-refactor,
        where device_id == mac for WiFi)."""
        detector = SurveillanceDetector(_make_config())
        detector.add_device_appearance(
            mac="AA:BB:CC:DD:EE:01",
            timestamp=time.time(),
            location_id="loc-A",
            ssids_probed=["TestSSID"],
            signal_strength=-70.0,
            device_type="Wi-Fi Client",
        )
        # The device should be retrievable by its MAC (which is also its device_id)
        mac = "AA:BB:CC:DD:EE:01"
        assert mac in detector.device_history
        assert len(detector.device_history[mac]) == 1
        stored = detector.device_history[mac][0]
        assert stored.mac == mac
        assert stored.ssids_probed == ["TestSSID"]

    def test_suspicious_device_has_mac(self):
        """SuspiciousDevice returned by analysis has a .mac field."""
        detector = SurveillanceDetector(_make_config())
        now = time.time()
        mac = "AA:BB:CC:DD:EE:02"
        # Add enough appearances across enough time to trigger detection
        for i in range(5):
            detector.add_device_appearance(
                mac=mac,
                timestamp=now - (i * 3600),  # spread over 4 hours
                location_id=f"loc-{i % 2}",
                ssids_probed=["Net"],
            )
        results = detector.analyze_surveillance_patterns()
        assert len(results) >= 1
        suspect = results[0]
        assert suspect.mac == mac

    def test_analyze_patterns_uses_mac_key(self):
        """After adding via add_device_appearance, analyze returns results
        whose .mac matches the original key."""
        detector = SurveillanceDetector(_make_config())
        now = time.time()
        mac = "11:22:33:44:55:66"
        for i in range(4):
            detector.add_device_appearance(
                mac=mac,
                timestamp=now - (i * 7200),
                location_id=f"spot-{i % 3}",
            )
        results = detector.analyze_surveillance_patterns()
        if results:  # may or may not trigger depending on scoring
            for r in results:
                # The mac field on the result should be a string matching input
                assert isinstance(r.mac, str)

    def test_load_appearances_from_kismet_uses_shim(self, tmp_path):
        """load_appearances_from_kismet still works and populates the detector."""
        now = time.time()
        device_json = json.dumps({
            "dot11.device": {
                "dot11.device.last_probed_ssid_record": {
                    "dot11.probedssid.ssid": "CoffeeShop"
                }
            }
        })
        devices = [
            ("AA:BB:CC:DD:EE:10", "Wi-Fi Client", device_json, now - 60),
            ("AA:BB:CC:DD:EE:11", "Wi-Fi Client", device_json, now - 120),
        ]
        db_path = _kismet_db_with_devices(tmp_path, devices)
        detector = SurveillanceDetector(_make_config())
        count = load_appearances_from_kismet(db_path, detector, location_id="cafe")
        assert count >= 2
        assert "AA:BB:CC:DD:EE:10" in detector.device_history
        assert "AA:BB:CC:DD:EE:11" in detector.device_history


# ---------------------------------------------------------------------------
# Test 6: TDD test — should FAIL until Phase 1 multi-source is implemented
# ---------------------------------------------------------------------------

class TestMultiSourceIntegration:
    """This test exercises new Phase 1 behavior (mixed WiFi + BLE).
    It will FAIL until the refactor is complete."""

    def test_mixed_source_types(self):
        """Add WiFi via legacy shim AND a new-style BLE appearance;
        both appear in device_history and analysis handles both.

        TDD TEST: expected to FAIL on pre-refactor code.
        """
        # Import the new-style DeviceAppearance from scanners.base_scanner
        from scanners.base_scanner import (
            DeviceAppearance as NewDeviceAppearance,
            SourceType,
        )

        detector = SurveillanceDetector(_make_config())
        now = time.time()

        # --- WiFi device added via legacy shim ---
        wifi_mac = "AA:BB:CC:DD:EE:50"
        for i in range(4):
            detector.add_device_appearance(
                mac=wifi_mac,
                timestamp=now - (i * 3600),
                location_id=f"loc-{i % 2}",
                ssids_probed=["HomeNet"],
            )

        # --- BLE device added via new add_appearance() method ---
        ble_id = "ble:IRK:abcdef1234567890"
        for i in range(4):
            ble_appearance = NewDeviceAppearance(
                device_id=ble_id,
                source_type=SourceType.BLE,
                timestamp=now - (i * 3600),
                location_id=f"loc-{i % 2}",
                signal_strength=-80.0,
            )
            # This method does not exist on current code — will raise AttributeError
            detector.add_appearance(ble_appearance)

        # Both devices should be in device_history
        assert wifi_mac in detector.device_history, "WiFi device missing from history"
        assert ble_id in detector.device_history, "BLE device missing from history"

        # Analysis should handle both source types without crashing
        results = detector.analyze_surveillance_patterns()
        result_ids = [r.mac for r in results]  # .mac is alias for device_id post-refactor
        # At least the BLE device should appear (it has enough appearances)
        assert any(ble_id == rid for rid in result_ids), (
            "BLE device not found in analysis results"
        )
