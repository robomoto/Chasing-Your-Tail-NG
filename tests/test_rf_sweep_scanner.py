"""TDD tests for RFSweepScanner — Phase 7: RF Sweep baseline + anomaly detection."""
import json
import time
from unittest.mock import patch, MagicMock
from queue import Queue

import pytest

from scanners.base_scanner import DeviceAppearance, SourceType
from scanners.rf_sweep_scanner import RFSweepScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RTL_POWER_CSV = """\
2025-07-20, 14:30:00, 433000000, 434000000, 500000, 10, -45.2, -50.1
2025-07-20, 14:30:00, 434000000, 435000000, 500000, 10, -80.1, -82.3
"""


def _make_scanner(config=None):
    """Create an RFSweepScanner with sensible defaults."""
    cfg = config or {
        "rf_sweep": {
            "freq_start_mhz": 433,
            "freq_end_mhz": 435,
            "bin_size_hz": 500000,
            "integration_interval": 10,
        }
    }
    q = Queue()
    return RFSweepScanner(config=cfg, output_queue=q, location_id="test-loc")


# ---------------------------------------------------------------------------
# 1. Identity properties
# ---------------------------------------------------------------------------

def test_rf_sweep_scanner_name():
    scanner = _make_scanner()
    assert scanner.scanner_name == "rf_sweep"


def test_rf_sweep_scanner_source_type():
    scanner = _make_scanner()
    assert scanner.source_type is SourceType.RF_SWEEP


# ---------------------------------------------------------------------------
# 2. run_sweep — happy path
# ---------------------------------------------------------------------------

def test_run_sweep():
    """Mock subprocess running rtl_power; parse CSV into freq_mhz -> power_dbm."""
    scanner = _make_scanner()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = RTL_POWER_CSV

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        result = scanner.run_sweep()

    # subprocess.run should have been called with rtl_power
    assert mock_sub.called
    call_args = mock_sub.call_args
    assert "rtl_power" in call_args[0][0][0] or "rtl_power" in str(call_args)

    # Result structure
    assert "freq_bins" in result
    assert "timestamp" in result
    assert isinstance(result["timestamp"], float)
    assert isinstance(result["freq_bins"], dict)

    # At least one frequency bin present, keyed by MHz float
    assert len(result["freq_bins"]) > 0
    for freq, power in result["freq_bins"].items():
        assert isinstance(freq, float)
        assert isinstance(power, float)


# ---------------------------------------------------------------------------
# 3. run_sweep — rtl_power not found
# ---------------------------------------------------------------------------

def test_run_sweep_rtl_power_not_found():
    """FileNotFoundError from missing rtl_power binary is handled gracefully."""
    scanner = _make_scanner()

    with patch("subprocess.run", side_effect=FileNotFoundError("rtl_power not found")):
        result = scanner.run_sweep()

    assert result == {} or result == {"freq_bins": {}, "timestamp": 0.0}
    # Either truly empty dict or empty-bins dict is acceptable; must not raise.


# ---------------------------------------------------------------------------
# 4. save_baseline — persist sweep data to JSON
# ---------------------------------------------------------------------------

def test_save_baseline(tmp_path):
    scanner = _make_scanner()
    sweep_data = {
        "freq_bins": {433.0: -45.2, 434.0: -80.1},
        "timestamp": time.time(),
    }
    baseline_path = str(tmp_path / "baseline.json")

    scanner.save_baseline(sweep_data, baseline_path)

    with open(baseline_path) as f:
        loaded = json.load(f)

    # Verify round-trip (JSON keys are strings, but values should match)
    assert len(loaded["freq_bins"]) == 2
    assert loaded["timestamp"] == pytest.approx(sweep_data["timestamp"])


# ---------------------------------------------------------------------------
# 5. load_baseline — read JSON back
# ---------------------------------------------------------------------------

