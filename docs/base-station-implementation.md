# Base Station: Implementation Plan

Full sensor expansion for the Raspberry Pi base station. Adds 9 scanner types to the existing WiFi-only CYT system.

## Architecture Overview

### Orchestration: Threading with Queue

Chosen over asyncio (Tkinter incompatibility) and multiprocessing (overkill for IO-bound scanners).

```
Main thread (Tkinter event loop)
  |
  +-- ScannerOrchestrator
        |-- WiFi scanner thread (polls Kismet SQLite every 60s)
        |-- BLE scanner thread (bleak asyncio in thread, 10s scan / 50s pause)
        |-- BT Classic scanner thread (inquiry every 60s, time-slotted with BLE)
        |-- rtl_433 subprocess reader thread (continuous JSON stream)
        |-- LoRa/Meshtastic serial reader thread (continuous)
        |-- dump1090 subprocess reader thread (HTTP poll every 5s)
        |-- RF sweep thread (manual activation only, pauses rtl_433)
        |
        +-- All threads push DeviceAppearance into thread-safe Queue
        |
        +-- Fusion thread: reads Queue, runs cross-source correlation,
            feeds SurveillanceDetector, signals GUI via root.after()
```

### Core Data Model Change

The single most important modification — replaces MAC as primary key with generic `device_id`:

```python
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

@dataclass
class DeviceAppearance:
    device_id: str              # Primary key (replaces mac)
    source_type: SourceType
    timestamp: float
    location_id: str
    signal_strength: Optional[float] = None
    device_type: Optional[str] = None
    mac: Optional[str] = None
    ssids_probed: List[str] = field(default_factory=list)
    payload_hash: Optional[str] = None
    frequency_mhz: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_stationary: Optional[bool] = None
```

### device_id Format by Source

| Source | device_id Format | Example |
|--------|-----------------|---------|
| WiFi | `<mac_address>` | `AA:BB:CC:DD:EE:FF` |
| BLE (AirTag) | `findmy:<payload_hash>` | `findmy:a1b2c3d4e5f6` |
| BLE (SmartTag) | `smarttag:<payload_hash>` | `smarttag:1234abcd` |
| BLE (Tile) | `tile:<payload_hash>` | `tile:5678efgh` |
| BT Classic | `btc:<mac_address>` | `btc:11:22:33:44:55:66` |
| TPMS | `tpms:<sensor_id>` | `tpms:0x1A2B3C4D` |
| Sub-GHz generic | `subghz:<protocol>:<id>` | `subghz:honeywell:12345` |
| LoRa/Meshtastic | `lora:<node_id>` | `lora:!a1b2c3d4` |
| Drone (Remote ID) | `drone:<serial_number>` | `drone:DJI12345678` |
| Drone (WiFi SSID) | `drone_ssid:<ssid>` | `drone_ssid:TELLO-ABC123` |
| Aircraft (ADS-B) | `icao:<hex_code>` | `icao:A12345` |
| RF anomaly | `rf_anomaly:<freq_mhz>` | `rf_anomaly:433.920` |

## Scanner Specifications

### 1. BLE Tracker Scanner (`scanners/ble_scanner.py`)

| Attribute | Value |
|-----------|-------|
| Pip packages | `bleak>=0.21.0` |
| Hardware | Built-in Pi BT 5.0 or USB dongle |
| Execution | Daemon thread, `asyncio.run()` internally |
| Scan cycle | 10s scan, 50s pause (configurable) |

Detects: AirTags, SmartTags, Tile, AirPods (Find My), Google Find My Device, BLE Remote ID (drones).

MAC rotation handling: Maintains short-term correlation table mapping rotating MAC -> payload fingerprint. Persistence engine only sees `device_id` = payload hash.

### 2. Sub-GHz SDR Scanner (`scanners/sdr_scanner.py`)

| Attribute | Value |
|-----------|-------|
| System packages | `rtl-433`, `rtl-sdr`, `libusb-1.0` |
| Hardware | RTL-SDR V4 ($32) |
| Execution | Daemon thread reading rtl_433 JSON stdout |
| Command | `rtl_433 -F json -M time:utc -M level` |

Detects: TPMS (315/433 MHz), key fobs, security sensors, weather stations, Z-Wave, LoRa energy, garage doors.

