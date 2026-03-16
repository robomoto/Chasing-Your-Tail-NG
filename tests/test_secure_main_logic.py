"""Tests for SecureCYTMonitor in secure_main_logic.py."""

import json
import sqlite3
import time

import pytest
from io import StringIO

from secure_main_logic import SecureCYTMonitor
from secure_database import SecureKismetDB


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_device(db_path, mac, device_json, last_time, dtype="Wi-Fi Client"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)",
        (mac, dtype, device_json, last_time),
    )
    conn.commit()
    conn.close()


def _make_monitor(sample_config, log_file, ignore_macs=None, ignore_ssids=None):
    return SecureCYTMonitor(
        config=sample_config,
        ignore_list=ignore_macs or [],
        ssid_ignore_list=ignore_ssids or [],
        log_file=log_file,
    )


# ===================================================================
# 1. __init__ – ignore list normalisation
# ===================================================================

class TestInit:
    def test_ignore_list_uppercased(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file, ignore_macs=["aa:bb:cc:dd:ee:ff"])
        assert "AA:BB:CC:DD:EE:FF" in mon.ignore_list

    def test_ignore_list_stored_as_set(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file, ignore_macs=["AA:BB:CC:DD:EE:FF"])
        assert isinstance(mon.ignore_list, set)

    def test_ssid_ignore_stored_as_set(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file, ignore_ssids=["Home"])
        assert isinstance(mon.ssid_ignore_list, set)

    def test_empty_ignore_lists(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        assert len(mon.ignore_list) == 0
        assert len(mon.ssid_ignore_list) == 0

    def test_tracking_lists_start_empty(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        for attr in (
            "past_five_mins_macs", "five_ten_min_ago_macs",
            "ten_fifteen_min_ago_macs", "fifteen_twenty_min_ago_macs",
            "past_five_mins_ssids", "five_ten_min_ago_ssids",
            "ten_fifteen_min_ago_ssids", "fifteen_twenty_min_ago_ssids",
        ):
            assert len(getattr(mon, attr)) == 0


# ===================================================================
# 2. _filter_macs
# ===================================================================

class TestFilterMacs:
    def test_empty_input(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        assert mon._filter_macs([]) == set()

    def test_no_ignore(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        result = mon._filter_macs(["AA:BB:CC:DD:EE:01"])
        assert result == {"AA:BB:CC:DD:EE:01"}

    def test_ignore_filters_out(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file, ignore_macs=["AA:BB:CC:DD:EE:01"])
        result = mon._filter_macs(["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"])
        assert result == {"AA:BB:CC:DD:EE:02"}

    def test_case_insensitive_ignore(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file, ignore_macs=["aa:bb:cc:dd:ee:01"])
        result = mon._filter_macs(["AA:BB:CC:DD:EE:01"])
        assert result == set()

    def test_case_insensitive_input(self, sample_config, log_file):
        """Lowercase input MACs are uppercased in output."""
        mon = _make_monitor(sample_config, log_file)
        result = mon._filter_macs(["aa:bb:cc:dd:ee:01"])
        assert "AA:BB:CC:DD:EE:01" in result


# ===================================================================
# 3. _filter_ssids
# ===================================================================

class TestFilterSSIDs:
    def test_empty_input(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        assert mon._filter_ssids([]) == set()

    def test_filters_ignored_ssids(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file, ignore_ssids=["HomeNetwork"])
        result = mon._filter_ssids(["HomeNetwork", "CoffeeShop"])
        assert result == {"CoffeeShop"}

    def test_filters_empty_strings(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        result = mon._filter_ssids(["", "ValidSSID"])
        assert result == {"ValidSSID"}

    def test_filters_none_values(self, sample_config, log_file):
        """None values are falsy, should be filtered out."""
        mon = _make_monitor(sample_config, log_file)
        result = mon._filter_ssids([None, "ValidSSID"])
        assert result == {"ValidSSID"}


# ===================================================================
# 4. initialize_tracking_lists  (uses real SecureKismetDB)
# ===================================================================

class TestInitializeTrackingLists:
    def test_empty_db(self, mock_kismet_db, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        with SecureKismetDB(mock_kismet_db) as db:
            mon.initialize_tracking_lists(db)
        # All lists should be empty
        assert len(mon.past_five_mins_macs) == 0

    def test_populated_db_recent(self, mock_kismet_db, sample_config, log_file):
        """A device within the last 5 minutes lands in past_five_mins_macs."""
        now = time.time()
        _insert_device(mock_kismet_db, "AA:BB:CC:DD:EE:01", None, now - 60)
        mon = _make_monitor(sample_config, log_file)
        with SecureKismetDB(mock_kismet_db) as db:
            mon.initialize_tracking_lists(db)
        assert "AA:BB:CC:DD:EE:01" in mon.past_five_mins_macs

    def test_log_file_written(self, mock_kismet_db, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        with SecureKismetDB(mock_kismet_db) as db:
            mon.initialize_tracking_lists(db)
        content = log_file.getvalue()
        assert "MACs added to the" in content
        assert "Probed SSIDs added to the" in content


# ===================================================================
# 5. rotate_tracking_lists
# ===================================================================

class TestRotateTrackingLists:
    def test_rotation_shifts_mac_lists(self, mock_kismet_db, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        # Seed lists manually
        mon.past_five_mins_macs = {"MAC_A"}
        mon.five_ten_min_ago_macs = {"MAC_B"}
        mon.ten_fifteen_min_ago_macs = {"MAC_C"}
        mon.fifteen_twenty_min_ago_macs = {"MAC_D"}

        with SecureKismetDB(mock_kismet_db) as db:
            mon.rotate_tracking_lists(db)

        # 15-20 should now be what was 10-15
        assert "MAC_C" in mon.fifteen_twenty_min_ago_macs
        # 10-15 should now be what was 5-10
        assert "MAC_B" in mon.ten_fifteen_min_ago_macs
        # 5-10 should now be what was past-5
        assert "MAC_A" in mon.five_ten_min_ago_macs

    def test_rotation_shifts_ssid_lists(self, mock_kismet_db, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mon.past_five_mins_ssids = {"SSID_A"}
        mon.five_ten_min_ago_ssids = {"SSID_B"}
        mon.ten_fifteen_min_ago_ssids = {"SSID_C"}
        mon.fifteen_twenty_min_ago_ssids = {"SSID_D"}

        with SecureKismetDB(mock_kismet_db) as db:
            mon.rotate_tracking_lists(db)

        assert "SSID_C" in mon.fifteen_twenty_min_ago_ssids
        assert "SSID_B" in mon.ten_fifteen_min_ago_ssids
        assert "SSID_A" in mon.five_ten_min_ago_ssids

    def test_rotation_refreshes_past_five(self, mock_kismet_db, sample_config, log_file):
        """After rotation, past_five_mins gets fresh DB data (empty DB -> empty)."""
        mon = _make_monitor(sample_config, log_file)
        mon.past_five_mins_macs = {"STALE"}
        with SecureKismetDB(mock_kismet_db) as db:
            mon.rotate_tracking_lists(db)
        # DB is empty, so fresh fetch returns nothing
        assert "STALE" not in mon.past_five_mins_macs

    def test_rotation_log_output(self, mock_kismet_db, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        with SecureKismetDB(mock_kismet_db) as db:
            mon.rotate_tracking_lists(db)
        content = log_file.getvalue()
        assert "MACs moved to the" in content
        assert "Probed SSIDs moved to the" in content


# ===================================================================
# 6. _check_ssid_history
# ===================================================================

class TestCheckSSIDHistory:
    def test_match_five_ten(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mon.five_ten_min_ago_ssids = {"TestSSID"}
        mon._check_ssid_history("TestSSID")
        assert "5 to 10 mins" in log_file.getvalue()

    def test_match_ten_fifteen(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mon.ten_fifteen_min_ago_ssids = {"TestSSID"}
        mon._check_ssid_history("TestSSID")
        assert "10 to 15 mins" in log_file.getvalue()

    def test_match_fifteen_twenty(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mon.fifteen_twenty_min_ago_ssids = {"TestSSID"}
        mon._check_ssid_history("TestSSID")
        assert "15 to 20 mins" in log_file.getvalue()

    def test_no_match_writes_nothing(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mon._check_ssid_history("UnknownSSID")
        assert log_file.getvalue() == ""


# ===================================================================
# 7. _process_mac_tracking
# ===================================================================

class TestProcessMacTracking:
    def test_ignored_mac_skipped(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file, ignore_macs=["AA:BB:CC:DD:EE:01"])
        mon.five_ten_min_ago_macs = {"AA:BB:CC:DD:EE:01"}
        mon._process_mac_tracking("AA:BB:CC:DD:EE:01")
        assert log_file.getvalue() == ""

    def test_match_five_ten(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mon.five_ten_min_ago_macs = {"AA:BB:CC:DD:EE:01"}
        mon._process_mac_tracking("AA:BB:CC:DD:EE:01")
        assert "5 to 10 mins" in log_file.getvalue()

    def test_match_all_windows(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mac = "AA:BB:CC:DD:EE:01"
        mon.five_ten_min_ago_macs = {mac}
        mon.ten_fifteen_min_ago_macs = {mac}
        mon.fifteen_twenty_min_ago_macs = {mac}
        mon._process_mac_tracking(mac)
        content = log_file.getvalue()
        assert "5 to 10 mins" in content
        assert "10 to 15 mins" in content
        assert "15 to 20 mins" in content


# ===================================================================
# 8. _process_probe_requests
# ===================================================================

class TestProcessProbeRequests:
    def test_valid_probe(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        device_data = json.loads(make_device_json("TestSSID"))
        mon._process_probe_requests(device_data, "AA:BB:CC:DD:EE:01")
        assert "Found a probe!: TestSSID" in log_file.getvalue()

    def test_none_device_data(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mon._process_probe_requests(None, "AA:BB:CC:DD:EE:01")
        assert log_file.getvalue() == ""

    def test_empty_device_data(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        mon._process_probe_requests({}, "AA:BB:CC:DD:EE:01")
        assert log_file.getvalue() == ""

    def test_ignored_ssid_not_logged(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file, ignore_ssids=["IgnoreMe"])
        device_data = json.loads(make_device_json("IgnoreMe"))
        mon._process_probe_requests(device_data, "AA:BB:CC:DD:EE:01")
        assert log_file.getvalue() == ""

    def test_empty_ssid_not_logged(self, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        device_data = json.loads(make_device_json(""))
        mon._process_probe_requests(device_data, "AA:BB:CC:DD:EE:01")
        assert log_file.getvalue() == ""

    def test_malformed_dot11_device(self, sample_config, log_file):
        """Non-dict dot11.device should not crash."""
        mon = _make_monitor(sample_config, log_file)
        device_data = {"dot11.device": "not-a-dict"}
        mon._process_probe_requests(device_data, "AA:BB:CC:DD:EE:01")
        assert log_file.getvalue() == ""


# ===================================================================
# 9. process_current_activity  (integration with real DB)
# ===================================================================

class TestProcessCurrentActivity:
    def test_with_populated_db(self, populated_kismet_db, sample_config, log_file):
        """Integration: process_current_activity reads devices from a real DB."""
        mon = _make_monitor(sample_config, log_file)
        with SecureKismetDB(populated_kismet_db) as db:
            mon.process_current_activity(db)
        # The populated DB has recent devices with probes; at least one should appear
        # (depending on timing; the fixtures use now-60 etc. which is within the 2-min current window)
        # We mainly check no crash occurs.

    def test_empty_db_no_crash(self, mock_kismet_db, sample_config, log_file):
        mon = _make_monitor(sample_config, log_file)
        with SecureKismetDB(mock_kismet_db) as db:
            mon.process_current_activity(db)
        # Should simply complete without error
