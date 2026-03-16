# Base Station: Detailed Upgrade Plan

Actionable, code-level implementation plan for upgrading CYT from WiFi-only to multi-sensor base station. Each phase is designed so that existing WiFi/Kismet functionality continues working at every boundary.

---

## Phase 1: Foundation (No New Hardware, $0)

**Goal:** Introduce the scanner abstraction layer, refactor the data model, create the orchestrator, and wrap existing WiFi/Kismet functionality as the first scanner -- all without changing any user-visible behavior.

### 1.1 New File: `scanners/__init__.py`

```python
# Empty file, makes scanners/ a package
```

### 1.2 New File: `scanners/base_scanner.py`

This is the single most important new file. It defines the abstract base class all scanners implement, plus the new `SourceType` enum and the upgraded `DeviceAppearance` dataclass.

```python
"""Abstract base class for all CYT scanners."""
import threading
import logging
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from queue import Queue

logger = logging.getLogger(__name__)


class SourceType(Enum):
    WIFI = "wifi"
    BLE = "ble"
    BT_CLASSIC = "bt_classic"
    SUBGHZ = "subghz"
    LORA = "lora"
    DRONE = "drone"
    AIRCRAFT = "aircraft"
    RF_SWEEP = "rf_sweep"
    HANDHELD_IMPORT = "handheld_import"


class ScannerState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class DeviceAppearance:
    """Universal device appearance record.

    This replaces the old DeviceAppearance that was keyed on MAC.
    The ``device_id`` field is the primary key across all source types.
    For WiFi devices, device_id == mac address (backward-compatible).
    """
    device_id: str
    source_type: SourceType
    timestamp: float
    location_id: str
    signal_strength: Optional[float] = None
    device_type: Optional[str] = None
    mac: Optional[str] = None           # Still populated for WiFi/BLE/BT
    ssids_probed: List[str] = field(default_factory=list)
    payload_hash: Optional[str] = None  # For BLE tracker correlation
    frequency_mhz: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_stationary: Optional[bool] = None


class BaseScanner(ABC):
    """Abstract base class for all scanner threads.

    Subclasses must implement:
        _scan_loop()  -- the main scanning logic, runs in a daemon thread
        scanner_name  -- property returning a human-readable name

    The base class provides:
        start() / stop() / pause() / resume()
        state property
        Internal queue reference for pushing DeviceAppearance objects
    """

    def __init__(self, config: dict, output_queue: Queue, location_id: str = "unknown"):
        self.config = config
        self._output_queue = output_queue
        self.location_id = location_id
        self._state = ScannerState.STOPPED
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused by default
        self.logger = logging.getLogger(f"cyt.scanner.{self.scanner_name}")

    @property
    @abstractmethod
    def scanner_name(self) -> str:
        """Human-readable scanner name, e.g. 'wifi', 'ble'."""
        ...

    @abstractmethod
    def _scan_loop(self) -> None:
        """Main scan loop. Runs inside a daemon thread.

        Must check self._stop_event.is_set() periodically to allow clean shutdown.
        Must call self._pause_event.wait() to honor pause requests.
        Must call self._emit(appearance) to push results.
        """
        ...

    def _emit(self, appearance: DeviceAppearance) -> None:
        """Push a DeviceAppearance onto the shared queue."""
        self._output_queue.put(appearance)

    @property
    def state(self) -> ScannerState:
        return self._state

    def start(self) -> None:
        if self._state == ScannerState.RUNNING:
            self.logger.warning(f"{self.scanner_name} already running")
            return
        self._stop_event.clear()
        self._pause_event.set()
        self._state = ScannerState.STARTING
        self._thread = threading.Thread(
            target=self._run_wrapper, name=f"scanner-{self.scanner_name}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()  # Unpause so thread can exit
        self._state = ScannerState.STOPPED
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

    def pause(self) -> None:
        self._pause_event.clear()
        self._state = ScannerState.PAUSED

    def resume(self) -> None:
        self._pause_event.set()
        self._state = ScannerState.RUNNING

    def _run_wrapper(self) -> None:
        try:
            self._state = ScannerState.RUNNING
            self._scan_loop()
        except Exception as e:
            self.logger.error(f"{self.scanner_name} crashed: {e}", exc_info=True)
            self._state = ScannerState.ERROR
        finally:
            if self._state != ScannerState.ERROR:
                self._state = ScannerState.STOPPED
```

### 1.3 New File: `scanners/wifi_scanner.py`

Wraps the existing Kismet SQLite polling as a `BaseScanner`. This is NOT a rewrite of the Kismet integration -- it reuses `SecureKismetDB` and `load_appearances_from_kismet` directly.

```python
"""WiFi scanner -- wraps existing Kismet SQLite polling as a BaseScanner."""
import glob
import os
import time
import logging
from queue import Queue

from scanners.base_scanner import BaseScanner, DeviceAppearance, SourceType
from secure_database import SecureKismetDB

logger = logging.getLogger(__name__)


class WiFiScanner(BaseScanner):

    @property
    def scanner_name(self) -> str:
        return "wifi"

    def __init__(self, config: dict, output_queue: Queue, location_id: str = "unknown"):
        super().__init__(config, output_queue, location_id)
        self._db_pattern = config.get("paths", {}).get("kismet_logs", "/tmp/*.kismet")
        scanner_cfg = config.get("scanners", {}).get("wifi", {})
        self._check_interval = scanner_cfg.get("check_interval",
                                                config.get("timing", {}).get("check_interval", 60))
        self._last_poll_time: float = 0.0

    def _find_latest_db(self) -> str | None:
        files = glob.glob(self._db_pattern)
        if not files:
            return None
        return max(files, key=os.path.getmtime)

    def _scan_loop(self) -> None:
        """Poll Kismet DB every check_interval seconds, emit DeviceAppearance objects."""
        while not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            db_path = self._find_latest_db()
            if not db_path:
                self.logger.warning("No Kismet DB found, retrying...")
                self._stop_event.wait(self._check_interval)
                continue

            try:
                poll_start = time.time()
                with SecureKismetDB(db_path) as db:
                    # Get devices seen since last poll (or last 5 min on first run)
                    since = self._last_poll_time if self._last_poll_time else (poll_start - 300)
                    devices = db.get_devices_by_time_range(since)

                    for device in devices:
                        mac = device.get("mac", "")
                        if not mac:
                            continue

                        # Extract SSIDs
                        ssids = []
                        dd = device.get("device_data") or {}
                        dot11 = dd.get("dot11.device", {})
                        if isinstance(dot11, dict):
                            probe = dot11.get("dot11.device.last_probed_ssid_record", {})
                            if isinstance(probe, dict):
                                ssid = probe.get("dot11.probedssid.ssid")
                                if ssid:
                                    ssids = [ssid]

                        appearance = DeviceAppearance(
                            device_id=mac,                # WiFi: device_id == MAC
                            source_type=SourceType.WIFI,
                            timestamp=device.get("last_time", poll_start),
                            location_id=self.location_id,
                            mac=mac,
                            ssids_probed=ssids,
                            device_type=device.get("type"),
                        )
                        self._emit(appearance)

                self._last_poll_time = poll_start

            except Exception as e:
                self.logger.error(f"WiFi scan cycle failed: {e}")

            self._stop_event.wait(self._check_interval)
```

