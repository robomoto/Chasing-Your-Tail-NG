# Data Visualization Review: CYT-NG

**Reviewer:** Data Visualization Specialist
**Date:** 2026-03-16
**Scope:** Dashboard, map, RF spectrum, handheld display, and report visualizations across all 9 sensor types

---

## 1. Dashboard Visualizations (Base Station, 800x480)

### 1.1 Unified Detection Feed

The base station implementation plan specifies a Tkinter GUI at 800x480 with a color-coded unified detection feed. Nine source types at varying sample rates (BLE every 60s, ADS-B every 5s, rtl_433 continuous, RF sweep manual) create a heterogeneous event stream. Recommendations:

**Use a scrolling event log with source-type columns, not a flat text stream.** The current `cyt_gui.py` uses a `scrolledtext` widget which produces an undifferentiated wall of text. At 9 source types this becomes unreadable within minutes. Replace with a `ttk.Treeview` configured as a table:

| Time | Source | Device ID | Signal | Persistence | Alert |
|------|--------|-----------|--------|-------------|-------|

- Color the Source column cell background by type using the scheme already defined (green=WiFi, blue=BLE, orange=sub-GHz, red=drone, purple=aircraft). Tkinter `Treeview` supports per-row tags for this.
- Cap visible rows at ~15 (given 800x480 minus header/status area). Older rows scroll off but stay in the buffer.
- Rate-limit the GUI update to 2 Hz via `root.after(500, ...)`. Even if rtl_433 and dump1090 are producing events continuously, the human eye cannot process updates faster than this. Batch events and insert them in a single Treeview refresh.
- Add a source-type filter row (toggle buttons per source) so the operator can isolate, e.g., only BLE + WiFi when doing tracker sweeps.

**Why not a canvas/custom widget?** Tkinter's Treeview is the lightest-weight tabular widget available. Custom canvas drawing for a live feed is more code, harder to scroll, and no faster on a Pi.

### 1.2 Scanner Health/Status Display

The plan calls for a "scanner status grid" replacing the single "Kismet: Running" indicator. For 9 scanners on an 800x480 display:

**Use a 3x3 status tile grid.** Each tile is roughly 250x50 pixels and shows:
- Scanner name (left-aligned, bold)
- Status indicator: a colored circle (green=active, yellow=paused, red=error, gray=disabled). Use `tk.Canvas` with `create_oval` -- a 12px circle is enough.
- Last event timestamp or "never" (right-aligned, smaller font)
- Event rate: e.g., "3/min" (subtle, bottom-right corner)

This gives at-a-glance health without consuming much vertical space. The grid fits in ~160px of vertical space, leaving room for the detection feed below.

**Do not use individual progress bars or animated widgets.** They waste CPU on the Pi and convey no useful information for scanners that are either on or off.

### 1.3 Persistence Score Visualization

Persistence scores are 0.0-1.0 continuous values that are the core output of the detection system. Current reports show them as plain numbers. For the dashboard:

**Use a horizontal bar with color gradient in the Treeview row.** Tkinter Treeview does not natively support in-cell graphics, so the pragmatic approach is:
- Show the numeric score (e.g., "0.73") in the Persistence column.
- Apply row background color: scores above 0.8 get a red-tinted row, 0.6-0.8 orange/yellow, below 0.6 default. This is achievable with Treeview tag-based styling.
- For the dedicated Analysis tab (if built as a separate view), use `tk.Canvas` to draw horizontal persistence bars for the top-N devices. A simple filled rectangle scaled to column width is effective.

**For threshold communication:** Add a single-line "Alert Summary" bar at the top of the detection feed: "3 devices above 0.8 | 7 above 0.6 | 142 total tracked". Color the counts by severity. This is more actionable than any chart at this screen size.

### 1.4 Cross-Source Correlation Visualization

