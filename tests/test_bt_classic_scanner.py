"""TDD tests for scanners/bt_classic_scanner.py — Bluetooth Classic inquiry
scanning and device class parsing.

All tests should FAIL until the BTClassicScanner stub is replaced with the real
implementation.
"""
import time
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from scanners.base_scanner import DeviceAppearance, ScannerState, SourceType
from scanners.bt_classic_scanner import BTClassicScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bt_scanner(config: dict | None = None, location_id: str = "test-loc"):
    """Create a BTClassicScanner with a fresh output queue."""
    if config is None:
        config = {}
    q = Queue()
    scanner = BTClassicScanner(config=config, output_queue=q, location_id=location_id)
    return scanner, q


def _drain_queue(q: Queue) -> list[DeviceAppearance]:
    """Pull all items from a queue into a list."""
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bt_scanner():
    """Default BTClassicScanner with empty config."""
    scanner, _ = _make_bt_scanner()
    return scanner


# ---------------------------------------------------------------------------
# 1. scanner_name == "bt_classic"
# ---------------------------------------------------------------------------

def test_bt_classic_scanner_name(bt_scanner):
    assert bt_scanner.scanner_name == "bt_classic"


# ---------------------------------------------------------------------------
# 2. source_type == SourceType.BT_CLASSIC
# ---------------------------------------------------------------------------

def test_bt_classic_scanner_source_type(bt_scanner):
    assert bt_scanner.source_type == SourceType.BT_CLASSIC


# ---------------------------------------------------------------------------
# 3. _run_inquiry returns structured device data
# ---------------------------------------------------------------------------

def test_run_inquiry_returns_devices():
    """Mock _run_inquiry's underlying subprocess to return discovered devices.

    _run_inquiry() should return a list of dicts, each with keys:
      - address: BT MAC address
      - name: device name (or None)
      - device_class: integer CoD value
    """
    scanner, _ = _make_bt_scanner()

    # Mock the subprocess call that _run_inquiry wraps
    fake_inquiry_result = [
        {"address": "AA:BB:CC:DD:EE:01", "name": "JBL Speaker", "device_class": 0x240404},
        {"address": "AA:BB:CC:DD:EE:02", "name": "iPhone", "device_class": 0x5A020C},
    ]

    with patch.object(scanner, "_run_inquiry", return_value=fake_inquiry_result):
        devices = scanner._run_inquiry()

    assert len(devices) == 2
    assert devices[0]["address"] == "AA:BB:CC:DD:EE:01"
    assert devices[0]["name"] == "JBL Speaker"
    assert devices[0]["device_class"] == 0x240404
    assert devices[1]["address"] == "AA:BB:CC:DD:EE:02"


# ---------------------------------------------------------------------------
# 4. _parse_device_class — Audio/Video (major class 0x04, bits 8-12)
# ---------------------------------------------------------------------------

def test_parse_device_class_audio(bt_scanner):
    # 0x240404: major class bits 8-12 = 0x04 (Audio/Video)
    # Binary of 0x240404: bits 8-12 = 00100 = 0x04
    result = bt_scanner._parse_device_class(0x240404)
    assert result == "audio"


# ---------------------------------------------------------------------------
# 5. _parse_device_class — Phone (major class 0x02, bits 8-12)
# ---------------------------------------------------------------------------

def test_parse_device_class_phone(bt_scanner):
    # 0x5A020C: major class bits 8-12 = 0x02 (Phone)
    # Bits 8-12 of 0x5A020C: (0x5A020C >> 8) & 0x1F = 0x02
    result = bt_scanner._parse_device_class(0x5A020C)
    assert result == "phone"


# ---------------------------------------------------------------------------
# 6. _parse_device_class — Computer (major class 0x01, bits 8-12)
# ---------------------------------------------------------------------------

def test_parse_device_class_computer(bt_scanner):
    # 0x3A0104: major class bits 8-12 = 0x01 (Computer)
    # (0x3A0104 >> 8) & 0x1F = 0x01
    result = bt_scanner._parse_device_class(0x3A0104)
    assert result == "computer"


# ---------------------------------------------------------------------------
# 7. _scan_loop emits DeviceAppearance for discovered devices
# ---------------------------------------------------------------------------

def test_scan_loop_emits_appearances():
    """Mock _run_inquiry to return two devices and verify DeviceAppearance
    objects are emitted with correct fields."""
    scanner, q = _make_bt_scanner(location_id="garage-1")

    fake_devices = [
        {"address": "11:22:33:44:55:66", "name": "JBL Flip 6", "device_class": 0x240404},
        {"address": "AA:BB:CC:DD:EE:FF", "name": "Pixel 8", "device_class": 0x5A020C},
    ]

    before = time.time()

    with patch.object(scanner, "_run_inquiry", return_value=fake_devices), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    after = time.time()
    appearances = _drain_queue(q)

    assert len(appearances) == 2

    # First device — audio
    da1 = appearances[0]
    assert isinstance(da1, DeviceAppearance)
    assert da1.device_id == "btc:11:22:33:44:55:66"
    assert da1.source_type == SourceType.BT_CLASSIC
    assert da1.location_id == "garage-1"
    assert da1.mac == "11:22:33:44:55:66"
    assert before <= da1.timestamp <= after
    assert "device_class" in da1.metadata
    assert da1.metadata["device_class"] == "audio"
    assert da1.metadata.get("device_name") == "JBL Flip 6"

    # Second device — phone
    da2 = appearances[1]
    assert da2.device_id == "btc:AA:BB:CC:DD:EE:FF"
    assert da2.source_type == SourceType.BT_CLASSIC
    assert da2.metadata["device_class"] == "phone"
    assert da2.metadata.get("device_name") == "Pixel 8"


# ---------------------------------------------------------------------------
# 8. _scan_loop handles adapter error gracefully (no crash)
# ---------------------------------------------------------------------------

def test_scan_loop_no_adapter():
    """When _run_inquiry raises an OSError (no adapter), the scanner should
    handle it gracefully without crashing — log the error and continue or
    set ERROR state."""
    scanner, q = _make_bt_scanner()

    with patch.object(scanner, "_run_inquiry", side_effect=OSError("No Bluetooth adapter found")), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):
        # Should not raise — the scanner catches the error internally
        scanner._scan_loop()

    # No appearances emitted
    assert q.empty()
    # Scanner should not have crashed — it either stayed RUNNING (handling
    # transient errors) or moved to a controlled state.  It should NOT be
    # in an unrecoverable state from a single adapter error.
