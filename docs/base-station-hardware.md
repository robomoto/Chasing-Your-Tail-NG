# Base Station: Hardware Plan

## Full-Featured Build (~$436)

### Compute: Raspberry Pi 5 (8GB) — $80

Pi 5 over Pi 4 because:
- Faster CPU (Cortex-A76 quad @ 2.4GHz vs A72 @ 1.8GHz)
- Dual USB 3.0 ports (critical for multiple SDR dongles at full bandwidth)
- PCIe lane for NVMe SSD (Kismet writes continuously)
- 8GB RAM justified by running Kismet + dump1090 + rtl_433 + bleak + CYT Python stack simultaneously

### Bill of Materials

| # | Component | Specific Part | Qty | Cost | Notes |
|---|-----------|--------------|-----|------|-------|
| 1 | Compute | Raspberry Pi 5 (8GB) | 1 | $80 | |
| 2 | WiFi adapter | Alfa AWUS036ACHM (MT7612U, dual-band) | 2 | $80 | One locked to 2.4GHz, one to 5GHz. MT7612U uses in-kernel mt76 driver — no DKMS. Avoid Realtek RTL8812AU (requires out-of-tree driver, breaks on kernel updates). |
| 3 | RTL-SDR (sub-GHz) | RTL-SDR Blog V4 | 1 | $32 | TPMS (315/433), LoRa energy (868/915), analog bugs, hidden cameras. TCXO for accuracy. Time-shares rtl_433 + rtl_power. |
| 4 | RTL-SDR (ADS-B) | RTL-SDR Blog V4 | 1 | $32 | Dedicated to 1090 MHz continuous reception. Cannot time-share — ADS-B needs continuous monitoring. |
| 5 | LoRa sniffer | Heltec V3 (ESP32-S3 + SX1262) | 1 | $18 | Meshtastic packet decoder. Connects via USB serial. Runs Meshtastic firmware in monitor mode. Extracts node IDs, GPS positions, roles. |
| 6 | GPS module | u-blox NEO-M8N (GY-NEO8MV2) | 1 | $10 | USB or UART. For base station location reference. |
| 7 | Display | Official Pi 7" touchscreen | 1 | $65 | Self-contained dashboard. Chromium kiosk mode. |
| 8 | ADS-B antenna | RTL-SDR Blog 1090 MHz tuned vertical | 1 | $15 | 10-20 dB better than wideband dipole at 1090 MHz. Mount high with sky view. |
| 9 | Sub-GHz antenna | Telescoping wideband dipole (included with V4) | 1 | $0 | Set to ~17cm for 433 MHz or ~8cm for 915 MHz. |
| 10 | Power supply | Official Pi 5 27W USB-C PSU | 1 | $12 | Must be USB-PD capable. |
| 11 | Powered USB hub | 4-port USB 3.0 powered | 1 | $15 | CRITICAL: 2x RTL-SDR + 2x WiFi adapter + LoRa sniffer = 5 USB devices. Prevents brown-outs. |
| 12 | Storage | NVMe M.2 HAT + 256GB SSD | 1 | $50 | Kismet writes continuously — NVMe far more durable than microSD. |
| 13 | Enclosure | SmartiPi Touch Pro (w/ touchscreen mount) | 1 | $30 | |
| 14 | SD card reader | USB microSD reader | 1 | $5 | For handheld session import (backup to USB-C direct). |
| 15 | Cabling | SMA pigtails, USB extensions, GPIO wires | — | $10 | |
| | **TOTAL** | | | **~$454** | |

### Budget Options

| Build | Changes | Savings | Total |
|-------|---------|---------|-------|
| No touchscreen (headless SSH/VNC) | Remove item 7 | -$65 | ~$389 |
| microSD instead of NVMe | Remove item 12, add $15 microSD | -$35 | ~$419 |
| Single WiFi adapter (both bands) | Remove one ACHM | -$40 | ~$414 |
| No LoRa sniffer | Remove item 5 | -$18 | ~$436 |
| **Minimum "everything works"** | All above savings | -$158 | **~$296** |

## Radio / Sensor Inventory

| Radio | Hardware | Interface | Frequency | What It Detects |
|-------|---------|-----------|-----------|----------------|
| WiFi 2.4 GHz | Alfa ACHM #1 | USB 3.0 | 2.4 GHz | Probe requests, WiFi drones, WiFi cameras/bugs |
| WiFi 5 GHz | Alfa ACHM #2 | USB 3.0 | 5 GHz | 5GHz probes, DJI OcuSync, 5GHz cameras |
| BLE + BT Classic | Pi 5 built-in (CYW43455) | Internal | 2.4 GHz | AirTags, SmartTags, Tile, Remote ID (BLE), audio bugs, BT devices |
| Sub-GHz | RTL-SDR V4 #1 | USB 2.0 | 24 MHz-1.766 GHz | TPMS, key fobs, analog bugs/cameras, Z-Wave, LoRa (energy), GSM bugs |
| ADS-B | RTL-SDR V4 #2 | USB 2.0 | 1090 MHz | Aircraft transponders (surveillance aircraft detection) |
| LoRa | Heltec V3 (SX1262) | USB serial | 868/915 MHz | Meshtastic/MeshCore nodes, ELRS/Crossfire drone control |
| GPS | NEO-M8N | USB/UART | 1575 MHz | Base station position reference |

