"""TDD tests for scanners/ble_scanner.py — BLE tracker scanner integration.

All tests should FAIL until the BLEScanner stub is replaced with the real
implementation.  Tests mock bleak.BleakScanner.discover() and the
BLETrackerClassifier to isolate scanner integration logic.
"""
import re
import time
from queue import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scanners.base_scanner import DeviceAppearance, ScannerState, SourceType
from scanners.ble_scanner import BLEScanner, BLETrackerClassifier


# ---------------------------------------------------------------------------
# Helpers: fake BLEDevice and AdvertisementData objects
# ---------------------------------------------------------------------------

def make_ble_device(address: str, rssi: int = -60):
    """Create a fake bleak BLEDevice."""
    dev = SimpleNamespace()
    dev.address = address
    dev.name = None
    dev.rssi = rssi
    return dev


def make_advertisement_data(manufacturer_data: dict = None, service_data: dict = None, rssi: int = -60):
    """Create a fake bleak AdvertisementData."""
    adv = SimpleNamespace()
    adv.manufacturer_data = manufacturer_data or {}
    adv.service_data = service_data or {}
    adv.rssi = rssi
    return adv


# Apple FindMy-style payload: company ID 0x004C with an advertisement payload
APPLE_COMPANY_ID = 0x004C
SAMSUNG_COMPANY_ID = 0x0075

AIRTAG_PAYLOAD = bytes([0x12, 0x19] + [0xAA] * 27)  # FindMy advertisement prefix + payload
AIRTAG_PAYLOAD_2 = bytes([0x12, 0x19] + [0xAA] * 27)  # Same payload, different MAC
SMARTTAG_PAYLOAD = bytes([0x01, 0x02] + [0xBB] * 20)

NON_TRACKER_MANUFACTURER_DATA = {0xFFFF: bytes([0x01, 0x02, 0x03])}


def make_airtag_device(address: str = "AA:BB:CC:DD:EE:01", rssi: int = -55):
    """Return (BLEDevice, AdvertisementData) mimicking an AirTag."""
    dev = make_ble_device(address, rssi)
    adv = make_advertisement_data(
        manufacturer_data={APPLE_COMPANY_ID: AIRTAG_PAYLOAD},
        rssi=rssi,
    )
    return (dev, adv)


def make_smarttag_device(address: str = "11:22:33:44:55:66", rssi: int = -70):
    """Return (BLEDevice, AdvertisementData) mimicking a Samsung SmartTag."""
    dev = make_ble_device(address, rssi)
    adv = make_advertisement_data(
        manufacturer_data={SAMSUNG_COMPANY_ID: SMARTTAG_PAYLOAD},
        rssi=rssi,
    )
    return (dev, adv)


def make_generic_ble_device(address: str = "FF:FF:FF:FF:FF:01", rssi: int = -80):
    """Return (BLEDevice, AdvertisementData) for a non-tracker BLE device."""
    dev = make_ble_device(address, rssi)
    adv = make_advertisement_data(
        manufacturer_data=NON_TRACKER_MANUFACTURER_DATA,
        rssi=rssi,
    )
    return (dev, adv)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ble_config():
    """Config with BLE scanner settings."""
    return {
        "scanners": {
            "ble": {
                "scan_duration": 5.0,
                "scan_interval": 15.0,
                "tracker_types": ["findmy", "smarttag", "tile"],
            }
        }
    }


@pytest.fixture
def ble_scanner(ble_config):
    """BLEScanner instance with standard config."""
    q = Queue()
    return BLEScanner(config=ble_config, output_queue=q, location_id="test-loc")


# ---------------------------------------------------------------------------
# 1. scanner_name == "ble"
# ---------------------------------------------------------------------------

def test_ble_scanner_name(ble_scanner):
    assert ble_scanner.scanner_name == "ble"


# ---------------------------------------------------------------------------
# 2. source_type == SourceType.BLE
# ---------------------------------------------------------------------------

def test_ble_scanner_source_type(ble_scanner):
    assert ble_scanner.source_type == SourceType.BLE


# ---------------------------------------------------------------------------
# 3. scan_duration, scan_interval read from config
# ---------------------------------------------------------------------------

def test_ble_scanner_reads_config(ble_config):
    q = Queue()
    scanner = BLEScanner(config=ble_config, output_queue=q)
    assert scanner._scan_duration == 5.0
    assert scanner._scan_interval == 15.0

    # Test defaults when config keys are absent
    scanner2 = BLEScanner(config={}, output_queue=q)
    assert scanner2._scan_duration > 0  # has a sensible default
    assert scanner2._scan_interval > 0