### 1.4 New File: `scanner_orchestrator.py`

The central thread manager. Reads config to decide which scanners to enable, starts/stops them, reads from the shared queue, and feeds `SurveillanceDetector`.

```python
"""Scanner orchestrator -- manages scanner threads and feeds SurveillanceDetector."""
import logging
import threading
import time
from queue import Queue, Empty
from typing import Dict, Optional, Callable

from scanners.base_scanner import BaseScanner, DeviceAppearance, ScannerState

logger = logging.getLogger(__name__)


class ScannerOrchestrator:
    """Manages all scanner threads and the shared DeviceAppearance queue.

    Usage:
        orchestrator = ScannerOrchestrator(config, on_appearance=callback)
        orchestrator.register_scanner(wifi_scanner)
        orchestrator.register_scanner(ble_scanner)
        orchestrator.start_all()
        ...
        orchestrator.stop_all()
    """

    def __init__(self, config: dict,
                 on_appearance: Optional[Callable[[DeviceAppearance], None]] = None):
        self.config = config
        self._queue: Queue[DeviceAppearance] = Queue(maxsize=10000)
        self._scanners: Dict[str, BaseScanner] = {}
        self._on_appearance = on_appearance
        self._consumer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._appearances_processed: int = 0

    @property
    def queue(self) -> Queue:
        return self._queue

    def register_scanner(self, scanner: BaseScanner) -> None:
        """Register a scanner instance. Must be called before start_all()."""
        self._scanners[scanner.scanner_name] = scanner
        logger.info(f"Registered scanner: {scanner.scanner_name}")

    def get_scanner(self, name: str) -> Optional[BaseScanner]:
        return self._scanners.get(name)

    def get_scanner_states(self) -> Dict[str, str]:
        """Return {scanner_name: state_string} for GUI display."""
        return {name: s.state.value for name, s in self._scanners.items()}

    def start_all(self) -> None:
        """Start all registered scanners and the consumer thread."""
        self._stop_event.clear()

        # Start consumer thread (reads queue, dispatches to callback)
        self._consumer_thread = threading.Thread(
            target=self._consume_loop, name="orchestrator-consumer", daemon=True
        )
        self._consumer_thread.start()

        # Start each scanner
        for name, scanner in self._scanners.items():
            scanner_cfg = self.config.get("scanners", {}).get(name, {})
            if scanner_cfg.get("enabled", True):
                logger.info(f"Starting scanner: {name}")
                scanner.start()
            else:
                logger.info(f"Scanner disabled in config: {name}")

    def stop_all(self) -> None:
        """Stop all scanners and the consumer thread."""
        self._stop_event.set()
        for name, scanner in self._scanners.items():
            logger.info(f"Stopping scanner: {name}")
            scanner.stop()
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=10)

    def _consume_loop(self) -> None:
        """Consumer thread: read DeviceAppearance from queue, dispatch."""
        while not self._stop_event.is_set():
            try:
                appearance = self._queue.get(timeout=1.0)
                self._appearances_processed += 1
                if self._on_appearance:
                    try:
                        self._on_appearance(appearance)
                    except Exception as e:
                        logger.error(f"Appearance callback error: {e}")
            except Empty:
                continue
```

### 1.5 Modify: `surveillance_detector.py`

**What changes:** `DeviceAppearance` and `SuspiciousDevice` dataclasses are replaced with imports from `scanners.base_scanner`. The `device_history` dict is re-keyed from `mac` to `device_id`. A compatibility shim preserves the old `add_device_appearance(mac=..., ...)` call signature.

**Current signatures that change:**

```python
# CURRENT (surveillance_detector.py line 17-25)
@dataclass
class DeviceAppearance:
    mac: str
    timestamp: float
    location_id: str
    ssids_probed: List[str]
    signal_strength: Optional[float] = None
    device_type: Optional[str] = None

# CURRENT (line 28-36)
@dataclass
class SuspiciousDevice:
    mac: str
    persistence_score: float
    appearances: List[DeviceAppearance]
    reasons: List[str]
    first_seen: datetime
    last_seen: datetime
    total_appearances: int
    locations_seen: List[str]
```

**New approach:**

```python
# DELETE the local DeviceAppearance dataclass.
# IMPORT from scanners.base_scanner instead:
from scanners.base_scanner import DeviceAppearance, SourceType

# SuspiciousDevice: rename 'mac' field to 'device_id', keep 'mac' as alias property
@dataclass
class SuspiciousDevice:
    device_id: str                        # NEW: was 'mac'
    source_type: SourceType               # NEW
    persistence_score: float
    appearances: List[DeviceAppearance]
    reasons: List[str]
    first_seen: datetime
    last_seen: datetime
    total_appearances: int
    locations_seen: List[str]

    @property
    def mac(self) -> str:
        """Backward-compat alias -- returns device_id (which IS the MAC for WiFi)."""
        return self.device_id
```

**`SurveillanceDetector` method changes:**

```python
class SurveillanceDetector:
    def __init__(self, config: Dict):
        # ... existing code ...
        self.device_history = defaultdict(list)  # key changes from mac -> device_id

    # NEW primary entry point (called by orchestrator consumer):
    def add_appearance(self, appearance: DeviceAppearance) -> None:
        """Add a DeviceAppearance (from any scanner) to the history."""
        self.appearances.append(appearance)
        self.device_history[appearance.device_id].append(appearance)

    # KEEP old entry point as compatibility shim:
    def add_device_appearance(self, mac: str, timestamp: float, location_id: str,
                              ssids_probed: List[str] = None, signal_strength: float = None,
                              device_type: str = None) -> None:
        """Legacy shim -- wraps old MAC-based call into new DeviceAppearance."""
        appearance = DeviceAppearance(
            device_id=mac,
            source_type=SourceType.WIFI,
            timestamp=timestamp,
            location_id=location_id,
            mac=mac,
            ssids_probed=ssids_probed or [],
            signal_strength=signal_strength,
            device_type=device_type,
        )
        self.add_appearance(appearance)

    def analyze_surveillance_patterns(self) -> List[SuspiciousDevice]:
        # Change: iterate device_history.items() -- key is now device_id
        # Change: SuspiciousDevice constructor uses device_id= instead of mac=
        # Change: determine source_type from first appearance in list
        # Everything else stays the same
        ...
```

