# Spectrum Expansion Roadmap

Priority-ordered plan for adding new wireless spectrum monitoring to CYT. Applicable to both Pi and ESP32 versions unless noted.

## Priority 1: BLE Tracker Detection
**Status:** Not started
**Platform:** Both Pi and ESP32
**Hardware cost:** $0-10 (Pi has built-in BT; ESP32-S3 has BLE 5.0)
**Integration effort:** Moderate

### Target Devices
| Tracker | Identifier | Network |
|---------|-----------|---------|
| Apple AirTag | Company ID 0x004C, type 0x12 | Find My |
| Samsung SmartTag | Company ID 0x0075 | SmartThings Find |
| Tile | Service UUID 0xFFFE | Tile network |
| Chipolo ONE Spot | Company ID 0x004C, type 0x12 | Find My (same as AirTag) |
| Google Find My Device | TBD | Google Find My Device |

### Key Challenge
BLE MAC address rotation (every ~15 min on AirTags). Cannot track by MAC like WiFi. Must use payload fingerprinting — identify manufacturer-specific advertisement data and track persistent presence of "a Find My device nearby" rather than a specific MAC.

### Integration Point
Feed detections into existing `DeviceAppearance` / `SurveillanceDetector` pipeline. Use payload signature hash as device identifier instead of MAC.

### Pi Implementation
- Library: `bleak` (Python, cross-platform BLE)
- New file: `ble_scanner.py`
- Scan for advertisements, filter by manufacturer ID, fingerprint payloads

### ESP32 Implementation
- ESP-IDF BLE GAP scanning API
- Alternating 45s WiFi / 10s BLE scan windows
- New file: `ble_scanner.c`

### References
- Apple Find My specification (OpenHaystack project documents the ad format)
- AirGuard (open source Android app, reference implementation)

---

## Priority 2: Sub-GHz via RTL-SDR
**Status:** Not started
**Platform:** Pi primary; ESP32 via USB OTG (feasibility TBD)
**Hardware cost:** $25-35 (RTL-SDR v4)
**Integration effort:** Moderate

### What It Detects
| Signal | Frequency | Why It Matters |
|--------|-----------|---------------|
| TPMS sensors | 315MHz (US) / 433MHz (EU) | Unique sensor IDs broadcast every 60-90s. Can track specific vehicles. |
| Cheap GPS trackers | 433MHz | Some budget PI-grade trackers report on ISM bands |
| Wireless cameras | 900MHz, 1.2GHz | Analog video transmitters |
| LoRa trackers | 868/915MHz | Long-range, low-power position reporting |
| Car key fobs | 315/433MHz | Vehicle compromise indicator |

### Integration Architecture
```
RTL-SDR -> rtl_433 (subprocess, JSON output) -> CYT parser -> DeviceAppearance pipeline
```

`rtl_433` decodes 200+ sub-GHz protocols and outputs structured JSON with device type, unique ID, and data. CYT wraps it as a subprocess and maps device IDs into the existing persistence engine.

### Key Value
TPMS tracking detection alone justifies the $35 investment. TPMS sensor IDs are persistent, unique per vehicle, and broadcast constantly — exactly the kind of persistent signal CYT is designed to detect.

### New Files
- `sdr_scanner.py` — rtl_433 subprocess management and JSON parsing

---

## Priority 2.5: LoRa / Meshtastic / MeshCore Detection
**Status:** Not started
**Platform:** Both Pi (via Heltec V3 USB sniffer) and ESP32 handheld (via SX1262 module)
**Hardware cost:** $18 (Heltec V3 for Pi) or $10 (SX1262 module for handheld)
**Integration effort:** Moderate

### Why This Matters
Meshtastic is exploding in popularity (tens of thousands of nodes). LoRa mesh nodes broadcast persistent node IDs in cleartext headers, GPS positions (if shared), and device roles. A Meshtastic device in someone's pocket following you is detectable the same way WiFi MACs are — by tracking node IDs across your locations and time windows.

### Key Protocol Facts
- **Frequencies:** 915 MHz (US), 868 MHz (EU) — same ISM bands as sub-GHz scanning
- **Node ID:** Derived from hardware MAC (last 4 bytes). Persistent. Transmitted in CLEARTEXT header of every packet — no decryption needed.
- **Position packets:** GPS lat/lon/alt, broadcast every 15 min (smart mode) or as low as 15s (tracker role)
- **Node roles:** CLIENT, ROUTER, REPEATER, TRACKER — transmitted in NodeInfo packets
- **Default encryption:** AES-128 but the default channel key ("AQ==") is public knowledge. Default-channel traffic is effectively unencrypted.

### RTL-SDR Cannot Decode LoRa
**Critical finding:** RTL-SDR detects LoRa energy (sees chirps in waterfall) but CANNOT demodulate/decode LoRa CSS packets. rtl_433 does NOT support LoRa. A dedicated LoRa radio (SX1262/SX1276) is required.

