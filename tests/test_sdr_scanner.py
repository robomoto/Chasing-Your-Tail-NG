"""TDD tests for SDRScanner — Sub-GHz scanning via RTL-SDR + rtl_433."""
import io
import json
import time
from queue import Queue
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from scanners.base_scanner import DeviceAppearance, SourceType
from scanners.sdr_scanner import SDRScanner


# ---------------------------------------------------------------------------
# Sample rtl_433 JSON output
# ---------------------------------------------------------------------------

TPMS_LINE = json.dumps({
    "time": "2025-07-23 14:30:00",
    "model": "Toyota",
    "type": "TPMS",
    "id": "1a2b3c4d",
    "pressure_PSI": 32.5,
    "temperature_C": 25.0,
})

WEATHER_LINE = json.dumps({
    "time": "2025-07-23 14:30:01",
    "model": "Acurite-Tower",
    "id": "12345",
    "temperature_C": 22.3,
    "humidity": 45,
})

SECURITY_LINE = json.dumps({
    "time": "2025-07-23 14:30:02",
    "model": "Honeywell-Security",
    "id": "abc123",
    "event": "open",
    "channel": 1,
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sdr_scanner():
    """Create an SDRScanner with minimal config."""
    config = {
        "scanners": {
            "sdr": {
                "rtl_433_path": "/usr/local/bin/rtl_433",
            },
        },
    }
    q = Queue()
    return SDRScanner(config=config, output_queue=q, location_id="test-loc-01")


def _make_stdout_mock(lines: list[str]):
    """Return a mock Popen whose stdout yields encoded JSON lines."""
    encoded = [line.encode("utf-8") + b"\n" for line in lines]
    stdout_mock = io.BytesIO(b"".join(encoded))
    proc = MagicMock()
    proc.stdout = stdout_mock
    proc.poll.return_value = None  # process "running"
    proc.pid = 12345
    proc.returncode = 0
    return proc


# ---------------------------------------------------------------------------
# 1-2: Identity tests
# ---------------------------------------------------------------------------

def test_sdr_scanner_name(sdr_scanner):
    """scanner_name property returns 'sdr'."""
    assert sdr_scanner.scanner_name == "sdr"


def test_sdr_scanner_source_type(sdr_scanner):
    """source_type property returns SourceType.SUBGHZ."""
    assert sdr_scanner.source_type == SourceType.SUBGHZ


# ---------------------------------------------------------------------------
# 3-7: JSON parsing tests
# ---------------------------------------------------------------------------

def test_parse_rtl433_json_tpms(sdr_scanner):
    """Parse a TPMS JSON line — extract model, id, time."""
    parsed = sdr_scanner._parse_rtl433_json(TPMS_LINE)
    assert parsed is not None
    assert parsed["model"] == "Toyota"
    assert parsed["id"] == "1a2b3c4d"
    assert parsed["time"] == "2025-07-23 14:30:00"
    assert parsed["type"] == "TPMS"
    assert parsed["pressure_PSI"] == 32.5


def test_parse_rtl433_json_weather(sdr_scanner):
    """Parse a weather station JSON line."""
    parsed = sdr_scanner._parse_rtl433_json(WEATHER_LINE)
    assert parsed is not None
    assert parsed["model"] == "Acurite-Tower"
    assert parsed["id"] == "12345"
    assert parsed["temperature_C"] == 22.3
    assert parsed["humidity"] == 45


def test_parse_rtl433_json_security(sdr_scanner):
    """Parse a security sensor JSON line."""
    parsed = sdr_scanner._parse_rtl433_json(SECURITY_LINE)
    assert parsed is not None
    assert parsed["model"] == "Honeywell-Security"
    assert parsed["id"] == "abc123"
    assert parsed["event"] == "open"
    assert parsed["channel"] == 1


def test_parse_rtl433_json_invalid(sdr_scanner):
    """Malformed JSON returns None."""
    result = sdr_scanner._parse_rtl433_json("{this is not json!!!")
    assert result is None


def test_parse_rtl433_json_missing_id(sdr_scanner):
    """JSON without 'id' field still parses — model used as fallback for device_id."""
    line = json.dumps({
        "time": "2025-07-23 14:31:00",
        "model": "Generic-Remote",
        "button": 3,
    })
    parsed = sdr_scanner._parse_rtl433_json(line)
    assert parsed is not None
    assert parsed["model"] == "Generic-Remote"
    # No 'id' key — caller should handle via _make_device_id fallback
    assert "id" not in parsed


# ---------------------------------------------------------------------------
# 8-9: Device ID generation
# ---------------------------------------------------------------------------

def test_make_device_id_tpms(sdr_scanner):
    """TPMS device_id format: 'tpms:<hex_id>'."""
    parsed = {"model": "Toyota", "type": "TPMS", "id": "1a2b3c4d"}
    device_id = sdr_scanner._make_device_id(parsed)
    assert device_id == "tpms:1a2b3c4d"


def test_make_device_id_generic(sdr_scanner):
    """Generic (non-TPMS) device_id format: 'subghz:<model>:<id>'."""
    parsed = {"model": "Acurite-Tower", "id": "12345"}
    device_id = sdr_scanner._make_device_id(parsed)
    assert device_id == "subghz:Acurite-Tower:12345"


# ---------------------------------------------------------------------------
# 10-12: Mobility classification
# ---------------------------------------------------------------------------

def test_classify_mobility_tpms(sdr_scanner):
    """TPMS model returns mobile (False = mobile)."""
    result = sdr_scanner._classify_mobility("Toyota")
    assert result is False  # mobile


def test_classify_mobility_weather(sdr_scanner):
    """Weather station model returns stationary (True = stationary)."""
    result = sdr_scanner._classify_mobility("Acurite-Tower")
    assert result is True  # stationary


def test_classify_mobility_unknown(sdr_scanner):
    """Unknown model returns None."""
    result = sdr_scanner._classify_mobility("SomeRandom-Device-9000")
    assert result is None


# ---------------------------------------------------------------------------
# 13-15: Scan loop integration tests
# ---------------------------------------------------------------------------

@patch("subprocess.Popen")
def test_scan_loop_emits_appearances(mock_popen, sdr_scanner):
    """Mock Popen stdout with JSON lines, verify DeviceAppearance objects emitted."""
    lines = [TPMS_LINE, WEATHER_LINE, SECURITY_LINE]
    proc = _make_stdout_mock(lines)
    # After reading all lines, poll returns 0 (process finished)
    proc.poll.side_effect = [None, None, None, 0]
    mock_popen.return_value = proc

    # Don't set stop_event — BytesIO exhausts after 3 lines, ending the for-loop naturally.
    # The _scan_loop will then exit because process stdout is consumed.
    sdr_scanner._scan_loop()

    q = sdr_scanner._output_queue
    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    assert len(appearances) == 3

    # Verify first appearance (TPMS)
    a0 = appearances[0]
    assert isinstance(a0, DeviceAppearance)
    assert a0.device_id == "tpms:1a2b3c4d"
    assert a0.source_type == SourceType.SUBGHZ
    assert a0.location_id == "test-loc-01"
    assert a0.is_stationary is False  # TPMS = mobile

    # Verify second appearance (weather)
    a1 = appearances[1]
    assert a1.device_id == "subghz:Acurite-Tower:12345"
    assert a1.is_stationary is True  # weather station = stationary

    # Verify third appearance (security)
    a2 = appearances[2]
    assert a2.device_id == "subghz:Honeywell-Security:abc123"


@patch("subprocess.Popen")
def test_scan_loop_rtl433_not_found(mock_popen, sdr_scanner):
    """rtl_433 binary not found — scanner handles FileNotFoundError gracefully."""
    mock_popen.side_effect = FileNotFoundError(
        "[Errno 2] No such file or directory: 'rtl_433'"
    )
    sdr_scanner._stop_event.set()

    # Should NOT raise — scanner handles it internally (logs error, returns/retries)
    sdr_scanner._scan_loop()

    # Queue should be empty — nothing emitted
    assert sdr_scanner._output_queue.empty()


@patch("subprocess.Popen")
def test_scan_loop_subprocess_crash(mock_popen, sdr_scanner):
    """rtl_433 process dies mid-run — scanner logs error and handles gracefully."""
    # First line reads fine, then the process crashes (stdout raises)
    proc = MagicMock()
    proc.pid = 99999

    # Simulate: one good line, then OSError on next read
    good_line = TPMS_LINE.encode("utf-8") + b"\n"
    proc.stdout = MagicMock()
    proc.stdout.__iter__ = MagicMock(
        side_effect=OSError("rtl_433 process died unexpectedly")
    )
    proc.poll.return_value = -9  # killed
    proc.returncode = -9
    mock_popen.return_value = proc

    sdr_scanner._stop_event.set()

    # Should NOT raise — scanner catches the error internally
    sdr_scanner._scan_loop()

    # Scanner should have handled the crash gracefully
    # (may or may not have emitted partial results depending on implementation)