**`load_appearances_from_kismet` function:** Keep it unchanged. It calls `detector.add_device_appearance(mac=..., ...)` which now hits the compatibility shim. Zero changes needed to callers.

**Import changes in this file:**

```python
# ADD at top:
from scanners.base_scanner import DeviceAppearance, SourceType
# REMOVE the local DeviceAppearance dataclass (lines 17-25)
```

### 1.6 Modify: `surveillance_analyzer.py`

Minimal changes in Phase 1. The `SurveillanceAnalyzer` class gains an optional `ScannerOrchestrator` but falls back to the existing direct-Kismet path if no orchestrator is provided.

**Changes:**

```python
# ADD import at top:
from scanner_orchestrator import ScannerOrchestrator
from scanners.wifi_scanner import WiFiScanner

class SurveillanceAnalyzer:
    def __init__(self, config_path: str = 'config.json', use_orchestrator: bool = False):
        # ... existing init code ...

        # NEW: optional orchestrator mode
        self._orchestrator = None
        if use_orchestrator:
            self._orchestrator = ScannerOrchestrator(
                self.config,
                on_appearance=self.detector.add_appearance
            )
            wifi = WiFiScanner(self.config, self._orchestrator.queue)
            self._orchestrator.register_scanner(wifi)

    # Existing analyze_kismet_data() method stays unchanged.
    # The orchestrator path is only used when explicitly enabled.
```

### 1.7 New File: `session_db.py`

```python
"""Historical session database for cross-session analysis."""
import sqlite3
import json
import time
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,                -- 'base_station' | 'handheld'
    start_time REAL NOT NULL,
    end_time REAL,
    device_count INTEGER DEFAULT 0,
    gps_lat REAL,
    gps_lon REAL
);

CREATE TABLE IF NOT EXISTS device_sightings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    lat REAL,
    lon REAL,
    rssi REAL,
    metadata TEXT,                       -- JSON
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    persistence_score REAL,
    reasons TEXT,                        -- JSON array
    locations TEXT,                      -- JSON array
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_sightings_device ON device_sightings(device_id);
CREATE INDEX IF NOT EXISTS idx_sightings_session ON device_sightings(session_id);
CREATE INDEX IF NOT EXISTS idx_sightings_time ON device_sightings(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts(device_id);
"""


class SessionDB:
    """SQLite session database for cross-session analysis."""

    def __init__(self, db_path: str = "./cyt_sessions.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        self._conn = sqlite3.connect(self.db_path, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,)
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    def start_session(self, session_id: str, source: str = "base_station",
                      lat: float = None, lon: float = None) -> None:
        self._conn.execute(
            "INSERT INTO sessions (session_id, source, start_time, gps_lat, gps_lon) VALUES (?, ?, ?, ?, ?)",
            (session_id, source, time.time(), lat, lon)
        )
        self._conn.commit()

    def end_session(self, session_id: str, device_count: int = 0) -> None:
        self._conn.execute(
            "UPDATE sessions SET end_time = ?, device_count = ? WHERE session_id = ?",
            (time.time(), device_count, session_id)
        )
        self._conn.commit()

    def record_sighting(self, session_id: str, device_id: str, source_type: str,
                        timestamp: float, lat: float = None, lon: float = None,
                        rssi: float = None, metadata: dict = None) -> None:
        self._conn.execute(
            """INSERT INTO device_sightings
               (session_id, device_id, source_type, timestamp, lat, lon, rssi, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, device_id, source_type, timestamp, lat, lon, rssi,
             json.dumps(metadata) if metadata else None)
        )
        # Commit in batches externally for performance

    def commit(self) -> None:
        self._conn.commit()

    def record_alert(self, session_id: str, device_id: str,
                     persistence_score: float, reasons: list, locations: list) -> None:
        self._conn.execute(
            """INSERT INTO alerts
               (session_id, device_id, persistence_score, reasons, locations, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, device_id, persistence_score,
             json.dumps(reasons), json.dumps(locations), time.time())
        )
        self._conn.commit()

    def get_device_history(self, device_id: str, days: int = 30) -> List[Dict]:
        cutoff = time.time() - (days * 86400)
        rows = self._conn.execute(
            "SELECT * FROM device_sightings WHERE device_id = ? AND timestamp >= ? ORDER BY timestamp",
            (device_id, cutoff)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cross_session_devices(self, min_sessions: int = 2, days: int = 30) -> List[Dict]:
        """Find devices seen across multiple sessions."""
        cutoff = time.time() - (days * 86400)
        rows = self._conn.execute(
            """SELECT device_id, COUNT(DISTINCT session_id) as session_count,
                      COUNT(*) as total_sightings, MIN(timestamp) as first_seen,
                      MAX(timestamp) as last_seen
               FROM device_sightings
               WHERE timestamp >= ?
               GROUP BY device_id
               HAVING COUNT(DISTINCT session_id) >= ?
               ORDER BY session_count DESC""",
            (cutoff, min_sessions)
        ).fetchall()
        return [dict(r) for r in rows]
```

### 1.8 Modify: `config.json`

Add the `scanners` section. Only `wifi` is enabled; all others default to `false`.

```json
{
  "paths": { ... },
  "timing": { ... },
  "search": { ... },
  "scanners": {
    "wifi": {
      "enabled": true,
      "check_interval": 60
    },
    "ble": { "enabled": false },
    "bt_classic": { "enabled": false },
    "sdr": { "enabled": false },
    "lora": { "enabled": false },
    "drone": { "enabled": false },
    "adsb": { "enabled": false },
    "rf_sweep": { "enabled": false },
    "handheld": { "enabled": false }
  },
  "session_db": {
    "path": "./cyt_sessions.db"
  }
}
```

**Key:** The `paths.kismet_logs` field stays where it is. `WiFiScanner` reads it from the existing location. No existing config breaks.

### 1.9 `chasing_your_tail.py` -- NO CHANGES in Phase 1

The main loop continues working exactly as before. It does not use the orchestrator. It still uses `SecureCYTMonitor` directly. The old and new paths coexist:

- **Old path:** `chasing_your_tail.py` -> `SecureCYTMonitor` -> `SecureKismetDB` (direct polling)
- **New path:** `ScannerOrchestrator` -> `WiFiScanner` -> `SecureKismetDB` -> queue -> `SurveillanceDetector`

Users run whichever they prefer. The GUI will eventually switch to the orchestrator path in Phase 5.

### 1.10 Dependency Setup

**pip packages:** None new (all stdlib: `threading`, `queue`, `abc`, `enum`, `dataclasses`).

**System packages:** None.

**Hardware:** None.

### 1.11 Testing Criteria

