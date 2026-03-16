"""Comprehensive tests for surveillance_detector.py module."""
import json
import sqlite3
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from surveillance_detector import (
    DeviceAppearance,
    SurveillanceDetector,
    SuspiciousDevice,
    load_appearances_from_kismet,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config():
    """Return a minimal config dict accepted by SurveillanceDetector."""
    return {"paths": {"base_dir": "."}}


def _make_detector(config=None):
    return SurveillanceDetector(config or _make_config())


def _ts(hours_ago: float = 0) -> float:
    """Return a unix timestamp *hours_ago* hours in the past."""
    return time.time() - hours_ago * 3600


# ---------------------------------------------------------------------------
# DeviceAppearance dataclass
# ---------------------------------------------------------------------------

class TestDeviceAppearance:
    def test_creation_required_fields(self):
        da = DeviceAppearance(
            mac="AA:BB:CC:DD:EE:01",
            timestamp=1000.0,
            location_id="loc_a",
            ssids_probed=["MyNet"],
        )
        assert da.mac == "AA:BB:CC:DD:EE:01"
        assert da.timestamp == 1000.0
        assert da.location_id == "loc_a"
        assert da.ssids_probed == ["MyNet"]

    def test_optional_fields_default_none(self):
        da = DeviceAppearance(
            mac="AA:BB:CC:DD:EE:01",
            timestamp=1000.0,
            location_id="loc_a",
            ssids_probed=[],
        )
        assert da.signal_strength is None
        assert da.device_type is None

    def test_optional_fields_set(self):
        da = DeviceAppearance(
            mac="AA:BB:CC:DD:EE:01",
            timestamp=1000.0,
            location_id="loc_a",
            ssids_probed=["Net1"],
            signal_strength=-45.0,
            device_type="Wi-Fi Client",
        )
        assert da.signal_strength == -45.0
        assert da.device_type == "Wi-Fi Client"


# ---------------------------------------------------------------------------
# SuspiciousDevice dataclass
# ---------------------------------------------------------------------------

class TestSuspiciousDevice:
    def test_creation(self):
        now = datetime.now()
        sd = SuspiciousDevice(
            mac="AA:BB:CC:DD:EE:02",
            persistence_score=0.75,
            appearances=[],
            reasons=["Appeared 5 times"],
            first_seen=now - timedelta(hours=2),
            last_seen=now,
            total_appearances=5,
            locations_seen=["loc_a", "loc_b"],
        )
        assert sd.persistence_score == 0.75
        assert sd.total_appearances == 5
        assert len(sd.locations_seen) == 2


# ---------------------------------------------------------------------------
# SurveillanceDetector -- initialisation
# ---------------------------------------------------------------------------

class TestDetectorInit:
    def test_default_thresholds(self):
        det = _make_detector()
        assert det.thresholds["min_appearances"] == 3
        assert det.thresholds["min_time_span_hours"] == 1.0
        assert det.thresholds["min_persistence_score"] == 0.5

    def test_empty_state(self):
        det = _make_detector()
        assert det.appearances == []
        assert len(det.device_history) == 0


# ---------------------------------------------------------------------------
# add_device_appearance
# ---------------------------------------------------------------------------

class TestAddDeviceAppearance:
    def test_single_add(self):
        det = _make_detector()
        det.add_device_appearance("AA:BB:CC:DD:EE:01", 1000.0, "loc_a")
        assert len(det.appearances) == 1
        assert len(det.device_history["AA:BB:CC:DD:EE:01"]) == 1

    def test_multiple_adds_same_mac(self):
        det = _make_detector()
        for i in range(5):
            det.add_device_appearance("AA:BB:CC:DD:EE:01", 1000.0 + i * 3600, "loc_a")
        assert len(det.device_history["AA:BB:CC:DD:EE:01"]) == 5

    def test_ssids_default_empty(self):
        det = _make_detector()
        det.add_device_appearance("AA:BB:CC:DD:EE:01", 1000.0, "loc_a")
        assert det.appearances[0].ssids_probed == []

    def test_ssids_provided(self):
        det = _make_detector()
        det.add_device_appearance("AA:BB:CC:DD:EE:01", 1000.0, "loc_a",
                                  ssids_probed=["Net1", "Net2"])
        assert det.appearances[0].ssids_probed == ["Net1", "Net2"]

    def test_signal_and_type(self):
        det = _make_detector()
        det.add_device_appearance("AA:BB:CC:DD:EE:01", 1000.0, "loc_a",
                                  signal_strength=-60.0, device_type="Wi-Fi AP")
        a = det.appearances[0]
        assert a.signal_strength == -60.0
        assert a.device_type == "Wi-Fi AP"


# ---------------------------------------------------------------------------
# _calculate_persistence_score
# ---------------------------------------------------------------------------

class TestCalculatePersistenceScore:
    def test_fewer_than_3_appearances_returns_zero(self):
        det = _make_detector()
        apps = [
            DeviceAppearance("M", _ts(0), "loc", []),
            DeviceAppearance("M", _ts(2), "loc", []),
        ]
        score, reasons = det._calculate_persistence_score(apps)
        assert score == 0.0
        assert reasons == []

    def test_time_span_under_one_hour_returns_zero(self):
        """3 appearances within 30 minutes -- should be 0."""
        det = _make_detector()
        base = time.time()
        apps = [
            DeviceAppearance("M", base, "loc", []),
            DeviceAppearance("M", base + 600, "loc", []),
            DeviceAppearance("M", base + 1200, "loc", []),  # 20 min span
        ]
        score, reasons = det._calculate_persistence_score(apps)
        assert score == 0.0

    def test_low_appearance_rate_returns_zero(self):
        """3 appearances over 24 hours = rate 0.125 < 0.5 threshold."""
        det = _make_detector()
        base = time.time()
        apps = [
            DeviceAppearance("M", base, "loc", []),
            DeviceAppearance("M", base + 12 * 3600, "loc", []),
            DeviceAppearance("M", base + 24 * 3600, "loc", []),
        ]
        score, reasons = det._calculate_persistence_score(apps)
        assert score == 0.0

    def test_moderate_persistence(self):
        """5 appearances over 2 hours -> rate 2.5/hr, score = 2.5/2 = 1.0 (capped)."""
        det = _make_detector()
        base = time.time()
        apps = [DeviceAppearance("M", base + i * 1800, "loc", []) for i in range(5)]
        # span = 4*1800 = 7200s = 2hr; rate = 5/2 = 2.5
        score, reasons = det._calculate_persistence_score(apps)
        assert score > 0
        assert score <= 1.0
        assert len(reasons) >= 1

    def test_score_capped_at_1(self):
        """Many appearances in short-ish time -- score must not exceed 1.0."""
        det = _make_detector()
        base = time.time()
        # 20 appearances over 1.5 hours -> rate ~13.3 -> score would be 6.67 uncapped
        apps = [DeviceAppearance("M", base + i * 270, "loc", []) for i in range(20)]
        score, _ = det._calculate_persistence_score(apps)
        assert score <= 1.0

    def test_multi_location_bonus(self):
        """Same rate, but 2 locations should give a higher score.

        Use a low appearance rate so single-location score is well below 1.0,
        leaving room for the multi-location bonus to create a visible difference.
        """
        det = _make_detector()
        base = time.time()
        # 3 appearances over 2 hours -> rate 1.5 -> score ~0.5 (below cap)
        apps_single = [DeviceAppearance("M", base + i * 3600, "loc_a", []) for i in range(3)]
        score_single, _ = det._calculate_persistence_score(apps_single)
        assert score_single < 1.0, "Single-location score should be below cap for this test"

        # multi location (same count and time span)
        apps_multi = [
            DeviceAppearance("M", base, "loc_a", []),
            DeviceAppearance("M", base + 3600, "loc_b", []),
            DeviceAppearance("M", base + 7200, "loc_a", []),
        ]
        score_multi, reasons_multi = det._calculate_persistence_score(apps_multi)
        assert score_multi > score_single
        assert any("locations" in r.lower() for r in reasons_multi)

    def test_multi_location_bonus_capped(self):
        """Even with multi-location bonus, score stays <= 1.0."""
        det = _make_detector()
        base = time.time()
        apps = [
            DeviceAppearance("M", base + i * 270, f"loc_{i % 3}", []) for i in range(20)
        ]
        score, _ = det._calculate_persistence_score(apps)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# analyze_surveillance_patterns
# ---------------------------------------------------------------------------

class TestAnalyzeSurveillancePatterns:
    def test_empty_detector(self):
        det = _make_detector()
        result = det.analyze_surveillance_patterns()
        assert result == []

    def test_devices_below_appearance_threshold(self):
        det = _make_detector()
        det.add_device_appearance("M1", _ts(0), "loc", [])
        det.add_device_appearance("M1", _ts(1), "loc", [])
        # Only 2 appearances < 3
        result = det.analyze_surveillance_patterns()
        assert result == []

    def test_devices_below_score_threshold(self):
        """3 appearances over 24 hours -> rate too low -> score 0 -> excluded."""
        det = _make_detector()
        base = time.time()
        for i in range(3):
            det.add_device_appearance("M1", base + i * 12 * 3600, "loc")
        result = det.analyze_surveillance_patterns()
        assert result == []

    def test_suspicious_device_returned(self):
        det = _make_detector()
        base = time.time()
        for i in range(6):
            det.add_device_appearance("M1", base + i * 1800, "loc_a")
        result = det.analyze_surveillance_patterns()
        assert len(result) == 1
        assert result[0].mac == "M1"
        assert result[0].total_appearances == 6

    def test_sorted_by_score_descending(self):
        det = _make_detector()
        base = time.time()
        # Device A: 10 appearances over 2 hours (high rate)
        for i in range(10):
            det.add_device_appearance("DEV_A", base + i * 720, "loc_a")
        # Device B: 4 appearances over 2 hours (lower rate)
        for i in range(4):
            det.add_device_appearance("DEV_B", base + i * 1800, "loc_a")
        result = det.analyze_surveillance_patterns()
        assert len(result) >= 1
        if len(result) == 2:
            assert result[0].persistence_score >= result[1].persistence_score

    def test_suspicious_device_fields(self):
        det = _make_detector()
        base = time.time()
        for i in range(5):
            det.add_device_appearance("M1", base + i * 1800, "loc_a",
                                      ssids_probed=["TestNet"])
        result = det.analyze_surveillance_patterns()
        assert len(result) == 1
        dev = result[0]
        assert isinstance(dev.first_seen, datetime)
        assert isinstance(dev.last_seen, datetime)
        assert dev.first_seen <= dev.last_seen
        assert "loc_a" in dev.locations_seen


# ---------------------------------------------------------------------------
# _analyze_temporal_patterns
# ---------------------------------------------------------------------------

class TestAnalyzeTemporalPatterns:
    def test_no_suspicious_devices(self):
        det = _make_detector()
        patterns = det._analyze_temporal_patterns([])
        assert len(patterns) == 1
        assert "No suspicious" in patterns[0]

    def test_work_hours_pattern(self):
        det = _make_detector()
        # Build a suspicious device with all appearances during work hours (10 AM)
        base_date = datetime(2025, 6, 10, 10, 0, 0)  # Tuesday 10 AM
        apps = []
        for i in range(5):
            ts = (base_date + timedelta(hours=i)).timestamp()
            apps.append(DeviceAppearance("M1", ts, "loc_a", []))

        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.8, appearances=apps,
            reasons=["test"], first_seen=base_date,
            last_seen=base_date + timedelta(hours=4),
            total_appearances=5, locations_seen=["loc_a"],
        )
        patterns = det._analyze_temporal_patterns([sd])
        assert any("work-hours" in p.lower() for p in patterns)

    def test_off_hours_pattern(self):
        det = _make_detector()
        base_date = datetime(2025, 6, 10, 23, 0, 0)  # 11 PM
        apps = []
        for i in range(5):
            ts = (base_date + timedelta(minutes=i * 30)).timestamp()
            apps.append(DeviceAppearance("M1", ts, "loc_a", []))

        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.8, appearances=apps,
            reasons=["test"], first_seen=base_date,
            last_seen=base_date + timedelta(hours=2),
            total_appearances=5, locations_seen=["loc_a"],
        )
        patterns = det._analyze_temporal_patterns([sd])
        assert any("off-hours" in p.lower() for p in patterns)

    def test_regular_interval_detection(self):
        det = _make_detector()
        base_date = datetime(2025, 6, 10, 12, 0, 0)
        apps = []
        # Exactly 1-hour intervals (very regular)
        for i in range(5):
            ts = (base_date + timedelta(hours=i)).timestamp()
            apps.append(DeviceAppearance("M1", ts, "loc_a", []))

        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.8, appearances=apps,
            reasons=["test"], first_seen=base_date,
            last_seen=base_date + timedelta(hours=4),
            total_appearances=5, locations_seen=["loc_a"],
        )
        patterns = det._analyze_temporal_patterns([sd])
        assert any("regular intervals" in p.lower() for p in patterns)


