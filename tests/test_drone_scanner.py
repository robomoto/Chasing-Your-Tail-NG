"""TDD tests for scanners/drone_scanner.py — Drone detection via WiFi SSID
pattern matching and Remote ID BLE parsing.

All tests should FAIL until the DroneScanner stub is replaced with the real
implementation.
"""
import json
import sqlite3
import struct
import time
from queue import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scanners.base_scanner import DeviceAppearance, SourceType
from scanners.drone_scanner import DroneScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_drone_scanner(config: dict | None = None, location_id: str = "test-loc"):
    """Create a DroneScanner with a fresh output queue."""
    if config is None:
        config = {}
    q = Queue()
    scanner = DroneScanner(config=config, output_queue=q, location_id=location_id)
    return scanner, q


def _drain_queue(q: Queue) -> list[DeviceAppearance]:
    """Pull all items from a queue into a list."""
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def make_ble_device(address: str, rssi: int = -60):
    """Fake bleak BLEDevice."""
    dev = SimpleNamespace()
    dev.address = address
    dev.name = None
    dev.rssi = rssi
    return dev


def make_advertisement_data(manufacturer_data: dict | None = None,
                            service_data: dict | None = None,
                            rssi: int = -60):
    """Fake bleak AdvertisementData."""
    adv = SimpleNamespace()
    adv.manufacturer_data = manufacturer_data or {}
    adv.service_data = service_data or {}
    adv.rssi = rssi
    return adv


def build_remote_id_payload(serial: str = "1234567890AB",
                            lat: float = 33.4484,
                            lon: float = -112.0740,
                            altitude: float = 120.0,
                            speed: float = 5.0,
                            operator_lat: float = 33.4480,
                            operator_lon: float = -112.0745) -> bytes:
    """Build a simplified ASTM F3411 Remote ID payload for testing.

    Real Remote ID uses a specific message format.  We encode a simplified
    version that the DroneScanner should be able to parse:
      - Byte 0: message type 0x0F (our chosen Remote ID marker)
      - Bytes 1-12: serial (ASCII, zero-padded to 12 bytes)
      - Bytes 13-16: latitude  (float32 LE)
      - Bytes 17-20: longitude (float32 LE)
      - Bytes 21-24: altitude  (float32 LE)
      - Bytes 25-28: speed     (float32 LE)
      - Bytes 29-32: operator lat (float32 LE)
      - Bytes 33-36: operator lon (float32 LE)
    """
    serial_bytes = serial.encode("ascii")[:12].ljust(12, b"\x00")
    payload = (
        b"\x0f"
        + serial_bytes
        + struct.pack("<f", lat)
        + struct.pack("<f", lon)
        + struct.pack("<f", altitude)
        + struct.pack("<f", speed)
        + struct.pack("<f", operator_lat)
        + struct.pack("<f", operator_lon)
    )
    return payload


# A known Remote ID service UUID (ASTM F3411-22a Open Drone ID)
REMOTE_ID_SERVICE_UUID = "0000fffa-0000-1000-8000-00805f9b34fb"

# Manufacturer ID used for Remote ID (we'll use 0x0D for Open Drone ID)
REMOTE_ID_MANUFACTURER_ID = 0x0D


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def drone_scanner():
    """Default DroneScanner with empty config."""
    scanner, _ = _make_drone_scanner()
    return scanner