Stationary tagging: TPMS = always mobile. Security sensors = always stationary. Key fobs = mobile/transient. Weather stations = stationary. Tagged via protocol type lookup.

### 3. LoRa/Meshtastic Scanner (`scanners/lora_scanner.py`)

| Attribute | Value |
|-----------|-------|
| Pip packages | `meshtastic>=2.0` |
| Hardware | Heltec V3 ($18) via USB serial |
| Execution | Daemon thread reading Meshtastic serial API |

Detects: Meshtastic/MeshCore nodes, LoRaWAN devices (presence only).

Extracts from cleartext headers: node_id, hop count. From decrypted default-channel packets: GPS position, node role, device name, telemetry.

Mobile vs stationary discrimination:
1. Multi-location correlation (same node at distant locations = following)
2. RSSI pattern analysis (bell curve = stationary, constant = mobile)
3. Node role (ROUTER/REPEATER = likely infrastructure)
4. GPS position tracking (same coordinates = stationary)
5. Known-infrastructure allowlist (seeded from meshmap.net)

### 4. Bluetooth Classic Scanner (`scanners/bt_classic_scanner.py`)

| Attribute | Value |
|-----------|-------|
| Pip packages | `PyBluez>=0.30` or subprocess `bluetoothctl` |
| Hardware | Same BT adapter as BLE |
| Execution | Daemon thread, inquiry every 60-120s |

Detects: Discoverable BT audio bugs, persistent BT devices, OBD-II BT dongles.

Time-slotted with BLE scanner (shared radio): 45s idle -> 10s BLE -> 5s BT Classic -> repeat. Managed by BluetoothScheduler.

### 5. Drone Scanner (`scanners/drone_scanner.py`)

| Attribute | Value |
|-----------|-------|
| Pip packages | `opendroneid>=0.7` (or custom ASTM F3411 parser) |
| Hardware | Existing WiFi adapter + BLE adapter |
| Execution | Two sub-scanners in one thread |

Sub-scanner A: BLE Remote ID — parsed during BLE scan window. Extracts drone serial, position, altitude, speed, **operator GPS position**.

Sub-scanner B: WiFi SSID pattern matching — queries Kismet DB for `DJI-*`, `TELLO-*`, `Skydio-*`, `ANAFI-*`, `Autel-*`, `PARROT-*`.

Sub-scanner C (future): WiFi NAN Remote ID — parse ASTM F3411 action frames from Kismet.

### 6. ADS-B Aircraft Scanner (`scanners/adsb_scanner.py`)

| Attribute | Value |
|-----------|-------|
| System packages | `dump1090-mutability` or `readsb` |
| Hardware | Dedicated RTL-SDR V4 at 1090 MHz ($32) + tuned antenna ($15) |
| Execution | Daemon thread polling dump1090 JSON API (HTTP localhost:8080/data/aircraft.json every 5s) |

Detects: All aircraft with ADS-B transponders. Cross-references ICAO hex codes against configurable list of known government/LE registrations.

Alert: Same aircraft circling your area across multiple sessions.

### 7. RF Sweep Scanner (`scanners/rf_sweep_scanner.py`)

| Attribute | Value |
|-----------|-------|
| System packages | `rtl-sdr` (shares dongle with sub-GHz) |
| Pip packages | `numpy>=1.24.0` |
| Hardware | Same RTL-SDR as sub-GHz |
| Execution | Manual activation only. Pauses rtl_433, runs rtl_power, resumes rtl_433. |

Mode: User activates "RF Sweep" from GUI for room/vehicle bug sweeps. Not always-on.

Baseline: First sweep establishes RF environment fingerprint. Subsequent sweeps compare and flag new persistent signals.

### 8. Handheld Session Importer (`scanners/handheld_importer.py`)

| Attribute | Value |
|-----------|-------|
| Hardware | USB-C cable or SD card reader |
| Execution | Manual trigger (GUI button) or directory watch |

Parses ESP32 handheld CSV session files. Cross-references handheld detections against base station data for the same time period. A device seen on BOTH handheld and base station = strong cross-correlation signal (1.5x persistence score multiplier).

### 9. Historical Session Database (`session_db.py`)

SQLite database for cross-session analysis:

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    source TEXT,  -- 'base_station' | 'handheld'
    start_time REAL,
    end_time REAL,
    device_count INTEGER,
    gps_lat REAL,
    gps_lon REAL
);

