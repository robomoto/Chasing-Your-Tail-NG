"""BLE tracker scanner — detects AirTags, SmartTags, Tile, etc."""
import asyncio
import hashlib
import logging
import time

from scanners.base_scanner import BaseScanner, DeviceAppearance, ScannerState, SourceType

logger = logging.getLogger(__name__)

try:
    from bleak import BleakScanner as _BleakScanner
    BleakScanner = _BleakScanner
except ImportError:
    BleakScanner = None


class BLETrackerClassifier:
    """Classifies BLE advertisements as known tracker types. Pure logic, no I/O."""

    APPLE_COMPANY_ID = 0x004C
    SAMSUNG_COMPANY_ID = 0x0075
    GOOGLE_COMPANY_ID = 0x00E0
    TILE_SERVICE_UUID = "0000feed-0000-1000-8000-00805f9b34fb"

    def classify(self, manufacturer_data: dict, service_data: dict) -> dict | None:
        """Classify a BLE advertisement. Returns dict with tracker_type and payload_hash, or None."""
        # Check manufacturer data in priority order
        if self.APPLE_COMPANY_ID in manufacturer_data:
            result = self._check_apple(manufacturer_data[self.APPLE_COMPANY_ID])
            if result is not None:
                return result

        if self.SAMSUNG_COMPANY_ID in manufacturer_data:
            result = self._check_samsung(manufacturer_data[self.SAMSUNG_COMPANY_ID])
            if result is not None:
                return result

        if self.GOOGLE_COMPANY_ID in manufacturer_data:
            result = self._check_google(manufacturer_data[self.GOOGLE_COMPANY_ID])
            if result is not None:
                return result

        # Check service data for Tile
        if service_data:
            result = self._check_tile(service_data)
            if result is not None:
                return result

        return None

    def _check_apple(self, data: bytes) -> dict | None:
        """Check Apple manufacturer data for Find My / AirPods advertisements."""
        if not data or len(data) < 2:
            return None

        type_byte = data[0]

        if type_byte == 0x12:
            # Find My (AirTag/Chipolo) — require >= 25 bytes total
            if len(data) >= 25:
                return {
                    "tracker_type": "findmy",
                    "payload_hash": self._compute_payload_hash(data, "findmy"),
                }
            # Too short for a real Find My payload
            return None

        if type_byte == 0x07:
            # Find My Nearby (AirPods)
            return {
                "tracker_type": "findmy_nearby",
                "payload_hash": self._compute_payload_hash(data, "findmy_nearby"),
            }

        return None

    def _check_samsung(self, data: bytes) -> dict | None:
        """Check Samsung manufacturer data for SmartTag advertisements."""
        if not data or len(data) < 4:
            return None
        return {
            "tracker_type": "smarttag",
            "payload_hash": self._compute_payload_hash(data, "smarttag"),
        }

    def _check_google(self, data: bytes) -> dict | None:
        """Check Google manufacturer data for Find My Device advertisements."""
        if not data:
            return None
        return {
            "tracker_type": "google_findmy",
            "payload_hash": self._compute_payload_hash(data, "google_findmy"),
        }

    def _check_tile(self, service_data: dict) -> dict | None:
        """Check service data for Tile advertisements (UUID containing 'feed')."""
        for uuid, data in service_data.items():
            if "feed" in str(uuid).lower():
                return {
                    "tracker_type": "tile",
                    "payload_hash": self._compute_payload_hash(data, "tile"),
                }
        return None

    def _compute_payload_hash(self, data: bytes, prefix: str) -> str:
        """SHA-256 of data, first 16 hex chars, prepended with prefix."""
        digest = hashlib.sha256(data).hexdigest()[:16]
        return f"{prefix}:{digest}"


class BLEScanner(BaseScanner):
    """Scans for BLE tracker advertisements."""

    def __init__(self, config: dict, output_queue, location_id: str = "unknown"):
        super().__init__(config=config, output_queue=output_queue, location_id=location_id)
        ble_config = config.get("scanners", {}).get("ble", {})
        self._scan_duration = ble_config.get("scan_duration", 10)
        self._scan_interval = ble_config.get("scan_interval", 60)
        tracker_types = ble_config.get("tracker_types", None)
        self._tracker_types = set(tracker_types) if tracker_types is not None else None
        self._classifier = BLETrackerClassifier()

    @property
    def scanner_name(self) -> str:
        return "ble"

    @property
    def source_type(self) -> SourceType:
        return SourceType.BLE

    def _scan_loop(self) -> None:
        """Main scan loop — runs until stop_event is set."""
        if BleakScanner is None:
            self._logger.error("bleak library is not installed; BLE scanning unavailable")
            self._state = ScannerState.ERROR
            return

        while not self._stop_event.is_set():
            try:
                asyncio.run(self._do_scan())
            except OSError as exc:
                self._logger.warning("BLE adapter error: %s", exc)
            except Exception as exc:
                self._logger.exception("Unexpected error during BLE scan: %s", exc)

            # Wait for scan_interval (or until stopped)
            self._stop_event.wait(timeout=self._scan_interval)

    async def _do_scan(self) -> None:
        """Run a single BLE scan window and emit DeviceAppearance for detected trackers."""
        result = await BleakScanner.discover(timeout=self._scan_duration, return_adv=True)

        # Handle both dict (real bleak return_adv=True) and list (test mocks)
        if isinstance(result, dict):
            devices = result.values()
        else:
            devices = result

        for device, adv in devices:
            classification = self._classifier.classify(
                manufacturer_data=adv.manufacturer_data,
                service_data=adv.service_data,
            )
            if classification is None:
                continue

            tracker_type = classification["tracker_type"]

            # Filter by configured tracker types
            if self._tracker_types is not None and tracker_type not in self._tracker_types:
                continue

            payload_hash = classification["payload_hash"]
            device_id = f"{tracker_type}:{payload_hash}"

            appearance = DeviceAppearance(
                device_id=device_id,
                source_type=SourceType.BLE,
                timestamp=time.time(),
                location_id=self.location_id,
                signal_strength=adv.rssi,
                device_type=tracker_type,
                mac=device.address,
                payload_hash=payload_hash,
                metadata={"tracker_type": tracker_type},
            )
            self._emit(appearance)
