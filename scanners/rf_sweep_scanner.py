"""RF wideband sweep via rtl_power — baseline + anomaly detection."""
import json
import logging
import subprocess
import time
from typing import Dict, List, Optional

from scanners.base_scanner import BaseScanner, SourceType

logger = logging.getLogger(__name__)


class RFSweepScanner(BaseScanner):
    """Wideband RF spectrum sweep for bug/transmitter detection."""

    def __init__(self, config: dict, output_queue=None, location_id: str = "unknown"):
        super().__init__(config=config, output_queue=output_queue, location_id=location_id)
        rf_cfg = config.get("rf_sweep", {})
        self.freq_start = rf_cfg.get("freq_start", "24M")
        self.freq_end = rf_cfg.get("freq_end", "1766M")
        self.rtl_power_path = rf_cfg.get("rtl_power_path", "rtl_power")
        self.freq_start_mhz = rf_cfg.get("freq_start_mhz")
        self.freq_end_mhz = rf_cfg.get("freq_end_mhz")
        self.bin_size_hz = rf_cfg.get("bin_size_hz", 1000000)
        self.integration_interval = rf_cfg.get("integration_interval", 1)

    @property
    def scanner_name(self) -> str:
        return "rf_sweep"

    @property
    def source_type(self) -> SourceType:
        return SourceType.RF_SWEEP

    def _scan_loop(self) -> None:
        """Manual-only scanner; just wait for stop signal."""
        self._stop_event.wait()

    def run_sweep(self) -> dict:
        """Run rtl_power and parse CSV output into freq_mhz -> power_dbm map."""
        # Build frequency range string
        if self.freq_start_mhz is not None and self.freq_end_mhz is not None:
            freq_range = f"{self.freq_start_mhz}M:{self.freq_end_mhz}M:{self.bin_size_hz}"
        else:
            freq_range = f"{self.freq_start}:{self.freq_end}:1M"

        try:
            result = subprocess.run(
                [self.rtl_power_path, "-f", freq_range, "-g", "40",
                 "-i", str(self.integration_interval), "-1"],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return {}

        freq_bins: Dict[float, float] = {}
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue
            try:
                hz_low = float(parts[2])
                hz_high = float(parts[3])
                hz_step = float(parts[4])
                # num_samples = int(parts[5])
                db_values = [float(v) for v in parts[6:] if v.strip()]
            except (ValueError, IndexError):
                continue

            # Each dB value corresponds to a frequency bin starting at hz_low
            for i, db in enumerate(db_values):
                freq_hz = hz_low + i * hz_step
                freq_mhz = freq_hz / 1_000_000.0
                # If same freq appears in multiple rows, keep the latest value
                freq_bins[freq_mhz] = db

        return {
            "freq_bins": freq_bins,
            "timestamp": time.time(),
        }

    def save_baseline(self, sweep_data: dict, path: str) -> None:
        """Write sweep data as JSON. Float keys become strings for JSON compat."""
        serializable = {
            "freq_bins": {str(k): v for k, v in sweep_data.get("freq_bins", {}).items()},
            "timestamp": sweep_data.get("timestamp", 0.0),
        }
        with open(path, "w") as f:
            json.dump(serializable, f)

    def load_baseline(self, path: str) -> dict:
        """Read JSON baseline, converting string keys back to floats."""
        try:
            with open(path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

        if "freq_bins" in data:
            data["freq_bins"] = {float(k): v for k, v in data["freq_bins"].items()}
        return data

    def compare_to_baseline(self, sweep_data: dict, baseline: dict,
                            threshold_db: float = 10.0) -> list:
        """Compare sweep to baseline; return anomalies where power exceeds baseline + threshold.

        Returns list of dicts with keys: freq, measured_db, baseline_db, delta_db.
        """
        anomalies: List[dict] = []
        sweep_bins = sweep_data.get("freq_bins", {})
        baseline_bins = baseline.get("freq_bins", {})

        for freq, measured in sweep_bins.items():
            freq = float(freq)
            if freq not in baseline_bins:
                continue
            baseline_db = baseline_bins[freq]
            # In dBm, higher (less negative) means more power.
            # delta = measured - baseline; positive means stronger signal.
            delta = measured - baseline_db
            if delta >= threshold_db:
                anomalies.append({
                    "freq": freq,
                    "measured_db": measured,
                    "baseline_db": baseline_db,
                    "delta_db": delta,
                })

        return anomalies