1. **Unit test: DeviceAppearance compatibility.** Create a `DeviceAppearance` with `device_id=mac, source_type=SourceType.WIFI`. Verify `.mac` field is populated and `.device_id == .mac`.

2. **Unit test: SurveillanceDetector shim.** Call `detector.add_device_appearance(mac="AA:BB:CC:DD:EE:FF", ...)` and verify it ends up in `device_history["AA:BB:CC:DD:EE:FF"]` as a new-style `DeviceAppearance` with `source_type == SourceType.WIFI`.

3. **Integration test: WiFiScanner -> Queue.** Create a `WiFiScanner` pointing at a test `.kismet` file, run for one cycle, verify `DeviceAppearance` objects appear in the queue.

4. **Integration test: Full old-path regression.** Run `python3 chasing_your_tail.py` with a live Kismet DB. Verify it still detects devices, logs MACs to time-window lists, and rotates correctly. This must be byte-for-byte identical behavior.

5. **Integration test: Orchestrator path.** Create an `ScannerOrchestrator` with `WiFiScanner`, start it, let it run for 2 cycles, verify `SurveillanceDetector.device_history` is populated.

6. **Edge case: No Kismet DB.** `WiFiScanner` should log a warning and retry, not crash.

7. **Edge case: Empty Kismet DB.** `WiFiScanner` should emit zero appearances, not crash.

### 1.12 Migration Path

- All existing imports of `DeviceAppearance` from `surveillance_detector` continue to work via a re-export: keep `from scanners.base_scanner import DeviceAppearance` at module level and add `DeviceAppearance` to `surveillance_detector.__all__`.
- `load_appearances_from_kismet()` is unchanged -- still calls the old `add_device_appearance(mac=...)` shim.
- `surveillance_analyzer.py` can be run with `use_orchestrator=False` (default) and works exactly as before.
- `chasing_your_tail.py` is untouched.
- `cyt_gui.py` is untouched.

### 1.13 File Checklist

| Action | File | Lines Changed |
|--------|------|--------------|
| CREATE | `scanners/__init__.py` | ~1 |
| CREATE | `scanners/base_scanner.py` | ~130 |
| CREATE | `scanners/wifi_scanner.py` | ~90 |
| CREATE | `scanner_orchestrator.py` | ~100 |
| CREATE | `session_db.py` | ~140 |
| MODIFY | `surveillance_detector.py` | ~40 (delete old dataclass, add imports, add shim, re-key dict) |
| MODIFY | `surveillance_analyzer.py` | ~15 (add optional orchestrator init) |
| MODIFY | `config.json` | ~20 (add scanners section) |

---

## Phase 2: BLE Tracker Detection (No New Hardware, $0)

**Goal:** Detect AirTags, Samsung SmartTags, Tile trackers, and other BLE Find My devices. Integrate alongside existing WiFi scanning.

### 2.1 New File: `scanners/ble_scanner.py`

```python
"""BLE tracker scanner -- detects AirTags, SmartTags, Tile, etc."""
import asyncio
import time
import hashlib
import struct
import logging
from queue import Queue
from typing import Optional, Dict, List

from scanners.base_scanner import BaseScanner, DeviceAppearance, SourceType

logger = logging.getLogger(__name__)

# Apple Find My manufacturer data company ID
APPLE_COMPANY_ID = 0x004C
# Samsung company ID
SAMSUNG_COMPANY_ID = 0x0075
# Tile company ID (in service data)
TILE_SERVICE_UUID = "0000feed-0000-1000-8000-00805f9b34fb"
# Google Find My Network
GOOGLE_COMPANY_ID = 0x00E0


class BLETrackerClassifier:
    """Classify BLE advertisements into tracker types."""

    @staticmethod
    def classify(device_name: str, manufacturer_data: Dict[int, bytes],
                 service_data: Dict[str, bytes], service_uuids: List[str]) -> Optional[Dict]:
        """Returns {'tracker_type': str, 'payload_hash': str} or None."""

        # Apple Find My (AirTag, AirPods, etc.)
        if APPLE_COMPANY_ID in manufacturer_data:
            mfr = manufacturer_data[APPLE_COMPANY_ID]
            if len(mfr) >= 2:
                # Find My payload: type byte 0x12 with length 0x19
                if mfr[0] == 0x12 and len(mfr) >= 27:
                    # Extract the rotating public key portion for fingerprinting
                    payload_bytes = mfr[2:27]
                    payload_hash = hashlib.sha256(payload_bytes).hexdigest()[:16]
                    return {
                        "tracker_type": "findmy",
                        "payload_hash": payload_hash,
                        "status_byte": mfr[2] if len(mfr) > 2 else None,
                    }
                # AirPods nearby: type byte 0x07
                if mfr[0] == 0x07:
                    payload_hash = hashlib.sha256(mfr).hexdigest()[:16]
                    return {
                        "tracker_type": "findmy_airpods",
                        "payload_hash": payload_hash,
                    }

        # Samsung SmartTag
        if SAMSUNG_COMPANY_ID in manufacturer_data:
            mfr = manufacturer_data[SAMSUNG_COMPANY_ID]
            if len(mfr) >= 4:
                payload_hash = hashlib.sha256(mfr).hexdigest()[:16]
                return {
                    "tracker_type": "smarttag",
                    "payload_hash": payload_hash,
                }

        # Tile (advertises via service data)
        for uuid_str, data in service_data.items():
            if "feed" in uuid_str.lower():
                payload_hash = hashlib.sha256(data).hexdigest()[:16]
                return {
                    "tracker_type": "tile",
                    "payload_hash": payload_hash,
                }

        # Google Find My Device
        if GOOGLE_COMPANY_ID in manufacturer_data:
            mfr = manufacturer_data[GOOGLE_COMPANY_ID]
            if len(mfr) >= 4:
                payload_hash = hashlib.sha256(mfr).hexdigest()[:16]
                return {
                    "tracker_type": "google_findmy",
                    "payload_hash": payload_hash,
                }

        return None


class BLEScanner(BaseScanner):
    """BLE scanner using bleak. Runs asyncio event loop inside its thread."""

    @property
    def scanner_name(self) -> str:
        return "ble"

    def __init__(self, config: dict, output_queue: Queue, location_id: str = "unknown"):
        super().__init__(config, output_queue, location_id)
        ble_cfg = config.get("scanners", {}).get("ble", {})
        self._scan_duration = ble_cfg.get("scan_duration", 10)
        self._scan_interval = ble_cfg.get("scan_interval", 60)
        self._tracker_types = set(ble_cfg.get("tracker_types", ["findmy", "smarttag", "tile"]))
        self._classifier = BLETrackerClassifier()
        # MAC rotation correlation: maps rotating MAC -> (payload_hash, last_seen)
        self._mac_correlation: Dict[str, tuple] = {}
        self._correlation_ttl = 300  # 5 min TTL for MAC correlation entries

    def _scan_loop(self) -> None:
        """Run asyncio BLE scan loop inside this thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_scan_loop())
        finally:
            loop.close()

    async def _async_scan_loop(self) -> None:
        from bleak import BleakScanner

        while not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            try:
                devices = await BleakScanner.discover(
                    timeout=self._scan_duration,
                    return_adv=True
                )

                now = time.time()
                self._prune_correlation_table(now)

                for address, (device, adv_data) in devices.items():
                    mfr_data = adv_data.manufacturer_data or {}
                    svc_data = adv_data.service_data or {}
                    svc_uuids = adv_data.service_uuids or []

                    result = self._classifier.classify(
                        device.name or "",
                        mfr_data,
                        svc_data,
                        svc_uuids,
                    )

                    if result is None:
                        continue

                    tracker_type = result["tracker_type"]
                    if tracker_type not in self._tracker_types:
                        continue

                    payload_hash = result["payload_hash"]
                    device_id = f"{tracker_type}:{payload_hash}"

                    # Track MAC rotation
                    self._mac_correlation[address] = (payload_hash, now)

                    appearance = DeviceAppearance(
                        device_id=device_id,
                        source_type=SourceType.BLE,
                        timestamp=now,
                        location_id=self.location_id,
                        signal_strength=adv_data.rssi,
                        mac=address,
                        payload_hash=payload_hash,
                        device_type=tracker_type,
                        metadata={
                            "device_name": device.name,
                            "tracker_type": tracker_type,
                            "status_byte": result.get("status_byte"),
                        },
                    )
                    self._emit(appearance)

            except ImportError:
                self.logger.error("bleak not installed. Run: pip install bleak>=0.21.0")
                self._state = self._state  # Keep error state
                return
            except Exception as e:
                self.logger.error(f"BLE scan cycle failed: {e}")

            # Wait for next scan interval (minus scan duration)
            pause_time = max(1, self._scan_interval - self._scan_duration)
            self._stop_event.wait(pause_time)

    def _prune_correlation_table(self, now: float) -> None:
        expired = [mac for mac, (_, ts) in self._mac_correlation.items()
                   if now - ts > self._correlation_ttl]
        for mac in expired:
            del self._mac_correlation[mac]
```

