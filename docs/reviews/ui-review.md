# CYT-NG UI Design Review

## 1. Base Station Dashboard (800x480 Touchscreen)

### Current State Assessment

The existing `cyt_gui.py` is a single-screen layout with flat button rows and a log pane. It was designed for WiFi-only monitoring and will not scale to 9 scanner types. The planned `ttk.Notebook` migration is the right call. Below are concrete layouts for each tab.

### Tab 1: Dashboard (Default View)

This is the "glance and go" screen. The user should understand system health and threat status within 2 seconds of looking at it.

```
+--[ Dashboard ]--[ Scanners ]--[ Analysis ]--[ RF Sweep ]------------+
|                                                                      |
|  SCANNER STATUS GRID (top strip, ~60px tall)                        |
|  +--------+--------+--------+--------+--------+--------+--------+   |
|  | WiFi   | BLE    | BT Cls | SubGHz | LoRa   | Drone  | ADS-B  |  |
|  | [green]| [green]| [gray] | [green]| [amber]| [green]| [off]  |  |
|  | 142 dev| 8 trk  | --     | 23 sig | 3 node | 0 det  | --     |  |
|  +--------+--------+--------+--------+--------+--------+--------+   |
|                                                                      |
|  ACTIVE ALERTS BANNER (~80px, only visible when alerts exist)       |
|  +----------------------------------------------------------------+ |
|  | [!] PERSISTENT DEVICE: findmy:a1b2c3 | Score: 0.87 | 3 loc   | |
|  | [!] TPMS+WiFi CORR: tpms:0x1A2B + AA:BB:CC | Score: 0.92     | |
|  +----------------------------------------------------------------+ |
|                                                                      |
|  UNIFIED DETECTION FEED (remaining space, ~280px)                   |
|  +----------------------------------------------------------------+ |
|  | 14:23:07 [WiFi ] AA:BB:CC:DD:EE:FF  probe="HomeNet" RSSI:-62  | |
|  | 14:23:05 [BLE  ] findmy:a1b2c3d4    AirTag          RSSI:-71  | |
|  | 14:23:03 [SubGz] tpms:0x1A2B3C4D   TPMS 433.9MHz   RSSI:-45  | |
|  | 14:22:58 [Drone] drone:DJI12345678  RemoteID BLE    RSSI:-68  | |
|  | 14:22:55 [LoRa ] lora:!a1b2c3d4    Meshtastic       RSSI:-89  | |
|  +----------------------------------------------------------------+ |
+----------------------------------------------------------------------+
```

**Scanner status grid**: Each cell is a touch target (~100x60px). Tap to jump to that scanner's detail in the Scanners tab. States:
- Green fill: active, receiving data
- Amber fill: active, no data recently (possible issue)
- Gray fill: disabled in config
- Red fill: error state (crashed, hardware missing)

The count line shows the most relevant metric per scanner type (device count, tracker count, signal count, etc.).

**Active alerts banner**: Appears only when there are unacknowledged alerts. Sorted by persistence score descending. Each alert row is a touch target that opens alert detail. The banner uses a dark background with a colored left-edge strip indicating severity (see threat level colors in Section 3). Limit to 3 visible rows with a "+N more" indicator to avoid consuming the feed space.

**Unified detection feed**: Reverse-chronological event stream. Each line is prefix-colored by source type (see Section 3). The feed should use a monospace font (Courier 11) for column alignment. Rows with persistence flags get a subtle background tint. Touch a row to see device detail.

### Tab 2: Scanners

Per-scanner controls in a two-column grid layout. Each scanner gets a card (~380x100px) with:

```
+--[ Dashboard ]--[ Scanners ]--[ Analysis ]--[ RF Sweep ]------------+
|                                                                      |
|  +-- WiFi -----------------------+  +-- BLE Trackers -------------+ |
|  | Status: Running  [Stop]       |  | Status: Scanning  [Stop]   | |
|  | Kismet DB: 142 devices        |  | AirTags: 3  SmartTags: 1   | |
|  | Last poll: 12s ago            |  | Tiles: 0   Window: 8/10s   | |
|  +-------------------------------+  +-----------------------------+ |
|                                                                      |
|  +-- BT Classic ------------------+  +-- Sub-GHz (RTL-SDR) ------+ |
|  | Status: Idle (time-slot wait) |  | Status: Receiving          | |
|  | Next scan: 22s                |  | rtl_433 PIDs: 1            | |
|  | Last inquiry: 2 devices       |  | Protocols decoded: 23      | |
|  +-------------------------------+  +-----------------------------+ |
|                                                                      |
|  +-- LoRa/Meshtastic ------------+  +-- Drone Detection ---------+ |
|  | Status: Listening             |  | Status: Monitoring          | |
|  | Nodes seen: 3 (1 mobile)     |  | BLE RemoteID: active        | |
|  | Serial: /dev/ttyUSB0 OK      |  | WiFi SSID match: active     | |
|  +-------------------------------+  +-----------------------------+ |
|                                                                      |
|  +-- ADS-B Aircraft --------------+  +-- Handheld Import --------+ |
|  | Status: Disabled  [Enable]    |  | [Import from USB]          | |
|  | dump1090: not running         |  | [Import from SD card]      | |
|  | Hardware: not detected        |  | Last import: never         | |
|  +-------------------------------+  +-----------------------------+ |
+----------------------------------------------------------------------+
```

Each card has a start/stop toggle button (top right). Cards for disabled scanners show a muted appearance with an "Enable" button. The Handheld Import card is special -- it has import action buttons rather than start/stop.

### Tab 3: Analysis

```
+--[ Dashboard ]--[ Scanners ]--[ Analysis ]--[ RF Sweep ]------------+
|                                                                      |
|  SESSION HISTORY                                                     |
|  +----------------------------------------------------------------+ |
|  | Date       | Source    | Duration | Devices | Alerts | Location| |
|  |------------|----------|----------|---------|--------|---------- | |
|  | 2026-03-16 | Base Stn | 2h 14m  | 247     | 3      | Home    | |
|  | 2026-03-16 | Handheld | 45m      | 89      | 1      | Downtown| |
|  | 2026-03-15 | Base Stn | 8h 02m  | 1,203   | 7      | Home    | |
|  +----------------------------------------------------------------+ |
|                                                                      |
|  CROSS-SESSION QUERIES                                               |
|  +-------------------------------+  +-----------------------------+ |
|  | Device ID: [_____________]    |  | Results:                    | |
|  | Source type: [All        v]   |  | findmy:a1b2c3 seen at:     | |
|  | Date range: [__] to [__]     |  |   Home - 3 sessions         | |
|  | Min score: [0.5______]       |  |   Downtown - 1 session      | |
|  | [Search]  [Export CSV]       |  |   Score: 0.87 -> 0.92       | |
|  +-------------------------------+  +-----------------------------+ |
|                                                                      |
|  [Generate KML Report]  [Generate HTML Report]  [Export All JSON]   |
+----------------------------------------------------------------------+
```

The session history table is scrollable and sortable by column. Tapping a session row populates the right pane with session detail. Cross-session queries let the user search for a specific device_id across all sessions -- critical for answering "has this device followed me before?"

### Tab 4: RF Sweep

```
+--[ Dashboard ]--[ Scanners ]--[ Analysis ]--[ RF Sweep ]------------+
|                                                                      |
|  SWEEP CONTROLS                                                      |
|  Freq start: [24___] MHz  Freq end: [1766__] MHz  Bin: [1 MHz v]   |
|  [Start Sweep]  [Compare to Baseline]  [Save as Baseline]          |
|                                                                      |
|  NOTE: Starting sweep will pause Sub-GHz scanner (shared RTL-SDR)   |
|                                                                      |
|  FREQUENCY vs POWER (Canvas, ~350px tall)                           |
|  +----------------------------------------------------------------+ |
|  |  dBm                                                            | |
|  |  -20|                                                           | |
|  |  -40|     __                          ___                       | |
|  |  -60|____/  \____         ___________/   \_____                 | |
|  |  -80|            \_______/                     \_________       | |
|  | -100|__________________________________________________|       | |
|  |     24    200    400    600    800   1000   1200   1400  1766   | |
|  |                         MHz                                     | |
|  +----------------------------------------------------------------+ |
|  Legend: [--- Current] [--- Baseline] [### Anomalies]              |
|                                                                      |
|  ANOMALIES DETECTED: 2                                               |
|  | 433.92 MHz | +18 dB above baseline | Possible: rtl_433 device  | |
|  | 915.00 MHz | +12 dB above baseline | Possible: LoRa transmitter| |
+----------------------------------------------------------------------+
```

