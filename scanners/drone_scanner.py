"""Drone detection via Remote ID (BLE + WiFi SSID pattern matching)."""
import asyncio
import fnmatch
import glob
import json
import logging
import re
import sqlite3
import struct
import time

from scanners.base_scanner import BaseScanner, DeviceAppearance, ScannerState, SourceType

logger = logging.getLogger(__name__)

try:
    from bleak import BleakScanner as _BleakScanner
    BleakScanner = _BleakScanner
except ImportError:
    BleakScanner = None

# Open Drone ID service UUID (ASTM F3411-22a)
REMOTE_ID_SERVICE_UUID = "0000fffa-0000-1000-8000-00805f9b34fb"


class DroneScanner(BaseScanner):
    """Detects drones via Remote ID BLE broadcasts and WiFi SSID patterns."""

    DEFAULT_SSID_PATTERNS = ["DJI-*", "TELLO-*", "Skydio-*", "ANAFI-*", "Autel-*", "PARROT-*"]

    def __init__(self, config: dict, output_queue, location_id: str = "unknown"):
        super().__init__(config=config, output_queue=output_queue, location_id=location_id)
        drone_cfg = config.get("scanners", {}).get("drone", {})

        # SSID patterns: use config override or defaults
        raw_patterns = drone_cfg.get("ssid_patterns", self.DEFAULT_SSID_PATTERNS)
        self._ssid_patterns = raw_patterns
        # Compile fnmatch patterns into case-insensitive regexes
        self._ssid_regexes = [
            re.compile(fnmatch.translate(p), re.IGNORECASE)
            for p in raw_patterns
        ]

        # Scan intervals
        self._scan_interval = drone_cfg.get("scan_interval", 30)
        self._ble_scan_duration = drone_cfg.get("ble_scan_duration", 10)

        # Feature toggles
        self._enable_wifi_ssid = drone_cfg.get("enable_wifi_ssid", True)
        self._enable_remote_id = drone_cfg.get("enable_remote_id", True)

        # Kismet DB path
        self._db_path = config.get("paths", {}).get("kismet_logs", "*.kismet")

    @property
    def scanner_name(self) -> str:
        return "drone"

    @property
    def source_type(self) -> SourceType:
        return SourceType.DRONE

    def match_drone_ssid(self, ssid: str) -> bool:
        """Match an SSID against compiled drone patterns. Case-insensitive."""
        if not ssid:
            return False
        for regex in self._ssid_regexes:
            if regex.match(ssid):
                return True
        return False

    def parse_remote_id_ble(self, manufacturer_data: dict, service_data: dict) -> dict | None:
        """Parse Open Drone ID Remote ID data from BLE advertisement.

        Looks for the ASTM F3411 service UUID in service_data and parses
        the simplified payload format:
          - Byte 0: 0x0F marker
          - Bytes 1-12: serial (ASCII)
          - Bytes 13-16: lat (float32 LE)
          - Bytes 17-20: lon (float32 LE)
          - Bytes 21-24: altitude (float32 LE)
          - Bytes 25-28: speed (float32 LE)
          - Bytes 29-32: operator_lat (float32 LE)
          - Bytes 33-36: operator_lon (float32 LE)

        Returns dict with parsed fields or None if not Remote ID.
        """
        payload = service_data.get(REMOTE_ID_SERVICE_UUID)
        if payload is None:
            return None

        # Validate minimum length: 1 marker + 12 serial + 6*4 floats = 37 bytes
        if len(payload) < 37:
            return None

        # Check marker byte
        if payload[0] != 0x0F:
            return None

        serial = payload[1:13].rstrip(b"\x00").decode("ascii", errors="replace")
        lat, lon, altitude, speed, operator_lat, operator_lon = struct.unpack_from(
            "<ffffff", payload, 13
        )

        return {
            "serial": serial,
            "lat": lat,
            "lon": lon,
            "altitude": altitude,
            "speed": speed,
            "operator_lat": operator_lat,
            "operator_lon": operator_lon,
        }

    def _scan_wifi_ssids(self):
        """Scan Kismet DB for WiFi SSIDs matching drone patterns."""
        # Find the DB file(s)
        db_path = self._db_path
        # If the path is a glob pattern, find the latest match
        if "*" in db_path or "?" in db_path:
            matches = glob.glob(db_path)
            if not matches:
                logger.warning("No .kismet files found matching: %s", db_path)
                return
            import os
            db_path = max(matches, key=os.path.getmtime)

        try:
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute(
                    "SELECT devmac, type, device, last_time FROM devices"
                )
                for row in cursor.fetchall():
                    devmac, dev_type, device_json, last_time = row
                    if not device_json:
                        continue
                    try:
                        device_data = json.loads(device_json)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    # Extract SSID from device data
                    ssid = None
                    try:
                        dot11 = device_data.get("dot11.device", {})
                        if isinstance(dot11, dict):
                            probe_record = dot11.get("dot11.device.last_probed_ssid_record", {})
                            if isinstance(probe_record, dict):
                                ssid = probe_record.get("dot11.probedssid.ssid", "")
                    except (AttributeError, TypeError):
                        pass

                    if not ssid:
                        # Try commonname as fallback
                        ssid = device_data.get("kismet.device.base.commonname", "")

                    if ssid and self.match_drone_ssid(ssid):
                        appearance = DeviceAppearance(
                            device_id=f"drone_ssid:{ssid}",
                            source_type=SourceType.DRONE,
                            timestamp=last_time or time.time(),
                            location_id=self.location_id,
                            mac=devmac,
                            device_type="drone_wifi",
                            metadata={
                                "ssid": ssid,
                                "detection_method": "wifi_ssid",
                                "device_type": dev_type,
                            },
                        )
                        self._emit(appearance)
            finally:
                conn.close()
        except Exception:
            logger.exception("Error reading Kismet database %s", db_path)

    def _scan_remote_id_ble(self):
        """Scan for Remote ID BLE advertisements."""
        if BleakScanner is None:
            logger.warning("bleak library not installed; Remote ID BLE scanning unavailable")
            return

        try:
            result = asyncio.run(
                BleakScanner.discover(timeout=self._ble_scan_duration, return_adv=True)
            )
        except Exception:
            logger.exception("Error during BLE Remote ID scan")
            return

        # Handle both dict and list return types
        if isinstance(result, dict):
            devices = result.values()
        else:
            devices = result

        for device, adv in devices:
            parsed = self.parse_remote_id_ble(
                manufacturer_data=adv.manufacturer_data,
                service_data=adv.service_data,
            )
            if parsed is None:
                continue

            serial = parsed["serial"]
            appearance = DeviceAppearance(
                device_id=f"drone:{serial}",
                source_type=SourceType.DRONE,
                timestamp=time.time(),
                location_id=self.location_id,
                signal_strength=adv.rssi,
                device_type="drone_remote_id",
                mac=device.address,
                metadata={
                    "serial": serial,
                    "lat": parsed["lat"],
                    "lon": parsed["lon"],
                    "altitude": parsed["altitude"],
                    "speed": parsed["speed"],
                    "operator_lat": parsed["operator_lat"],
                    "operator_lon": parsed["operator_lon"],
                    "detection_method": "remote_id_ble",
                },
            )
            self._emit(appearance)

    def _scan_loop(self) -> None:
        """Main scan loop — WiFi SSID matching and Remote ID BLE scanning."""
        while not self._stop_event.is_set():
            if self._enable_wifi_ssid:
                self._scan_wifi_ssids()

            if self._enable_remote_id:
                self._scan_remote_id_ble()

            # Wait for scan interval or until stopped
            if self._stop_event.wait(timeout=self._scan_interval):
                break