CREATE TABLE device_sightings (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    device_id TEXT,
    source_type TEXT,
    timestamp REAL,
    lat REAL,
    lon REAL,
    rssi REAL,
    metadata TEXT  -- JSON
);

CREATE TABLE alerts (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    device_id TEXT,
    persistence_score REAL,
    reasons TEXT,  -- JSON array
    locations TEXT  -- JSON array
);
```

## Data Fusion

### Cross-Source Correlation Rules

| Correlation | Signal | Score Multiplier |
|-------------|--------|-----------------|
| Same MAC on WiFi + handheld | Device follows across your locations | 1.5x |
| TPMS IDs appear at same times as a WiFi phone MAC | Same vehicle's tires + driver's phone | 2.0x |
| BLE tracker + same-location WiFi device | AirTag + owner's phone nearby | 1.3x |
| Drone Remote ID serial seen across multiple sessions | Repeated drone surveillance | 2.0x |
| Aircraft ICAO seen circling multiple times | Aerial surveillance | 1.5x |
| LoRa node at multiple of your distant locations | LoRa device following you | 1.5x |

### Stationary vs Mobile Discrimination

Applied to: LoRa nodes, sub-GHz devices, BLE beacons.

| Method | Applies To | Mechanism |
|--------|-----------|-----------|
| Protocol-based | TPMS (always mobile), security sensors (always stationary) | Lookup table by protocol type |
| Multi-location | All | Same device at 2+ distant locations = mobile |
| RSSI bell curve | LoRa, BLE | Constant RSSI over time = co-traveling; bell curve = stationary pass-by |
| Self-reported position | Meshtastic | GPS coordinates change = mobile |
| Node role | Meshtastic | ROUTER/REPEATER = likely stationary |
| Allowlist | LoRa, WiFi | Known infrastructure node IDs |

## File Structure

### New Files (13)

```
scanners/
  __init__.py
  base_scanner.py           # BaseScanner ABC + DeviceAppearance + SourceType
  ble_scanner.py            # BLE tracker detection (AirTag, SmartTag, Tile, Remote ID)
  bt_classic_scanner.py     # Bluetooth Classic inquiry scanning
  sdr_scanner.py            # RTL-SDR + rtl_433 sub-GHz decoder
  lora_scanner.py           # Meshtastic/LoRa via serial or SDR
  drone_scanner.py          # Remote ID (BLE + WiFi NAN) + SSID pattern matching
  adsb_scanner.py           # dump1090 ADS-B aircraft tracking
  rf_sweep_scanner.py       # rtl_power wideband sweep + anomaly detection
  handheld_importer.py      # ESP32 handheld CSV session import
