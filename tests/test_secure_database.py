"""Tests for secure_database.py module."""
import json
import sqlite3
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from secure_database import SecureKismetDB, SecureTimeWindows, create_secure_db_connection


# ---------------------------------------------------------------------------
# SecureKismetDB – construction & lifecycle
# ---------------------------------------------------------------------------

class TestSecureKismetDBLifecycle:
    """Connection lifecycle, context manager, and close semantics."""

    def test_init_stores_path(self, mock_kismet_db):
        db = SecureKismetDB(mock_kismet_db)
        assert db.db_path == mock_kismet_db
        assert db._connection is None

    def test_connect_creates_connection(self, mock_kismet_db):
        db = SecureKismetDB(mock_kismet_db)
        db.connect()
        assert db._connection is not None
        db.close()

    def test_close_sets_connection_none(self, mock_kismet_db):
        db = SecureKismetDB(mock_kismet_db)
        db.connect()
        db.close()
        assert db._connection is None

    def test_close_idempotent_when_not_connected(self, mock_kismet_db):
        """Closing without a connection should not raise."""
        db = SecureKismetDB(mock_kismet_db)
        db.close()  # no-op

    def test_context_manager_connects_and_closes(self, mock_kismet_db):
        with SecureKismetDB(mock_kismet_db) as db:
            assert db._connection is not None
        assert db._connection is None

    def test_context_manager_closes_on_exception(self, mock_kismet_db):
        with pytest.raises(ZeroDivisionError):
            with SecureKismetDB(mock_kismet_db) as db:
                1 / 0
        assert db._connection is None

    def test_connect_invalid_path_raises(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent_dir" / "db.kismet")
        db = SecureKismetDB(bad_path)
        # sqlite3 may or may not raise on connect for bad dirs – but the
        # file won't be usable. On most systems connect creates the file,
        # so we just confirm it doesn't crash for a writable tmp dir.
        # Instead test with truly invalid path:
        db2 = SecureKismetDB("/dev/null/impossible/path.db")
        with pytest.raises(sqlite3.Error):
            db2.connect()


# ---------------------------------------------------------------------------
# SecureKismetDB – execute_safe_query
# ---------------------------------------------------------------------------

class TestExecuteSafeQuery:
    """Parameterized query execution."""

    def test_execute_before_connect_raises_runtime_error(self, mock_kismet_db):
        db = SecureKismetDB(mock_kismet_db)
        with pytest.raises(RuntimeError, match="Database not connected"):
            db.execute_safe_query("SELECT 1")

    def test_simple_select(self, mock_kismet_db):
        with SecureKismetDB(mock_kismet_db) as db:
            rows = db.execute_safe_query("SELECT COUNT(*) AS count FROM devices")
            assert rows[0]["count"] == 0

    def test_parameterized_insert_and_select(self, mock_kismet_db):
        with SecureKismetDB(mock_kismet_db) as db:
            db._connection.execute(
                "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
                ("AA:BB:CC:DD:EE:FF", "Wi-Fi AP", None, 1000.0),
            )
            db._connection.commit()
            rows = db.execute_safe_query(
                "SELECT devmac FROM devices WHERE last_time >= ?", (999.0,)
            )
            assert len(rows) == 1
            assert rows[0]["devmac"] == "AA:BB:CC:DD:EE:FF"

    def test_bad_sql_raises_sqlite_error(self, mock_kismet_db):
        with SecureKismetDB(mock_kismet_db) as db:
            with pytest.raises(sqlite3.Error):
                db.execute_safe_query("SELECT * FROM nonexistent_table")


# ---------------------------------------------------------------------------
# SecureKismetDB – get_devices_by_time_range
# ---------------------------------------------------------------------------

class TestGetDevicesByTimeRange:
    """Time-range device queries including JSON parsing edge cases."""

    def test_returns_all_devices_when_start_is_zero(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            devices = db.get_devices_by_time_range(0)
            assert len(devices) == 5

    def test_time_range_filters_correctly(self, populated_kismet_db):
        now = time.time()
        with SecureKismetDB(populated_kismet_db) as db:
            # Only devices within last 90 seconds
            devices = db.get_devices_by_time_range(now - 90)
            assert len(devices) == 1
            assert devices[0]["mac"] == "AA:BB:CC:DD:EE:01"

    def test_time_range_with_end_time(self, populated_kismet_db):
        now = time.time()
        with SecureKismetDB(populated_kismet_db) as db:
            # Devices between 150s and 250s ago
            devices = db.get_devices_by_time_range(now - 250, now - 150)
            assert len(devices) == 2
            macs = {d["mac"] for d in devices}
            assert "AA:BB:CC:DD:EE:03" in macs
            assert "AA:BB:CC:DD:EE:04" in macs

    def test_start_after_end_returns_empty(self, populated_kismet_db):
        now = time.time()
        with SecureKismetDB(populated_kismet_db) as db:
            devices = db.get_devices_by_time_range(now, now - 1000)
            assert devices == []

    def test_empty_db_returns_empty(self, mock_kismet_db):
        with SecureKismetDB(mock_kismet_db) as db:
            devices = db.get_devices_by_time_range(0)
            assert devices == []

    def test_valid_json_parsed(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            devices = db.get_devices_by_time_range(0)
            dev01 = next(d for d in devices if d["mac"] == "AA:BB:CC:DD:EE:01")
            assert isinstance(dev01["device_data"], dict)
            assert "dot11.device" in dev01["device_data"]

    def test_malformed_json_yields_none(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            devices = db.get_devices_by_time_range(0)
            dev04 = next(d for d in devices if d["mac"] == "AA:BB:CC:DD:EE:04")
            assert dev04["device_data"] is None

    def test_null_device_field_yields_none(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            devices = db.get_devices_by_time_range(0)
            dev03 = next(d for d in devices if d["mac"] == "AA:BB:CC:DD:EE:03")
            assert dev03["device_data"] is None

    def test_null_devmac_row(self, mock_kismet_db):
        """Row with NULL devmac is still returned (mac will be None)."""
        conn = sqlite3.connect(mock_kismet_db)
        conn.execute(
            "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
            (None, "Wi-Fi AP", None, time.time()),
        )
        conn.commit()
        conn.close()
        with SecureKismetDB(mock_kismet_db) as db:
            devices = db.get_devices_by_time_range(0)
            assert len(devices) == 1
            assert devices[0]["mac"] is None


# ---------------------------------------------------------------------------
# SecureKismetDB – get_mac_addresses_by_time_range
# ---------------------------------------------------------------------------

class TestGetMacAddressesByTimeRange:

    def test_returns_mac_strings(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            macs = db.get_mac_addresses_by_time_range(0)
            assert all(isinstance(m, str) for m in macs)
            assert len(macs) == 5

    def test_excludes_none_macs(self, mock_kismet_db):
        conn = sqlite3.connect(mock_kismet_db)
        conn.execute(
            "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
            (None, "Wi-Fi AP", None, time.time()),
        )
        conn.execute(
            "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
            ("AA:BB:CC:DD:EE:FF", "Wi-Fi AP", None, time.time()),
        )
        conn.commit()
        conn.close()
        with SecureKismetDB(mock_kismet_db) as db:
            macs = db.get_mac_addresses_by_time_range(0)
            assert macs == ["AA:BB:CC:DD:EE:FF"]


# ---------------------------------------------------------------------------
# SecureKismetDB – get_probe_requests_by_time_range
# ---------------------------------------------------------------------------

class TestGetProbeRequestsByTimeRange:

    def test_extracts_valid_probes(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            probes = db.get_probe_requests_by_time_range(0)
            ssids = {p["ssid"] for p in probes}
            assert "HomeNetwork" in ssids
            assert "CoffeeShop" in ssids

    def test_skips_empty_ssid(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            probes = db.get_probe_requests_by_time_range(0)
            # Device 05 has empty SSID – should be excluded
            assert all(p["ssid"] != "" for p in probes)

    def test_skips_null_device_data(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            probes = db.get_probe_requests_by_time_range(0)
            probe_macs = {p["mac"] for p in probes}
            assert "AA:BB:CC:DD:EE:03" not in probe_macs  # NULL device

    def test_handles_non_dict_dot11_device(self, mock_kismet_db):
        """If dot11.device is a string instead of dict, skip gracefully."""
        bad_json = json.dumps({"dot11.device": "not a dict"})
        conn = sqlite3.connect(mock_kismet_db)
        conn.execute(
            "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
            ("FF:FF:FF:FF:FF:FF", "Wi-Fi Client", bad_json, time.time()),
        )
        conn.commit()
        conn.close()
        with SecureKismetDB(mock_kismet_db) as db:
            probes = db.get_probe_requests_by_time_range(0)
            assert probes == []


# ---------------------------------------------------------------------------
# SecureKismetDB – validate_connection
# ---------------------------------------------------------------------------

class TestValidateConnection:

    def test_validates_good_db(self, populated_kismet_db):
        with SecureKismetDB(populated_kismet_db) as db:
            assert db.validate_connection() is True

    def test_validates_empty_db(self, mock_kismet_db):
        with SecureKismetDB(mock_kismet_db) as db:
            assert db.validate_connection() is True


# ---------------------------------------------------------------------------
# create_secure_db_connection factory
# ---------------------------------------------------------------------------

class TestFactoryFunction:

    def test_returns_secure_kismet_db_instance(self, mock_kismet_db):
        db = create_secure_db_connection(mock_kismet_db)
        assert isinstance(db, SecureKismetDB)
        assert db.db_path == mock_kismet_db


# ---------------------------------------------------------------------------
# SecureTimeWindows – get_time_boundaries
# ---------------------------------------------------------------------------

class TestGetTimeBoundaries:

    def test_contains_expected_keys(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        boundaries = stw.get_time_boundaries()
        assert "recent_time" in boundaries
        assert "medium_time" in boundaries
        assert "old_time" in boundaries
        assert "oldest_time" in boundaries
        assert "current_time" in boundaries

    def test_boundaries_decrease_with_larger_windows(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        b = stw.get_time_boundaries()
        assert b["recent_time"] > b["medium_time"]
        assert b["medium_time"] > b["old_time"]
        assert b["old_time"] > b["oldest_time"]

    @patch("secure_database.datetime")
    @patch("secure_database.time")
    def test_deterministic_boundaries(self, mock_time_mod, mock_dt, sample_config):
        """Pin datetime.now() to get deterministic results."""
        fixed_now = datetime(2025, 1, 15, 12, 0, 0)
        mock_dt.now.return_value = fixed_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # timedelta must still work
        mock_time_mod.mktime = time.mktime

        stw = SecureTimeWindows(sample_config)
        b = stw.get_time_boundaries()

        expected_recent = time.mktime((fixed_now - timedelta(minutes=5)).timetuple())
        expected_current = time.mktime((fixed_now - timedelta(minutes=2)).timetuple())
        assert b["recent_time"] == expected_recent
        assert b["current_time"] == expected_current

    def test_default_windows_when_config_missing(self):
        stw = SecureTimeWindows({})
        b = stw.get_time_boundaries()
        # Should use defaults: recent=5, medium=10, old=15, oldest=20
        assert "recent_time" in b
        assert "oldest_time" in b


# ---------------------------------------------------------------------------
# SecureTimeWindows – filter_devices_by_ignore_list
# ---------------------------------------------------------------------------

class TestFilterDevicesByIgnoreList:

    def test_filters_matching_macs(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        devices = ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:03"]
        ignore = ["AA:BB:CC:DD:EE:02"]
        result = stw.filter_devices_by_ignore_list(devices, ignore)
        assert result == ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:03"]

    def test_case_insensitive_filtering(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        devices = ["aa:bb:cc:dd:ee:01"]
        ignore = ["AA:BB:CC:DD:EE:01"]
        result = stw.filter_devices_by_ignore_list(devices, ignore)
        assert result == []

    def test_empty_ignore_list_returns_all(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        devices = ["AA:BB:CC:DD:EE:01"]
        result = stw.filter_devices_by_ignore_list(devices, [])
        assert result == devices

    def test_non_string_devices_excluded(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        devices = ["AA:BB:CC:DD:EE:01", None, 42]
        ignore = ["XX:XX:XX:XX:XX:XX"]
        result = stw.filter_devices_by_ignore_list(devices, ignore)
        assert result == ["AA:BB:CC:DD:EE:01"]

    def test_empty_devices_list(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        result = stw.filter_devices_by_ignore_list([], ["AA:BB:CC:DD:EE:01"])
        assert result == []


# ---------------------------------------------------------------------------
# SecureTimeWindows – filter_ssids_by_ignore_list
# ---------------------------------------------------------------------------

class TestFilterSsidsByIgnoreList:

    def test_filters_matching_ssids(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        ssids = ["HomeNetwork", "CoffeeShop", "Airport"]
        ignore = ["HomeNetwork", "CoffeeShop"]
        result = stw.filter_ssids_by_ignore_list(ssids, ignore)
        assert result == ["Airport"]

    def test_ssid_filter_is_case_sensitive(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        ssids = ["homenetwork"]
        ignore = ["HomeNetwork"]
        result = stw.filter_ssids_by_ignore_list(ssids, ignore)
        assert result == ["homenetwork"]

    def test_empty_ignore_returns_all(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        ssids = ["MySSID"]
        result = stw.filter_ssids_by_ignore_list(ssids, [])
        assert result == ssids

    def test_non_string_ssids_excluded(self, sample_config):
        stw = SecureTimeWindows(sample_config)
        ssids = ["Valid", None, 123]
        ignore = ["Other"]
        result = stw.filter_ssids_by_ignore_list(ssids, ignore)
        assert result == ["Valid"]
