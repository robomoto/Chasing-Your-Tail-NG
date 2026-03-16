"""TDD tests for scanners/adsb_scanner.py — ADS-B aircraft tracking via
dump1090/readsb HTTP JSON API.

All tests should FAIL until the ADSBScanner stub is replaced with the real
implementation.
"""
import time
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from scanners.base_scanner import DeviceAppearance, SourceType
from scanners.adsb_scanner import ADSBScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adsb_scanner(config: dict | None = None, location_id: str = "test-loc"):
    """Create an ADSBScanner with a fresh output queue."""
    if config is None:
        config = {}
    q = Queue()
    scanner = ADSBScanner(config=config, output_queue=q, location_id=location_id)
    return scanner, q


def _drain_queue(q: Queue) -> list[DeviceAppearance]:
    """Pull all items from a queue into a list."""
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def _make_dump1090_response(aircraft: list | None = None):
    """Build a fake dump1090 JSON response dict."""
    return {
        "now": 1700000000,
        "messages": 1234,
        "aircraft": aircraft or [],
    }


SAMPLE_AIRCRAFT = [
    {
        "hex": "A12345",
        "flight": "N12345",
        "lat": 33.45,
        "lon": -112.07,
        "alt_baro": 5000,
        "gs": 120,
        "track": 180,
        "squawk": "1200",
    },
    {
        "hex": "A67890",
        "lat": 33.46,
        "lon": -112.08,
        "alt_baro": 3000,
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def adsb_scanner():
    """Default ADSBScanner with empty config."""
    scanner, _ = _make_adsb_scanner()
    return scanner


@pytest.fixture
def suspicious_scanner():
    """ADSBScanner configured with suspicious ICAO registrations."""
    config = {
        "scanners": {
            "adsb": {
                "dump1090_url": "http://localhost:8080",
                "suspicious_registrations": ["FEDGOV1", "AE1234", "A00001"],
            }
        }
    }
    scanner, q = _make_adsb_scanner(config=config)
    return scanner, q


# ---------------------------------------------------------------------------
# 1. scanner_name == "adsb"
# ---------------------------------------------------------------------------

def test_adsb_scanner_name(adsb_scanner):
    assert adsb_scanner.scanner_name == "adsb"


# ---------------------------------------------------------------------------
# 2. source_type == SourceType.AIRCRAFT
# ---------------------------------------------------------------------------

def test_adsb_scanner_source_type(adsb_scanner):
    assert adsb_scanner.source_type == SourceType.AIRCRAFT


# ---------------------------------------------------------------------------
# 3. _poll_dump1090 — parses aircraft from HTTP JSON
# ---------------------------------------------------------------------------

def test_poll_dump1090_parses_aircraft(adsb_scanner):
    response_json = _make_dump1090_response(SAMPLE_AIRCRAFT)

    mock_response = MagicMock()
    mock_response.json.return_value = response_json
    mock_response.raise_for_status = MagicMock()

    with patch("scanners.adsb_scanner.requests.get", return_value=mock_response):
        result = adsb_scanner._poll_dump1090()

    assert isinstance(result, list)
    assert len(result) == 2
    # First aircraft should have all fields
    assert result[0]["hex"] == "A12345"
    assert result[0]["flight"] == "N12345"
    assert result[0]["lat"] == 33.45
    assert result[0]["lon"] == -112.07
    assert result[0]["alt_baro"] == 5000
    # Second aircraft — minimal fields
    assert result[1]["hex"] == "A67890"
    assert result[1]["alt_baro"] == 3000


# ---------------------------------------------------------------------------
# 4. _poll_dump1090 — empty/missing aircraft key returns empty list
# ---------------------------------------------------------------------------

def test_poll_dump1090_empty_response(adsb_scanner):
    # Response with no "aircraft" key
    mock_response = MagicMock()
    mock_response.json.return_value = {"now": 1700000000, "messages": 0}
    mock_response.raise_for_status = MagicMock()

    with patch("scanners.adsb_scanner.requests.get", return_value=mock_response):
        result = adsb_scanner._poll_dump1090()

    assert result == []


# ---------------------------------------------------------------------------
# 5. _poll_dump1090 — connection error returns empty list, no crash
# ---------------------------------------------------------------------------

def test_poll_dump1090_connection_error(adsb_scanner):
    with patch("scanners.adsb_scanner.requests.get", side_effect=ConnectionError("refused")):
        result = adsb_scanner._poll_dump1090()

    assert result == []


# ---------------------------------------------------------------------------
# 6. _check_suspicious_registration — normal ICAO not in list
# ---------------------------------------------------------------------------

def test_check_suspicious_normal():
    scanner, _ = _make_adsb_scanner(config={
        "scanners": {
            "adsb": {
                "suspicious_registrations": ["FEDGOV1", "AE1234"],
            }
        }
    })
    assert scanner._check_suspicious_registration("A12345") is False


# ---------------------------------------------------------------------------
# 7. _check_suspicious_registration — ICAO in suspicious list
# ---------------------------------------------------------------------------

def test_check_suspicious_match():
    scanner, _ = _make_adsb_scanner(config={
        "scanners": {
            "adsb": {
                "suspicious_registrations": ["FEDGOV1", "AE1234"],
            }
        }
    })
    assert scanner._check_suspicious_registration("FEDGOV1") is True


# ---------------------------------------------------------------------------
# 8. _scan_loop emits DeviceAppearance for each aircraft
# ---------------------------------------------------------------------------

def test_scan_loop_emits_appearances():
    config = {
        "scanners": {
            "adsb": {
                "dump1090_url": "http://localhost:8080",
                "suspicious_registrations": [],
            }
        }
    }
    scanner, q = _make_adsb_scanner(config=config, location_id="home-1")

    response_json = _make_dump1090_response(SAMPLE_AIRCRAFT)
    mock_response = MagicMock()
    mock_response.json.return_value = response_json
    mock_response.raise_for_status = MagicMock()

    with patch("scanners.adsb_scanner.requests.get", return_value=mock_response), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    appearances = _drain_queue(q)

    assert len(appearances) >= 2

    # Find the appearance for A12345
    a12345 = [a for a in appearances if a.device_id == "icao:A12345"]
    assert len(a12345) == 1
    da = a12345[0]
    assert da.source_type == SourceType.AIRCRAFT
    assert da.location_id == "home-1"
    assert da.metadata["lat"] == 33.45
    assert da.metadata["lon"] == -112.07
    assert da.metadata["alt_baro"] == 5000
    assert da.metadata["flight"] == "N12345"

    # Find the appearance for A67890
    a67890 = [a for a in appearances if a.device_id == "icao:A67890"]
    assert len(a67890) == 1


# ---------------------------------------------------------------------------
# 9. _scan_loop flags suspicious aircraft in metadata
# ---------------------------------------------------------------------------

def test_scan_loop_flags_suspicious():
    config = {
        "scanners": {
            "adsb": {
                "dump1090_url": "http://localhost:8080",
                "suspicious_registrations": ["A12345"],
            }
        }
    }
    scanner, q = _make_adsb_scanner(config=config, location_id="home-1")

    response_json = _make_dump1090_response(SAMPLE_AIRCRAFT)
    mock_response = MagicMock()
    mock_response.json.return_value = response_json
    mock_response.raise_for_status = MagicMock()

    with patch("scanners.adsb_scanner.requests.get", return_value=mock_response), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    appearances = _drain_queue(q)

    # A12345 is suspicious
    a12345 = [a for a in appearances if a.device_id == "icao:A12345"]
    assert len(a12345) == 1
    assert a12345[0].metadata["suspicious"] is True

    # A67890 is NOT suspicious
    a67890 = [a for a in appearances if a.device_id == "icao:A67890"]
    assert len(a67890) == 1
    assert a67890[0].metadata.get("suspicious", False) is False


# ---------------------------------------------------------------------------
# 10. _scan_loop handles HTTP failure gracefully, scanner continues
# ---------------------------------------------------------------------------

def test_scan_loop_http_failure():
    config = {
        "scanners": {
            "adsb": {
                "dump1090_url": "http://localhost:8080",
                "suspicious_registrations": [],
            }
        }
    }
    scanner, q = _make_adsb_scanner(config=config, location_id="home-1")

    # First call raises, second call succeeds, then stop
    response_json = _make_dump1090_response(SAMPLE_AIRCRAFT)
    mock_response = MagicMock()
    mock_response.json.return_value = response_json
    mock_response.raise_for_status = MagicMock()

    with patch("scanners.adsb_scanner.requests.get",
               side_effect=[ConnectionError("refused"), mock_response]), \
         patch.object(scanner._stop_event, "is_set",
                      side_effect=[False, False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    # Should still have gotten aircraft from the second successful call
    appearances = _drain_queue(q)
    assert len(appearances) >= 2