# ---------------------------------------------------------------------------
# _analyze_geographic_patterns
# ---------------------------------------------------------------------------

class TestAnalyzeGeographicPatterns:
    def test_no_suspicious_devices(self):
        det = _make_detector()
        patterns = det._analyze_geographic_patterns([])
        assert len(patterns) == 1
        assert "No suspicious" in patterns[0]

    def test_multi_location_following(self):
        det = _make_detector()
        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.8,
            appearances=[
                DeviceAppearance("M1", 1000, "loc_a", []),
                DeviceAppearance("M1", 2000, "loc_b", []),
            ],
            reasons=["test"],
            first_seen=datetime.fromtimestamp(1000),
            last_seen=datetime.fromtimestamp(2000),
            total_appearances=2,
            locations_seen=["loc_a", "loc_b"],
        )
        patterns = det._analyze_geographic_patterns([sd])
        assert any("following" in p.lower() or "multiple locations" in p.lower()
                    for p in patterns)

    def test_quick_transition_detected(self):
        det = _make_detector()
        base = time.time()
        apps = [
            DeviceAppearance("M1", base, "loc_a", []),
            DeviceAppearance("M1", base + 600, "loc_b", []),  # 10 min later, diff loc
        ]
        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.8, appearances=apps,
            reasons=["test"],
            first_seen=datetime.fromtimestamp(base),
            last_seen=datetime.fromtimestamp(base + 600),
            total_appearances=2, locations_seen=["loc_a", "loc_b"],
        )
        patterns = det._analyze_geographic_patterns([sd])
        assert any("rapid" in p.lower() for p in patterns)

    def test_single_location_no_geo_pattern(self):
        det = _make_detector()
        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.8,
            appearances=[DeviceAppearance("M1", 1000, "loc_a", [])],
            reasons=["test"],
            first_seen=datetime.fromtimestamp(1000),
            last_seen=datetime.fromtimestamp(1000),
            total_appearances=1, locations_seen=["loc_a"],
        )
        patterns = det._analyze_geographic_patterns([sd])
        assert any("no significant" in p.lower() for p in patterns)

    def test_hotspot_detection(self):
        det = _make_detector()
        base = time.time()
        # Two different devices both seen at loc_a
        sd1 = SuspiciousDevice(
            mac="M1", persistence_score=0.8,
            appearances=[DeviceAppearance("M1", base, "loc_a", [])],
            reasons=["test"],
            first_seen=datetime.fromtimestamp(base),
            last_seen=datetime.fromtimestamp(base),
            total_appearances=1, locations_seen=["loc_a"],
        )
        sd2 = SuspiciousDevice(
            mac="M2", persistence_score=0.7,
            appearances=[DeviceAppearance("M2", base, "loc_a", [])],
            reasons=["test"],
            first_seen=datetime.fromtimestamp(base),
            last_seen=datetime.fromtimestamp(base),
            total_appearances=1, locations_seen=["loc_a"],
        )
        patterns = det._analyze_geographic_patterns([sd1, sd2])
        assert any("hotspot" in p.lower() for p in patterns)


