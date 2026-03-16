"""TDD integration tests for CYTEngine — the CYT-NG entry point."""
import json
import time
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from scanners.base_scanner import DeviceAppearance, SourceType, ScannerState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_dict(tmp_path):
    """Full config dict with session DB pointed at tmp_path."""
    return {
        "paths": {
            "base_dir": str(tmp_path),
            "log_dir": str(tmp_path / "logs"),
            "kismet_logs": str(tmp_path / "*.kismet"),
            "ignore_lists": {"mac": "mac_list.json", "ssid": "ssid_list.json"},
        },
        "timing": {
            "check_interval": 60,
            "list_update_interval": 5,
            "time_windows": {"recent": 5, "medium": 10, "old": 15, "oldest": 20},
        },
        "search": {
            "lat_min": 31.3, "lat_max": 37.0,
            "lon_min": -114.8, "lon_max": -109.0,
        },
        "scanners": {
            "wifi": {"enabled": True, "check_interval": 60},
            "ble": {"enabled": False, "scan_duration": 10},
            "bt_classic": {"enabled": False},
            "sdr": {"enabled": False},
            "lora": {"enabled": False},
            "drone": {"enabled": False},
            "adsb": {"enabled": False},
            "rf_sweep": {"enabled": False},
            "handheld": {"import_dir": str(tmp_path / "handheld_imports"), "auto_import": False},
        },
        "session_db": {"path": str(tmp_path / "cyt_sessions.db")},
        "fusion": {
            "correlation_window_seconds": 30,
            "cross_source_multiplier": 1.5,
        },
    }


@pytest.fixture
def config_file(tmp_path, config_dict):
    """Write config_dict to a JSON file and return its path."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps(config_dict))
    return str(p)


# ---------------------------------------------------------------------------
# Test 1: Engine init loads config from file
# ---------------------------------------------------------------------------

class TestEngineInitLoadsConfig:
    def test_engine_init_loads_config(self, config_file, config_dict):
        """CYTEngine(config_path) reads the JSON and stores config internally."""
        from cyt_ng import CYTEngine

        engine = CYTEngine(config_path=config_file)

        # It should have a config dict with the expected keys
        assert hasattr(engine, "config") or hasattr(engine, "_config")
        cfg = getattr(engine, "config", None) or getattr(engine, "_config", None)
        assert cfg is not None
        assert cfg["scanners"]["wifi"]["enabled"] is True


# ---------------------------------------------------------------------------
# Test 2: Engine init with custom config dict
# ---------------------------------------------------------------------------

class TestEngineInitWithCustomConfig:
    def test_engine_init_with_custom_config(self, config_dict):
        """CYTEngine can accept a config dict directly, skipping file load."""
        from cyt_ng import CYTEngine

        engine = CYTEngine(config=config_dict)
        cfg = getattr(engine, "config", None) or getattr(engine, "_config", None)
        assert cfg is not None
        assert cfg["scanners"]["wifi"]["enabled"] is True


# ---------------------------------------------------------------------------
# Test 3: WiFi scanner always registered
# ---------------------------------------------------------------------------

class TestEngineRegistersWiFiScanner:
    @patch("cyt_ng.WiFiScanner")
    def test_engine_registers_wifi_scanner(self, MockWiFi, config_dict):
        """WiFi scanner is always registered as the core scanner."""
        from cyt_ng import CYTEngine

        mock_instance = MagicMock()
        mock_instance.scanner_name = "wifi"
        MockWiFi.return_value = mock_instance

        engine = CYTEngine(config=config_dict)

        MockWiFi.assert_called_once()
        # The orchestrator should contain the wifi scanner
        states = engine.orchestrator.get_scanner_states()
        assert "wifi" in states


# ---------------------------------------------------------------------------
# Test 4: Enabled scanners get registered
# ---------------------------------------------------------------------------

class TestEngineRegistersEnabledScanners:
    @patch("cyt_ng.WiFiScanner")
    def test_engine_registers_enabled_scanners(self, MockWiFi, config_dict, tmp_path):
        """Scanners with enabled=true in config get registered."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        MockWiFi.return_value = mock_wifi

        # Enable BLE for this test
        config_dict["scanners"]["ble"]["enabled"] = True

        with patch("cyt_ng.BLEScanner") as MockBLE:
            mock_ble = MagicMock()
            mock_ble.scanner_name = "ble"
            MockBLE.return_value = mock_ble

            engine = CYTEngine(config=config_dict)
            states = engine.orchestrator.get_scanner_states()
            assert "ble" in states