scanner_orchestrator.py     # Thread management, Queue, fusion
session_db.py               # SQLite historical session database
mobility_analyzer.py        # Stationary vs mobile discrimination (RSSI, multi-location)
```

### Modified Files (4)

```
surveillance_detector.py    # DeviceAppearance: mac -> device_id as primary key
surveillance_analyzer.py    # Integrate ScannerOrchestrator, multi-source reports
config.json                 # Add scanners.* configuration sections
cyt_gui.py                  # Tabbed interface: WiFi | BLE | Sub-GHz | Drones | Aircraft | Alerts
```

## Implementation Phases

### Phase 1: Foundation ($0, no new hardware)
- Create `scanners/base_scanner.py` with `BaseScanner`, `DeviceAppearance`, `SourceType`
- Modify `surveillance_detector.py`: `device_history` keyed by `device_id` instead of `mac`
- Create `scanner_orchestrator.py` with thread management + Queue
- Create `session_db.py` with schema
- Wrap existing WiFi/Kismet polling as `WiFiScanner(BaseScanner)`
- **Deliverable:** Existing functionality works unchanged through new abstraction

### Phase 2: BLE Tracker Detection ($0)
- Create `scanners/ble_scanner.py`
- Add `bleak` to requirements.txt
- Add `scanners.ble` to config.json
- Integrate into orchestrator
- **Deliverable:** AirTag/SmartTag/Tile detection live alongside WiFi monitoring

### Phase 3: Sub-GHz / TPMS ($32, one RTL-SDR)
- Create `scanners/sdr_scanner.py`
- Install rtl_433 system package
- Add `scanners.sdr` to config.json
- Create `mobility_analyzer.py` for stationary vs mobile tagging
- **Deliverable:** TPMS vehicle tracking, analog bug detection, key fob detection

### Phase 4: Drones + BT Classic ($0)
- Create `scanners/drone_scanner.py` (Remote ID via BLE + WiFi SSID matching)
- Create `scanners/bt_classic_scanner.py`
- Implement BluetoothScheduler for BLE/BT Classic time-slotting
- **Deliverable:** Drone detection via Remote ID + BT Classic audio bug scanning

### Phase 5: Data Fusion + GUI ($0)
- Implement cross-source correlation rules in orchestrator
- Update `cyt_gui.py` with tabbed multi-source dashboard
- Add session database integration
- **Deliverable:** Unified dashboard with cross-source intelligence

### Phase 6: ADS-B + LoRa ($50, second RTL-SDR + Heltec V3)
- Create `scanners/adsb_scanner.py`
- Create `scanners/lora_scanner.py`
- Install dump1090, meshtastic packages
- Add government aircraft registration lookup
- Add LoRa mobile-vs-stationary discrimination (RSSI, multi-location, node role)
- Known-infrastructure allowlist for Meshtastic routers
- **Deliverable:** Aircraft surveillance detection + LoRa/Meshtastic tracking

### Phase 7: RF Sweep + Handheld Import ($0)
- Create `scanners/rf_sweep_scanner.py`
- Create `scanners/handheld_importer.py`
- RF baseline management (store/compare)
- CSV import pipeline with cross-device correlation
- **Deliverable:** Bug sweep capability + handheld session integration

## GUI Updates

### Tabbed Interface (`ttk.Notebook`)
- **Tab 1: Dashboard** — scanner status grid + active alerts + unified detection feed (color-coded by source type)
- **Tab 2: Scanners** — per-scanner controls, start/stop toggles, detailed status
- **Tab 3: Analysis** — session history, cross-session queries, export controls
- **Tab 4: RF Sweep** — manual sweep controls and frequency-vs-power visualization

### New UI Elements
- Scanner status grid (replaces single "Kismet: Running" indicator)
- Unified detection feed with color coding (green=WiFi, blue=BLE, orange=sub-GHz, red=drone, purple=aircraft)
- RF Sweep button (pauses rtl_433, runs sweep, resumes)
- Handheld Import button (file dialog + cross-correlation results)
- Active Alerts banner (high-persistence devices needing attention)

## Configuration (Expanded config.json)

```json
{
  "paths": { ... },
  "timing": { ... },
  "search": { ... },
  "scanners": {
    "wifi": {
      "enabled": true,
      "kismet_db_path": "/home/matt/kismet_logs/*.kismet",
      "check_interval": 60
    },
    "ble": {
      "enabled": true,
      "scan_duration": 10,
      "scan_interval": 60,
      "tracker_types": ["findmy", "smarttag", "tile"]
    },
    "bt_classic": {
      "enabled": true,
      "inquiry_duration": 5,
      "inquiry_interval": 120
    },
    "sdr": {
      "enabled": true,
      "device_index": 0,
      "frequency": "433.92M",
      "protocols": "all"
    },
    "lora": {
      "enabled": true,
      "method": "serial",
      "serial_port": "/dev/ttyUSB0",
      "known_nodes_allowlist": "known_lora_nodes.json"
    },
    "drone": {
      "enabled": true,
      "ssid_patterns": ["DJI-*", "TELLO-*", "Skydio-*", "ANAFI-*", "Autel-*", "PARROT-*"],
      "remote_id_ble": true,
      "remote_id_wifi_nan": true
    },
    "adsb": {
      "enabled": false,
      "device_index": 1,
      "dump1090_url": "http://localhost:8080",
      "suspicious_registrations": "suspicious_aircraft.json"
    },
    "rf_sweep": {
      "enabled": true,
      "freq_start": "24M",
      "freq_end": "1766M",
      "baseline_file": "rf_baseline.json"
    },
    "handheld": {
      "import_dir": "./handheld_imports/",
      "auto_import": true
    }
  },
  "session_db": {
    "path": "./cyt_sessions.db"
  },
  "fusion": {
    "cross_source_multiplier": 1.5,
    "tpms_wifi_correlation_multiplier": 2.0,
    "drone_repeat_multiplier": 2.0
  }
}
```