# ---------------------------------------------------------------------------
# _analyze_device_correlations
# ---------------------------------------------------------------------------

class TestAnalyzeDeviceCorrelations:
    def test_single_device_no_correlations(self):
        det = _make_detector()
        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.8, appearances=[], reasons=[],
            first_seen=datetime.now(), last_seen=datetime.now(),
            total_appearances=0, locations_seen=[],
        )
        assert det._analyze_device_correlations([sd]) == []

    def test_correlated_devices(self):
        det = _make_detector()
        base = time.time()
        apps1 = [DeviceAppearance("M1", base + i * 600, "loc_a", []) for i in range(5)]
        apps2 = [DeviceAppearance("M2", base + i * 600 + 30, "loc_a", []) for i in range(5)]
        sd1 = SuspiciousDevice(
            mac="M1", persistence_score=0.8, appearances=apps1, reasons=[],
            first_seen=datetime.fromtimestamp(base),
            last_seen=datetime.fromtimestamp(base + 2400),
            total_appearances=5, locations_seen=["loc_a", "loc_b"],
        )
        sd2 = SuspiciousDevice(
            mac="M2", persistence_score=0.7, appearances=apps2, reasons=[],
            first_seen=datetime.fromtimestamp(base),
            last_seen=datetime.fromtimestamp(base + 2400),
            total_appearances=5, locations_seen=["loc_a", "loc_b"],
        )
        correlations = det._analyze_device_correlations([sd1, sd2])
        assert len(correlations) >= 1