**Total simultaneous radios: 7** (2x WiFi + BLE/BT + 2x SDR + LoRa + GPS)

## Antenna Strategy

| Antenna | For | Type | Mount | Cost |
|---------|-----|------|-------|------|
| 2x 5dBi dual-band omni (included with ACHM) | WiFi monitor mode | RP-SMA dipole | Desktop or window | $0 |
| Telescoping wideband dipole (included with V4) | Sub-GHz RTL-SDR | SMA adjustable | Desktop | $0 |
| RTL-SDR Blog 1090 MHz antenna | ADS-B | Tuned vertical w/ ground plane | Highest point, sky view | $15 |
| Ceramic patch (included with NEO-M8N) | GPS | Passive patch | Window or outdoor | $0 |
| Heltec V3 PCB antenna | LoRa | Built-in | — | $0 |

**Optional upgrades:**
| Antenna | Purpose | Cost |
|---------|---------|------|
| Alfa 9dBi dual-band omni | Extended WiFi range | $12 |
| Wideband discone (25-1300 MHz) outdoor mount | Best sub-GHz + ADS-B combo | $30 |
| Dedicated 1090 MHz collinear (outdoor) | Maximum aircraft range (200+ nm) | $25 |

## Software Stack

| Software | Purpose | Runs On |
|----------|---------|---------|
| Kismet | WiFi packet capture + device tracking | Pi (system service) |
| bleak | BLE scanning (AirTag, SmartTag, Tile, Remote ID) | Pi (Python async) |
| bluetoothctl / PyBluez | Bluetooth Classic inquiry scans | Pi (Python) |
| rtl_433 | Sub-GHz protocol decoding (TPMS, sensors, key fobs) | Pi (subprocess, JSON output) |
| dump1090 / readsb | ADS-B aircraft decoding | Pi (subprocess, JSON output) |
| rtl_power | Wideband RF spectrum sweep | Pi (subprocess, time-shares with rtl_433) |
| meshtastic Python library | LoRa packet monitoring via Heltec V3 | Pi (Python, serial) |
| CYT-NG Python stack | Persistence detection, session ingestion, reporting | Pi (main application) |
| Chromium (kiosk) | Dashboard display | Pi (if touchscreen attached) |

## Power

### Stationary (wall power)
- Official Pi 5 27W USB-C PSU ($12)
- Powered USB 3.0 hub ($15) — required for 5+ USB devices

### Vehicle deployment
- 12V cigarette lighter to USB-C PD adapter ($15)
- OR: PiSugar 3 Plus UPS (5000mAh, $40) for clean shutdown on ignition-off

### Portable (battery)
- 20,000 mAh USB-C PD power bank (~$30-40)
- Estimated runtime: ~6-8 hours (full sensor load ~2.5A @ 5V)
- Pi Zero 2W alternative would roughly double battery life but reduces processing headroom

## Storage

**Primary: NVMe SSD via M.2 HAT** ($50 total)
- 256GB provides months of Kismet databases + session history
- Far more durable than microSD for continuous write workloads
- 5-10x faster random I/O for SQLite operations

**Backup: 128GB microSD** ($15)
- Adequate for lighter use
- Replace every 6-12 months under heavy Kismet write load

## USB Port Allocation

Pi 5 has 2x USB 3.0 + 2x USB 2.0. With powered hub:

| Port | Device | Speed |
|------|--------|-------|
| USB 3.0 #1 | Powered hub (expands to 4 ports) | Hub |
| Hub port 1 | Alfa ACHM #1 (2.4 GHz WiFi) | USB 3.0 |
| Hub port 2 | Alfa ACHM #2 (5 GHz WiFi) | USB 3.0 |
| Hub port 3 | RTL-SDR V4 #1 (sub-GHz) | USB 2.0 |
| Hub port 4 | RTL-SDR V4 #2 (ADS-B) | USB 2.0 |
| USB 3.0 #2 | Heltec V3 (LoRa sniffer) | USB 2.0 (serial) |
| USB 2.0 #1 | GPS module (NEO-M8N) | USB 2.0 (serial) |
| USB 2.0 #2 | Available (handheld upload, SD reader) | USB 2.0 |

## Complete System Cost

| Component | Cost |
|-----------|------|
| Base station (full-featured) | ~$454 |
| Handheld (full-featured with LoRa) | ~$58 |
| **Complete system** | **~$512** |
| Budget base + budget handheld | ~$296 + $38 = ~$334 |