The `FusionEngine` maintains correlation groups (e.g., a phone's WiFi MAC linked to TPMS sensor IDs from the same vehicle). The challenge is showing these linkages on a small screen.

**Primary approach: inline group indicator in the detection feed.** Add a "Group" column to the Treeview. Correlated devices share the same group badge (a short alphanumeric ID or a colored dot). When the user selects a row, highlight all rows in the same correlation group. This is low-cost and works within the existing table paradigm.

**Secondary approach (Analysis tab): simple adjacency list.** When the user clicks "Show Correlations," display a text-based list:
```
Group A: AA:BB:CC (WiFi) <-> tpms:0x1A2B (TPMS) [rule: TPMS-WiFi co-occurrence, 2.0x]
Group B: findmy:a1b2c3 (BLE) <-> AA:BB:CC (WiFi) [rule: BLE+WiFi co-location, 1.3x]
```

**Do not build a node-link graph for the dashboard.** Graph visualizations (networkx, graphviz) are powerful but inappropriate for an 800x480 Tkinter app on a Pi. They require a rendering library, are slow to lay out, and are unreadable at this resolution when there are more than ~10 nodes. If a graph is ever needed, generate it as a static PNG in the report (see Section 5).

### 1.5 Time-Based Patterns (Device Appearance Timeline)

The temporal analysis in `gps_tracker.py` already detects work-hour vs off-hour patterns. For the dashboard:

**Sparkline approach (Analysis tab).** For the top-N suspicious devices, render a 24-hour horizontal bar in a Canvas widget. Each bar is 400px wide (one pixel per 3.6 minutes). Fill pixels where the device was seen. This gives an instant visual of when the device appeared.

Rendering: `canvas.create_rectangle(x1, y, x2, y+8, fill=color)` for each appearance window. Extremely lightweight. No charting library needed.

**This is not appropriate for the main detection feed tab** -- it belongs on a dedicated Analysis tab where the user has opted in to slower, more detailed views.

---

## 2. Map / Spatial Visualization

### 2.1 Current KML Export -- Assessment

The `KMLExporter` class in `gps_tracker.py` is well-built. It generates rich KML with:
- Per-location placemarks with persistence-level styling
- Device tracking paths (LineStrings connecting locations where the same device appeared)
- Heatmap-style polygon overlays for surveillance intensity
- Temporal pattern analysis overlays
- Hierarchical folder structure (critical/high/medium devices)

**KML for Google Earth is the right primary approach for post-session analysis.** It is a zero-dependency output format, it produces professional-looking results, and Google Earth handles large datasets efficiently. The implementation is solid.

**Issues to address in the current KML code:**

1. **The code still references `device.mac` everywhere** despite the base station plan switching to `device_id` as the primary key. The `SuspiciousDevice` dataclass in `surveillance_detector.py` still uses `mac` as its identifier. This needs to migrate to `device_id` for the multi-source expansion to work. The KML templates, balloon content, and folder names all hardcode `.mac`.

2. **Style references are inconsistent.** The `_get_enhanced_kml_template` defines styles like `criticalLocationStyle` and `highThreatLocationStyle`, but the placemark generation code in `generate_kml` references different style IDs (`criticalPersistenceStyle`, `highPersistenceStyle`) that come from the older `kml_template`. Pick one set and use it consistently.

3. **The heatmap circle radius calculation is naive.** `radius_deg = radius_meters / 111000` only works at the equator. At higher latitudes, longitude degrees are narrower. For a tool likely used in the US (Phoenix coordinates in the test data), this is a ~15% error at 33N. Use `radius_deg_lon = radius_meters / (111000 * cos(lat_rad))` for the longitude component.

4. **Missing: multi-source device type rendering.** When CYT-NG expands to 9 sources, the KML should use distinct icons per source type. KML supports custom icon URLs. Use different Google Maps shapes for WiFi (circle), BLE (diamond), TPMS (car), drone (plane-shaped), aircraft (triangle), LoRa (square), etc. The color can still represent persistence level while the shape conveys source type.

### 2.2 Real-Time Map on the Dashboard

**Do not embed a real-time map in the Tkinter dashboard.** The reasons:

- **Leaflet/Folium** generate HTML. Embedding a webview in Tkinter requires `tkinterweb` or `cefpython3`, both of which are heavy, crash-prone on ARM, and pull in Chromium dependencies. On a Pi with 2-4GB RAM running 9 scanner threads, this is a non-starter.
- **Matplotlib with Basemap/Cartopy** is CPU-intensive for real-time updates and the map rendering is slow (1-3 seconds per redraw on a Pi 4).
- **Static image maps** (downloading tiles and blitting with Pillow/tkinter PhotoImage) are technically possible but require significant custom code for pan/zoom and provide a poor experience.

**Recommended alternative: generate a live-updating HTML map file that the user opens in a browser.** The base station runs a lightweight HTTP server (Flask/Bottle, already a reasonable dependency) serving a Leaflet map at `localhost:8080/map`. The map auto-refreshes every 30 seconds via JavaScript polling or SSE. This gives:
- Full pan/zoom/layer control
- Marker clustering for dense device populations
- Polyline tracks for device movement
- Source-type filtering via layer controls
- Works on any browser, including a second monitor or a phone on the same network

This is a clean separation of concerns: the Python backend produces JSON, the browser renders maps. No Tkinter map widget needed.

If a web server is too much scope, the simpler fallback is: on each analysis cycle, overwrite a local HTML file with Folium output and let the user open it manually. Folium generates self-contained HTML with embedded Leaflet.

### 2.3 Device Tracking Paths, Clustering, Multi-Location Correlation

For the KML output and/or the web map:

- **Device paths:** Already implemented as KML LineStrings. For the web map, use Leaflet Polylines with the same color scheme. Add arrowheads to show direction of travel (Leaflet plugin: `leaflet-arrowheads`).
- **Location clustering:** The `GPSTracker` already clusters within 100m. On the map, use Leaflet.markercluster for locations with many devices. Show cluster count as the badge number.
- **Multi-location correlations:** Draw dashed lines between locations where the same device appeared, with the line labeled with the device count. On the KML side, this is already done. On the web map, use colored polylines with a device-count tooltip.
- **Geofencing:** Consider adding configurable geofence circles (home, work, gym) that the user defines once. Any device seen inside 2+ geofences is automatically flagged. Visualize these as semi-transparent circle overlays.

---

## 3. RF Spectrum Visualization

### 3.1 Displaying rtl_power Sweep Data

`rtl_power` outputs CSV rows: `date, time, freq_low, freq_high, freq_step, num_samples, dB_values...`. The natural visualization is a **frequency vs. power line chart** (spectrum plot).

**For the RF Sweep tab (Tkinter):** Use `tk.Canvas` to draw the spectrum directly. This avoids importing matplotlib and keeps memory low.

Implementation sketch:
- Canvas is 750x300 pixels (fitting within 800x480 minus controls).
- X-axis: frequency (24 MHz to 1766 MHz per the config). Map linearly to canvas width.
- Y-axis: power in dBm (typical range -60 to 0 dBm). Map linearly to canvas height.
- Draw the sweep as a polyline: `canvas.create_line(points, fill='#00ff41', width=1)`.
- Add axis labels at major frequency bands (433 MHz, 915 MHz, 1090 MHz, 2.4 GHz if the SDR reaches it).
- Use `canvas.create_text()` for axis labels.

This renders in under 10ms even on a Pi and requires zero external libraries.

### 3.2 Baseline vs. Current Comparison

**Overlay chart.** Draw the baseline sweep as a semi-transparent gray polyline and the current sweep as a bright green polyline on the same canvas. The user instantly sees deviations.

For areas where current exceeds baseline by a configurable threshold (e.g., 10 dB):
- Fill the region between the two curves with a translucent red polygon (`canvas.create_polygon` with `stipple='gray50'` for transparency effect, or use a red fill).
- Add a marker/label at the peak of each anomaly region.

**This dual-overlay approach is the standard in TSCM (Technical Surveillance Countermeasures) tools** and will be immediately familiar to anyone with RF sweep experience.

### 3.3 Anomaly Highlighting

When the RF sweep scanner detects a new persistent signal (present in current sweep but not baseline):

- On the spectrum canvas, draw a vertical band at the anomaly frequency range with a red translucent fill.
- Add a text annotation above the band: frequency, delta-dB, and known protocol if identifiable (e.g., "433.92 MHz +18dB -- possible sub-GHz device").
- In the detection feed, insert an `rf_anomaly:<freq>` entry with the anomaly details.

**Waterfall display (stretch goal).** If multiple sweeps are run in sequence, a waterfall plot (time on Y-axis, frequency on X-axis, power as color) is the gold standard for spotting intermittent transmitters. This can be rendered on a Canvas by drawing horizontal line-by-line with pixel colors mapped from a blue-yellow-red palette. Each new sweep adds one row at the bottom and scrolls older rows up. Limit to ~100 rows of history to keep memory bounded.

---

## 4. Handheld Display (170x320 TFT)

### 4.1 What Fits on 170x320

At 170 pixels wide, you can fit roughly 20 characters of text at a readable font size (8px monospace). At 320 pixels tall, roughly 20 lines of text or 5-6 distinct UI regions. This is a constraint that demands extreme economy.

**Do not attempt charts, graphs, or maps on this screen.** They will be unreadable at this resolution. Even sparklines at 170px wide convey almost nothing useful.

### 4.2 Recommended Handheld Screen Layout

Use a **3-screen rotation** controlled by the three buttons (up/down to scroll within a screen, mode button to switch screens):

**Screen 1: Status + Alert Summary**
```
+------------------+
| CYT  12:34  GPS* |  <- header: time, GPS fix indicator
| ================  |
| WiFi: 47  BLE: 12|  <- device counts by source
| LoRa:  3  Sub:  8|
| ================  |
| ALERT  [====    ] |  <- highest persistence score as a bar
| AA:BB:CC 0.82    |  <- top suspicious device + score
| 3 locations       |  <- key detail
| ================  |
| Session: 2h14m   |  <- session duration
| SD: 847 events   |  <- SD card write count
+------------------+
```

The persistence bar (`[====    ]`) is the single most important visual element on the handheld. It is an 8-character text-based progress bar using block characters. At 0.0 it is empty; at 1.0 it is full. Color the bar text: green below 0.5, yellow 0.5-0.8, red above 0.8. The ST7789 TFT supports 65K colors.

**Screen 2: Device List (scrollable)**
```
+------------------+
| DEVICES  pg 1/3  |
| ================  |
| >AA:BB:CC  W 0.82|  <- selected row, W=WiFi, score
|  findmy:a1  B 0.71|  <- B=BLE
|  tpms:0x1A  S 0.45|  <- S=SubGHz
|  lora:!a1b  L 0.33|  <- L=LoRa
|  drone:DJI  D 0.28|  <- D=Drone
| ================  |
| Sort: score  Filt:|
| [all sources]     |
+------------------+
```

One-character source abbreviation saves space. Sorted by persistence score descending. Scroll with up/down buttons.

**Screen 3: Current Alert Detail**
```
+------------------+
| ALERT DETAIL     |
| ================  |
| AA:BB:CC:DD:EE:FF|
| Type: WiFi probe |
| Score: 0.82      |
| Seen: 14 times   |
| Locs: 3          |
| Last: 2min ago   |
| ================  |
| Reasons:         |
| -Multi-location  |
| -High frequency  |
+------------------+
```

### 4.3 Alert Severity -- Glanceable Communication

The buzzer is the primary alert channel. But visually:

- **Screen background color shift.** When the highest persistence score crosses 0.8, tint the entire screen background from black (#000000) to dark red (#200000). This is visible in peripheral vision even when the device is in a pocket (screen glow through fabric). The ST7789 can set background color per-frame.
- **Flashing header.** Alternate the header text between normal and inverse (white-on-red) at 1Hz when an alert is active. No complex animation needed -- just toggle the color in the draw loop.
- **Buzzer pattern encodes severity:** short beep = new device above 0.5, double beep = above 0.8, continuous pulse = above 0.95 (critical). The firmware maps persistence score to buzzer pattern.

---

## 5. Report Visualization

### 5.1 Current State

Reports are generated as markdown (`.md`) and converted to HTML via pandoc. They contain text-based tables and lists. No charts or diagrams.

### 5.2 Recommended Chart Additions

Use **matplotlib** for report-time chart generation. Matplotlib is already a reasonable dependency (numpy is required for RF sweep anyway), and generating static PNGs for inclusion in HTML reports is a well-trodden path. These charts are generated once at report time, not rendered live, so Pi performance is acceptable.

**Chart 1: Device Timeline (Gantt-style)**

A horizontal bar chart where:
- Y-axis: one row per suspicious device (device_id, truncated)
- X-axis: time (hours or days depending on session length)
- Each bar spans from first_seen to last_seen
- Bar color: persistence score mapped to a red gradient
- Thin tick marks on the bar at each individual appearance timestamp

This is the single most informative chart for a surveillance detection report. It immediately shows which devices overlap in time and which ones have suspiciously long presence durations. Implementation: `matplotlib.barh()` with custom coloring.

**Chart 2: Persistence Score Distribution**

A histogram of all tracked devices' persistence scores.
- X-axis: persistence score (0.0 to 1.0, bins of 0.05)
- Y-axis: device count
- Color the bars: green below 0.5, yellow 0.5-0.8, red above 0.8
- Vertical dashed line at the alert threshold (0.5 default)

This shows the operator how many devices are "normal" vs. suspicious. A healthy environment should have a heavy left skew (most devices near 0). A right-heavy tail suggests a problem. Implementation: `matplotlib.hist()`.

**Chart 3: Source Type Breakdown**

A horizontal bar chart (not pie -- pie charts are hard to read with 9 categories):
- Y-axis: source type (WiFi, BLE, BT Classic, Sub-GHz, LoRa, Drone, Aircraft, RF Sweep, Handheld)
- X-axis: number of unique devices detected per type
- Secondary bar (stacked or grouped): number of devices above the persistence threshold per type

This tells the operator which sensor types are contributing the most detections and, more importantly, which types are producing the most suspicious hits. If all high-persistence devices are from a single source type, that either points to a real pattern or a calibration issue.

**Chart 4: Hourly Activity Heatmap**

A 7x24 grid (day-of-week vs. hour-of-day) with cell color intensity proportional to the number of suspicious device appearances. This reveals scheduling patterns (e.g., surveillance that occurs M-F 9-5, or every evening).

Implementation: `matplotlib.imshow()` or `seaborn.heatmap()` (seaborn is a lighter add than it seems and produces clean heatmaps).

**Chart 5: Cross-Source Correlation Graph (report only)**

For the report (not the dashboard), a node-link diagram is justified. Use `networkx` to lay out the correlation groups from `FusionEngine.get_correlated_groups()`:
- Nodes: device_ids, colored by source type, sized by persistence score
- Edges: correlation rules, labeled with the rule name and score multiplier
- Layout: spring layout for small graphs (<50 nodes), or hierarchical if groups are cleanly separated

Render to PNG with `matplotlib` backend. This is a report artifact, not a live widget, so rendering time (1-2 seconds) is acceptable.

### 5.3 Embedding Charts in Reports

Current flow: Python generates `.md`, then pandoc converts to `.html`.

Recommended flow:
1. Matplotlib generates PNGs to a `report_assets/` directory alongside the report.
2. The markdown report references the images: `![Device Timeline](report_assets/timeline_20260316.png)`
3. Pandoc converts to HTML with embedded images (use `--self-contained` flag to base64-encode images into the HTML for a single portable file).

Alternatively, skip the markdown intermediate and generate HTML directly with base64-encoded chart images using Python's `base64` module. This removes the pandoc dependency.

---

## 6. Library Recommendations Summary

| Context | Library | Rationale |
|---------|---------|-----------|
| Dashboard (live, Pi) | Tkinter Treeview + Canvas | Already in use, zero additional dependencies, fast enough |
| Dashboard RF spectrum | tk.Canvas polylines | No external library, renders in <10ms |
| Web map (optional) | Flask + Leaflet.js | Clean separation, works on any browser, lightweight server |
| KML export | String templates (current) | No library needed, current approach is correct |
| Report charts | matplotlib | Already needed (numpy for RF), generates static PNGs |
| Report heatmap | matplotlib.imshow (or seaborn) | Clean heatmaps with minimal code |
| Report correlation graph | networkx + matplotlib | Standard graph layout, renders to PNG |
| Handheld display | Direct ST7789 framebuffer | No visualization library -- raw pixel writes + text rendering |

**Libraries to avoid on the Pi dashboard:** plotly (heavy, needs browser), bokeh (same), dash (full web framework), PyQtGraph (Qt dependency), pygame (overkill).

---

## 7. Key Action Items (Prioritized)

1. **Replace the scrolledtext detection feed with a Treeview table.** This is the single highest-impact improvement for dashboard usability with 9 sources.

2. **Migrate KML code from `device.mac` to `device_id`.** The entire multi-source expansion depends on this. The KML templates, balloon HTML, folder names, and the `SuspiciousDevice` dataclass all need updating.

3. **Fix KML style ID inconsistencies.** The `generate_kml` method references styles not defined in `_get_enhanced_kml_template` and vice versa. Unify to one style set.

4. **Build the RF spectrum Canvas widget** for the RF Sweep tab. This is a <200-line implementation using only tk.Canvas and is the primary visualization for bug sweep mode.

5. **Add matplotlib report charts** (timeline, histogram, source breakdown). Three charts, roughly 50-80 lines of matplotlib each, with major information gain in the reports.

6. **Design the handheld 3-screen layout** and implement the text-based persistence bar and background color severity indicator.

7. **Consider a lightweight web map server** as a Phase 5+ addition. Keep it out of scope until the core dashboard and reports are solid.