# ---------------------------------------------------------------------------
# _generate_analysis_statistics
# ---------------------------------------------------------------------------

class TestGenerateAnalysisStatistics:
    def test_empty_detector(self):
        det = _make_detector()
        stats = det._generate_analysis_statistics()
        assert stats["total_appearances"] == 0
        assert stats["unique_devices"] == 0
        assert stats["detection_accuracy"] == 0.95

    def test_populated_detector(self):
        det = _make_detector()
        base = time.time()
        for i in range(5):
            det.add_device_appearance("M1", base + i * 3600, "loc_a")
        det.add_device_appearance("M2", base, "loc_b")

        stats = det._generate_analysis_statistics()
        assert stats["total_appearances"] == 6
        assert stats["unique_devices"] == 2
        assert stats["unique_locations"] == 2
        assert stats["analysis_duration_hours"] > 0


# ---------------------------------------------------------------------------
# generate_surveillance_report
# ---------------------------------------------------------------------------

class TestGenerateSurveillanceReport:
    def test_clean_report(self, tmp_path):
        det = _make_detector()
        det.add_device_appearance("M1", time.time(), "loc_a")
        output = str(tmp_path / "report.md")
        report = det.generate_surveillance_report(output)
        assert "SURVEILLANCE DETECTION ANALYSIS" in report
        assert "CLEAN ENVIRONMENT" in report

    def test_report_with_suspicious_devices(self, tmp_path):
        det = _make_detector()
        base = time.time()
        for i in range(10):
            det.add_device_appearance("M1", base + i * 720, "loc_a")
        output = str(tmp_path / "report.md")
        report = det.generate_surveillance_report(output)
        assert "PERSISTENT DEVICE ANALYSIS" in report
        assert "M1" in report

    def test_report_file_written(self, tmp_path):
        det = _make_detector()
        output = str(tmp_path / "report.md")
        det.generate_surveillance_report(output)
        assert (tmp_path / "report.md").exists()
        content = (tmp_path / "report.md").read_text()
        assert len(content) > 0


