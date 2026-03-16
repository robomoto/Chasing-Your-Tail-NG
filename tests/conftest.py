"""Shared fixtures for CYT-NG test suite."""
import json
import os
import sqlite3
import sys
import time
import pytest
from io import StringIO
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set test mode before any CYT imports to avoid interactive password prompts
os.environ["CYT_TEST_MODE"] = "true"


@pytest.fixture
def sample_config():
    """Minimal valid CYT config."""
    return {
        "paths": {
            "base_dir": ".",
            "log_dir": "/tmp/cyt_test_logs",
            "kismet_logs": "/tmp/test_kismet/*.kismet",
            "ignore_lists": {"mac": "mac_list.json", "ssid": "ssid_list.json"},
        },
        "timing": {
            "check_interval": 60,
            "list_update_interval": 5,
            "time_windows": {"recent": 5, "medium": 10, "old": 15, "oldest": 20},
        },
        "search": {
            "lat_min": 31.3,
            "lat_max": 37.0,
            "lon_min": -114.8,
            "lon_max": -109.0,
        },
    }


def make_device_json(ssid):
    """Build a Kismet device JSON blob with a probe request SSID."""
    return json.dumps(
        {
            "dot11.device": {
                "dot11.device.last_probed_ssid_record": {
                    "dot11.probedssid.ssid": ssid
                }
            }
        }
    )


@pytest.fixture
def mock_kismet_db(tmp_path):
    """Create an empty temporary Kismet-schema SQLite database."""
    db_path = tmp_path / "test.kismet"
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
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def populated_kismet_db(mock_kismet_db):
    """Kismet DB with sample device rows."""
    conn = sqlite3.connect(mock_kismet_db)
    now = time.time()
    devices = [
        ("AA:BB:CC:DD:EE:01", "Wi-Fi AP", make_device_json("HomeNetwork"), now - 60),
        (
            "AA:BB:CC:DD:EE:02",
            "Wi-Fi Client",
            make_device_json("CoffeeShop"),
            now - 120,
        ),
        ("AA:BB:CC:DD:EE:03", "Wi-Fi Client", None, now - 180),
        ("AA:BB:CC:DD:EE:04", "Wi-Fi Client", "{invalid json", now - 240),
        (
            "AA:BB:CC:DD:EE:05",
            "Wi-Fi Client",
            make_device_json(""),
            now - 300,
        ),  # Empty SSID
    ]
    for mac, dtype, device_json, ts in devices:
        conn.execute(
            "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
            (mac, dtype, device_json, ts),
        )
    conn.commit()
    conn.close()
    return mock_kismet_db


@pytest.fixture
def log_file():
    """StringIO log file for SecureCYTMonitor."""
    return StringIO()


@pytest.fixture
def mac_list_json(tmp_path):
    """JSON file with valid MAC addresses."""
    p = tmp_path / "mac_list.json"
    p.write_text(json.dumps(["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]))
    return p


@pytest.fixture
def ssid_list_json(tmp_path):
    """JSON file with valid SSIDs."""
    p = tmp_path / "ssid_list.json"
    p.write_text(json.dumps(["HomeNetwork", "CoffeeShop"]))
    return p


@pytest.fixture
def mac_list_python(tmp_path):
    """Python-format MAC ignore list file."""
    p = tmp_path / "mac_list.py"
    p.write_text("ignore_list = ['AA:BB:CC:DD:EE:FF', '11:22:33:44:55:66']")
    return p
