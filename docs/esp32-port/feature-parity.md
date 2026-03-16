# ESP32 Handheld: Feature Parity Matrix

## Legend
- **FULL** — feature works identically to Pi version
- **PARTIAL** — feature works with reduced capability
- **DEFERRED** — done on PC from SD card data, not on device
- **NEW** — capability that doesn't exist on Pi version
- **IMPOSSIBLE** — hardware limitation, no workaround

## Core Detection

| Feature | Pi + Kismet | ESP32 | Status | Notes |
|---------|-------------|-------|--------|-------|
| 2.4GHz probe request capture | Full (via Kismet) | Native promiscuous mode | FULL | |
| 5GHz probe request capture | Full (with 5GHz adapter) | Not supported | IMPOSSIBLE | 20-30% device blind spot |
| MAC address tracking | Full | Full | FULL | |
| SSID extraction from probes | Full | Full (parse raw frame) | FULL | |
| Time window system (5/10/15/20 min) | 4 Python sets | window_flags bitfield | FULL | Actually more efficient |
| Persistence scoring | Float arithmetic | Float arithmetic | FULL | Ports 1:1 |
| Ignore list filtering | JSON + hash set | NVS + hash set | FULL | |
| Device type identification | Kismet JSON metadata | Limited (frame analysis only) | PARTIAL | No Kismet device classification |

## GPS & Location

| Feature | Pi + Kismet | ESP32 | Status | Notes |
|---------|-------------|-------|--------|-------|
| GPS coordinates | BT GPS via Kismet | Direct UART GPS module | FULL | Simpler integration |
| Location clustering (100m) | Haversine in Python | Haversine in C | FULL | |
| Multi-location tracking | Full | Full | FULL | |
| GPS-device correlation | Via Kismet DB timestamps | Direct (same device captures) | FULL | Better temporal accuracy |

## Reporting & Visualization

| Feature | Pi + Kismet | ESP32 | Status | Notes |
|---------|-------------|-------|--------|-------|
| Real-time alert display | Tkinter GUI | TFT screen | FULL | Different UI, same info |
| KML file generation | On device (gps_tracker.py) | From SD card data on PC | DEFERRED | Too memory-intensive for ESP32 |
| Markdown reports | On device | From SD card data on PC | DEFERRED | |
| HTML reports (pandoc) | On device | From SD card data on PC | DEFERRED | |
| Raw data logging | Log files | CSV to SD card | FULL | More portable format |

## Network & API

| Feature | Pi + Kismet | ESP32 | Status | Notes |
|---------|-------------|-------|--------|-------|
| WiGLE API queries | On device (optional) | Batch from SD card on PC | DEFERRED | Can't HTTP while sniffing |
| Kismet web UI | localhost:2501 | Not applicable | N/A | ESP32 replaces Kismet |

## New Capabilities (ESP32 only)

| Feature | Status | Notes |
|---------|--------|-------|
| BLE tracker detection (AirTag/SmartTag/Tile) | NEW | Alternating WiFi/BLE scan windows |
| Portable battery operation (13-15h) | NEW | Pi requires wall power or large battery pack |
| Pocket-size form factor | NEW | ~$36 BOM in small enclosure |
| Audible/haptic alerts | NEW | Buzzer or vibration motor for discreet alerting |
| Sub-GHz scanning (with RTL-SDR add-on) | NEW (optional) | TPMS, 433MHz trackers via USB OTG |

## What You Gain vs Lose

### Gains
- Truly portable and concealable
- 13-15 hour battery life
- BLE tracker detection (AirTags etc.)
- Lower cost ($36 vs $80+ for Pi + adapter + battery + case)
- Instant-on (no Linux boot)
- Real-time TFT alerts without a full desktop environment

### Losses
- 5GHz blind spot (20-30% of modern devices)
- No on-device report generation (KML, HTML, markdown)
- No WiGLE API integration in the field
- No Kismet device classification metadata
- Smaller device tracking capacity (10K vs unlimited on Pi)
- Must rewrite entire codebase in C (no Python)