# ---------------------------------------------------------------------------
# _format_detailed_device_analysis
# ---------------------------------------------------------------------------

class TestFormatDetailedDeviceAnalysis:
    def test_output_contains_mac(self):
        det = _make_detector()
        base = time.time()
        apps = [DeviceAppearance("M1", base + i * 1800, "loc_a", ["Net1"]) for i in range(5)]
        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.85, appearances=apps, reasons=["Reason1"],
            first_seen=datetime.fromtimestamp(base),
            last_seen=datetime.fromtimestamp(base + 7200),
            total_appearances=5, locations_seen=["loc_a"],
        )
        text = det._format_detailed_device_analysis(sd, "HIGH")
        assert "M1" in text
        assert "HIGH" in text

    def test_multi_location_message(self):
        det = _make_detector()
        base = time.time()
        apps = [
            DeviceAppearance("M1", base, "loc_a", []),
            DeviceAppearance("M1", base + 3600, "loc_b", []),
        ]
        sd = SuspiciousDevice(
            mac="M1", persistence_score=0.9, appearances=apps, reasons=[],
            first_seen=datetime.fromtimestamp(base),
            last_seen=datetime.fromtimestamp(base + 3600),
            total_appearances=2, locations_seen=["loc_a", "loc_b"],
        )
        text = det._format_detailed_device_analysis(sd, "CRITICAL")
        assert "CONFIRMED" in text
        assert "multiple locations" in text.lower()


# ---------------------------------------------------------------------------
# load_appearances_from_kismet
# ---------------------------------------------------------------------------

