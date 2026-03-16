"""Tests for gps_tracker.py – GPSTracker and KMLExporter."""

import math
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock

import pytest

from gps_tracker import GPSTracker, GPSLocation, KMLExporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PHOENIX_HOME = (33.4484, -112.0740)
PHOENIX_OFFICE = (33.4734, -112.0431)

# Two points ~50 m apart (well within 100 m threshold)
CLOSE_A = (33.448400, -112.074000)
CLOSE_B = (33.448850, -112.074000)  # ~50 m north of CLOSE_A

# Two points ~150 m apart (beyond 100 m threshold)
FAR_A = (33.448400, -112.074000)
FAR_B = (33.449750, -112.074000)  # ~150 m north of FAR_A


def _make_tracker(config=None):
    """Return a GPSTracker with a minimal config dict."""
    return GPSTracker(config or {})


# ---------------------------------------------------------------------------
# GPSTracker – add_gps_reading
# ---------------------------------------------------------------------------

class TestAddGpsReading:

    @patch("gps_tracker.time")
    def test_returns_location_id(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        loc_id = tracker.add_gps_reading(33.4484, -112.0740)
        assert isinstance(loc_id, str)
        assert len(loc_id) > 0

    @patch("gps_tracker.time")
    def test_creates_session(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(33.4484, -112.0740)
        assert len(tracker.location_sessions) == 1
        assert tracker.current_location is not None

    @patch("gps_tracker.time")
    def test_uses_location_name_in_id(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        loc_id = tracker.add_gps_reading(33.4484, -112.0740, location_name="Home Base")
        assert "Home_Base" in loc_id

    @patch("gps_tracker.time")
    def test_generates_coordinate_based_id_when_no_name(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        loc_id = tracker.add_gps_reading(33.4484, -112.0740)
        assert loc_id.startswith("loc_")

    @patch("gps_tracker.time")
    def test_stores_location_in_locations_list(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(33.4484, -112.0740, altitude=100.0, accuracy=5.0)
        assert len(tracker.locations) == 1
        assert tracker.locations[0].altitude == 100.0
        assert tracker.locations[0].accuracy == 5.0


# ---------------------------------------------------------------------------
# GPSTracker – _calculate_distance (Haversine)
# ---------------------------------------------------------------------------

class TestCalculateDistance:

    def test_zero_distance_same_point(self):
        tracker = _make_tracker()
        loc = GPSLocation(latitude=33.4484, longitude=-112.0740)
        assert tracker._calculate_distance(loc, loc) == pytest.approx(0.0, abs=1e-6)

    def test_known_distance_phoenix_to_office(self):
        """Phoenix Home to Phoenix Office is roughly 3.7 km."""
        tracker = _make_tracker()
        loc1 = GPSLocation(latitude=33.4484, longitude=-112.0740)
        loc2 = GPSLocation(latitude=33.4734, longitude=-112.0431)
        dist = tracker._calculate_distance(loc1, loc2)
        assert 3500 < dist < 4000  # ~3.7 km

    def test_antipodal_points(self):
        """Antipodal points should be roughly half the Earth's circumference."""
        tracker = _make_tracker()
        loc1 = GPSLocation(latitude=0.0, longitude=0.0)
        loc2 = GPSLocation(latitude=0.0, longitude=180.0)
        dist = tracker._calculate_distance(loc1, loc2)
        half_circumference = math.pi * 6371000  # ~20015 km
        assert dist == pytest.approx(half_circumference, rel=0.01)

    def test_short_distance_accuracy(self):
        """Two points ~111 m apart (0.001 degree latitude at equator)."""
        tracker = _make_tracker()
        loc1 = GPSLocation(latitude=0.0, longitude=0.0)
        loc2 = GPSLocation(latitude=0.001, longitude=0.0)
        dist = tracker._calculate_distance(loc1, loc2)
        assert 100 < dist < 120  # ~111 m

    def test_symmetry(self):
        tracker = _make_tracker()
        loc1 = GPSLocation(latitude=33.4484, longitude=-112.0740)
        loc2 = GPSLocation(latitude=33.4734, longitude=-112.0431)
        assert tracker._calculate_distance(loc1, loc2) == pytest.approx(
            tracker._calculate_distance(loc2, loc1), abs=1e-6
        )


# ---------------------------------------------------------------------------
# GPSTracker – Location clustering
# ---------------------------------------------------------------------------

class TestLocationClustering:

    @patch("gps_tracker.time")
    def test_nearby_readings_cluster_together(self, mock_time):
        """Two readings within ~50 m should share the same session ID."""
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        id1 = tracker.add_gps_reading(*CLOSE_A)
        mock_time.time.return_value = 1010.0
        id2 = tracker.add_gps_reading(*CLOSE_B)
        assert id1 == id2
        assert len(tracker.location_sessions) == 1

    @patch("gps_tracker.time")
    def test_distant_readings_create_separate_clusters(self, mock_time):
        """Two readings ~150 m apart should produce different session IDs."""
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        id1 = tracker.add_gps_reading(*FAR_A)
        mock_time.time.return_value = 1010.0
        id2 = tracker.add_gps_reading(*FAR_B)
        assert id1 != id2
        assert len(tracker.location_sessions) == 2

    @patch("gps_tracker.time")
    def test_custom_threshold(self, mock_time):
        """Increasing threshold should merge previously separate clusters."""
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.location_threshold = 200  # 200 m
        id1 = tracker.add_gps_reading(*FAR_A)
        mock_time.time.return_value = 1010.0
        id2 = tracker.add_gps_reading(*FAR_B)
        assert id1 == id2


# ---------------------------------------------------------------------------
# GPSTracker – Session management
# ---------------------------------------------------------------------------

class TestSessionManagement:

    @patch("gps_tracker.time")
    def test_session_continues_within_timeout(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*CLOSE_A)

        mock_time.time.return_value = 1500.0  # 500 s later, within 600 s timeout
        tracker.add_gps_reading(*CLOSE_B)

        assert len(tracker.location_sessions) == 1
        assert tracker.location_sessions[0].end_time == 1500.0

    @patch("gps_tracker.time")
    def test_session_breaks_after_timeout(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*CLOSE_A, location_name="Spot")

        # Jump past session_timeout (600 s) — same cluster ID but new session
        mock_time.time.return_value = 1700.0  # 700 s later
        tracker.add_gps_reading(*CLOSE_B, location_name="Spot")

        assert len(tracker.location_sessions) == 2

    @patch("gps_tracker.time")
    def test_end_time_updated_on_continued_session(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*CLOSE_A)

        mock_time.time.return_value = 1200.0
        tracker.add_gps_reading(*CLOSE_B)

        session = tracker.location_sessions[0]
        assert session.start_time == 1000.0
        assert session.end_time == 1200.0


# ---------------------------------------------------------------------------
# GPSTracker – add_device_at_current_location
# ---------------------------------------------------------------------------

class TestAddDeviceAtCurrentLocation:

    @patch("gps_tracker.time")
    def test_adds_mac_to_current_session(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(33.4484, -112.0740)
        result = tracker.add_device_at_current_location("AA:BB:CC:DD:EE:01")
        assert result is not None
        assert "AA:BB:CC:DD:EE:01" in tracker.current_location.devices_seen

    @patch("gps_tracker.time")
    def test_no_current_location_returns_none(self, mock_time):
        tracker = _make_tracker()
        result = tracker.add_device_at_current_location("AA:BB:CC:DD:EE:01")
        assert result is None

    @patch("gps_tracker.time")
    def test_duplicate_mac_not_added_twice(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(33.4484, -112.0740)
        tracker.add_device_at_current_location("AA:BB:CC:DD:EE:01")
        tracker.add_device_at_current_location("AA:BB:CC:DD:EE:01")
        assert tracker.current_location.devices_seen.count("AA:BB:CC:DD:EE:01") == 1


# ---------------------------------------------------------------------------
# GPSTracker – get_devices_across_locations
# ---------------------------------------------------------------------------

class TestGetDevicesAcrossLocations:

    @patch("gps_tracker.time")
    def test_device_at_two_locations_returned(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*PHOENIX_HOME)
        tracker.add_device_at_current_location("AA:BB:CC:DD:EE:01")

        mock_time.time.return_value = 1010.0
        tracker.add_gps_reading(*PHOENIX_OFFICE)
        tracker.add_device_at_current_location("AA:BB:CC:DD:EE:01")

        result = tracker.get_devices_across_locations()
        assert "AA:BB:CC:DD:EE:01" in result
        assert len(result["AA:BB:CC:DD:EE:01"]) == 2

    @patch("gps_tracker.time")
    def test_single_location_device_excluded(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*PHOENIX_HOME)
        tracker.add_device_at_current_location("AA:BB:CC:DD:EE:01")

        result = tracker.get_devices_across_locations()
        assert "AA:BB:CC:DD:EE:01" not in result

    @patch("gps_tracker.time")
    def test_empty_when_no_devices(self, mock_time):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*PHOENIX_HOME)
        assert tracker.get_devices_across_locations() == {}


# ---------------------------------------------------------------------------
# GPSTracker – get_location_history
# ---------------------------------------------------------------------------

class TestGetLocationHistory:

    @patch("gps_tracker.time")
    def test_sorted_by_start_time(self, mock_time):
        tracker = _make_tracker()

        mock_time.time.return_value = 2000.0
        tracker.add_gps_reading(*PHOENIX_OFFICE)

        mock_time.time.return_value = 1000.0
        tracker.add_gps_reading(*PHOENIX_HOME)

        history = tracker.get_location_history()
        assert len(history) == 2
        assert history[0].start_time <= history[1].start_time

    @patch("gps_tracker.time")
    def test_empty_when_no_sessions(self, mock_time):
        tracker = _make_tracker()
        assert tracker.get_location_history() == []


# ---------------------------------------------------------------------------
# KMLExporter – generate_kml
# ---------------------------------------------------------------------------

class TestKMLExporterGenerateKml:

    @patch("gps_tracker.time")
    def test_produces_valid_xml(self, mock_time, tmp_path):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*PHOENIX_HOME, location_name="Home")

        exporter = KMLExporter()
        output_file = str(tmp_path / "test.kml")
        kml_string = exporter.generate_kml(tracker, surveillance_devices=[], output_file=output_file)

        # Must parse as valid XML
        root = ET.fromstring(kml_string)
        assert root.tag.endswith("kml")

    @patch("gps_tracker.time")
    def test_contains_document_and_folder(self, mock_time, tmp_path):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*PHOENIX_HOME, location_name="Home")

        exporter = KMLExporter()
        output_file = str(tmp_path / "test.kml")
        kml_string = exporter.generate_kml(tracker, surveillance_devices=[], output_file=output_file)

        assert "<Document>" in kml_string
        assert "<Folder>" in kml_string
        assert "Monitoring Locations" in kml_string

    @patch("gps_tracker.time")
    def test_contains_placemark_with_coordinates(self, mock_time, tmp_path):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*PHOENIX_HOME, location_name="Home")

        exporter = KMLExporter()
        output_file = str(tmp_path / "test.kml")
        kml_string = exporter.generate_kml(tracker, surveillance_devices=[], output_file=output_file)

        assert "<Placemark>" in kml_string
        assert "-112.074" in kml_string
        assert "33.4484" in kml_string

    @patch("gps_tracker.time")
    def test_writes_file_to_disk(self, mock_time, tmp_path):
        mock_time.time.return_value = 1000.0
        tracker = _make_tracker()
        tracker.add_gps_reading(*PHOENIX_HOME, location_name="Home")

        exporter = KMLExporter()
        output_file = str(tmp_path / "output.kml")
        exporter.generate_kml(tracker, surveillance_devices=[], output_file=output_file)

        assert (tmp_path / "output.kml").exists()
        content = (tmp_path / "output.kml").read_text()
        assert content.startswith("<?xml")


# ---------------------------------------------------------------------------
# KMLExporter – _generate_empty_kml
# ---------------------------------------------------------------------------

class TestGenerateEmptyKml:

    def test_produces_valid_xml(self, tmp_path):
        exporter = KMLExporter()
        output_file = str(tmp_path / "empty.kml")
        kml_string = exporter._generate_empty_kml(output_file)
        root = ET.fromstring(kml_string)
        assert root.tag.endswith("kml")

    def test_contains_no_data_message(self, tmp_path):
        exporter = KMLExporter()
        output_file = str(tmp_path / "empty.kml")
        kml_string = exporter._generate_empty_kml(output_file)
        assert "No GPS Data Available" in kml_string

    def test_fallback_when_no_sessions(self, tmp_path):
        """generate_kml falls back to empty KML when tracker has no sessions."""
        tracker = _make_tracker()
        exporter = KMLExporter()
        output_file = str(tmp_path / "fallback.kml")
        kml_string = exporter.generate_kml(tracker, output_file=output_file)
        assert "No GPS Data Available" in kml_string

    def test_writes_file_to_disk(self, tmp_path):
        exporter = KMLExporter()
        output_file = str(tmp_path / "empty.kml")
        exporter._generate_empty_kml(output_file)
        assert (tmp_path / "empty.kml").exists()


# ---------------------------------------------------------------------------
# KMLExporter – _generate_circle_coordinates
# ---------------------------------------------------------------------------

class TestGenerateCircleCoordinates:

    def test_returns_37_points(self):
        """Circle is 36 segments + 1 closing point = 37 coordinate triples."""
        exporter = KMLExporter()
        coords_str = exporter._generate_circle_coordinates(-112.074, 33.4484, 100)
        points = coords_str.strip().split(" ")
        assert len(points) == 37

    def test_circle_is_closed(self):
        """First and last coordinate should be the same (closed polygon)."""
        exporter = KMLExporter()
        coords_str = exporter._generate_circle_coordinates(-112.074, 33.4484, 100)
        points = coords_str.strip().split(" ")
        assert points[0] == points[-1]

    def test_coordinates_format(self):
        """Each point should be lon,lat,0 format."""
        exporter = KMLExporter()
        coords_str = exporter._generate_circle_coordinates(0.0, 0.0, 500)
        points = coords_str.strip().split(" ")
        for point in points:
            parts = point.split(",")
            assert len(parts) == 3
            assert parts[2] == "0"
            # lon and lat should be valid floats
            float(parts[0])
            float(parts[1])
