# Device Spectrum Reference

Comprehensive reference of what wireless signals surveillance-relevant devices emit, organized by frequency. Use this to determine what hardware CYT needs to monitor.

## Frequencies Quick Reference (Sorted)

| Frequency | What's There | Detection Hardware |
|-----------|-------------|-------------------|
| 88-108 MHz | FM audio bugs | RTL-SDR |
| 130-174 MHz | VHF audio bugs, law enforcement body wires | RTL-SDR |
| 315 MHz | TPMS (US), key fobs (US), cheap wireless bugs, security sensors | RTL-SDR + rtl_433 |
| 400-470 MHz | UHF audio bugs, body wires, surveillance team radios (P25) | RTL-SDR |
| 433.92 MHz | TPMS (EU), key fobs (EU), Z-Wave (EU), ISM devices | RTL-SDR + rtl_433 |
| 700-900 MHz | LTE bands 12/13 (cellular trackers), Blink camera sub-GHz link | RTL-SDR (energy only) |
| 850/1900 MHz | GSM/3G (cheap GPS trackers, GSM bugs) | RTL-SDR + gr-gsm |
| 868 MHz | LoRa (EU), Z-Wave (EU), ELRS/Crossfire drone control (EU) | RTL-SDR + rtl_433 |
| 908 MHz | Z-Wave (US) | RTL-SDR + rtl_433 |
| 915 MHz | LoRa (US), ELRS/Crossfire drone control (US), toll transponders | RTL-SDR + rtl_433 |
| 1090 MHz | ADS-B (aircraft surveillance detection) | RTL-SDR + dump1090 |
| 1.2-1.3 GHz | Analog video transmitters (hidden cameras) | RTL-SDR |
| 2.4 GHz | WiFi, BLE (AirTags, trackers), BT Classic, Zigbee, Remote ID, drone WiFi | ESP32, WiFi adapter, Kismet |
| 5 GHz | WiFi 5/6, DJI OcuSync, FPV drones | 5GHz WiFi adapter + Kismet |
| 5.8 GHz | FPV video (analog + digital), DJI OcuSync | HackRF ($300) or 5GHz adapter |
| 6 GHz | WiFi 6E | 6GHz WiFi adapter ($30-60) |
| 6.5-8 GHz | UWB (AirTag precision finding, UWB car keys) | No consumer scanner |

---

## By Device Category

### Consumer Trackers

| Device | Always-On Signal | Frequency | Protocol | Detection |
|--------|-----------------|-----------|----------|-----------|
| Apple AirTag | BLE advertisement (~2s interval) | 2.4 GHz | BLE 5.0, company ID 0x004C type 0x12 | ESP32 BLE scan |
| Samsung SmartTag2 | BLE advertisement (~2s) | 2.4 GHz | BLE 5.0, company ID 0x0075 | ESP32 BLE scan |
| Tile | BLE advertisement (~8s) | 2.4 GHz | BLE, service UUID 0xFFFE | ESP32 BLE scan |
| AirPods (in case) | Find My BLE beacon (same as AirTag!) | 2.4 GHz | BLE, company ID 0x004C type 0x12 | ESP32 BLE scan |

### GPS Trackers (Cellular)

| Device | Cellular Protocol | Bands | Report Interval | RF Detectable? |
|--------|-------------------|-------|-----------------|---------------|
| Spytec GL300 | LTE Cat-M1 | B2/B4/B5/B12/B13 | 5s-60min | Practically no (blends with cell traffic) |
| LandAirSea Overdrive | LTE Cat-M1 | B2/B4/B12 | 3s-3min | Practically no |
| Cheap Chinese (TK102/GT06) | 2G GSM/GPRS | 850/900/1800/1900 | 10s-30min | YES with RTL-SDR + gr-gsm |
| Pet trackers (Fi, Tractive) | LTE-M / 2G fallback | Various | 2s-60min | BLE portion detectable with ESP32 |

**Key gap:** Modern LTE-M cellular trackers are effectively invisible to consumer SDR. Physical inspection remains best countermeasure for planted GPS trackers.

### Vehicle Signals

| Signal | Frequency | Protocol | Broadcast Interval | Detection |
|--------|-----------|----------|-------------------|-----------|
| TPMS sensors | 315 MHz (US) / 433 MHz (EU) | OOK/FSK | Every 60-90 seconds | RTL-SDR + rtl_433 |
| Key fobs | 315/433 MHz | OOK/FSK rolling code | On button press only | RTL-SDR + rtl_433 |
| OBD-II WiFi dongles | 2.4 GHz | WiFi AP | Continuous | CYT WiFi scanning |
| Connected car telematics | 2.4/5 GHz WiFi + LTE | WiFi AP + cellular | Continuous | WiFi AP SSID detectable |

### Drones