### 2.2 Modify: `config.json`

Enable the BLE scanner:

```json
"ble": {
    "enabled": true,
    "scan_duration": 10,
    "scan_interval": 60,
    "tracker_types": ["findmy", "smarttag", "tile", "findmy_airpods", "google_findmy"]
}
```

### 2.3 Modify: `requirements.txt`

Add:

```
bleak>=0.21.0
```

### 2.4 Modify: `scanner_orchestrator.py`

Add BLE scanner auto-registration in a new factory method:

```python
def create_default_scanners(self) -> None:
    """Create and register scanners based on config."""
    from scanners.wifi_scanner import WiFiScanner

    scanners_cfg = self.config.get("scanners", {})

    # WiFi (always available)
    if scanners_cfg.get("wifi", {}).get("enabled", True):
        wifi = WiFiScanner(self.config, self._queue)
        self.register_scanner(wifi)

    # BLE (requires bleak)
    if scanners_cfg.get("ble", {}).get("enabled", False):
        try:
            from scanners.ble_scanner import BLEScanner
            ble = BLEScanner(self.config, self._queue)
            self.register_scanner(ble)
        except ImportError:
            logger.warning("BLE scanner unavailable: bleak not installed")
```

### 2.5 Modify: `surveillance_detector.py`

Add BLE-specific persistence scoring. Inside `_calculate_persistence_score`:

```python
def _calculate_persistence_score(self, appearances: List[DeviceAppearance]) -> Tuple[float, List[str]]:
    # ... existing logic ...

    # NEW: BLE tracker bonus -- a BLE tracker following you is inherently more suspicious
    source_types = set(a.source_type for a in appearances if hasattr(a, 'source_type'))
    if SourceType.BLE in source_types:
        ble_appearances = [a for a in appearances if a.source_type == SourceType.BLE]
        tracker_types = set(a.device_type for a in ble_appearances if a.device_type)
        if tracker_types & {"findmy", "smarttag", "tile"}:
            score = min(score + 0.2, 1.0)
            reasons.append(f"BLE tracker detected ({', '.join(tracker_types)})")

    return score, reasons
```

### 2.6 Dependency Setup

| Item | Details |
|------|---------|
| pip | `pip install bleak>=0.21.0` |
| System | Bluetooth must be enabled: `sudo systemctl enable bluetooth && sudo systemctl start bluetooth` |
| System | User must be in `bluetooth` group: `sudo usermod -aG bluetooth $USER` |
| Hardware | Built-in Pi Bluetooth 5.0 (Pi 4/5) or any USB BLE dongle |

**Important Raspberry Pi note:** On Raspberry Pi OS, the default BlueZ stack works with bleak out of the box. No kernel modules needed. Verify with `bluetoothctl show` -- it should show a controller.

### 2.7 Testing Criteria

1. **Unit test: BLETrackerClassifier.** Feed known manufacturer data byte sequences for AirTag, SmartTag, and Tile. Verify correct `tracker_type` and non-empty `payload_hash`.

2. **Unit test: device_id format.** Verify BLE appearances have `device_id` matching `findmy:<hash>` pattern.

3. **Manual test: AirTag detection.** Place a known AirTag near the Pi. Start the BLE scanner. Verify it appears in the queue with `tracker_type=findmy` within 60 seconds.

4. **Manual test: WiFi still works.** Run the orchestrator with both WiFi and BLE enabled. Verify WiFi devices still appear in `SurveillanceDetector.device_history` alongside BLE devices.

5. **Edge case: No BLE hardware.** If `bleak` fails to find a BLE adapter, the scanner should log an error and enter `ERROR` state without crashing the orchestrator. WiFi continues.

6. **Edge case: bleak not installed.** The `create_default_scanners()` factory catches `ImportError` and skips BLE. WiFi continues.

7. **Edge case: MAC rotation.** Feed two BLE advertisements from different MAC addresses but same payload hash. Verify they produce the same `device_id`.

### 2.8 Migration Path

- Users who don't want BLE keep `"ble": {"enabled": false}` in config (the default from Phase 1).
- Users who want BLE run `pip install bleak` and set `"enabled": true`.
- The old `chasing_your_tail.py` loop is unaffected. It doesn't touch BLE at all.
- `surveillance_analyzer.py` with `use_orchestrator=True` now gets both WiFi and BLE data.

---

## Phase 3: Sub-GHz / TPMS ($32, one RTL-SDR)

**Goal:** Detect TPMS tire pressure sensors, key fobs, security sensors, and other sub-GHz devices using `rtl_433`.

### 3.1 New File: `scanners/sdr_scanner.py`