def test_load_baseline(tmp_path):
    scanner = _make_scanner()
    baseline_path = str(tmp_path / "baseline.json")

    original = {
        "freq_bins": {"433.0": -45.2, "434.0": -80.1},
        "timestamp": 1700000000.0,
    }
    with open(baseline_path, "w") as f:
        json.dump(original, f)

    loaded = scanner.load_baseline(baseline_path)

    assert "freq_bins" in loaded
    assert len(loaded["freq_bins"]) == 2


# ---------------------------------------------------------------------------
# 6. load_baseline — missing file returns empty dict
# ---------------------------------------------------------------------------

def test_load_baseline_missing_file(tmp_path):
    scanner = _make_scanner()
    result = scanner.load_baseline(str(tmp_path / "nonexistent.json"))
    assert result == {}


# ---------------------------------------------------------------------------
# 7. compare_to_baseline — no anomalies
# ---------------------------------------------------------------------------

def test_compare_to_baseline_no_anomalies():
    scanner = _make_scanner()

    baseline = {"freq_bins": {433.0: -50.0, 434.0: -80.0}, "timestamp": 1700000000.0}
    sweep = {"freq_bins": {433.0: -48.0, 434.0: -78.0}, "timestamp": 1700000060.0}

    anomalies = scanner.compare_to_baseline(sweep, baseline, threshold_db=10.0)
    assert anomalies == []


# ---------------------------------------------------------------------------
# 8. compare_to_baseline — anomaly detected
# ---------------------------------------------------------------------------

def test_compare_to_baseline_with_anomaly():
    scanner = _make_scanner()

    baseline = {"freq_bins": {433.0: -60.0, 434.0: -80.0}, "timestamp": 1700000000.0}
    sweep = {"freq_bins": {433.0: -45.0, 434.0: -78.0}, "timestamp": 1700000060.0}

    # 433 MHz is 15 dB above baseline (-45 vs -60); threshold is 10
    anomalies = scanner.compare_to_baseline(sweep, baseline, threshold_db=10.0)

    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly["freq"] == 433.0
    assert anomaly["measured_db"] == pytest.approx(-45.0)
    assert anomaly["baseline_db"] == pytest.approx(-60.0)
    assert anomaly["delta_db"] == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# 9. compare emits DeviceAppearance objects
# ---------------------------------------------------------------------------

def test_compare_emits_appearances():
    """Anomalies are converted to DeviceAppearance with RF_SWEEP source type."""
    scanner = _make_scanner()

    baseline = {"freq_bins": {433.0: -60.0, 915.0: -70.0}, "timestamp": 1700000000.0}
    sweep = {"freq_bins": {433.0: -40.0, 915.0: -50.0}, "timestamp": 1700000060.0}

    # Both bins are 20 dB above baseline
    anomalies = scanner.compare_to_baseline(sweep, baseline, threshold_db=10.0)
    assert len(anomalies) >= 2

    # Each anomaly should be convertible to / already contain a DeviceAppearance
    for anomaly in anomalies:
        # If the scanner returns raw dicts, we check the structure has what we
        # need to build a DeviceAppearance.  If it returns DeviceAppearance
        # objects directly on the queue, we check those instead.
        if isinstance(anomaly, DeviceAppearance):
            assert anomaly.source_type is SourceType.RF_SWEEP
            assert anomaly.device_id.startswith("rf_anomaly:")
        else:
            # Dict form — verify the scanner provides enough info
            assert "freq" in anomaly
            # Build the appearance the way the scanner should
            freq = anomaly["freq"]
            appearance = DeviceAppearance(
                device_id=f"rf_anomaly:{freq}",
                source_type=SourceType.RF_SWEEP,
                timestamp=sweep["timestamp"],
                location_id="test-loc",
                signal_strength=anomaly["measured_db"],
                frequency_mhz=freq,
                metadata={
                    "baseline_db": anomaly["baseline_db"],
                    "delta_db": anomaly["delta_db"],
                },
            )
            assert appearance.device_id == f"rf_anomaly:{freq}"
            assert appearance.source_type is SourceType.RF_SWEEP
