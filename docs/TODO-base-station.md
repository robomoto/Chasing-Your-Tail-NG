# Base Station TODO

Remaining work items for the Raspberry Pi base station. The scanner framework, all 9 sensor implementations, integration wiring, fusion engine, alert system, and safety features are complete. These items are lower priority or require interactive/hardware testing.

## GUI Overhaul (Medium Effort — Own Branch)

### Tabbed Interface
- [ ] Replace single-view layout with `ttk.Notebook` tabs: Dashboard, Scanners, Analysis, RF Sweep
- [ ] Dashboard tab: scanner status grid (7 cells, color-coded), active alerts banner (top 3), unified detection feed
- [ ] Scanners tab: per-scanner start/stop controls, detailed status per scanner
- [ ] Analysis tab: session history table, cross-session device search, export controls
- [ ] RF Sweep tab: sweep controls, tk.Canvas frequency-vs-power plot, baseline comparison overlay

### Detection Feed
- [ ] Replace `scrolledtext` widget with `ttk.Treeview` for multi-column detection feed
- [ ] Color-code rows by source type (WiFi=green, BLE=blue, Sub-GHz=orange, Drone=red, Aircraft=purple, LoRa=magenta)
- [ ] Rate-limit GUI updates to 2 Hz max

### Thread Safety
- [ ] Fix all background threads that directly modify Tkinter widgets — wrap in `root.after()` calls
- [ ] Affected methods: `_update_status_background`, `_check_status_background`, `_create_ignore_lists_background`, `_run_cyt_background`, `_analyze_logs_background`, `_surveillance_analysis_background`

### Color System
- [ ] Implement source type color palette (deuteranopia-safe): WiFi=#28a745, BLE=#007bff, BT Classic=#17a2b8, Sub-GHz=#fd7e14, LoRa=#e83e8c, Drone=#dc3545, Aircraft=#6f42c1, RF Sweep=#6c757d
- [ ] Implement threat level palette: green (0-0.29), amber (0.3-0.49), orange (0.5-0.79), red (0.8-1.0)
- [ ] Non-color fallbacks for all status indicators (letter codes, bracketed tags)

### Discreet Alert Display
- [ ] Alert banner at top of Dashboard tab with threat-level left-border coloring
- [ ] No sound, no animation, no popups by default
- [ ] Critical alerts: subtle `[!]` in window title
- [ ] Safety resources always accessible from menu

## Report Generation (Medium Effort)

### Chart Generation
- [ ] Device timeline (gantt-style, matplotlib) showing when each suspicious device was seen
- [ ] Persistence score histogram
- [ ] Source type breakdown bar chart
- [ ] Hourly activity heatmap
- [ ] Cross-source correlation graph (networkx)
- [ ] Embed as base64 PNGs in self-contained HTML (eliminate pandoc dependency)

### Report Content Updates
- [ ] Replace raw persistence scores with tier labels (INFORMATIONAL/NOTABLE/ELEVATED/REVIEW)
- [ ] Replace "CRITICAL"/"surveillance" language with AlertFormatter output
- [ ] Add response guidance to report footer
- [ ] Include safety resource links in every report

## Daily Summary Mode (Quick)

- [ ] Implement daily summary digest: aggregate alerts from the past 24h into a single report
- [ ] Make daily summary the default mode (real-time alerting opt-in via config)
- [ ] Summary includes: top suspicious devices, new correlated groups, scanner health, data retention stats

## Self-Monitoring Mode Enforcement (Quick)

- [ ] When `monitoring_mode: "self"`, auto-delete raw device sightings that don't meet any persistence threshold after each session
- [ ] Only retain data for devices that appear in multiple time windows or locations
- [ ] Log a count of discarded records for transparency

## Hardware-Dependent Testing

These require actual Pi hardware and can't be tested in CI:
- [ ] Verify Alfa AWUS036ACHM monitor mode with mt76 driver on Pi 5
- [ ] Verify dual RTL-SDR V4 operation on powered USB hub
- [ ] Test BLE scanning with real AirTag/SmartTag/Tile devices
- [ ] Test rtl_433 with real TPMS signals
- [ ] Test dump1090 with real ADS-B signals
- [ ] Test Heltec V3 LoRa sniffer with real Meshtastic traffic
- [ ] Verify USB bandwidth with all 5+ USB devices connected simultaneously
- [ ] Battery life testing with PiSugar UPS

## Documentation

- [ ] User guide for first-time setup (targeted at non-technical users per UX review)
- [ ] Scanner configuration reference
- [ ] Troubleshooting guide (common hardware issues)
- [ ] Contributing guide
