"""Handheld session importer — ingests CSV from ESP32 handheld."""
import csv
import io
import logging
from pathlib import Path

from scanners.base_scanner import DeviceAppearance, SourceType

logger = logging.getLogger(__name__)


class HandheldImporter:
    """Imports CSV session files from the ESP32 handheld device."""

    def __init__(self, config: dict):
        self.config = config
        handheld_cfg = config.get("handheld", {})
        self.import_dir = handheld_cfg.get("import_dir", "./handheld_imports")
        self.location_id = handheld_cfg.get("location_id", "handheld")

    def import_session(self, csv_path: str) -> list:
        """Read CSV file, skip comment lines, parse each data row, return list of DeviceAppearance."""
        try:
            path = Path(csv_path)
            if not path.exists():
                logger.warning("CSV file not found: %s", csv_path)
                return []

            text = path.read_text()
        except OSError as e:
            logger.error("Error reading CSV file %s: %s", csv_path, e)
            return []

        # Filter out comment lines (starting with #), keep header + data
        data_lines = [line for line in text.splitlines() if not line.startswith("#")]

        if not data_lines:
            return []

        reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
        appearances = []
        for row in reader:
            appearance = self.parse_csv_row(row)
            if appearance is not None:
                appearances.append(appearance)

        return appearances

    def parse_csv_row(self, row: dict) -> DeviceAppearance | None:
        """Parse a single CSV row dict into a DeviceAppearance, or None if invalid."""
        try:
            device_id = row.get("device_id")
            timestamp_raw = row.get("timestamp")

            if not device_id or not timestamp_raw:
                return None

            timestamp = float(timestamp_raw)
        except (ValueError, TypeError):
            return None

        mac = row.get("mac") or None
        ssid = row.get("ssid", "")
        ssids_probed = [ssid] if ssid else []

        signal_strength = None
        rssi_raw = row.get("rssi")
        if rssi_raw:
            try:
                signal_strength = float(rssi_raw)
            except (ValueError, TypeError):
                pass

        metadata = {}
        for float_key in ("lat", "lon"):
            val = row.get(float_key)
            if val:
                try:
                    metadata[float_key] = float(val)
                except (ValueError, TypeError):
                    pass

        for int_key in ("window_flags", "appearance_count"):
            val = row.get(int_key)
            if val:
                try:
                    metadata[int_key] = int(val)
                except (ValueError, TypeError):
                    pass

        return DeviceAppearance(
            device_id=device_id,
            source_type=SourceType.HANDHELD_IMPORT,
            timestamp=timestamp,
            location_id=self.location_id,
            mac=mac,
            ssids_probed=ssids_probed,
            signal_strength=signal_strength,
            metadata=metadata,
        )

    def get_session_metadata(self, csv_path: str) -> dict | None:
        """Read first line of file; if it's a comment header, parse key=value pairs."""
        try:
            path = Path(csv_path)
            if not path.exists():
                return None

            with open(path, "r") as f:
                first_line = f.readline().strip()
        except OSError:
            return None

        if not first_line.startswith("# "):
            return None

        # Strip the "# " prefix and parse comma-separated key=value pairs
        header_content = first_line[2:]
        metadata = {}
        for pair in header_content.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                metadata[key.strip()] = value.strip()

        return metadata if metadata else None