| Type | Control Link | Video Link | Remote ID |
|------|-------------|------------|-----------|
| DJI (OcuSync) | 2.4/5.8 GHz OFDM | 2.4/5.8 GHz OFDM | WiFi NAN + BLE (ASTM F3411) |
| DJI (Enhanced WiFi) | 2.4/5.8 GHz 802.11 | Same | WiFi NAN + BLE |
| Parrot ANAFI | 2.4/5.8 GHz 802.11 | Same | WiFi NAN + BLE |
| Skydio | 2.4/5.8 GHz 802.11 | Same | WiFi NAN + BLE |
| FPV (ELRS sub-GHz) | 868/915 MHz LoRa | 5.8 GHz analog/digital | WiFi NAN + BLE (if compliant) |
| FPV (ELRS 2.4GHz) | 2.4 GHz FLRC | 5.8 GHz | WiFi NAN + BLE (if compliant) |
| FPV (Crossfire) | 868/915 MHz LoRa | 5.8 GHz | WiFi NAN + BLE (if compliant) |

**Remote ID is key:** FAA-mandated, unencrypted, broadcasts drone serial number + operator GPS location on WiFi NAN (channel 6) and BLE. Receivable with ESP32 and standard WiFi adapters. Open-source decoder: OpenDroneID.

### Audio Bugs / Listening Devices

| Type | Frequency | Protocol | Detection |
|------|-----------|----------|-----------|
| FM transmitter bugs | 88-108 MHz | Analog FM | RTL-SDR (trivial) |
| VHF bugs | 130-174 MHz | Analog FM narrowband | RTL-SDR |
| UHF bugs | 400-470 MHz | Analog FM narrowband | RTL-SDR |
| GSM listening devices | 850/900/1800/1900 MHz | GSM voice/data | RTL-SDR + gr-gsm |
| WiFi bugs (ESP32-based) | 2.4 GHz | WiFi | CYT existing WiFi scanning |
| Bluetooth audio bugs | 2.4 GHz | BT Classic A2DP or BLE | ESP32 BLE/BT scan |
| Spread-spectrum (mil-spec) | 900 MHz-6 GHz | FHSS encrypted | Professional TSCM equipment only |

### Hidden Cameras

| Type | Frequency | Detection |
|------|-----------|-----------|
| WiFi IP cameras (most common today) | 2.4/5 GHz | CYT WiFi scanning (already works) |
| Analog wireless (900 MHz) | 900 MHz | RTL-SDR |
| Analog wireless (1.2 GHz) | 1.2-1.3 GHz | RTL-SDR |
| Blink (proprietary to Sync Module) | ~900 MHz | RTL-SDR |
| 4G cellular cameras | LTE bands | Not practical with consumer SDR |

### Aerial Surveillance

| Platform | Detection Method | Hardware |
|----------|-----------------|----------|
| Drones (all types) | Remote ID (WiFi NAN + BLE) | ESP32 + WiFi adapter |
| Drones (WiFi-based) | WiFi SSID pattern matching | CYT existing |
| Drones (sub-GHz control) | LoRa signal detection | RTL-SDR |
| Surveillance aircraft (Cessna, helicopter) | ADS-B transponder | RTL-SDR + dump1090 |
| Government aircraft identification | ADS-B + registration database | dump1090 + ADS-B Exchange |

---

## Detection Hardware Coverage Matrix

What each piece of hardware can see:

| Target | ESP32 ($18) | WiFi Adapter ($0-30) | RTL-SDR ($25-35) | HackRF ($300) |
|--------|-------------|---------------------|-------------------|---------------|
| BLE trackers (AirTag etc.) | **YES** | No | No | No |
| WiFi probes | Partial (2.4 only) | **YES** (2.4+5) | No | No |
| WiFi drones/cameras | Partial (2.4 only) | **YES** | No | No |
| Remote ID (BLE) | **YES** | No | No | No |
| Remote ID (WiFi NAN) | **YES** | **YES** | No | No |
| TPMS | No | No | **YES** | YES |
| Audio bugs (FM/VHF/UHF) | No | No | **YES** | YES |
| Hidden cameras (analog) | No | No | **YES** (900/1.2GHz) | YES |
| Key fobs | No | No | **YES** | YES |
| Sub-GHz drone control | No | No | **YES** (868/915) | YES |
| ADS-B aircraft | No | No | **YES** (1090 MHz) | YES |
| GSM bugs/trackers | No | No | **YES** (with gr-gsm) | YES |
| 5.8 GHz FPV/video | No | Partial | No (out of range) | **YES** |
| LTE cellular trackers | No | No | No | Partial |
| Spread-spectrum bugs | No | No | No | No |

### Recommended Hardware Tiers

| Tier | Hardware | Total Cost | Coverage |
|------|----------|-----------|----------|
| **Minimum** | ESP32-S3 + existing WiFi adapter | ~$18 | WiFi + BLE + Remote ID |
| **Good** | + RTL-SDR v4 | ~$53 | + sub-GHz (TPMS, bugs, cameras, aircraft, drones) |
| **Better** | + second RTL-SDR (dedicated ADS-B or wideband sweep) | ~$88 | + continuous aircraft monitoring + RF baseline |
| **Advanced** | + HackRF One | ~$388 | + 5.8 GHz coverage + full 1-6 GHz |
| **Field sweep** | + TinySA Ultra | +$120 | + visual spectrum analyzer for room sweeps |