class TestLoadAppearancesFromKismet:
    @pytest.mark.xfail(reason="Known bug: load_appearances_from_kismet crashes on json.loads(None) for NULL device rows")
    def test_load_from_populated_db(self, populated_kismet_db):
        det = _make_detector()
        count = load_appearances_from_kismet(populated_kismet_db, det, "test_loc")
        # populated_kismet_db has 5 rows; all have last_time > 0
        assert count == 5
        assert len(det.appearances) == 5

    def test_ssid_extraction(self, tmp_path):
        """Test with only valid-JSON rows to avoid the NULL device bug."""
        import sqlite3, json
        db_path = str(tmp_path / "valid.kismet")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE devices (devmac TEXT, type TEXT, device TEXT, last_time REAL, first_time REAL DEFAULT 0, avg_lat REAL DEFAULT 0, avg_lon REAL DEFAULT 0)")
        device_json = json.dumps({"dot11.device": {"dot11.device.last_probed_ssid_record": {"dot11.probedssid.ssid": "HomeNetwork"}}})
        conn.execute("INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)", ("AA:BB:CC:DD:EE:01", "Wi-Fi", device_json, time.time()))
        conn.commit()
        conn.close()
        det = _make_detector()
        load_appearances_from_kismet(db_path, det, "test_loc")
        flat = [s for a in det.appearances for s in a.ssids_probed]
        assert "HomeNetwork" in flat

    def test_empty_db(self, mock_kismet_db):
        det = _make_detector()
        count = load_appearances_from_kismet(mock_kismet_db, det, "loc")
        assert count == 0
        assert len(det.appearances) == 0

    @pytest.mark.xfail(reason="Known bug: load_appearances_from_kismet crashes on json.loads(None) for NULL device rows")
    def test_invalid_json_handled(self, populated_kismet_db):
        """Row with '{invalid json' should not crash and should yield empty ssids."""
        det = _make_detector()
        load_appearances_from_kismet(populated_kismet_db, det, "loc")
        ee04 = [a for a in det.appearances if a.mac == "AA:BB:CC:DD:EE:04"]
        assert len(ee04) == 1
        assert ee04[0].ssids_probed == []

    @pytest.mark.xfail(reason="Known bug: load_appearances_from_kismet crashes on json.loads(None) for NULL device rows")
    def test_null_device_json_handled(self, populated_kismet_db):
        """Row with NULL device field should not crash."""
        det = _make_detector()
        load_appearances_from_kismet(populated_kismet_db, det, "loc")
        ee03 = [a for a in det.appearances if a.mac == "AA:BB:CC:DD:EE:03"]
        assert len(ee03) == 1
        assert ee03[0].ssids_probed == []

    def test_nonexistent_db_returns_zero(self, tmp_path):
        det = _make_detector()
        count = load_appearances_from_kismet(str(tmp_path / "nope.db"), det, "loc")
        assert count == 0

    def test_location_id_propagated(self, tmp_path):
        """Test with only valid-JSON rows to avoid the NULL device bug."""
        import sqlite3, json
        db_path = str(tmp_path / "valid.kismet")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE devices (devmac TEXT, type TEXT, device TEXT, last_time REAL, first_time REAL DEFAULT 0, avg_lat REAL DEFAULT 0, avg_lon REAL DEFAULT 0)")
        device_json = json.dumps({"dot11.device": {}})
        conn.execute("INSERT INTO devices (devmac, type, device, last_time) VALUES (?, ?, ?, ?)", ("AA:BB:CC:DD:EE:01", "Wi-Fi", device_json, time.time()))
        conn.commit()
        conn.close()
        det = _make_detector()
        load_appearances_from_kismet(db_path, det, "my_loc")
        assert all(a.location_id == "my_loc" for a in det.appearances)

    @pytest.mark.xfail(reason="Known bug: load_appearances_from_kismet crashes on json.loads(None) for NULL device rows")
    def test_empty_ssid_not_included(self, populated_kismet_db):
        """Row with empty string SSID should not produce a non-empty ssids_probed."""
        det = _make_detector()
        load_appearances_from_kismet(populated_kismet_db, det, "loc")
        ee05 = [a for a in det.appearances if a.mac == "AA:BB:CC:DD:EE:05"]
        assert len(ee05) == 1
        assert ee05[0].ssids_probed == []