**Interface:**

```python
class SDRScanner(BaseScanner):
    scanner_name = "sdr"

    def __init__(self, config, output_queue, location_id="unknown"):
        # Reads config.scanners.sdr.device_index (default 0)
        # Reads config.scanners.sdr.protocols (default "all")
        # Reads config.scanners.sdr.frequency (default "433.92M")
        ...

    def _scan_loop(self):
        # Starts rtl_433 as subprocess:
        #   rtl_433 -d <device_index> -F json -M time:utc -M level
        # Reads stdout line by line (JSON per line)
        # Parses each JSON object, extracts:
        #   - model, id, channel, battery_ok, temperature_C, etc.
        #   - For TPMS: tire pressure, tire temperature, tire_id
        # Constructs device_id:
        #   - TPMS: "tpms:<id>"
        #   - Generic: "subghz:<model>:<id>"
        # Sets is_stationary based on protocol lookup table
        # Emits DeviceAppearance with source_type=SourceType.SUBGHZ
        ...

    def stop(self):
        # Terminates rtl_433 subprocess
        # Calls super().stop()
        ...
```

**Stationary lookup table (built into the class):**

```python
STATIONARY_PROTOCOLS = {
    "Acurite-Tower", "Acurite-5n1", "LaCrosse-TX", "Oregon-Scientific",
    "Ambientweather", "Fineoffset-WH",  # Weather stations
    "Honeywell", "DSC-Security", "GE-Security",  # Security sensors
}
MOBILE_PROTOCOLS = {
    "Toyota-TPMS", "Schrader-TPMS", "Ford-TPMS", "Citroen-TPMS",
    "PMV-107J", "Renault-TPMS",  # TPMS
}
# Anything not in either set defaults to is_stationary=None (unknown)
```

### 3.2 New File: `mobility_analyzer.py`

```python
class MobilityAnalyzer:
    """Determines if a device is stationary infrastructure or mobile/following."""

    def __init__(self, config: dict):
        self._location_history: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        # Maps device_id -> [(location_id, timestamp), ...]

    def record_sighting(self, device_id: str, location_id: str, timestamp: float) -> None:
        ...

    def is_mobile(self, device_id: str) -> Optional[bool]:
        """Returns True if seen at 2+ distant locations, False if always same location, None if insufficient data."""
        ...

    def get_rssi_pattern(self, device_id: str, rssi_history: List[Tuple[float, float]]) -> str:
        """Returns 'bell_curve' (stationary pass-by), 'constant' (co-traveling), or 'unknown'."""
        ...
```

### 3.3 Dependencies

| Item | Details |
|------|---------|
| System | `sudo apt-get install rtl-433 rtl-sdr libusb-1.0-0-dev` |
| Hardware | RTL-SDR V4 dongle (~$32) |
| pip | None new |

### 3.4 Config Changes

```json
"sdr": {
    "enabled": true,
    "device_index": 0,
    "protocols": "all",
    "frequency": "433.92M"
}
```

### 3.5 Testing Criteria

1. **Without hardware:** Mock `rtl_433` output by piping JSON lines to stdin. Verify correct `DeviceAppearance` parsing for TPMS, weather station, and security sensor payloads.
2. **With hardware:** Plug in RTL-SDR, start scanner, verify TPMS from nearby cars appears within 2 minutes.
3. **Stationary tagging:** Weather station protocols should get `is_stationary=True`. TPMS should get `is_stationary=False`.
4. **WiFi/BLE unaffected:** Run all three scanners simultaneously.

### 3.6 Migration Path

- SDR scanner is opt-in (`"enabled": false` by default).
- Requires explicit hardware purchase and `rtl_433` installation.
- Zero impact on WiFi-only or WiFi+BLE configurations.

---

## Phase 4: Drones + BT Classic ($0)

**Goal:** Detect drones via Remote ID (BLE broadcast) and WiFi SSID patterns. Add Bluetooth Classic scanning with time-slotting to share the radio with BLE.

### 4.1 New File: `scanners/drone_scanner.py`

```python
class DroneScanner(BaseScanner):
    scanner_name = "drone"

    # Sub-scanner A: Filters BLE advertisements for ASTM F3411 Remote ID
    #   - Registers as a secondary consumer of BLE scan results
    #   - Extracts: serial_number, operator_lat, operator_lon, altitude, speed
    #   - device_id = "drone:<serial_number>"
    #
    # Sub-scanner B: Queries Kismet DB for drone WiFi SSIDs
    #   - Matches patterns: DJI-*, TELLO-*, Skydio-*, ANAFI-*, Autel-*, PARROT-*
    #   - device_id = "drone_ssid:<ssid>"
    #
    # Both push DeviceAppearance with source_type=SourceType.DRONE
```

### 4.2 New File: `scanners/bt_classic_scanner.py`

```python
class BTClassicScanner(BaseScanner):
    scanner_name = "bt_classic"

    # Uses subprocess: bluetoothctl scan on / scan off
    # Alternative: PyBluez bluetooth.discover_devices()
    # inquiry_duration = 5 seconds (config)
    # inquiry_interval = 120 seconds (config)
    # device_id = "btc:<mac_address>"
    # source_type = SourceType.BT_CLASSIC
```

### 4.3 New Class: `BluetoothScheduler` (in `scanner_orchestrator.py`)

```python
class BluetoothScheduler:
    """Time-slots BLE and BT Classic to share the radio.

    Schedule per 60s cycle:
        0-10s:  BLE scan active, BT Classic paused
        10-15s: BT Classic inquiry, BLE paused
        15-60s: Both paused (radio idle)
    """
    def __init__(self, ble_scanner: BaseScanner, btc_scanner: BaseScanner): ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

### 4.4 Dependencies

| Item | Details |
|------|---------|
| pip (optional) | `PyBluez>=0.30` -- falls back to `bluetoothctl` subprocess if unavailable |
| pip (optional) | `opendroneid>=0.7` -- for Remote ID parsing; can use manual ASTM F3411 byte parsing as fallback |
| System | `bluez` (already installed for BLE) |
| Hardware | Same Bluetooth adapter as BLE |

### 4.5 Testing Criteria

1. **Drone SSID detection:** Create a mock Kismet DB with a device named `DJI-MINI3-ABC`. Verify drone scanner detects it.
2. **BLE Remote ID:** Feed a mock BLE advertisement with ASTM F3411 service UUID. Verify serial number extraction.
3. **Time-slotting:** Verify BLE and BT Classic don't scan simultaneously (check pause/resume events).
4. **No regression:** WiFi + BLE + SDR continue working alongside drone + BT Classic.

---

## Phase 5: Data Fusion + GUI ($0)

**Goal:** Implement cross-source correlation rules and upgrade the GUI to a tabbed multi-source dashboard.

### 5.1 New: Cross-Source Correlation Engine (in `scanner_orchestrator.py`)

```python
class FusionEngine:
    """Cross-source correlation between scanner results.

    Rules implemented:
        1. TPMS + WiFi co-occurrence -> 2.0x multiplier (same vehicle)
        2. BLE tracker + WiFi device at same time/location -> 1.3x (AirTag + owner)
        3. Device on base station + handheld -> 1.5x (cross-platform confirm)
        4. Repeated drone serial across sessions -> 2.0x
        5. Repeated aircraft ICAO circling -> 1.5x
        6. LoRa node at multiple distant locations -> 1.5x
    """
    def correlate(self, appearances: List[DeviceAppearance]) -> Dict[str, float]:
        """Returns {device_id: multiplier} for score adjustments."""
        ...
