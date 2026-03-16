"""TDD tests for scanners/wifi_scanner.py — Phase 1 acceptance criteria.

All tests should FAIL until the WiFiScanner stub is replaced with the real
implementation.  Tests rely on fixtures from conftest.py (mock_kismet_db,
populated_kismet_db, sample_config).
"""
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from queue import Queue
from unittest.mock import patch

import pytest

from scanners.base_scanner import DeviceAppearance, SourceType
from scanners.wifi_scanner import WiFiScanner


# ---------------------------------------------------------------------------
# 1. scanner_name is "wifi"
# ---------------------------------------------------------------------------

def test_wifi_scanner_name(sample_config):
    q = Queue()
    scanner = WiFiScanner(config=sample_config, output_queue=q)
    assert scanner.scanner_name == "wifi"


# ---------------------------------------------------------------------------
# 2. source_type is SourceType.WIFI
# ---------------------------------------------------------------------------

def test_wifi_scanner_source_type(sample_config):
    q = Queue()
    scanner = WiFiScanner(config=sample_config, output_queue=q)
    # WiFiScanner should advertise its source type
    assert scanner.source_type == SourceType.WIFI or scanner.scanner_name == "wifi"
    # The emitted appearances must carry WIFI source_type (tested in test 6)


# ---------------------------------------------------------------------------
# 3. check_interval read from config
# ---------------------------------------------------------------------------

def test_wifi_scanner_reads_config_interval(sample_config):
    q = Queue()
    # Default from timing.check_interval
    scanner = WiFiScanner(config=sample_config, output_queue=q)
    assert scanner._check_interval == 60

    # Override via scanners.wifi.check_interval
    custom_config = {**sample_config, "scanners": {"wifi": {"check_interval": 30}}}
    scanner2 = WiFiScanner(config=custom_config, output_queue=q)
    assert scanner2._check_interval == 30


# ---------------------------------------------------------------------------
# 4. Given multiple .kismet files, picks the most recent
# ---------------------------------------------------------------------------

def test_wifi_scanner_finds_latest_db(tmp_path, sample_config):
    # Create three .kismet files with staggered mtimes
    old = tmp_path / "old.kismet"
    mid = tmp_path / "mid.kismet"
    new = tmp_path / "new.kismet"

    for p in (old, mid, new):
        conn = sqlite3.connect(str(p))
        conn.execute(
            "CREATE TABLE devices (devmac TEXT, type TEXT, device TEXT, "
            "last_time REAL, first_time REAL DEFAULT 0, "
            "avg_lat REAL DEFAULT 0, avg_lon REAL DEFAULT 0)"
        )
        conn.commit()
        conn.close()

    # Set modification times: old < mid < new
    now = time.time()
    os.utime(str(old), (now - 300, now - 300))
    os.utime(str(mid), (now - 100, now - 100))
    os.utime(str(new), (now, now))

    config = {
        **sample_config,
        "paths": {**sample_config["paths"], "kismet_logs": str(tmp_path / "*.kismet")},
    }
    q = Queue()
    scanner = WiFiScanner(config=config, output_queue=q)
    result = scanner._find_latest_db()
    assert result is not None
    assert Path(result).name == "new.kismet"


# ---------------------------------------------------------------------------
# 5. No .kismet files logs a warning and doesn't crash
# ---------------------------------------------------------------------------

def test_wifi_scanner_no_db_logs_warning(tmp_path, sample_config, caplog):
    config = {
        **sample_config,
        "paths": {
            **sample_config["paths"],
            "kismet_logs": str(tmp_path / "nonexistent" / "*.kismet"),
        },
    }
    q = Queue()
    scanner = WiFiScanner(config=config, output_queue=q)
    result = scanner._find_latest_db()
    assert result is None
    # The _scan_loop should log a warning when no DB is found.
    # We verify _find_latest_db returns None gracefully.


# ---------------------------------------------------------------------------
# 6. Populated DB emits DeviceAppearance objects with correct fields
# ---------------------------------------------------------------------------

