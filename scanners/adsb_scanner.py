"""ADS-B aircraft tracking via dump1090/readsb."""
import time
import logging

import requests

from scanners.base_scanner import BaseScanner, DeviceAppearance, SourceType

logger = logging.getLogger(__name__)


class ADSBScanner(BaseScanner):
    """Tracks aircraft via ADS-B transponders using dump1090."""

    def __init__(self, config: dict, output_queue, location_id: str = "unknown"):
        super().__init__(config=config, output_queue=output_queue, location_id=location_id)
        adsb_cfg = config.get("scanners", {}).get("adsb", {})
        self.dump1090_url = adsb_cfg.get("dump1090_url", "http://localhost:8080")
        self.poll_interval = adsb_cfg.get("poll_interval", 5)
        self.suspicious_registrations = [
            s.upper() for s in adsb_cfg.get("suspicious_registrations", [])
        ]

    @property
    def scanner_name(self) -> str:
        return "adsb"

    @property
    def source_type(self) -> SourceType:
        return SourceType.AIRCRAFT

    def _poll_dump1090(self) -> list:
        """GET aircraft.json from dump1090 and return the aircraft list."""
        try:
            resp = requests.get(f"{self.dump1090_url}/data/aircraft.json")
            resp.raise_for_status()
            data = resp.json()
            return data.get("aircraft", [])
        except Exception:
            return []

    def _check_suspicious_registration(self, icao_hex: str) -> bool:
        """Check if an ICAO hex code is in the suspicious registrations list."""
        return icao_hex.upper() in self.suspicious_registrations

    def _scan_loop(self) -> None:
        """Poll dump1090 and emit DeviceAppearance for each aircraft."""
        while not self._stop_event.is_set():
            aircraft_list = self._poll_dump1090()
            for ac in aircraft_list:
                hex_code = ac.get("hex", "unknown")
                metadata = dict(ac)
                metadata["suspicious"] = self._check_suspicious_registration(hex_code)
                appearance = DeviceAppearance(
                    device_id=f"icao:{hex_code}",
                    source_type=SourceType.AIRCRAFT,
                    timestamp=time.time(),
                    location_id=self.location_id,
                    metadata=metadata,
                )
                self._emit(appearance)
            self._stop_event.wait(timeout=self.poll_interval)