```

### 5.2 Modify: `cyt_gui.py`

Replace the flat layout with `ttk.Notebook` tabs:

```python
class CYTGui:
    def setup_ui(self):
        # ... existing header and status code ...

        # NEW: Replace controls_frame + log_frame with tabbed notebook
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Dashboard (scanner status grid + unified feed)
        self.dashboard_tab = self._create_dashboard_tab()

        # Tab 2: Scanners (per-scanner controls, start/stop)
        self.scanners_tab = self._create_scanners_tab()

        # Tab 3: Analysis (session history, cross-session queries)
        self.analysis_tab = self._create_analysis_tab()

        # Tab 4: RF Sweep (Phase 7, placeholder for now)
        self.rf_tab = self._create_rf_tab()
```

**Scanner status grid widget:**

```python
def _create_scanner_status_grid(self, parent):
    """Grid showing each scanner's state with color indicator.

    | Scanner     | State   | Devices | Last Update |
    |-------------|---------|---------|-------------|
    | WiFi        | Running | 142     | 10s ago     |
    | BLE         | Running | 3       | 45s ago     |
    | Sub-GHz     | Stopped | --      | --          |
    | ...         |         |         |             |
    """
```

**Color coding for detection feed:**

```python
SOURCE_COLORS = {
    SourceType.WIFI: "#00ff41",       # Green
    SourceType.BLE: "#3399ff",        # Blue
    SourceType.SUBGHZ: "#ff9933",     # Orange
    SourceType.DRONE: "#ff3333",      # Red
    SourceType.AIRCRAFT: "#cc66ff",   # Purple
    SourceType.BT_CLASSIC: "#00cccc", # Cyan
    SourceType.LORA: "#ffcc00",       # Yellow
}
```

### 5.3 Modify: `surveillance_detector.py`

Integrate `FusionEngine` multipliers into `_calculate_persistence_score`:

```python
def _calculate_persistence_score(self, appearances):
    # ... existing scoring ...

    # Apply fusion multiplier if available
    if self._fusion_multipliers and device_id in self._fusion_multipliers:
        multiplier = self._fusion_multipliers[device_id]
        score = min(score * multiplier, 1.0)
        reasons.append(f"Cross-source correlation ({multiplier:.1f}x)")
```

### 5.4 Testing Criteria

1. **Fusion: TPMS + WiFi.** Inject a TPMS appearance and a WiFi appearance at the same timestamp/location. Verify 2.0x multiplier applied.
2. **GUI: Tabs render.** Launch GUI, verify all 4 tabs are present and clickable.
3. **GUI: Scanner status grid.** With orchestrator running WiFi + BLE, verify grid shows correct states.
4. **GUI: Color-coded feed.** Inject appearances from multiple source types, verify color coding in detection feed.

---

## Phase 6: ADS-B + LoRa ($50)

**Goal:** Add aircraft tracking via dump1090/ADS-B and LoRa/Meshtastic node detection.

### 6.1 New File: `scanners/adsb_scanner.py`

```python
class ADSBScanner(BaseScanner):
    scanner_name = "adsb"

    # Polls http://localhost:8080/data/aircraft.json every 5 seconds
    # Parses JSON: hex (ICAO), flight, lat, lon, altitude, speed, track
    # device_id = "icao:<hex>"
    # Cross-references against suspicious_aircraft.json allowlist
    # source_type = SourceType.AIRCRAFT
    # Requires: dump1090-mutability or readsb running as system service
    # Requires: dedicated RTL-SDR tuned to 1090 MHz
```

### 6.2 New File: `scanners/lora_scanner.py`

```python
class LoRaScanner(BaseScanner):
    scanner_name = "lora"

    # Reads Meshtastic serial API via meshtastic Python package
    # Extracts: node_id, hop_count, gps_position, node_role, device_name
    # device_id = "lora:<node_id>"  (e.g., "lora:!a1b2c3d4")
    # source_type = SourceType.LORA
    # Mobile vs stationary discrimination:
    #   1. Node role ROUTER/REPEATER = likely infrastructure
    #   2. GPS position tracking (same coords = stationary)
    #   3. Multi-location correlation via MobilityAnalyzer
    #   4. RSSI bell curve analysis
    #   5. Known-infrastructure allowlist (known_lora_nodes.json)
```

### 6.3 Dependencies

| Item | Details |
|------|---------|
| pip | `meshtastic>=2.0` |
| System | `sudo apt-get install dump1090-mutability` (or build `readsb` from source) |
| Hardware | Dedicated RTL-SDR V4 for 1090 MHz (~$32) + 1090 MHz antenna (~$15) |
| Hardware | Heltec V3 LoRa board (~$18) connected via USB serial |

### 6.4 Config Changes

```json
"adsb": {
    "enabled": true,
    "dump1090_url": "http://localhost:8080",
    "poll_interval": 5,
    "suspicious_registrations": "suspicious_aircraft.json",
    "device_index": 1
},
"lora": {
    "enabled": true,
    "method": "serial",
    "serial_port": "/dev/ttyUSB0",
    "baud_rate": 115200,
    "known_nodes_allowlist": "known_lora_nodes.json"
}
```

### 6.5 New Data File: `suspicious_aircraft.json`

```json
{
    "description": "ICAO hex codes of known government/LE aircraft to flag",
    "registrations": {
        "A12345": {"owner": "Example Agency", "type": "Cessna 208"},
        "_comment": "Seed from public FAA registry + ADSB-Exchange data"
    }
}
```

### 6.6 Testing Criteria

1. **ADS-B without hardware:** Mock the dump1090 JSON endpoint. Inject aircraft JSON, verify `DeviceAppearance` with `device_id=icao:A12345`.
2. **LoRa without hardware:** Mock the Meshtastic serial API. Inject node packets, verify correct device_id and metadata extraction.
3. **Suspicious aircraft flagging:** Inject an ICAO hex matching `suspicious_aircraft.json`. Verify persistence score gets flagged.
4. **LoRa infrastructure filtering:** Inject a node with role=ROUTER. Verify `is_stationary=True`.

---

## Phase 7: RF Sweep + Handheld Import ($0)

**Goal:** Add manual RF sweep capability for bug detection and CSV import from ESP32 handheld units.

### 7.1 New File: `scanners/rf_sweep_scanner.py`

```python
class RFSweepScanner(BaseScanner):
    scanner_name = "rf_sweep"

    # NOT always-on. Triggered manually from GUI.
    # On activation:
    #   1. Pauses SDRScanner (releases RTL-SDR dongle)
    #   2. Runs: rtl_power -f <start>:<end>:<step> -g 50 -i 10 -e 60 sweep.csv
    #   3. Parses CSV output into frequency-power pairs
    #   4. Compares against stored baseline (rf_baseline.json)
    #   5. Flags new persistent signals as rf_anomaly:<freq_mhz>
    #   6. Resumes SDRScanner
    #
    # Requires numpy for FFT baseline comparison