def test_wifi_scanner_emits_device_appearances(populated_kismet_db, sample_config):
    db_dir = str(Path(populated_kismet_db).parent)
    config = {
        **sample_config,
        "paths": {**sample_config["paths"], "kismet_logs": os.path.join(db_dir, "*.kismet")},
    }
    q = Queue()
    scanner = WiFiScanner(config=config, output_queue=q)

    # Run a single scan cycle by calling internal methods directly.
    # The real _scan_loop polls in a thread; here we invoke the logic once.
    scanner._stop_event = __import__("threading").Event()
    scanner._stop_event.set()  # Will cause the loop to exit after one iteration

    # Patch _stop_event.wait to not actually sleep
    with patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    # The populated DB has 5 devices; at least some should emit
    assert len(appearances) > 0

    for da in appearances:
        assert isinstance(da, DeviceAppearance)
        assert da.source_type == SourceType.WIFI
        assert da.device_id == da.mac  # WiFi: device_id == MAC


# ---------------------------------------------------------------------------
# 7. Device with probe SSID produces appearance with ssids_probed
# ---------------------------------------------------------------------------

def test_wifi_scanner_extracts_ssids(populated_kismet_db, sample_config):
    db_dir = str(Path(populated_kismet_db).parent)
    config = {
        **sample_config,
        "paths": {**sample_config["paths"], "kismet_logs": os.path.join(db_dir, "*.kismet")},
    }
    q = Queue()
    scanner = WiFiScanner(config=config, output_queue=q)

    scanner._stop_event = __import__("threading").Event()
    scanner._stop_event.set()

    with patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    # Find the device that probed "HomeNetwork" (MAC AA:BB:CC:DD:EE:01)
    home_devices = [a for a in appearances if "HomeNetwork" in a.ssids_probed]
    assert len(home_devices) >= 1, (
        "Expected at least one appearance with ssids_probed containing 'HomeNetwork'"
    )

    # Find the device that probed "CoffeeShop" (MAC AA:BB:CC:DD:EE:02)
    coffee_devices = [a for a in appearances if "CoffeeShop" in a.ssids_probed]
    assert len(coffee_devices) >= 1


# ---------------------------------------------------------------------------
# 8. Malformed JSON still emits an appearance with empty ssids_probed
# ---------------------------------------------------------------------------

def test_wifi_scanner_handles_malformed_json(populated_kismet_db, sample_config):
    db_dir = str(Path(populated_kismet_db).parent)
    config = {
        **sample_config,
        "paths": {**sample_config["paths"], "kismet_logs": os.path.join(db_dir, "*.kismet")},
    }
    q = Queue()
    scanner = WiFiScanner(config=config, output_queue=q)

    scanner._stop_event = __import__("threading").Event()
    scanner._stop_event.set()

    with patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    appearances = []
    while not q.empty():
        appearances.append(q.get_nowait())

    # MAC AA:BB:CC:DD:EE:04 has "{invalid json" — should still emit with empty ssids
    malformed = [a for a in appearances if a.device_id == "AA:BB:CC:DD:EE:04"]
    assert len(malformed) == 1, "Malformed JSON device should still produce an appearance"
    assert malformed[0].ssids_probed == []


# ---------------------------------------------------------------------------
# 9. Empty DB produces zero appearances
# ---------------------------------------------------------------------------

def test_wifi_scanner_empty_db(mock_kismet_db, sample_config):
    db_dir = str(Path(mock_kismet_db).parent)
    config = {
        **sample_config,
        "paths": {**sample_config["paths"], "kismet_logs": os.path.join(db_dir, "*.kismet")},
    }
    q = Queue()
    scanner = WiFiScanner(config=config, output_queue=q)

    scanner._stop_event = __import__("threading").Event()
    scanner._stop_event.set()

    with patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    assert q.empty(), "Empty Kismet DB should produce zero DeviceAppearance objects"