### Detection Hardware
- **Base station:** Heltec V3 (~$18) running Meshtastic firmware in monitor mode, connected via USB serial. The `meshtastic` Python library reads all received packets with metadata.
- **Handheld:** SX1262 module (~$10 with antenna) on SPI bus, custom firmware for passive LoRa reception.

### Mobile vs Stationary Node Discrimination

This is the key challenge. Most Meshtastic nodes are stationary routers/repeaters.

**Method 1: Multi-location correlation (strongest signal, already in CYT)**
- If node X appears at Location A (your home) AND Location B (your office 15km away), it's mobile and following you.
- A stationary router only appears when you're within its ~1-5km range from a fixed position.
- This maps directly to the existing `SurveillanceDetector` multi-location persistence logic.

**Method 2: RSSI pattern analysis**
- Stationary node: RSSI follows a bell curve as you approach, pass, and move away.
- Mobile follower: RSSI stays relatively constant over extended time (source maintains distance).
- Log (node_id, rssi, snr, timestamp, your_gps) and analyze RSSI-vs-position curve.

**Method 3: Node role filtering**
- ROUTER or REPEATER role → likely stationary infrastructure, lower suspicion weight.
- TRACKER or CLIENT role → likely mobile device, higher suspicion weight.
- Role is in cleartext NodeInfo packets.

**Method 4: GPS position from packets**
- If the node broadcasts its GPS position (most do on default channel), compare its reported position over time.
- Stationary: same coordinates every broadcast. Mobile: coordinates change.
- Limitation: adversary could disable position sharing or use a private channel.

**Method 5: Known-infrastructure allowlist**
- Maintain a database of known stationary nodes from public Meshtastic maps (meshmap.net).
- Similar to existing MAC/SSID ignore lists.

### Integration
- New `source_type="lora"` in DeviceAppearance pipeline
- Node ID as `device_id` for persistence tracking
- New file: `lora_monitor.py` (Pi) — reads Meshtastic serial API, extracts node data
- RSSI analysis module for bell-curve vs constant-RSSI discrimination
- Known-node allowlist (seeds from public maps, user-editable)

---

## Priority 3: Bluetooth Classic
**Status:** Not started
**Platform:** Both Pi and ESP32
**Hardware cost:** $0 (same adapter as BLE)
**Integration effort:** Low

### What It Detects
- Audio bugs (often discoverable Bluetooth Classic devices)
- Persistent unknown BT devices (phones, OBD-II dongles)
- Devices with suspicious Class of Device codes (e.g., unexpected audio device)

### Implementation
- Pi: `PyBluez` or `bluetoothctl` for inquiry scans
- ESP32: `esp_bt_gap_start_discovery()` API
- Scan for discoverable devices, log device name + class + address
- Feed into persistence engine (BT Classic addresses are stable)

### Limitation
Only finds discoverable devices. Sophisticated bugs will be non-discoverable.

---

## Priority 4: RF Sweep Mode
**Status:** Not started
**Platform:** Pi (requires RTL-SDR from Priority 2)
**Hardware cost:** $0 additional (uses RTL-SDR)
**Integration effort:** Moderate

### Use Case
"Bug sweep" — detect hidden cameras, audio bugs, or GPS trackers by their RF emissions without needing to decode the protocol. User activates this mode when sweeping a room, vehicle, or person.

### Implementation
```
RTL-SDR -> rtl_power (wideband spectrum sweep) -> CYT RF analyzer -> anomaly detection
```

- Establish baseline RF environment
- Alert on new persistent signals
- Track signal strength changes as user moves (closer to bug = stronger signal)

### Challenge
High false positive rate in urban environments. Requires baselining and learning the user's typical RF environment. This is a secondary/manual mode, not always-on.

### New Files
- `rf_analyzer.py` — rtl_power integration, baseline comparison, anomaly scoring

---

## Priority 5: WiFi 6E (6 GHz)
**Status:** Not started
**Platform:** Pi only (no ESP32 support)
**Hardware cost:** $30-60 (6 GHz adapter, e.g., Intel AX210)
**Integration effort:** None (Kismet handles it)

### Notes
- No CYT code changes needed — just add a 6 GHz-capable adapter and configure Kismet
- Very few devices probe on 6 GHz today
- Future-proofing measure as WiFi 6E adoption grows
- Monitor mode support on 6 GHz is driver-dependent

---

## Priority 5.5: Drone / Remote ID Detection
**Status:** Not started
**Platform:** Both Pi and ESP32
**Hardware cost:** $0 (uses existing WiFi adapter + ESP32 BLE)
**Integration effort:** Moderate

### Why This Jumped Up
FAA Remote ID is mandated (Sep 2023) — compliant drones MUST broadcast serial number + operator GPS location, unencrypted. This is free intelligence on existing hardware.

