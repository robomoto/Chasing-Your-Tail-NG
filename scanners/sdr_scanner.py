"""Sub-GHz scanner via RTL-SDR + rtl_433."""
import json
import logging
import subprocess
import time

from scanners.base_scanner import BaseScanner, DeviceAppearance, SourceType

logger = logging.getLogger(__name__)


class SDRScanner(BaseScanner):
    """Wraps rtl_433 subprocess for sub-GHz protocol decoding."""

    PROTOCOL_MOBILITY = {
        "TPMS": "mobile",
        "Tire": "mobile",
        "Toyota": "mobile",
        "Ford": "mobile",
        "Schrader": "mobile",
        "Citroen": "mobile",
        "Hyundai": "mobile",
        "Acurite": "stationary",
        "security": "stationary",
        "door": "stationary",
        "window": "stationary",
        "motion": "stationary",
        "weather": "stationary",
        "temperature": "stationary",
        "rain": "stationary",
    }

    # Known TPMS brand keywords for device ID classification
    _TPMS_KEYWORDS = {"tpms", "tire", "toyota", "ford", "schrader", "citroen", "hyundai"}

    def __init__(self, config: dict, output_queue, location_id: str = "unknown"):
        super().__init__(config=config, output_queue=output_queue, location_id=location_id)
        sdr_config = config.get("scanners", {}).get("sdr", {})
        self._rtl433_path = sdr_config.get("rtl_433_path", "/usr/bin/rtl_433")
        self._device_index = sdr_config.get("device_index", 0)
        self._gain = sdr_config.get("gain", None)
        self._process = None

    @property
    def scanner_name(self) -> str:
        return "sdr"

    @property
    def source_type(self) -> SourceType:
        return SourceType.SUBGHZ

    def _parse_rtl433_json(self, line: str) -> dict | None:
        """Parse a JSON line from rtl_433 output.

        Returns dict with all fields from the JSON, or None if invalid.
        """
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return None
            return data
        except (json.JSONDecodeError, ValueError):
            return None

    def _make_device_id(self, parsed: dict) -> str:
        """Generate a device ID string from parsed rtl_433 data.

        TPMS devices get 'tpms:<id>' format.
        Others get 'subghz:<model>:<id>' or 'subghz:<model>' if no id.
        """
        model = parsed.get("model", "unknown")
        device_id_val = parsed.get("id")

        # Check if this is a TPMS device
        model_lower = model.lower()
        type_field = parsed.get("type", "")
        type_lower = type_field.lower() if isinstance(type_field, str) else ""

        is_tpms = False
        for keyword in self._TPMS_KEYWORDS:
            if keyword in model_lower or keyword in type_lower:
                is_tpms = True
                break

        if is_tpms and device_id_val is not None:
            return f"tpms:{device_id_val}"

        if device_id_val is not None:
            return f"subghz:{model}:{device_id_val}"

        return f"subghz:{model}"

    def _classify_mobility(self, model: str) -> bool | None:
        """Classify whether a model is stationary or mobile based on protocol table.

        Returns True for stationary, False for mobile, None for unknown.
        Case-insensitive substring matching against PROTOCOL_MOBILITY keys.
        """
        model_lower = model.lower()
        for key, value in self.PROTOCOL_MOBILITY.items():
            if key.lower() in model_lower:
                return value == "stationary"
        return None

    def _scan_loop(self) -> None:
        """Main scan loop — runs rtl_433 as subprocess and processes JSON output."""
        cmd = [self._rtl433_path, "-F", "json", "-M", "time:utc", "-M", "level"]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            self._logger.error("rtl_433 binary not found at %s", self._rtl433_path)
            return
        except OSError as e:
            self._logger.error("Failed to start rtl_433: %s", e)
            return

        try:
            for raw_line in self._process.stdout:
                if self._stop_event.is_set():
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                parsed = self._parse_rtl433_json(line)
                if parsed is None:
                    continue

                device_id = self._make_device_id(parsed)
                is_stationary = self._classify_mobility(parsed.get("model", ""))

                appearance = DeviceAppearance(
                    device_id=device_id,
                    source_type=self.source_type,
                    timestamp=time.time(),
                    location_id=self.location_id,
                    is_stationary=is_stationary,
                    metadata=parsed,
                )

                self._emit(appearance)

        except OSError as e:
            self._logger.error("rtl_433 process error: %s", e)
        finally:
            if self._process is not None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except Exception:
                    pass
                self._process = None
