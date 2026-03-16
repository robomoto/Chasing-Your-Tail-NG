"""CYT-NG multi-sensor entry point -- wires all scanners together."""

import json
import logging
import signal
import sys
import time
from pathlib import Path

from scanner_orchestrator import ScannerOrchestrator
from surveillance_detector import SurveillanceDetector
from fusion_engine import FusionEngine
from session_db import SessionDB
from scanners.wifi_scanner import WiFiScanner
from scanners.ble_scanner import BLEScanner
from scanners.sdr_scanner import SDRScanner
from scanners.drone_scanner import DroneScanner
from scanners.bt_classic_scanner import BTClassicScanner
from scanners.adsb_scanner import ADSBScanner
from scanners.lora_scanner import LoRaScanner
from scanners.handheld_importer import HandheldImporter
from scanners.rf_sweep_scanner import RFSweepScanner

logger = logging.getLogger(__name__)

# Map of config key -> scanner class for optional scanners
_OPTIONAL_SCANNERS = {
    "ble": BLEScanner,
    "bt_classic": BTClassicScanner,
    "sdr": SDRScanner,
    "drone": DroneScanner,
    "adsb": ADSBScanner,
    "lora": LoRaScanner,
    "rf_sweep": RFSweepScanner,
}


class CYTEngine:
    """Main engine that connects all components."""

    def __init__(self, config=None, config_path: str = "config.json"):
        # Load config
        if isinstance(config, dict):
            self.config = config
        else:
            with open(config_path, "r") as f:
                self.config = json.load(f)

        # Core subsystems
        self.detector = SurveillanceDetector(self.config)
        self.fusion = FusionEngine(self.config)
        self.session_db = SessionDB(
            self.config.get("session_db", {}).get("path", "cyt_sessions.db")
        )
        self.orchestrator = ScannerOrchestrator(
            self.config, on_appearance=self._on_appearance
        )

        # Determine location_id from config
        location_id = self.config.get("location_id", "unknown")

        # Always register WiFi scanner
        scanners_cfg = self.config.get("scanners", {})
        wifi = WiFiScanner(self.config, self.orchestrator.queue, location_id)
        self.orchestrator.register_scanner(wifi)

        # Register optional scanners that are enabled
        for key, cls in _OPTIONAL_SCANNERS.items():
            scanner_cfg = scanners_cfg.get(key, {})
            if scanner_cfg.get("enabled", False):
                scanner = cls(self.config, self.orchestrator.queue, location_id)
                self.orchestrator.register_scanner(scanner)

    def _on_appearance(self, appearance) -> None:
        """Callback invoked by the orchestrator for each detection."""
        self.detector.add_appearance(appearance)
        self.fusion.process_appearance(appearance)
        self.session_db.record_sighting(
            session_id="live",
            device_id=appearance.device_id,
            source_type=appearance.source_type.value
            if hasattr(appearance.source_type, "value")
            else str(appearance.source_type),
            timestamp=appearance.timestamp,
        )

    def start(self) -> None:
        """Start all scanners via the orchestrator."""
        self.orchestrator.start_all()

    def stop(self) -> None:
        """Stop all scanners and close the session database."""
        self.orchestrator.stop_all()
        self.session_db.close()

    def get_status(self) -> dict:
        """Return current engine status."""
        return {
            "scanner_states": self.orchestrator.get_scanner_states(),
            "appearances_processed": self.orchestrator.appearances_processed,
            "correlation_count": self.fusion.correlation_count,
        }

    def import_handheld_session(self, csv_path: str) -> dict:
        """Import a handheld CSV session and feed appearances through the pipeline."""
        importer = HandheldImporter(self.config)
        appearances = importer.import_session(csv_path)
        for appearance in appearances:
            self._on_appearance(appearance)
        return {"imported": len(appearances)}

    def run_rf_sweep(self) -> dict:
        """Run an RF wideband sweep and return results."""
        scanner = RFSweepScanner(self.config, self.orchestrator.queue)
        return scanner.run_sweep()


def main():
    """Create CYTEngine, start it, run until KeyboardInterrupt, then stop."""
    logging.basicConfig(level=logging.INFO)
    engine = CYTEngine()
    engine.start()
    logger.info("CYT-NG engine started. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