```

### 7.2 New File: `scanners/handheld_importer.py`

```python
class HandheldImporter(BaseScanner):
    scanner_name = "handheld"

    # Watches import_dir for new CSV files (or triggered by GUI button)
    # Parses ESP32 handheld CSV format:
    #   timestamp, mac, rssi, ssids_probed, gps_lat, gps_lon
    # For each row:
    #   device_id = mac (same as WiFi)
    #   source_type = SourceType.HANDHELD_IMPORT
    #   Emits DeviceAppearance
    # Cross-correlation handled by FusionEngine:
    #   Device seen on BOTH handheld and base station = 1.5x multiplier
```

### 7.3 Dependencies

| Item | Details |
|------|---------|
| pip | `numpy>=1.24.0` (for RF sweep baseline comparison) |
| System | `rtl_power` (included with `rtl-sdr` package, already installed in Phase 3) |
| Hardware | Same RTL-SDR as Phase 3 (shared, time-slotted) |

### 7.4 RF Sweep GUI Integration (in `cyt_gui.py`)

The RF Sweep tab (placeholder from Phase 5) gets populated:

```python
def _create_rf_tab(self):
    # "Start Sweep" button (triggers RFSweepScanner)
    # "Load Baseline" / "Save Baseline" buttons
    # Canvas widget showing frequency vs power plot
    # Anomaly list: frequency, power delta, classification
```

### 7.5 Testing Criteria

1. **RF Sweep without hardware:** Feed a mock `rtl_power` CSV output. Verify baseline comparison detects new signals.
2. **Handheld import:** Create a sample ESP32 CSV. Trigger import. Verify appearances end up in `SurveillanceDetector` with `source_type=HANDHELD_IMPORT`.
3. **Cross-correlation:** Import handheld data that overlaps with existing WiFi base station data for the same MAC. Verify 1.5x multiplier applied.
4. **SDR pause/resume:** Start SDR scanner, trigger RF sweep, verify SDR pauses and resumes cleanly.

---

## Cross-Cutting Concerns

### Backward Compatibility Guarantee

At every phase boundary, this command must succeed unchanged:

```bash
python3 chasing_your_tail.py
```

This is guaranteed because:
1. `chasing_your_tail.py` does NOT import from `scanners/` or `scanner_orchestrator.py`.
2. `surveillance_detector.py` keeps the old `add_device_appearance(mac=...)` method as a shim.
3. `config.json` additions are in new top-level keys (`scanners`, `session_db`) that the old code ignores.
4. No existing function signatures are removed, only extended.

### Error Isolation

Each scanner runs in its own daemon thread. If a scanner crashes:
- The `BaseScanner._run_wrapper()` catches the exception and sets state to `ERROR`.
- The orchestrator consumer thread continues reading from the queue.
- Other scanners are unaffected.
- The GUI scanner status grid shows the error state.

### Config-Driven Enable/Disable

Every scanner reads `config.scanners.<name>.enabled`. Setting it to `false` means:
- `ScannerOrchestrator.create_default_scanners()` skips it.
- No thread is created.
- No hardware is accessed.
- No import errors (scanner modules are imported lazily inside the factory).

### Import Strategy

All scanner imports in `scanner_orchestrator.py` are **lazy** (inside the factory method, not at module top-level). This means:
- Users without `bleak` installed don't get an `ImportError` when importing the orchestrator.
- Users without `meshtastic` installed can still use WiFi + BLE + SDR.
- Each scanner dependency is isolated.

### Thread Safety

- The `Queue` is thread-safe (stdlib `queue.Queue`).
- `SurveillanceDetector.add_appearance()` must be called ONLY from the consumer thread (single-writer).
- Scanner threads only call `self._emit()` (queue.put), never touch the detector directly.
- GUI updates use `root.after()` to schedule callbacks on the main thread.

### GPS Location Updates

The `location_id` field on `DeviceAppearance` comes from the scanner's `self.location_id` attribute. The orchestrator updates this when GPS position changes:

```python
def update_location(self, location_id: str) -> None:
    """Called by GPS tracker when location changes."""
    for scanner in self._scanners.values():
        scanner.location_id = location_id
```

---

## Implementation Order Summary

| Phase | New Files | Modified Files | Dependencies | Hardware |
|-------|-----------|---------------|-------------|----------|
| 1 | `scanners/__init__.py`, `scanners/base_scanner.py`, `scanners/wifi_scanner.py`, `scanner_orchestrator.py`, `session_db.py` | `surveillance_detector.py`, `surveillance_analyzer.py`, `config.json` | None | None |
| 2 | `scanners/ble_scanner.py` | `scanner_orchestrator.py`, `surveillance_detector.py`, `config.json`, `requirements.txt` | `bleak>=0.21.0` | Built-in BT |
| 3 | `scanners/sdr_scanner.py`, `mobility_analyzer.py` | `scanner_orchestrator.py`, `config.json` | `rtl-433` (system) | RTL-SDR V4 |
| 4 | `scanners/drone_scanner.py`, `scanners/bt_classic_scanner.py` | `scanner_orchestrator.py`, `config.json` | `opendroneid` (optional), `PyBluez` (optional) | None |
| 5 | None | `scanner_orchestrator.py` (FusionEngine), `cyt_gui.py` (tabbed UI), `surveillance_detector.py` (fusion multipliers) | None | None |
| 6 | `scanners/adsb_scanner.py`, `scanners/lora_scanner.py`, `suspicious_aircraft.json`, `known_lora_nodes.json` | `scanner_orchestrator.py`, `config.json` | `meshtastic>=2.0`, `dump1090` (system) | RTL-SDR V4 #2, Heltec V3 |
| 7 | `scanners/rf_sweep_scanner.py`, `scanners/handheld_importer.py` | `cyt_gui.py` (RF Sweep tab) | `numpy>=1.24.0` | None |