### Detection Layers (cheapest first)

**Layer 1: WiFi drone SSID matching (zero effort)**
- Add known drone SSID patterns to existing WiFi monitoring: `DJI-*`, `TELLO-*`, `Skydio-*`, `ANAFI-*`, `Autel-*`, `PARROT-*`
- Catches all WiFi-based drones within existing Kismet pipeline

**Layer 2: Remote ID via BLE (ESP32, already planned)**
- BLE advertisements per ASTM F3411 spec
- Decode: drone serial number, GPS position, altitude, speed, operator location
- Combine with BLE tracker scanning in the same 10s BLE window
- Open-source: OpenDroneID ESP32 receiver firmware

**Layer 3: Remote ID via WiFi NAN (Kismet)**
- WiFi Neighbor Awareness Networking action frames on channel 6
- Same data as BLE Remote ID, longer range (~1 km vs ~300m BLE)
- Kismet has Remote ID detection plugins

**Layer 4: Sub-GHz drone control links (RTL-SDR, already planned)**
- ELRS and Crossfire on 868/915 MHz — LoRa chirp signals detectable with RTL-SDR
- Catches FPV drones that may not have Remote ID

### Key Data Extracted
- Drone serial number
- Drone GPS position + altitude + speed + heading
- **Operator GPS position** (where the pilot is standing)
- Emergency status

### Integration
- New `source_type="drone"` in DeviceAppearance pipeline
- Drone serial number as `device_id` for persistence tracking
- A drone with the same serial number appearing across multiple CYT sessions = strong surveillance indicator
- Operator location enables: "the person flying this drone is standing at lat/lon"

### Open-Source Reference
- OpenDroneID (opendroneid.org) — reference decoder for WiFi NAN + BLE
- proto17/dji_droneid — DJI proprietary DroneID decoder (needs HackRF for best results)
- Kismet Remote ID plugins

---

## Priority 5.7: ADS-B Aircraft Tracking
**Status:** Not started
**Platform:** Pi only (needs dedicated RTL-SDR on 1090 MHz)
**Hardware cost:** $0 additional if RTL-SDR already present, or $25-35 for a dedicated dongle
**Integration effort:** Low

### Why Include This
Law enforcement and intelligence agencies use persistent aerial surveillance via small aircraft (FBI Cessna fleet, DHS, CBP). ADS-B transponders broadcast aircraft registration, position, altitude, and speed at 1090 MHz.

### Detection
- `dump1090` / `readsb` decodes ADS-B from RTL-SDR
- Cross-reference with government/LE aircraft registration databases (ADS-B Exchange, OSINT projects tracking FBI/DHS aircraft)
- Alert if the same aircraft circles your area repeatedly

### Integration
- `source_type="aircraft"` in DeviceAppearance
- ICAO hex code as `device_id`
- Persistence scoring: aircraft appearing over your location across multiple sessions

### Limitation
- Requires a dedicated RTL-SDR (can't time-share with sub-GHz scanning since it's at 1090 MHz)
- Or time-share with rtl_433 if sub-GHz scanning is duty-cycled

---

## Priority 6: IMSI Catcher Detection
**Status:** Deferred
**Platform:** Pi only
**Hardware cost:** $300+ (LimeSDR for LTE; $25 RTL-SDR for GSM-only)
**Integration effort:** Very high

### Notes
- State-actor threat — rarely relevant for CYT's primary user base (stalking victims)
- Decoding LTE requires expensive SDR and complex signal processing
- GSM-only detection possible with RTL-SDR + gr-gsm but limited value (2G being sunset)
- Legal considerations vary by jurisdiction
- Document as future/advanced module for users who bring their own SDR hardware

---

## Priority 7: Zigbee / Z-Wave
**Status:** Deferred indefinitely
**Platform:** Pi
**Hardware cost:** $10 (CC2531 for Zigbee)
**Integration effort:** Low

### Notes
- Not relevant to mobile surveillance detection
- Stationary indoor protocols (smart home)
- Could be relevant for a future "sweep a room for bugs" mode
- Z-Wave (908MHz) would be caught by the RTL-SDR sub-GHz scanning in Priority 2

---

## Architecture Note

All new spectrums feed into the existing `SurveillanceDetector` persistence engine. The scoring math does not change — just the input sources. Key modification: add `source_type` field to `DeviceAppearance` dataclass (wifi, ble, bt_classic, subghz, rf) and allow non-MAC device identifiers (payload hashes, TPMS sensor IDs, etc.).

### Files to Modify
- `surveillance_detector.py` — add `source_type` to `DeviceAppearance`
- `surveillance_analyzer.py` — orchestrate multiple scanner types
- `config.json` — add scanner configuration sections
- `cyt_gui.py` — add scanner status indicators