@pytest.fixture
def drone_kismet_db(tmp_path):
    """Kismet DB containing a drone WiFi SSID."""
    db_path = tmp_path / "drone.kismet"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE devices (
            devmac TEXT,
            type TEXT,
            device TEXT,
            last_time REAL,
            first_time REAL DEFAULT 0,
            avg_lat REAL DEFAULT 0,
            avg_lon REAL DEFAULT 0
        )
        """
    )
    now = time.time()
    # Drone SSID
    drone_device_json = json.dumps({
        "dot11.device": {
            "dot11.device.last_probed_ssid_record": {
                "dot11.probedssid.ssid": "DJI-MAVIC3-ABC123"
            }
        },
        "kismet.device.base.commonname": "DJI-MAVIC3-ABC123",
    })
    # Normal WiFi (should not match)
    normal_device_json = json.dumps({
        "dot11.device": {
            "dot11.device.last_probed_ssid_record": {
                "dot11.probedssid.ssid": "MyHomeWiFi"
            }
        },
        "kismet.device.base.commonname": "MyHomeWiFi",
    })
    conn.execute(
        "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
        ("AA:BB:CC:DD:EE:D1", "Wi-Fi AP", drone_device_json, now - 30),
    )
    conn.execute(
        "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
        ("AA:BB:CC:DD:EE:N1", "Wi-Fi AP", normal_device_json, now - 60),
    )
    conn.commit()
    conn.close()
    return str(db_path)


# ---------------------------------------------------------------------------
# 1. scanner_name == "drone"
# ---------------------------------------------------------------------------

def test_drone_scanner_name(drone_scanner):
    assert drone_scanner.scanner_name == "drone"


# ---------------------------------------------------------------------------
# 2. source_type == SourceType.DRONE
# ---------------------------------------------------------------------------

def test_drone_scanner_source_type(drone_scanner):
    assert drone_scanner.source_type == SourceType.DRONE


# ---------------------------------------------------------------------------
# 3. match_drone_ssid — DJI pattern
# ---------------------------------------------------------------------------

def test_match_drone_ssid_dji(drone_scanner):
    assert drone_scanner.match_drone_ssid("DJI-MAVIC3-ABC123") is True


# ---------------------------------------------------------------------------
# 4. match_drone_ssid — TELLO pattern
# ---------------------------------------------------------------------------

def test_match_drone_ssid_tello(drone_scanner):
    assert drone_scanner.match_drone_ssid("TELLO-123456") is True


# ---------------------------------------------------------------------------
# 5. match_drone_ssid — Skydio pattern
# ---------------------------------------------------------------------------

def test_match_drone_ssid_skydio(drone_scanner):
    assert drone_scanner.match_drone_ssid("Skydio-X2E-789") is True


# ---------------------------------------------------------------------------
# 6. match_drone_ssid — PARROT pattern (case-insensitive)
# ---------------------------------------------------------------------------

def test_match_drone_ssid_parrot(drone_scanner):
    # The default patterns include "PARROT-*", and matching should be
    # case-insensitive so "parrot-anafi-001" also matches.
    assert drone_scanner.match_drone_ssid("PARROT-ANAFI-001") is True
    assert drone_scanner.match_drone_ssid("parrot-anafi-001") is True


# ---------------------------------------------------------------------------
# 7. match_drone_ssid — no match
# ---------------------------------------------------------------------------

def test_match_drone_ssid_no_match(drone_scanner):
    assert drone_scanner.match_drone_ssid("MyHomeWiFi") is False
    assert drone_scanner.match_drone_ssid("Linksys-5G") is False
    assert drone_scanner.match_drone_ssid("") is False


# ---------------------------------------------------------------------------
# 8. match_drone_ssid — custom patterns from config
# ---------------------------------------------------------------------------

def test_match_drone_ssid_custom_patterns():
    config = {
        "scanners": {
            "drone": {
                "ssid_patterns": ["FPV-*"],
            }
        }
    }
    scanner, _ = _make_drone_scanner(config=config)
    # Custom pattern should match
    assert scanner.match_drone_ssid("FPV-RACER-01") is True
    # Default patterns should NOT match when custom patterns are provided
    assert scanner.match_drone_ssid("DJI-MAVIC3-ABC123") is False


# ---------------------------------------------------------------------------
# 9. parse_remote_id_ble — valid Remote ID payload via service data
# ---------------------------------------------------------------------------

def test_parse_remote_id_valid(drone_scanner):
    payload = build_remote_id_payload(
        serial="DRONE-SN-001",
        lat=33.4484,
        lon=-112.0740,
        altitude=120.0,
        speed=5.0,
        operator_lat=33.4480,
        operator_lon=-112.0745,
    )

    # Remote ID can arrive via service_data keyed on the Remote ID UUID
    result = drone_scanner.parse_remote_id_ble(
        manufacturer_data={},
        service_data={REMOTE_ID_SERVICE_UUID: payload},
    )

    assert result is not None
    assert result["serial"] == "DRONE-SN-001"
    assert abs(result["lat"] - 33.4484) < 0.01
    assert abs(result["lon"] - (-112.0740)) < 0.01
    assert abs(result["altitude"] - 120.0) < 1.0
    assert abs(result["speed"] - 5.0) < 0.5
    assert abs(result["operator_lat"] - 33.4480) < 0.01
    assert abs(result["operator_lon"] - (-112.0745)) < 0.01


# ---------------------------------------------------------------------------
# 10. parse_remote_id_ble — non-Remote-ID data returns None
# ---------------------------------------------------------------------------

def test_parse_remote_id_no_match(drone_scanner):
    # Random manufacturer data that is NOT Remote ID
    result = drone_scanner.parse_remote_id_ble(
        manufacturer_data={0xFFFF: b"\x01\x02\x03"},
        service_data={},
    )
    assert result is None

    # Empty data
    result = drone_scanner.parse_remote_id_ble(
        manufacturer_data={},
        service_data={},
    )
    assert result is None

    # Service data with wrong UUID
    result = drone_scanner.parse_remote_id_ble(
        manufacturer_data={},
        service_data={"0000feed-0000-1000-8000-00805f9b34fb": b"\x01\x02\x03"},
    )
    assert result is None


# ---------------------------------------------------------------------------
# 11. _scan_loop emits DeviceAppearance for drone SSID from Kismet DB
# ---------------------------------------------------------------------------

def test_scan_loop_emits_ssid_match(drone_kismet_db):
    config = {
        "paths": {
            "kismet_logs": drone_kismet_db,
        },
        "scanners": {
            "drone": {
                "enable_wifi_ssid": True,
                "enable_remote_id": False,
            }
        },
    }
    scanner, q = _make_drone_scanner(config=config, location_id="field-1")

    # Run scan loop for one iteration then stop
    with patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    appearances = _drain_queue(q)

    # Should have found the DJI drone SSID but not MyHomeWiFi
    assert len(appearances) >= 1
    drone_appearances = [a for a in appearances if "DJI-MAVIC3-ABC123" in a.device_id]
    assert len(drone_appearances) == 1

    da = drone_appearances[0]
    assert da.device_id == "drone_ssid:DJI-MAVIC3-ABC123"
    assert da.source_type == SourceType.DRONE
    assert da.location_id == "field-1"
    assert isinstance(da.metadata, dict)


# ---------------------------------------------------------------------------
# 12. _scan_loop emits DeviceAppearance for Remote ID BLE advertisement
# ---------------------------------------------------------------------------

def test_scan_loop_emits_remote_id():
    config = {
        "scanners": {
            "drone": {
                "enable_wifi_ssid": False,
                "enable_remote_id": True,
            }
        },
    }
    scanner, q = _make_drone_scanner(config=config, location_id="field-2")

    # Build a fake BLE scan result with Remote ID data
    rid_payload = build_remote_id_payload(
        serial="SN-ABCDEF99",
        lat=34.0522,
        lon=-118.2437,
        altitude=50.0,
        speed=3.0,
        operator_lat=34.0520,
        operator_lon=-118.2440,
    )

    fake_device = make_ble_device("DD:DD:DD:DD:DD:01", rssi=-50)
    fake_adv = make_advertisement_data(
        service_data={REMOTE_ID_SERVICE_UUID: rid_payload},
        rssi=-50,
    )

    mock_discover = AsyncMock(return_value=[(fake_device, fake_adv)])

    with patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True), \
         patch("scanners.drone_scanner.BleakScanner", create=True) as MockBleakScanner:
        MockBleakScanner.discover = mock_discover
        scanner._scan_loop()

    appearances = _drain_queue(q)

    assert len(appearances) >= 1
    da = appearances[0]
    assert da.device_id == "drone:SN-ABCDEF99"
    assert da.source_type == SourceType.DRONE
    assert da.location_id == "field-2"
    assert da.signal_strength == -50

    # Metadata should contain operator location
    assert "operator_lat" in da.metadata
    assert "operator_lon" in da.metadata
    assert abs(da.metadata["operator_lat"] - 34.0520) < 0.01
    assert abs(da.metadata["operator_lon"] - (-118.2440)) < 0.01
    assert "altitude" in da.metadata
    assert "serial" in da.metadata
    assert da.metadata["serial"] == "SN-ABCDEF99"