# ---------------------------------------------------------------------------
# Test 5: Disabled scanners not started
# ---------------------------------------------------------------------------

class TestEngineSkipsDisabledScanners:
    @patch("cyt_ng.WiFiScanner")
    def test_engine_skips_disabled_scanners(self, MockWiFi, config_dict):
        """Scanners with enabled=false should not be started (though may be registered)."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        MockWiFi.return_value = mock_wifi

        engine = CYTEngine(config=config_dict)
        engine.start()

        # BLE is disabled, so it should not have been started
        states = engine.orchestrator.get_scanner_states()
        # BLE should either not be present or be in stopped state
        if "ble" in states:
            assert states["ble"] == "stopped"

        engine.stop()


# ---------------------------------------------------------------------------
# Test 6: Start/stop lifecycle
# ---------------------------------------------------------------------------

class TestEngineStartStopLifecycle:
    @patch("cyt_ng.WiFiScanner")
    def test_engine_start_stop_lifecycle(self, MockWiFi, config_dict):
        """start() then stop() runs cleanly without errors."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        mock_wifi.state = ScannerState.STOPPED
        MockWiFi.return_value = mock_wifi

        engine = CYTEngine(config=config_dict)
        engine.start()
        engine.stop()

        # After stop, no exception means success
        mock_wifi.stop.assert_called()


# ---------------------------------------------------------------------------
# Test 7: get_status returns expected structure
# ---------------------------------------------------------------------------

class TestEngineGetStatus:
    @patch("cyt_ng.WiFiScanner")
    def test_engine_get_status(self, MockWiFi, config_dict):
        """get_status() returns dict with scanner_states, appearances_processed, correlation_count."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        mock_wifi.state = ScannerState.STOPPED
        MockWiFi.return_value = mock_wifi

        engine = CYTEngine(config=config_dict)
        status = engine.get_status()

        assert isinstance(status, dict)
        assert "scanner_states" in status
        assert "appearances_processed" in status
        assert "correlation_count" in status
        assert isinstance(status["scanner_states"], dict)
        assert status["appearances_processed"] == 0
        assert status["correlation_count"] == 0


# ---------------------------------------------------------------------------
# Test 8: Appearance callback feeds SurveillanceDetector
# ---------------------------------------------------------------------------

class TestEngineAppearanceCallbackFeedsDetector:
    @patch("cyt_ng.WiFiScanner")
    def test_engine_appearance_callback_feeds_detector(self, MockWiFi, config_dict):
        """An appearance flowing through the callback reaches SurveillanceDetector.add_appearance()."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        MockWiFi.return_value = mock_wifi

        engine = CYTEngine(config=config_dict)

        appearance = DeviceAppearance(
            device_id="AA:BB:CC:DD:EE:01",
            source_type=SourceType.WIFI,
            timestamp=time.time(),
            location_id="test_loc",
        )

        # Invoke the callback directly (simulates orchestrator consumer)
        engine._on_appearance(appearance)

        assert len(engine.detector.appearances) == 1


# ---------------------------------------------------------------------------
# Test 9: Appearance callback feeds FusionEngine
# ---------------------------------------------------------------------------