# ---------------------------------------------------------------------------
# 4. Mocked discover() returns AirTag-like device -> DeviceAppearance emitted
# ---------------------------------------------------------------------------

def test_ble_scan_emits_appearances(ble_config):
    q = Queue()
    scanner = BLEScanner(config=ble_config, output_queue=q, location_id="test-loc")

    airtag = make_airtag_device()

    mock_discover = AsyncMock(return_value=[airtag])
    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = {
        "tracker_type": "findmy",
        "payload_hash": "abcdef1234567890",
    }

    scanner._classifier = mock_classifier

    with patch("scanners.ble_scanner.BleakScanner") as MockBleakScanner:
        MockBleakScanner.discover = mock_discover

        with patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
             patch.object(scanner._stop_event, "wait", return_value=True):
            scanner._scan_loop()

    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    assert len(appearances) >= 1
    da = appearances[0]
    assert isinstance(da, DeviceAppearance)
    assert da.source_type == SourceType.BLE


# ---------------------------------------------------------------------------
# 5. device_id matches "findmy:<hex>" pattern
# ---------------------------------------------------------------------------

def test_device_id_format(ble_config):
    q = Queue()
    scanner = BLEScanner(config=ble_config, output_queue=q, location_id="test-loc")

    airtag = make_airtag_device()

    mock_discover = AsyncMock(return_value=[airtag])
    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = {
        "tracker_type": "findmy",
        "payload_hash": "a1b2c3d4e5f6",
    }

    with patch("scanners.ble_scanner.BleakScanner", autospec=True) as MockBleakScanner, \
         patch.object(scanner, "_classifier", mock_classifier, create=True), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):

        MockBleakScanner.discover = mock_discover
        scanner._scan_loop()

    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    assert len(appearances) >= 1
    # device_id should be "findmy:<hex_hash>"
    assert re.match(r"^findmy:[0-9a-f]+$", appearances[0].device_id), \
        f"device_id '{appearances[0].device_id}' does not match 'findmy:<hex>' pattern"


# ---------------------------------------------------------------------------
# 6. Two devices with different MACs but same payload hash -> same device_id
# ---------------------------------------------------------------------------

def test_mac_rotation_same_device_id(ble_config):
    q = Queue()
    scanner = BLEScanner(config=ble_config, output_queue=q, location_id="test-loc")

    device_a = make_airtag_device(address="AA:BB:CC:DD:EE:01")
    device_b = make_airtag_device(address="11:22:33:44:55:66")  # different MAC, same payload

    mock_discover = AsyncMock(return_value=[device_a, device_b])
    mock_classifier = MagicMock()
    # Both devices produce the same payload_hash (same underlying tracker)
    mock_classifier.classify.return_value = {
        "tracker_type": "findmy",
        "payload_hash": "deadbeef42",
    }

    with patch("scanners.ble_scanner.BleakScanner", autospec=True) as MockBleakScanner, \
         patch.object(scanner, "_classifier", mock_classifier, create=True), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):

        MockBleakScanner.discover = mock_discover
        scanner._scan_loop()

    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    assert len(appearances) == 2
    # Same payload_hash means same device_id despite different MACs
    assert appearances[0].device_id == appearances[1].device_id, \
        "Two devices with identical payload_hash should produce the same device_id"
    # But MACs should differ
    assert appearances[0].mac != appearances[1].mac


# ---------------------------------------------------------------------------
# 7. Non-tracker BLE device -> no DeviceAppearance emitted
# ---------------------------------------------------------------------------

def test_unrecognized_ble_device_not_emitted(ble_config):
    q = Queue()
    scanner = BLEScanner(config=ble_config, output_queue=q, location_id="test-loc")

    generic = make_generic_ble_device()

    mock_discover = AsyncMock(return_value=[generic])
    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = None  # not recognized as a tracker

    with patch("scanners.ble_scanner.BleakScanner", autospec=True) as MockBleakScanner, \
         patch.object(scanner, "_classifier", mock_classifier, create=True), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):

        MockBleakScanner.discover = mock_discover
        scanner._scan_loop()

    assert q.empty(), "Non-tracker BLE device should not produce a DeviceAppearance"


# ---------------------------------------------------------------------------
# 8. Config only includes ["findmy"] -> SmartTag not emitted
# ---------------------------------------------------------------------------

