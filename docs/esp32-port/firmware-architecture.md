# ESP32 Handheld: Firmware Architecture

## Language & Framework

**ESP-IDF (C/C++)** — not Arduino, not MicroPython.
- MicroPython's GC pauses (10-50ms) cause catastrophic packet loss in the promiscuous callback
- Arduino framework abstracts away the FreeRTOS task pinning and memory allocation control we need
- ESP-IDF gives direct access to promiscuous mode APIs, PSRAM allocation, and dual-core task pinning

## Task Architecture (Dual-Core)

```
Core 0 (WiFi/Radio):               Core 1 (Application):
  WiFi driver (system task)           Analysis task (8KB stack)
  Promiscuous callback                  - Dequeue from packet queue
    -> xQueueSendFromISR               - Hash table lookup/insert
  Channel hop task (4KB stack)          - Window flag updates
  BLE scan task (4KB stack)             - Persistence scoring
    (alternates with WiFi)              - Alert generation
                                      Display task (4KB stack)
                                        - Update TFT every 2s
                                      Logger task (4KB stack)
                                        - Batch write to SD every 60s
                                      GPS task (4KB stack)
                                        - Read UART every 30-60s
```

## Critical Constraint: Promiscuous Callback

The `wifi_promiscuous_cb` runs in the WiFi driver's task context on Core 0. Budget: **~4-6 microseconds**.

**MUST NOT do in callback:**
- malloc / heap allocation
- PSRAM access (80-200ns per read, unpredictable)
- Mutex locks (use `xQueueSendFromISR` only)
- printf / ESP_LOG
- Any blocking operation

**MUST do in callback:**
- Copy 48 bytes (MAC + SSID + RSSI + timestamp) to SRAM ring buffer
- Enqueue via `xQueueSendFromISR`
- Return immediately

## Memory Layout (ESP32-S3, 8MB PSRAM)

### Internal SRAM (~320KB usable)

| Component | Size | Notes |
|-----------|------|-------|
| WiFi stack | 60KB | Non-negotiable |
| BLE stack (when active) | 40KB | Freed when BLE suspended |
| FreeRTOS kernel + task stacks | 32KB | 4 tasks x 4-8KB |
| Packet queue (512 entries) | 24KB | 48 bytes x 512, ring buffer |
| Hash table index (8192 buckets) | 32KB | Pointers to PSRAM chains |
| Display driver + SPI DMA | 20KB | ST7789 partial framebuffer |
| GPS NMEA parser | 4KB | |
| Alignment + canaries | 8KB | |
| **Total** | **~220KB** | **~100KB headroom** |

### PSRAM (8MB)

| Component | Size | Notes |
|-----------|------|-------|
| Device record array (10K slots) | 480KB | 48 bytes per record |
| SSID string pool | 128KB | Deduplicated |
| Appearance log (50K circular) | 400KB | 8 bytes per entry |
| Display frame buffer | 150KB | 320x170x16bpp |
| SD write buffer | 64KB | Batch writes |
| Output generation buffer | 128KB | Streaming CSV/data |
| **Total** | **~1.35MB** | **~6.6MB free** |

## Device Record Structure

```c
typedef struct {
    uint8_t  mac[6];           // 6 bytes
    uint8_t  ssid[33];         // 33 bytes (32 chars + null)
    uint8_t  ssid_len;         // 1 byte
    int8_t   rssi_avg;         // 1 byte
    uint8_t  appearance_count; // 1 byte (max 255)
    uint8_t  window_flags;     // 1 byte (bits: 5min|10min|15min|20min)
    uint32_t first_seen;       // 4 bytes (epoch seconds)
    uint32_t last_seen;        // 4 bytes
} __attribute__((packed)) device_record_t;  // 48 bytes total
```

### Window Flags (replaces Python's 4 separate sets)

```
Bit 0: seen in current 5-min window
Bit 1: seen in 5-10 min window
Bit 2: seen in 10-15 min window
Bit 3: seen in 15-20 min window
Bits 4-7: reserved (BLE seen, sub-GHz seen, etc.)
```

Rotation: `window_flags = (window_flags >> 1)` every 5 minutes, then set bit 0 for newly seen devices. Any device with multiple bits set = persistent = suspicious. This is more efficient than the Python set-copy approach.