class TestEngineAppearanceCallbackFeedsFusion:
    @patch("cyt_ng.WiFiScanner")
    def test_engine_appearance_callback_feeds_fusion(self, MockWiFi, config_dict):
        """An appearance flowing through the callback reaches FusionEngine.process_appearance()."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        MockWiFi.return_value = mock_wifi

        engine = CYTEngine(config=config_dict)

        # Patch process_appearance to track calls
        engine.fusion.process_appearance = MagicMock(return_value=[])

        appearance = DeviceAppearance(
            device_id="AA:BB:CC:DD:EE:01",
            source_type=SourceType.WIFI,
            timestamp=time.time(),
            location_id="test_loc",
        )

        engine._on_appearance(appearance)
        engine.fusion.process_appearance.assert_called_once_with(appearance)


# ---------------------------------------------------------------------------
# Test 10: Appearance callback feeds SessionDB
# ---------------------------------------------------------------------------

class TestEngineAppearanceCallbackFeedsSessionDB:
    @patch("cyt_ng.WiFiScanner")
    def test_engine_appearance_callback_feeds_session_db(self, MockWiFi, config_dict):
        """An appearance flowing through the callback records a sighting in SessionDB."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        MockWiFi.return_value = mock_wifi

        engine = CYTEngine(config=config_dict)

        # Patch record_sighting to track calls
        engine.session_db.record_sighting = MagicMock()

        appearance = DeviceAppearance(
            device_id="AA:BB:CC:DD:EE:01",
            source_type=SourceType.WIFI,
            timestamp=time.time(),
            location_id="test_loc",
        )

        engine._on_appearance(appearance)
        engine.session_db.record_sighting.assert_called_once()


# ---------------------------------------------------------------------------
# Test 11: import_handheld_session
# ---------------------------------------------------------------------------

class TestEngineImportHandheld:
    @patch("cyt_ng.WiFiScanner")
    @patch("cyt_ng.HandheldImporter")
    def test_engine_import_handheld(self, MockImporter, MockWiFi, config_dict, tmp_path):
        """import_handheld_session() delegates to HandheldImporter and returns stats."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        MockWiFi.return_value = mock_wifi

        mock_importer_instance = MagicMock()
        fake_appearances = [
            DeviceAppearance(
                device_id="ESP32-001",
                source_type=SourceType.HANDHELD_IMPORT,
                timestamp=time.time(),
                location_id="handheld",
            ),
            DeviceAppearance(
                device_id="ESP32-002",
                source_type=SourceType.HANDHELD_IMPORT,
                timestamp=time.time(),
                location_id="handheld",
            ),
        ]
        mock_importer_instance.import_session.return_value = fake_appearances
        MockImporter.return_value = mock_importer_instance

        engine = CYTEngine(config=config_dict)
        csv_path = str(tmp_path / "session.csv")

        result = engine.import_handheld_session(csv_path)
        assert isinstance(result, dict)
        assert result.get("imported", 0) == 2


# ---------------------------------------------------------------------------
# Test 12: run_rf_sweep
# ---------------------------------------------------------------------------

class TestEngineRFSweep:
    @patch("cyt_ng.WiFiScanner")
    @patch("cyt_ng.RFSweepScanner")
    def test_engine_rf_sweep(self, MockRF, MockWiFi, config_dict):
        """run_rf_sweep() delegates to RFSweepScanner.run_sweep() and returns results."""
        from cyt_ng import CYTEngine

        mock_wifi = MagicMock()
        mock_wifi.scanner_name = "wifi"
        MockWiFi.return_value = mock_wifi

        mock_rf_instance = MagicMock()
        mock_rf_instance.scanner_name = "rf_sweep"
        fake_sweep = {
            "freq_bins": {100.0: -40.0, 200.0: -55.0},
            "timestamp": time.time(),
        }
        mock_rf_instance.run_sweep.return_value = fake_sweep
        MockRF.return_value = mock_rf_instance

        engine = CYTEngine(config=config_dict)
        result = engine.run_rf_sweep()

        assert isinstance(result, dict)
        assert "freq_bins" in result
        assert "timestamp" in result