def test_tracker_type_filter():
    config = {
        "scanners": {
            "ble": {
                "scan_duration": 5.0,
                "scan_interval": 15.0,
                "tracker_types": ["findmy"],  # only FindMy, no SmartTag
            }
        }
    }
    q = Queue()
    scanner = BLEScanner(config=config, output_queue=q, location_id="test-loc")

    airtag = make_airtag_device()
    smarttag = make_smarttag_device()

    mock_discover = AsyncMock(return_value=[airtag, smarttag])
    mock_classifier = MagicMock()

    def classify_side_effect(manufacturer_data, service_data):
        if APPLE_COMPANY_ID in manufacturer_data:
            return {"tracker_type": "findmy", "payload_hash": "aaa111"}
        if SAMSUNG_COMPANY_ID in manufacturer_data:
            return {"tracker_type": "smarttag", "payload_hash": "bbb222"}
        return None

    mock_classifier.classify.side_effect = classify_side_effect

    with patch("scanners.ble_scanner.BleakScanner", autospec=True) as MockBleakScanner, \
         patch.object(scanner, "_classifier", mock_classifier, create=True), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):

        MockBleakScanner.discover = mock_discover
        scanner._scan_loop()

    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    # Only FindMy should be emitted; SmartTag filtered out
    assert len(appearances) == 1
    assert "findmy" in appearances[0].device_id
    assert appearances[0].payload_hash != "bbb222"


# ---------------------------------------------------------------------------
# 9. bleak not available -> scanner handles gracefully (ERROR state, no crash)
# ---------------------------------------------------------------------------

def test_bleak_import_error(ble_config):
    q = Queue()
    scanner = BLEScanner(config=ble_config, output_queue=q, location_id="test-loc")

    # Simulate bleak not being importable by patching the module reference
    with patch("scanners.ble_scanner.BleakScanner", None), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):

        # The scanner should handle the missing bleak gracefully.
        # Depending on implementation, it may set ERROR state or raise
        # a controlled exception caught by BaseScanner._run().
        try:
            scanner._scan_loop()
        except (ImportError, TypeError, AttributeError):
            # If _scan_loop raises, BaseScanner._run() would catch it
            # and set state to ERROR. Simulate that path.
            scanner._state = ScannerState.ERROR

    # Either the scanner caught it internally or we simulated _run() catching it.
    # The key requirement: no unhandled crash, state should be ERROR.
    assert scanner.state == ScannerState.ERROR
    assert q.empty(), "No appearances should be emitted when bleak is unavailable"


# ---------------------------------------------------------------------------
# 10. BleakScanner raises adapter error -> logged, scanner continues
# ---------------------------------------------------------------------------

def test_no_ble_adapter(ble_config, caplog):
    q = Queue()
    scanner = BLEScanner(config=ble_config, output_queue=q, location_id="test-loc")

    mock_discover = AsyncMock(side_effect=OSError("Bluetooth adapter not found"))

    with patch("scanners.ble_scanner.BleakScanner", autospec=True) as MockBleakScanner, \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):

        MockBleakScanner.discover = mock_discover

        # The scanner should catch the adapter error, log it, and continue
        # the scan loop rather than crashing outright.
        scanner._scan_loop()

    # Scanner should still be alive (not in ERROR state) — it handled the
    # transient adapter error and continued the loop.
    assert scanner.state != ScannerState.ERROR or scanner.state == ScannerState.RUNNING
    assert q.empty(), "No appearances should be emitted when adapter is unavailable"


# ---------------------------------------------------------------------------
# 11. Verify all DeviceAppearance fields are populated correctly
# ---------------------------------------------------------------------------

def test_scan_produces_correct_fields(ble_config):
    q = Queue()
    scanner = BLEScanner(config=ble_config, output_queue=q, location_id="office-1")

    airtag = make_airtag_device(address="AA:BB:CC:DD:EE:01", rssi=-55)

    mock_discover = AsyncMock(return_value=[airtag])
    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = {
        "tracker_type": "findmy",
        "payload_hash": "cafebabe",
    }

    before = time.time()

    with patch("scanners.ble_scanner.BleakScanner", autospec=True) as MockBleakScanner, \
         patch.object(scanner, "_classifier", mock_classifier, create=True), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):

        MockBleakScanner.discover = mock_discover
        scanner._scan_loop()

    after = time.time()

    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    assert len(appearances) == 1
    da = appearances[0]

    # Verify all fields
    assert da.device_id == "findmy:cafebabe"
    assert da.source_type == SourceType.BLE
    assert before <= da.timestamp <= after, "timestamp should be approximately now"
    assert da.location_id == "office-1"
    assert da.signal_strength == -55
    assert da.device_type == "findmy"
    assert da.mac == "AA:BB:CC:DD:EE:01"
    assert da.payload_hash == "cafebabe"
    assert da.ssids_probed == []  # BLE trackers don't probe SSIDs
    assert isinstance(da.metadata, dict)