## Hash Table (MAC Lookup)

- 8192-bucket table in SRAM, each bucket is a 4-byte pointer to PSRAM
- Hash: XOR-fold MAC bytes 3-5 to 13 bits (skips OUI, uses device-unique portion)
- Average chain length at 5K devices: 0.6 (most lookups = 1 PSRAM read)
- Worst-case lookup: ~450ns (1 SRAM hash + 1-2 PSRAM reads)

## Channel Hopping Strategy

Weighted dwell — channels 1/6/11 get 4x the time:

```
Order: 1, 6, 11, 1, 6, 11, 2, 3, 4, 5, 1, 6, 11, 7, 8, 9, 10, 1, 6, 11, 12, 13
Dwell: 200ms on 1/6/11, 100ms on others
Cycle: ~3.6 seconds
```

After 5 minutes of data: adaptive weighting toward channels producing actual probes.

## WiFi / BLE Alternation

```
[WiFi promiscuous: 45s] -> [BLE GAP scan: 10s] -> repeat
```

- During WiFi window: promiscuous mode active, BLE controller suspended. Zero coex loss.
- During BLE window: promiscuous disabled, BLE scans for tracker advertisements.
- 10s BLE window catches most AirTag ads (Find My beacons at ~2s intervals).

## Storage Strategy

| Store | What | Write Frequency |
|-------|------|-----------------|
| PSRAM | Active device table, hash index | Continuous (per-packet) |
| NVS | Config, ignore lists, WiFi creds | Rarely (on user change) |
| LittleFS | Device DB snapshot for reboot persistence | Every 5-10 minutes |
| SD Card | Session logs (CSV), raw data for PC analysis | Every 60 seconds (batched) |

**Flash wear rule:** Never write to LittleFS more than once per 5 minutes. SD card handles high-frequency logging.

## Data Flow: Probe Request to Alert

```
WiFi radio (channel N)
  -> Promiscuous callback (Core 0, ISR context)
     -> Copy 48 bytes to SRAM ring buffer
     -> xQueueSendFromISR
  -> Analysis task (Core 1)
     -> Dequeue packet
     -> Hash MAC -> lookup in PSRAM device table
     -> If new: insert record, set window_flags bit 0
     -> If existing: update last_seen, RSSI, set window_flags bit 0
     -> If window_flags has multiple bits: SUSPICIOUS
        -> Calculate persistence score
        -> If score > threshold: push to alert queue
  -> Display task (Core 1)
     -> Every 2s: read alert queue, update TFT
  -> Logger task (Core 1)
     -> Every 60s: batch write device records to SD card as CSV
```

## Mapping CYT Python Modules to ESP32 Firmware

| Python Module | ESP32 Equivalent | Notes |
|---------------|-----------------|-------|
| `chasing_your_tail.py` | `main.c` (init + main loop) | |
| `secure_main_logic.py` (SecureCYTMonitor) | `analysis_task.c` | window_flags replaces 4 Python sets |
| `secure_database.py` (SecureKismetDB) | Not needed | No SQLite; direct packet capture |
| `surveillance_detector.py` | `persistence.c` | Scoring arithmetic ports 1:1 |
| `gps_tracker.py` | `gps_task.c` | UART NMEA parsing, simpler than Kismet BT GPS |
| `secure_ignore_loader.py` | `ignore_list.c` | Load from NVS, hash set in SRAM |
| `probe_analyzer.py` | PC post-processing | Read SD card CSV on computer |
| `surveillance_analyzer.py` | PC post-processing | KML generation on computer |
| `cyt_gui.py` | `display_task.c` | TFT status screens, not Tkinter |
| — (new) | `ble_scanner.c` | AirTag/SmartTag/Tile detection |

## Open Design Questions

- [ ] Alert notification — buzzer, LED, display flash, or all three?
- [ ] BLE fingerprinting strategy — how to track devices across MAC rotation using payload signatures
- [ ] Config interface — BLE serial from phone app? Web config via WiFi AP mode? SD card config file?
- [ ] OTA firmware updates — via WiFi AP mode or physical SD card?
