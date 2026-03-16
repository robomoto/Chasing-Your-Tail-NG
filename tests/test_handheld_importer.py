"""TDD tests for HandheldImporter — Phase 7: ESP32 handheld session CSV import."""
import pytest

from scanners.base_scanner import DeviceAppearance, SourceType
from scanners.handheld_importer import HandheldImporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_HEADER = "# session_id=sess-001,fw_ver=1.0.0,start=1700000000,end=1700003600,device_count=3"
CSV_COLUMNS = "timestamp,mac,device_id,source_type,rssi,lat,lon,ssid,window_flags,appearance_count"

ROWS = [
    "1700000060,AA:BB:CC:DD:EE:01,AA:BB:CC:DD:EE:01,wifi,-45,33.4500,-112.0700,HomeNetwork,1,5",
    "1700000120,AA:BB:CC:DD:EE:02,AA:BB:CC:DD:EE:02,wifi,-60,33.4500,-112.0700,CoffeeShop,3,10",
    "1700000180,,findmy:abc123,ble,-70,33.4510,-112.0710,,0,2",
]


def _write_csv(tmp_path, *, include_header=True, rows=None):
    """Write a handheld session CSV and return the path."""
    if rows is None:
        rows = ROWS
    lines = []
    if include_header:
        lines.append(SESSION_HEADER)
    lines.append(CSV_COLUMNS)
    lines.extend(rows)
    path = tmp_path / "session.csv"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def _make_importer(config=None):
    cfg = config or {"handheld": {"import_dir": "/tmp/handheld_sessions"}}
    return HandheldImporter(config=cfg)


# ---------------------------------------------------------------------------
# 1. Basic import — 3 rows → 3 DeviceAppearance objects
# ---------------------------------------------------------------------------

def test_import_session_basic(tmp_path):
    importer = _make_importer()
    csv_path = _write_csv(tmp_path)

    appearances = importer.import_session(csv_path)

    assert len(appearances) == 3
    assert all(isinstance(a, DeviceAppearance) for a in appearances)


# ---------------------------------------------------------------------------
# 2. Empty file — header only → empty list
# ---------------------------------------------------------------------------

def test_import_session_empty_file(tmp_path):
    importer = _make_importer()
    csv_path = _write_csv(tmp_path, rows=[])

    appearances = importer.import_session(csv_path)

    assert appearances == []


# ---------------------------------------------------------------------------
# 3. Missing file → empty list, no crash
# ---------------------------------------------------------------------------

def test_import_session_missing_file(tmp_path):
    importer = _make_importer()
    missing_path = str(tmp_path / "does_not_exist.csv")

    appearances = importer.import_session(missing_path)

    assert appearances == []


# ---------------------------------------------------------------------------
# 4. Parse wifi row — correct fields
# ---------------------------------------------------------------------------

def test_parse_csv_row_wifi(tmp_path):
    importer = _make_importer()

    row = {
        "timestamp": "1700000060",
        "mac": "AA:BB:CC:DD:EE:01",
        "device_id": "AA:BB:CC:DD:EE:01",
        "source_type": "wifi",
        "rssi": "-45",
        "lat": "33.4500",
        "lon": "-112.0700",
        "ssid": "HomeNetwork",
        "window_flags": "1",
        "appearance_count": "5",
    }

    appearance = importer.parse_csv_row(row)

    assert appearance is not None
    assert appearance.device_id == "AA:BB:CC:DD:EE:01"
    assert appearance.mac == "AA:BB:CC:DD:EE:01"
    assert appearance.source_type is SourceType.HANDHELD_IMPORT
    assert appearance.signal_strength == -45.0
    assert appearance.timestamp == 1700000060.0
    assert "HomeNetwork" in appearance.ssids_probed
    assert appearance.metadata["lat"] == pytest.approx(33.45)
    assert appearance.metadata["lon"] == pytest.approx(-112.07)


# ---------------------------------------------------------------------------
# 5. Parse BLE row — empty mac → mac=None
# ---------------------------------------------------------------------------

def test_parse_csv_row_ble(tmp_path):
    importer = _make_importer()

    row = {
        "timestamp": "1700000180",
        "mac": "",
        "device_id": "findmy:abc123",
        "source_type": "ble",
        "rssi": "-70",
        "lat": "33.4510",
        "lon": "-112.0710",
        "ssid": "",
        "window_flags": "0",
        "appearance_count": "2",
    }

    appearance = importer.parse_csv_row(row)

    assert appearance is not None
    assert appearance.mac is None
    assert appearance.device_id == "findmy:abc123"
    assert appearance.source_type is SourceType.HANDHELD_IMPORT


# ---------------------------------------------------------------------------
# 6. Parse invalid row — missing required fields → None
# ---------------------------------------------------------------------------

def test_parse_csv_row_invalid():
    importer = _make_importer()

    # Missing device_id and timestamp
    row = {
        "mac": "AA:BB:CC:DD:EE:01",
        "rssi": "-45",
    }

    result = importer.parse_csv_row(row)
    assert result is None


# ---------------------------------------------------------------------------
# 7. get_session_metadata — parses comment header
# ---------------------------------------------------------------------------

def test_get_session_metadata(tmp_path):
    importer = _make_importer()
    csv_path = _write_csv(tmp_path)

    metadata = importer.get_session_metadata(csv_path)

    assert metadata is not None
    assert metadata["session_id"] == "sess-001"
    assert metadata["fw_ver"] == "1.0.0"
    assert metadata["start"] == "1700000000"
    assert metadata["end"] == "1700003600"
    assert metadata["device_count"] == "3"


# ---------------------------------------------------------------------------
# 8. get_session_metadata — no header comment → None
# ---------------------------------------------------------------------------

def test_get_session_metadata_no_header(tmp_path):
    importer = _make_importer()
    csv_path = _write_csv(tmp_path, include_header=False)

    metadata = importer.get_session_metadata(csv_path)

    assert metadata is None


# ---------------------------------------------------------------------------
# 9. All appearances have source_type = HANDHELD_IMPORT
# ---------------------------------------------------------------------------

def test_imported_appearances_have_correct_source_type(tmp_path):
    importer = _make_importer()
    csv_path = _write_csv(tmp_path)

    appearances = importer.import_session(csv_path)

    assert len(appearances) > 0
    for a in appearances:
        assert a.source_type is SourceType.HANDHELD_IMPORT


# ---------------------------------------------------------------------------
# 10. Location data preserved in metadata
# ---------------------------------------------------------------------------

def test_imported_appearances_preserve_location(tmp_path):
    importer = _make_importer()
    csv_path = _write_csv(tmp_path)

    appearances = importer.import_session(csv_path)

    # First row: lat=33.4500, lon=-112.0700
    first = appearances[0]
    assert "lat" in first.metadata
    assert "lon" in first.metadata
    assert first.metadata["lat"] == pytest.approx(33.45)
    assert first.metadata["lon"] == pytest.approx(-112.07)

    # Third row (BLE): lat=33.4510, lon=-112.0710
    third = appearances[2]
    assert third.metadata["lat"] == pytest.approx(33.451)
    assert third.metadata["lon"] == pytest.approx(-112.071)
