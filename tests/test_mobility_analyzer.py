"""TDD tests for MobilityAnalyzer — stationary vs mobile discrimination."""
import pytest

from scanners.mobility_analyzer import MobilityAnalyzer
from scanners.sdr_scanner import SDRScanner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def analyzer():
    """Create a MobilityAnalyzer instance."""
    return MobilityAnalyzer()


@pytest.fixture
def protocol_table():
    """Use SDRScanner.PROTOCOL_MOBILITY as the canonical protocol table."""
    return SDRScanner.PROTOCOL_MOBILITY


# ---------------------------------------------------------------------------
# 1-4: classify_by_protocol
# ---------------------------------------------------------------------------

def test_classify_by_protocol_tpms_mobile(analyzer, protocol_table):
    """TPMS -> mobile (False)."""
    result = analyzer.classify_by_protocol("Toyota", protocol_table)
    assert result is False  # mobile


def test_classify_by_protocol_weather_stationary(analyzer, protocol_table):
    """Weather station model -> stationary (True)."""
    result = analyzer.classify_by_protocol("Acurite-Tower", protocol_table)
    assert result is True  # stationary


def test_classify_by_protocol_unknown(analyzer, protocol_table):
    """Unknown model -> None."""
    result = analyzer.classify_by_protocol("UnknownDevice-XYZ", protocol_table)
    assert result is None


def test_classify_by_protocol_case_insensitive(analyzer, protocol_table):
    """Case-insensitive matching: 'tpms' matches 'TPMS' key."""
    result = analyzer.classify_by_protocol("tpms", protocol_table)
    assert result is False  # mobile — matches "TPMS" key


# ---------------------------------------------------------------------------
# 5-7: classify_by_multi_location
# ---------------------------------------------------------------------------

def test_classify_by_multi_location_distant(analyzer):
    """Device seen at 2 locations ~10km apart -> mobile (False).

    Phoenix, AZ area coordinates roughly 10km apart.
    """
    locations = [
        (33.4484, -112.0740),  # Phoenix downtown
        (33.5387, -112.0740),  # ~10km north
    ]
    result = analyzer.classify_by_multi_location(locations, min_distance_m=500.0)
    assert result is False  # mobile


def test_classify_by_multi_location_close(analyzer):
    """Device seen at 2 locations ~50m apart -> stationary (True)."""
    locations = [
        (33.4484, -112.0740),
        (33.44845, -112.07395),  # ~50m away
    ]
    result = analyzer.classify_by_multi_location(locations, min_distance_m=500.0)
    assert result is True  # stationary


def test_classify_by_multi_location_single(analyzer):
    """Device seen at only 1 location -> None (insufficient data)."""
    locations = [
        (33.4484, -112.0740),
    ]
    result = analyzer.classify_by_multi_location(locations, min_distance_m=500.0)
    assert result is None


# ---------------------------------------------------------------------------
# 8: classify_by_rssi_pattern
# ---------------------------------------------------------------------------

def test_classify_by_rssi_constant(analyzer):
    """RSSI stays roughly constant over 5 readings -> stationary (True).

    A stationary transmitter at a fixed distance produces consistent RSSI.
    GPS history shows our receiver is also stationary.
    """
    rssi_history = [-45.0, -46.0, -45.5, -44.8, -45.2]
    gps_history = [
        (33.4484, -112.0740),
        (33.4484, -112.0740),
        (33.4484, -112.0740),
        (33.4484, -112.0740),
        (33.4484, -112.0740),
    ]
    result = analyzer.classify_by_rssi_pattern(rssi_history, gps_history)
    # Constant RSSI + stationary receiver = stationary source
    assert result is True  # stationary
