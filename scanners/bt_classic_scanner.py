"""Bluetooth Classic scanner — discovers nearby BT devices via inquiry scans."""
import logging
import time

from scanners.base_scanner import BaseScanner, DeviceAppearance, SourceType

logger = logging.getLogger(__name__)

# Major device class mapping (bits 8-12 of the 24-bit Class of Device).
_MAJOR_DEVICE_CLASS: dict[int, str] = {
    0x01: "computer",
    0x02: "phone",
    0x03: "networking",
    0x04: "audio",
    0x05: "peripheral",
    0x06: "imaging",
}


class BTClassicScanner(BaseScanner):
    """Discovers Bluetooth Classic devices via inquiry scans."""

    def __init__(self, config: dict, output_queue, location_id: str = "unknown"):
        super().__init__(config=config, output_queue=output_queue, location_id=location_id)
        bt_cfg = config.get("scanners", {}).get("bt_classic", {})
        self.inquiry_duration: int = bt_cfg.get("inquiry_duration", 8)
        self.inquiry_interval: int = bt_cfg.get("inquiry_interval", 120)

    @property
    def scanner_name(self) -> str:
        return "bt_classic"

    @property
    def source_type(self) -> SourceType:
        return SourceType.BT_CLASSIC

    # ------------------------------------------------------------------
    # Inquiry
    # ------------------------------------------------------------------

    def _run_inquiry(self) -> list:
        """Execute a Bluetooth Classic inquiry and return discovered devices.

        Returns a list of dicts, each with keys:
            address  – BT MAC address (str)
            name     – device name or None
            device_class – integer Class of Device value

        The real implementation would shell out to ``bluetoothctl`` or use
        PyBluez; tests mock this method directly.
        """
        # Stub — overridden / mocked in tests and by real adapter code.
        return []

    # ------------------------------------------------------------------
    # Device class parsing
    # ------------------------------------------------------------------

    def _parse_device_class(self, device_class: int) -> str:
        """Extract the major device class from a 24-bit CoD integer.

        Bits 8-12 carry the major device class per the Bluetooth SIG spec.
        """
        major = (device_class >> 8) & 0x1F
        return _MAJOR_DEVICE_CLASS.get(major, "unknown")

    # ------------------------------------------------------------------
    # Scan loop
    # ------------------------------------------------------------------

    def _scan_loop(self) -> None:
        """Continuously run inquiries until the stop event is set."""
        while not self._stop_event.is_set():
            try:
                devices = self._run_inquiry()
            except OSError:
                self._logger.warning(
                    "Bluetooth inquiry failed (adapter error); will retry in %ss",
                    self.inquiry_interval,
                )
                self._stop_event.wait(timeout=self.inquiry_interval)
                continue

            for dev in devices:
                address: str = dev["address"]
                name = dev.get("name")
                raw_class: int = dev.get("device_class", 0)
                class_name = self._parse_device_class(raw_class)

                appearance = DeviceAppearance(
                    device_id=f"btc:{address}",
                    source_type=SourceType.BT_CLASSIC,
                    timestamp=time.time(),
                    location_id=self.location_id,
                    mac=address,
                    metadata={
                        "device_name": name,
                        "device_class": class_name,
                        "device_class_name": class_name,
                        "device_class_raw": raw_class,
                    },
                )
                self._emit(appearance)

            self._stop_event.wait(timeout=self.inquiry_interval)