The spectral plot should use a `tkinter.Canvas` widget drawing the power spectrum as a polyline. Baseline overlay in a muted color (gray). Anomaly bands highlighted with a red/orange fill. The canvas needs to handle touch-drag for zooming into frequency ranges.

### Typography Hierarchy

Given the 800x480 resolution and viewing distance (~50cm for a desk-mounted Pi screen):

| Element | Font | Size | Weight | Use |
|---------|------|------|--------|-----|
| Tab labels | Sans-serif | 12px | Bold | ttk.Notebook tabs |
| Scanner grid labels | Sans-serif | 11px | Bold | Scanner name in status grid |
| Scanner grid counts | Monospace | 10px | Regular | Device counts, metrics |
| Alert banner text | Sans-serif | 11px | Bold | Active alert descriptions |
| Feed entries | Monospace | 10px | Regular | Detection feed rows |
| Feed source tags | Monospace | 10px | Bold | [WiFi], [BLE] prefixes |
| Card titles | Sans-serif | 11px | Bold | Scanner card headers |
| Card body | Sans-serif | 10px | Regular | Scanner card status lines |
| Section headers | Sans-serif | 12px | Bold | "SESSION HISTORY", etc. |
| Button labels | Sans-serif | 10px | Bold | All buttons |

Recommendation: Use the system sans-serif ("Helvetica" on the Pi, which maps to DejaVu Sans). Avoid Arial -- it may not be installed. Monospace should be "DejaVu Sans Mono" or "Courier".

### Alert Visual Priority

Alerts in the banner should be ordered by persistence score (highest first) and use visual weight to communicate urgency:

| Score Range | Visual Treatment |
|-------------|-----------------|
| 0.9 - 1.0 (Critical) | Red left border (4px), bold white text on dark red background (#8B0000), pulsing dot indicator |
| 0.7 - 0.89 (High) | Orange left border (4px), bold text on dark orange background (#8B4500) |
| 0.5 - 0.69 (Medium) | Yellow left border (3px), regular text on dark yellow background (#6B6B00) |
| 0.3 - 0.49 (Low) | Blue left border (2px), regular text on standard dark background |

Do NOT use animation or flashing for alerts on the base station. A pulsing dot (alternating filled/hollow circle) for critical alerts is sufficient and avoids drawing attention if someone else is looking at the screen.

---

## 2. Handheld Display (170x320 TFT, ST7789)

### Constraints

- 170 pixels wide, 320 pixels tall (portrait orientation)
- 3 physical buttons: UP (GPIO 2), DOWN/SELECT (GPIO 3), BACK/MODE (GPIO 14)
- No touch. All navigation via buttons.
- Outdoor visibility matters -- high contrast is essential.
- ST7789 driver, 16-bit color (RGB565).
- Display refresh every 2 seconds (per firmware architecture).
- Target font: 8x16 bitmap font gives ~21 characters per line, ~20 lines. A 6x12 font gives ~28 chars/line, ~26 lines.

### Navigation Model

Three-button navigation with these consistent behaviors:

| Button | Short Press | Long Press (>1s) |
|--------|------------|-------------------|
| UP | Scroll up / previous item | Jump to top of list |
| DOWN/SELECT | Scroll down / next item | Select / open detail |
| BACK/MODE | Go back one screen | Cycle through main screens |

Screen flow:

```
Main Status ←→ Alert Screen ←→ Device List
     ↑              ↑               ↑
   (MODE)        (MODE)          (MODE)
     ↓              ↓               ↓
  cycles       cycles           cycles
```

Long-press BACK/MODE cycles through the three main screens. Within a screen, UP/DOWN scroll. Long-press DOWN opens detail for the selected item.

### Screen 1: Main Status (Default)

This is the "pocket glance" screen. Optimized for 6x12 font (28 chars/line).

```
+------------------+
| CYT-NG    14:23  |  <- Header: app name + time (always visible)
|==================|
| WiFi: 142  B:3/1 |  <- WiFi device count, BLE trackers/new
| SGHz: 23  Lr:3   |  <- Sub-GHz signals, LoRa nodes
| Drn: 0   AC: --  |  <- Drones, Aircraft (-- = disabled)
|------------------|
| ALERTS: 2        |  <- Alert count, color-coded
| [!] findmy:a1b2  |  <- Top alert, truncated
| [!] tpms+wifi    |  <- Second alert, truncated
|------------------|
| GPS: 3D  Sat:8   |  <- GPS fix type + satellite count
| Bat: 78% ~10.4h  |  <- Battery percentage + estimated runtime
| SD: 2.1G free    |  <- SD card space
| Ses: 01:23:45    |  <- Session duration
|==================|
| UP  DOWN/SEL  BCK|  <- Button hint strip (optional, can hide)
+------------------+
```

**What fits**: Device counts per scanner category (6 values), alert count + top 2 alert summaries, GPS status, battery, storage, session time. Total: 12 content lines at 6x12 font.

**What gets cut**: Signal strength per device, full device IDs (truncated to ~14 chars), alert detail/reasons, scanner health status (moved to a sub-screen if needed).

**Design decisions**:
- The header line (app name + clock) is persistent across all screens. It uses inverted colors (light text on source-color background) and costs 1 line.
- Device counts use abbreviated labels to fit 2 scanner categories per line.
- Alert section grows/shrinks: 0 alerts = "NO ALERTS" (1 line, green). 1-3 alerts = show them. 4+ alerts = show top 3 + "N more".
- Battery shows percentage AND estimated hours remaining (critical for fieldwork).
- GPS shows fix quality (No fix / 2D / 3D) and satellite count.

### Screen 2: Alert Screen

Shown when the user navigates to alerts, or auto-switches on new critical alert.

```
+------------------+
| ALERTS (2) 14:23 |  <- Header with count
|==================|
|>findmy:a1b2c3d4  |  <- Selected alert (highlighted row)
| Score: 0.87      |
| Type: BLE AirTag |
| Seen: 3 locations|
| Duration: 47 min |
| Last: 2m ago     |
|------------------|
| tpms:0x1A2B3C4D  |  <- Next alert (not selected)
| Score: 0.72      |
|                   |
|                   |
|                   |
|==================|
| UP  DOWN/SEL  BCK|
+------------------+
```

UP/DOWN moves the selection cursor (">") between alerts. The selected alert expands to show detail (score, type, location count, duration, recency). Unselected alerts show only device_id and score (2 lines each).

Long-press DOWN on a selected alert opens a full-detail sub-screen showing all reasons, all location timestamps, and the raw device_id.

### Screen 3: Device List

Scrollable list of all tracked devices, sorted by persistence score descending.

```
+------------------+
| DEVICES(142)14:23|  <- Header with total count
|==================|
|>AA:BB:CC:DD:EE:FF|  <- Selected device (highlighted)
| W Sc:0.42 -62dBm |  <- W=WiFi, score, RSSI
|------------------|
| findmy:a1b2c3d4  |
| B Sc:0.87 -71dBm |  <- B=BLE
|------------------|
| tpms:0x1A2B3C4D  |
| S Sc:0.72 -45dBm |  <- S=Sub-GHz
|------------------|
| lora:!a1b2c3d4   |
| L Sc:0.15 -89dBm |  <- L=LoRa
|------------------|
| drone:DJI1234567 |
| D Sc:0.00 -68dBm |  <- D=Drone
|==================|
| UP  DOWN/SEL  BCK|
+------------------+
```

Each device takes 2 lines: device_id on line 1, source-type letter + score + RSSI on line 2. With 20 content lines available, that is 10 devices visible at once. UP/DOWN scrolls through the full list. The selected device row is drawn with inverted colors.

**Source type single-letter codes** (for the constrained display):
- **W** = WiFi (green)
- **B** = BLE (blue)
- **C** = BT Classic (cyan)
- **S** = Sub-GHz (orange)
- **L** = LoRa (magenta)
- **D** = Drone (red)
- **A** = Aircraft (purple)

Long-press DOWN on a device opens full detail: all SSIDs probed, appearance timestamps, window flags, location history.

### What Gets Cut Entirely on Handheld

- RF sweep (requires RTL-SDR hardware the handheld does not have)
- Cross-session analysis (no SQLite on ESP32, offload to base station)
- KML/report generation (offload to PC/base station)
- Scanner configuration (pre-configure via SD card config file or BLE serial)
- WiGLE lookups (no internet connectivity)

---

## 3. Color System

### Source Type Colors

Designed to be distinguishable on both dark backgrounds (TFT, current Tkinter dark theme) and to degrade gracefully if viewed on a light background. Colors are specified in both hex (Tkinter) and RGB565 (TFT).

| Source Type | Hex | RGB565 | Mnemonic | Rationale |
|-------------|-----|--------|----------|-----------|
| WiFi | `#4CAF50` | `0x2E6A` | Green | Established convention from existing GUI; WiFi = green in network tools |
| BLE | `#2196F3` | `0x24BF` | Blue | Bluetooth = blue (brand color) |
| BT Classic | `#00BCD4` | `0x05F4` | Cyan | Related to BLE but distinct; lighter blue family |
| Sub-GHz | `#FF9800` | `0xFC60` | Orange | Warm color = RF energy; distinct from all blues/greens |
| LoRa | `#E040FB` | `0xE1FF` | Magenta | Long-range = distinct from short-range (BLE blue); visible at small sizes |
| Drone | `#F44336` | `0xF1C6` | Red | High attention; drones are noteworthy detections |
| Aircraft | `#9C27B0` | `0x9935` | Purple | Aviation = sky = purple; distinct from drone red |
| RF Sweep | `#607D8B` | `0x63D1` | Blue-gray | Utility function, not a device type; muted color |
| Handheld Import | `#795548` | `0x7AAA` | Brown | External data source; neutral earth tone |

### Threat Level Colors

For persistence score visualization on both devices.

| Level | Score | Dark BG Hex | Dark BG Use | TFT RGB565 | Light BG Hex |
|-------|-------|-------------|-------------|------------|--------------|
| None/Low | 0.0 - 0.29 | `#4CAF50` (green) | Text or dot | `0x2E6A` | `#2E7D32` |
| Medium | 0.3 - 0.49 | `#FFC107` (amber) | Text or dot | `0xFE03` | `#F57F17` |
| High | 0.5 - 0.79 | `#FF9800` (orange) | Text or bar | `0xFC60` | `#E65100` |
| Critical | 0.8 - 1.0 | `#F44336` (red) | Text, bar, or bg | `0xF1C6` | `#B71C1C` |

### Background and Chrome Colors

| Element | Dark Theme (Tkinter + TFT) | Purpose |
|---------|---------------------------|---------|
| Primary background | `#1A1A1A` (Tkinter), `0x0000` pure black (TFT) | Main background |
| Card/panel background | `#2A2A2A` (Tkinter), `0x18E3` dark gray (TFT) | Raised surfaces |
| Selected row | `#3A3A3A` (Tkinter), `0x39C7` (TFT) | List selection highlight |
| Primary text | `#E0E0E0` | Body text (not pure white -- reduces eye strain) |
| Secondary text | `#9E9E9E` | Timestamps, labels, metadata |
| Divider lines | `#424242` (Tkinter), `0x3186` (TFT) | Section separators |

### Accessibility Note

The source type palette was chosen so that the 6 primary types (WiFi, BLE, Sub-GHz, LoRa, Drone, Aircraft) are distinguishable under deuteranopia (red-green color blindness). The single-letter prefix codes on the handheld and the bracketed `[WiFi]`/`[BLE]` tags on the base station provide a non-color channel for source identification. Do not rely on color alone.

---

## 4. Alert Design: Discreet Notification

### Threat Model for Alerts

The user may be:
- In a vehicle being followed (base station mounted in car)
- Walking in public with the handheld in a pocket
- At home with the base station on a desk

Alerts must be **noticed by the user** but **invisible to a nearby observer**. This rules out: audible alarms in public, bright flashing screens, large red warning text visible from 3 meters.

### Base Station (800x480 Tkinter)

**Normal state**: The dashboard shows the unified feed and scanner grid. No special visual state.

**New alert arrival (medium/high)**:
- The alert banner area at the top of the Dashboard tab populates with the new alert.
- The tab label "Dashboard" gains a small colored dot indicator (not text change, not flashing).
- The alert row uses the threat-level left-border color coding described in Section 1.
- No sound. No animation. No popup dialog.

**New alert arrival (critical, score >= 0.9)**:
- Same as above, plus:
- The window title bar appends a subtle indicator: `CYT-NG [!]`
- A single short haptic buzz if a vibration motor is connected (future hardware addition).
- The alert banner row for this alert uses a slightly brighter background to distinguish it from high-level alerts.
- Still no sound, no flashing, no modal dialog.

**Rationale**: On the base station, the user is typically looking at the screen. The alert banner is positioned at the top of the default tab and is the first thing they see. No aggressive notification is needed -- presence in the banner IS the notification.

**Acknowledged alerts**: Tapping/clicking an alert row marks it as acknowledged. It moves from the active banner to the session's alert history (Analysis tab). This keeps the banner clean and focused on new threats.

### Handheld (170x320 TFT)

**Normal state**: Main Status screen shows "ALERTS: 0" in green text.

**New alert arrival (medium/high)**:
- The "ALERTS: N" line updates count and changes color to amber (medium) or orange (high).
- The top alert summary line appears below it.
- The status bar header line (top of screen) gains a small filled circle in the threat-level color, drawn in the top-right corner (2x2 pixel dot at 170px - visible to the user holding the device, invisible to anyone else).
- If the user is on a different screen, the header dot still appears (it is persistent across all screens).

**New alert arrival (critical, score >= 0.9)**:
- Same as above, plus:
- A single short buzz from the piezo buzzer (50ms, 2kHz tone). Short enough to sound like a phone notification, not an alarm. This is the ONLY audible alert and only for critical.
- If a vibration motor is added (per open decisions in hardware.md), prefer vibration over buzzer for true stealth.
- The screen auto-switches to the Alert Screen to show the critical alert detail. (This is the only case of forced screen navigation.)

**Notification while screen is off (display auto-off for battery saving)**:
- Critical alert: Wake the display for 5 seconds, show the Alert Screen, then return to auto-off. Single short buzz.
- High alert: Single short buzz only. Display stays off. User presses any button to check.
- Medium/low alert: No notification while screen is off. User sees it next time they check.

**Design for discretion on the handheld**:
- The TFT is 1.9 inches. At arm's length, only the user can read it. This is inherently discreet.
- The buzzer tone should be configurable (frequency, duration, or off entirely). Some users will want silent-only mode.
- Consider a "stealth mode" config option: disables buzzer entirely, reduces display brightness to minimum, and hides the app name from the header (shows only clock).
- The 3-button interface means the device looks like a generic sensor or MP3 player to a casual observer. Do not add any visible labels like "SURVEILLANCE DETECTOR" to the enclosure.

### Alert Information Architecture

What the user needs to know immediately (fits on both devices):

| Field | Base Station | Handheld | Why |
|-------|-------------|----------|-----|
| Device ID | Full | Truncated to 14 chars | Identification |
| Persistence score | Numeric (0.87) | Numeric (0.87) | Severity at a glance |
| Source type | Color-coded tag | Single letter + color | What kind of sensor detected it |
| Location count | "3 locations" | "3 loc" | Cross-location = high confidence |
| Duration | "47 minutes" | "47m" | How long they have been around |
| Recency | "Last seen 2m ago" | "2m ago" | Is it still here? |

What the user needs on drill-down (base station only, or handheld detail screen):

| Field | Where |
|-------|-------|
| All appearance timestamps | Analysis tab / handheld detail screen |
| All SSIDs probed | Analysis tab / handheld detail screen |
| Cross-source correlations | Analysis tab only |
| GPS coordinates per sighting | Analysis tab / KML export only |
| Reasons array (why flagged) | Alert detail on both devices |
| Score breakdown (which factors contributed) | Alert detail on base station |

---

## 5. Implementation Recommendations

### Priority Order

1. **Color system first**: Define the color constants as a shared module/header before building any UI. Both devices should import from the same palette definition. On the Python side, a `ui_colors.py` module. On the ESP32 side, a `ui_colors.h` header with RGB565 constants.

2. **Dashboard tab second**: This is the screen users will live on. Get the scanner status grid, alert banner, and detection feed working before the other tabs.

3. **Handheld main status screen third**: The most-viewed screen on the handheld. Nail the layout and font choice before building alert and device list screens.

4. **Alert system fourth**: Wire up the discreet notification pipeline on both devices simultaneously to ensure consistency.

### Tkinter-Specific Notes

- `ttk.Notebook` does not support colored tab indicators natively. To add an alert dot to a tab label, use a Unicode character in the tab text (e.g., change "Dashboard" to "Dashboard \u2022" where \u2022 is a bullet). Style the Notebook with a custom `ttk.Style` to control tab appearance.
- The scanner status grid should use `tk.Frame` widgets arranged in a grid, not a `ttk.Treeview`. Frames allow per-cell background color control for scanner state.
- The unified detection feed should use a `tk.Text` widget (not `ScrolledText` -- manage the scrollbar manually for better touch behavior). Use `tag_configure` to apply source-type colors to text ranges.
- For the RF sweep spectral plot, use `tk.Canvas` with `create_line` for the polyline and `create_rectangle` for anomaly bands. Canvas handles touch/drag natively on the Pi touchscreen.
- The current GUI uses 14pt Courier for the log area. This is too large for a multi-source feed. Drop to 10-11pt monospace for the detection feed.

### ESP32 (TFT) Specific Notes

- Use a bitmap font baked into firmware (no TrueType rendering on ESP32). Recommended: 6x12 for body text, 8x16 for headers. This gives 28 chars/line and 20 lines at 6x12, or 21 chars/line and 20 lines at 8x16.
- Partial framebuffer updates (not full-screen redraw) to keep display refresh under 50ms. Only redraw changed lines.
- Pre-render the static layout elements (borders, labels, header bar) once at boot. Only update dynamic content (counts, device IDs, scores) on the 2-second refresh cycle.
- Color constants should be defined as `uint16_t` RGB565 values in a header file, not computed at runtime.

### Current GUI Issues to Fix During Migration

1. **Thread safety**: `_update_status_background()` directly modifies Tkinter widgets from a background thread (lines 324-354 of `cyt_gui.py`). This is unsafe. All widget updates must go through `root.after()` to marshal back to the main thread. The architecture doc correctly specifies this for the new orchestrator, but the existing code violates it.

2. **Hardcoded colors**: The current GUI uses inline hex colors (`#1a1a1a`, `#00ff41`, etc.) with no central definition. Extract to `ui_colors.py` before adding source-type coding.

3. **Emoji in code**: The current GUI uses emoji characters in button labels and log messages. These render inconsistently across platforms and fonts. Replace with text labels or simple Unicode symbols from the basic multilingual plane (checkmark: \u2713, cross: \u2717, circle: \u25CF, etc.).

4. **Font size**: The 14pt Courier in the log output works for a single-purpose WiFi monitor but will not work for a multi-source feed. The detection feed needs 10-11pt monospace with source-type color coding to be information-dense enough.

5. **No touch optimization**: The current buttons have adequate size but the log area has no touch targets. The new detection feed needs per-row touch targets (device detail on tap). Use `tag_bind` on the `tk.Text` widget for this.
