"""WiFi scanner wrapping existing Kismet DB polling."""
import glob
import json
import logging
import os
import time
from pathlib import Path
from queue import Queue
from typing import Optional

from scanners.base_scanner import BaseScanner, DeviceAppearance, SourceType
from secure_database import SecureKismetDB

logger = logging.getLogger(__name__)


class WiFiScanner(BaseScanner):
    """Wraps existing Kismet SQLite polling as a BaseScanner."""

    def __init__(self, config: dict, output_queue: Queue, location_id: str = "unknown"):
        super().__init__(config=config, output_queue=output_queue, location_id=location_id)
        # Extract check_interval: prefer scanners.wifi.check_interval, fall back to timing.check_interval, default 60
        scanner_wifi_cfg = config.get("scanners", {}).get("wifi", {})
        self._check_interval: int = scanner_wifi_cfg.get(
            "check_interval",
            config.get("timing", {}).get("check_interval", 60),
        )
        # Glob pattern for finding .kismet files
        self._db_pattern: str = config.get("paths", {}).get("kismet_logs", "*.kismet")
        self._last_poll_time: float = 0.0

    @property
    def scanner_name(self) -> str:
        return "wifi"

    @property
    def source_type(self) -> SourceType:
        return SourceType.WIFI

    def _find_latest_db(self) -> Optional[str]:
        """Find the most recently modified .kismet file matching the configured pattern."""
        matches = glob.glob(self._db_pattern)
        if not matches:
            logger.warning("No .kismet files found matching pattern: %s", self._db_pattern)
            return None
        # Return the file with the most recent modification time
        return max(matches, key=os.path.getmtime)

    def _extract_ssids(self, device_data: Optional[dict]) -> list:
        """Extract probed SSIDs from parsed Kismet device JSON."""
        if not device_data:
            return []
        try:
            dot11 = device_data.get("dot11.device", {})
            if not isinstance(dot11, dict):
                return []
            probe_record = dot11.get("dot11.device.last_probed_ssid_record", {})
            if not isinstance(probe_record, dict):
                return []
            ssid = probe_record.get("dot11.probedssid.ssid", "")
            if ssid and isinstance(ssid, str):
                return [ssid]
        except (AttributeError, TypeError):
            pass
        return []

    def _scan_loop(self) -> None:
        """Poll the latest Kismet DB for new devices in a loop."""
        while not self._stop_event.is_set():
            db_path = self._find_latest_db()
            if db_path is None:
                logger.warning("No Kismet database available, will retry in %d seconds", self._check_interval)
                if self._stop_event.wait(timeout=self._check_interval):
                    break
                continue

            try:
                with SecureKismetDB(db_path) as db:
                    devices = db.get_devices_by_time_range(self._last_poll_time)

                    for dev in devices:
                        mac = dev["mac"]
                        device_data = dev.get("device_data")
                        ssids = self._extract_ssids(device_data)

                        appearance = DeviceAppearance(
                            device_id=mac,
                            source_type=SourceType.WIFI,
                            timestamp=dev.get("last_time", time.time()),
                            location_id=self.location_id,
                            device_type=dev.get("type"),
                            mac=mac,
                            ssids_probed=ssids,
                        )
                        self._emit(appearance)

                    # Update poll time to now so next iteration only gets new devices
                    self._last_poll_time = time.time()

            except Exception:
                logger.exception("Error reading Kismet database %s", db_path)

            # Wait for check_interval or until stop is signalled
            if self._stop_event.wait(timeout=self._check_interval):
                break
