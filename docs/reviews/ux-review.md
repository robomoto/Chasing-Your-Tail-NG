# UX Review: Chasing Your Tail - Next Generation

**Reviewer:** UX Specialist
**Date:** 2026-03-16
**Scope:** Full system review -- base station (Pi 5), handheld (ESP32-S3), GUI (`cyt_gui.py`), planned expansion (9 scanner types)

---

## 1. User Personas

### Persona A: Stalking / Domestic Violence Survivor

- **Technical skill:** Low to none. May not own a computer beyond a phone. Likely received this tool through a victim advocate or shelter.
- **Emotional state:** Fearful, hypervigilant, possibly in active danger. Cognitive load is already maxed out.
- **Primary need:** A clear yes/no answer: "Is someone tracking me right now?" They do not care about TPMS sensor IDs or LoRa node roles.
- **Key constraint:** The tool itself must not become a weapon against them. If discovered by their abuser, it could escalate violence. If it produces a false positive, they may make a dangerous confrontation. If it produces a false negative, they may lower their guard.
- **Device context:** Likely only uses the handheld. May never see the base station.

### Persona B: Security Researcher / Pentester

- **Technical skill:** High. Comfortable with SDR, Kismet, command-line tools, soldering.
- **Emotional state:** Curious, analytical. Wants granular data.
- **Primary need:** Raw data access, protocol-level detail, exportable logs, extensibility. Wants to see every BLE advertisement, every TPMS ID, every LoRa header.
- **Device context:** Uses both base station and handheld. Likely builds their own hardware.

### Persona C: Journalist / Activist Under Surveillance

- **Technical skill:** Moderate. Can follow setup instructions but is not an RF engineer.
- **Emotional state:** Alert but functional. Operating in a hostile environment (authoritarian state, organized crime investigation, protest).
- **Primary need:** Detect patterns over time -- "Am I being followed across days/weeks?" Needs session history, cross-location correlation, and exportable evidence.
- **Device context:** Needs the handheld to be discreet. May use the base station at a safe house or office.

### Persona D: Concerned Individual (Privacy-Conscious)

- **Technical skill:** Moderate. Hobbyist-level electronics comfort.
- **Emotional state:** Cautious but not in immediate danger. Wants to understand their RF environment.
- **Primary need:** Educational -- understand what is broadcasting around them. Bug sweep for a new apartment, check a used car for trackers.
- **Device context:** Full system, used occasionally rather than daily.

### Critical Observation

The project documentation and current GUI are designed for Persona B (the "BlackHat Arsenal" branding, matrix-green terminal aesthetic, technical jargon). **Persona A -- the person this tool could help the most -- is the least served by the current design.** This is the central tension of the entire UX strategy.

---

## 2. Critical User Flows

### 2.1 First-Time Setup

**Current state:** No guided setup exists. The user must read hardware docs, solder components, flash firmware, install system packages (`rtl_433`, `dump1090`, `bleak`, `meshtastic`), configure `config.json` manually, and start Kismet.

**Problems:**
- The BOM alone ($334-$512) requires sourcing 12-15 components from multiple vendors.
- GPIO pin mapping, SPI bus sharing, and antenna strategy require electronics knowledge.
- Software installation involves system packages, Python packages, Kismet configuration, and crontab entries.
- No first-run wizard or guided configuration exists.

**Recommendations:**

1. **Define a "Level 0" setup** that requires zero soldering and minimal configuration:
   - Handheld: Pre-flashed T-Display-S3 with USB-C cable. No LoRa, no external antenna, no GPS module. Just WiFi + BLE scanning with the built-in radios. Cost: ~$18 + battery.
   - Base station: Pi 5 with a single Alfa ACHM adapter. Kismet + CYT. No SDR, no LoRa sniffer. Cost: ~$120.
   - This covers the two highest-value detection capabilities (WiFi probe persistence + BLE tracker detection) with the simplest possible hardware.

2. **Ship a first-run wizard** in the GUI that:
   - Auto-detects connected hardware (which USB devices are present, is BLE available, is GPS connected).
   - Enables only the scanners that have hardware present.
   - Walks through creating an initial ignore list ("We are going to scan for 5 minutes to learn your normal environment. Stay in your home.").
   - Sets a location label for the current position.

3. **Provide pre-built SD card images** for the base station (Pi 5) with all software pre-installed. The user inserts the card, connects hardware, and powers on.

4. **For Persona A specifically:** Partner with DV organizations to provide pre-assembled, pre-configured kits. The user should unbox it and press one button.

### 2.2 Daily Carry Workflow (Handheld)

**Current state:** The handheld has a 1.9-inch 170x320 screen and 3 buttons. No firmware exists yet (planned), so this is a design-phase review.

**The ideal daily carry experience:**

1. User charges the handheld overnight (USB-C, same as phone charger).
2. User drops it in a bag or pocket in the morning. It auto-starts scanning on power-on.
3. **The user does not need to look at it unless it buzzes.** This is the most important design principle for the handheld.
4. If it buzzes, user glances at screen. Screen shows one of:
   - **Green: "All clear."** (Periodic heartbeat buzz, configurable, default off.)
   - **Yellow: "New device nearby -- monitoring."** (First sighting of a device; not yet suspicious.)
   - **Red: "ALERT: Device following you."** (Same device seen at multiple locations or across extended time.)
5. User can press a button to see details or dismiss.
6. At end of day, user plugs handheld into base station (or just charges it -- data uploads automatically or via SD swap).

**Recommendations:**

1. **Default to silent operation.** No buzzing, no screen activity unless there is a genuine alert. The screen should be off by default (saves battery, avoids drawing attention).
2. **Three-tier alert system:**
   - **Buzz pattern 1 (single short):** Informational. A device of interest was detected. No action needed.
   - **Buzz pattern 2 (double pulse):** Warning. A device has been seen at 2+ locations or for an extended period.
   - **Buzz pattern 3 (continuous):** Critical. High-confidence surveillance detection. User should take action.
3. **Wake-on-button:** Screen stays off until a button is pressed. First press shows current status summary (one line: "3 devices tracked, 0 alerts"). Second press shows device list. Third press cycles through details.
4. **Auto-location tagging via GPS:** The handheld should silently track location changes. When the user moves more than 500m from their last position, a new "location zone" begins. This is how multi-location correlation works -- the user never has to manually tag locations.
5. **Add a vibration motor.** The buzzer is audible and could draw attention. A vibration motor is discreet. The open decisions section already notes this -- strongly recommend making vibration the default, buzzer optional.

### 2.3 Alert Response

**Current state:** No alert response workflow exists. The GUI shows a log of detected devices but provides no guidance on what to do.

**This is the most dangerous UX gap in the entire system.** A user who receives an alert and does not know what to do may:
- Confront their stalker (escalation risk).
- Panic and behave erratically (tips off the stalker that they know).
- Ignore the alert (defeats the purpose).
- Call law enforcement unprepared (wastes the evidence opportunity).

**Recommendations:**

1. **Build an "Alert Response Guide" into the firmware/GUI.** When an alert fires, the first screen should not be technical details. It should be:

   ```
   ALERT: A device may be tracking you.

   DO:
   - Stay calm. Do not change your behavior.
   - Continue to your destination normally.
   - When safe, review the details below.

   DO NOT:
   - Confront anyone.
   - Try to find the device right now.
   - Post about this on social media.

   [View Details]  [Save Evidence]  [Dismiss]
   ```

2. **"Save Evidence" button:** One tap saves a timestamped snapshot of the detection (device IDs, times, locations, signal strengths) to a file suitable for law enforcement. Include a "How to file a police report with this data" guide in the documentation.

3. **Escalation tiers:**
   - **Tier 1 (informational):** "A BLE tracker has been near you for 30 minutes." Action: Awareness only.
   - **Tier 2 (warning):** "A device was seen at your home AND your workplace." Action: Consider varying your route. Save evidence.
   - **Tier 3 (critical):** "A device has followed you across 3+ locations over multiple days." Action: Contact law enforcement or a DV advocate. Evidence has been auto-saved.

4. **Never name the suspected tracker owner.** The system cannot know who placed a tracker. Showing a device name like "John's iPhone" could lead to incorrect and dangerous assumptions.

### 2.4 Session Review (Base Station)

**Current state:** The GUI has an "Analyze Logs" button that runs `probe_analyzer.py` and dumps text output to a log window. A "Surveillance Analysis" button generates KML files and markdown reports. The output is technical and text-heavy.

**Problems:**
- The log window uses 14pt Courier with matrix-green text on black background. This is stylistically on-brand but functionally poor for reading dense analytical output.
- Results are saved to timestamped files in `./reports/` and `./surveillance_reports/`. The user must navigate the filesystem to find them.
- No visual summary -- no charts, no maps in the GUI, no timeline view.
- Handheld import is planned but has no UI yet.

**Recommendations:**

1. **Dashboard-first design.** When the user opens the session review, they should see:
   - A number: "5 devices of interest today."
   - A severity breakdown: "0 critical, 2 warnings, 3 informational."
   - A timeline: horizontal bar showing when alerts occurred during the day.
   - A list, sorted by threat level, with expand-to-detail.

2. **Handheld data import should be automatic.** When the handheld is plugged in via USB-C, the base station should detect it, pull the session data, run cross-correlation, and present results. No file dialogs, no SD card swapping.

3. **Map integration.** The KML export to Google Earth is a good start, but requiring an external application adds friction. Consider an embedded map view (Leaflet.js in a webview, or a simple Python map library) that shows device sighting locations directly in the GUI.

4. **Report generation for law enforcement.** A "Generate Report" button should produce a clean PDF with:
   - Date range covered.
   - Summary of suspicious devices with evidence.
   - GPS coordinates and times.
   - Signal strength data supporting the "this device was physically near me" claim.
   - No technical jargon. Written for a detective, not an RF engineer.

### 2.5 Bug Sweep (Room / Vehicle)

**Current state:** RF Sweep is planned as a manual-activation mode that pauses `rtl_433` and runs `rtl_power` for wideband spectrum analysis. No UI exists yet.

**The bug sweep is a fundamentally different interaction model** from passive daily monitoring. It is active, focused, and time-bounded. The user is walking around a space, watching signal strength change in real time.

**Recommendations:**

1. **Dedicated "Sweep Mode" with its own UI.** Do not bury this in a tab. It should be a top-level mode that takes over the entire screen.

2. **Signal strength meter front and center.** The primary display during a sweep should be a large, clear signal strength indicator that updates in real time. As the user moves the handheld closer to a hidden transmitter, the bar/number goes up. This is the "Geiger counter" interaction model -- it must feel immediate and physical.

3. **Frequency band selection with plain-language labels:**
   - "Hidden cameras" (covers 900 MHz, 1.2 GHz, 2.4 GHz, 5.8 GHz analog/digital video)
   - "GPS trackers" (covers 315/433 MHz for cheap trackers, 2.4 GHz for BLE trackers)
   - "Audio bugs" (covers common wireless microphone frequencies)
   - "Full spectrum" (everything)

4. **Guided sweep procedure:**
   - Step 1: "Stand in the center of the room. Press Start to capture baseline."
   - Step 2: "Slowly walk along each wall, holding the device at waist height."
   - Step 3: "Check furniture, fixtures, electrical outlets, smoke detectors."
   - Step 4: "Review results."

5. **For vehicle sweeps:** Specific guidance on checking wheel wells (TPMS cross-reference: "We found 4 TPMS sensors, which is normal for a 4-tire vehicle. If you see 5+, investigate."), OBD-II port, under seats, inside headliner.

---

## 3. Onboarding

### The Complexity Problem

The full system has:
- 9 scanner types
- 7 simultaneous radios
- 12-15 hardware components
- 5+ system packages to install
- A JSON config file with 50+ settings
- Ignore lists, allowlists, baseline files, and session databases

This is appropriate for Persona B. It is an insurmountable barrier for Persona A.

### Minimum Viable Setup (for a non-technical stalking victim)

**Hardware:** T-Display-S3 + battery. Nothing else. Cost: ~$23.

**What it does:** WiFi probe persistence detection + BLE tracker detection. These two capabilities alone cover the most common consumer-level stalking tools (AirTags, SmartTags, Tile trackers) and the most common RF tracking vector (WiFi probe requests from a phone following you).

**Firmware behavior:** Power on, scan, alert if something follows you. No configuration. No base station. No GPS module (uses WiFi BSSID location estimation or simply tracks "I have been in the same place for a while and this device has been here the whole time").

**Onboarding flow (on-device):**
1. Power on. Screen shows: "Learning your environment. This takes 5 minutes. Stay where you are."
2. After 5 minutes: "Setup complete. I will alert you if a device follows you. Put me in your bag."
3. Done.

### Progressive Disclosure for Advanced Users

After the minimum viable setup, users who want more capability can progressively add:

| Level | What to Add | What It Enables | Complexity |
|-------|------------|-----------------|------------|
| 0 | Nothing (T-Display-S3 only) | WiFi + BLE tracking detection | Plug in and go |
| 1 | GPS module ($8, plug into header) | Location-aware alerts ("seen at home AND work") | Solder 2 wires |
| 2 | LoRa module ($10) | Meshtastic node detection | Solder 4 wires + SPI |
| 3 | Base station (Pi + 1 WiFi adapter) | Historical analysis, reports, 5 GHz WiFi | Follow setup guide |
| 4 | RTL-SDR ($32) | TPMS, sub-GHz bugs, RF sweep | Install system packages |
| 5 | Full base station (all radios) | ADS-B, full spectrum, data fusion | Full build |

**The GUI and firmware should adapt to the hardware present.** If no GPS is connected, do not show GPS-related options. If no RTL-SDR is present, do not show RF Sweep mode. Auto-detection, not configuration.

---

## 4. Alert Fatigue

### The Scale of the Problem

In a typical urban environment, a single 10-minute walk might encounter:
- 50-200 BLE advertisements (AirPods, fitness trackers, smartwatches, AirTags attached to luggage/keys/pets)
- 100-500 WiFi probe requests (phones, laptops, IoT devices)
- 20-50 TPMS signals (every passing car broadcasts 4 tire sensor IDs)
- 10-30 Meshtastic nodes (in areas with LoRa adoption)
- Dozens of sub-GHz signals (garage doors, weather stations, security sensors)

If every detection generates an alert, the tool is unusable within minutes.

### Alert Hierarchy (Recommended)

**Level 0: Silent logging (no notification)**
- First sighting of any device. Most devices will never be seen again.
- All TPMS signals from moving traffic.
- Known infrastructure (whitelisted LoRa routers, the user's own devices).
- Devices flagged as stationary (weather stations, security sensors).

**Level 1: Informational (logged, visible in review, no real-time alert)**
- A device has been seen for more than 20 minutes in the same location.
- A BLE tracker (AirTag/SmartTag/Tile) detected nearby. Note: Apple already sends AirTag alerts to iPhones. This is supplementary.
- A drone is detected via Remote ID.

**Level 2: Warning (vibration/buzz, shown on screen)**
- A device has been seen at 2 different locations (user moved 500m+ between sightings).
- A BLE tracker has been near the user for 1+ hours continuously.
- The same drone serial number is seen in multiple sessions.
- Cross-source correlation fires (e.g., same TPMS IDs + same WiFi MAC = same vehicle).

**Level 3: Critical (persistent vibration, unmissable alert)**
- A device has been seen at 3+ locations across different days.
- A device's persistence score exceeds the configurable threshold (default 0.8).
- Aircraft circling pattern detected with a known government registration.
- Cross-session handheld + base station correlation confirms following behavior.

### Filtering Strategies

1. **Time-gated suppression.** A device must be present for a minimum duration before any alert fires. Default: 15 minutes for WiFi, 30 minutes for BLE (because BLE MAC rotation makes short-term presence less meaningful), 5 minutes for TPMS (because TPMS is only relevant if the same vehicle is parked near you persistently).

2. **Movement-gated alerts.** The most valuable signal is "this device followed me from A to B." If the user has not moved, most detections are neighbors, coworkers, or ambient noise. Only escalate alerts when the user has changed location zones.

3. **Familiar device learning.** After a configurable period (default: 7 days), devices seen regularly at the user's home/work locations should be auto-added to a "familiar" list. The system should prompt: "We see this device every day at your home. Mark as familiar?" Familiar devices are suppressed unless they appear at unexpected locations.

4. **Context-aware baselines.** A coffee shop will always have dozens of devices. The system should learn that "50 devices at Location X is normal" and only alert on anomalies relative to the baseline for that location.

5. **User-adjustable sensitivity.** A simple slider: "Cautious" (more alerts, more false positives) to "Quiet" (fewer alerts, risk of missing something). Default to middle. Persona A should probably start at "Quiet" and Persona B at "Cautious."

---

## 5. Accessibility

### Vision Impairment

**Handheld (1.9-inch 170x320 TFT):**
- The screen is small enough that even users with normal vision will struggle in bright sunlight.
- For low-vision users, the screen is essentially useless for reading text.
- **Recommendation:** The handheld should work entirely without the screen via haptic/audio feedback. Vibration patterns and buzzer tones should encode all critical information:
  - 1 short buzz = all clear.
  - 2 short buzzes = warning.
  - 3 rapid buzzes = critical alert.
  - Long continuous buzz = sweep mode signal strength (faster = stronger).
- **Screen contrast:** When used, the screen should offer a high-contrast mode (black text on white, or white text on black, with large font). The matrix-green-on-black aesthetic in the current GUI fails WCAG contrast guidelines and should be avoided on the handheld.

**Base station GUI (`cyt_gui.py`):**
- The current GUI uses emoji-heavy labels (lock emoji, chart emoji, rocket emoji). Screen readers may or may not read these predictably.
- Matrix-green (#00ff41) on black (#000000) has a contrast ratio of ~5.5:1, which meets WCAG AA for large text but fails for body text (requires 4.5:1 minimum, and the 14pt Courier log is borderline).
- Status indicators rely on color alone (green = running, red = not running). Color-blind users cannot distinguish these.
- **Recommendations:**
  - Add text labels alongside all color indicators ("Running" / "Stopped" not just green/red dots).
  - Increase font size in the log area or make it configurable.
  - Use shape + color for status (checkmark + green, X + red) -- the emoji approach partially achieves this.
  - Offer a "high contrast" theme option.
  - Ensure all interactive elements are keyboard-navigable (Tkinter supports this natively with `takefocus` and key bindings).

### Motor Impairment

**Handheld (3 tactile buttons):**
- Tactile buttons with physical travel are actually better than touchscreens for motor-impaired users.
- However, 6mm buttons are small. Consider larger buttons (10-12mm) or a rocker switch design.
- Button hold durations should be configurable (long-press thresholds).
- The most critical interaction (dismissing an alert) should require only a single press of any button.

**Base station GUI:**
- Button sizes in the current GUI are reasonable (12-18 character width).
- The confirmation dialog for "Delete Ignore Lists" and "Quit" requires precise mouse targeting. Consider keyboard shortcuts for all primary actions.
- Touch screen support (the Pi 7-inch touchscreen is in the BOM) means buttons should have generous padding and hit targets of at least 48x48 pixels.

### Cognitive Accessibility

- The current GUI presents 7 buttons simultaneously, each with a two-line label.
- For users under extreme stress (Persona A), decision paralysis is real.
- **Recommendation:** A "simple mode" that shows exactly 2 elements:
  1. A large status indicator: "SAFE" (green) / "WARNING" (yellow) / "ALERT" (red).
  2. A single button: "Tell me more" (expands to details).

---

## 6. Safety Considerations

### The Tool Being Discovered

**Risk:** A stalker finds the handheld device on their victim. This could:
- Reveal that the victim knows they are being tracked (escalation trigger).
- Provide the stalker with the victim's location data (the GPS logs on the SD card).
- Be destroyed, removing the victim's evidence.

**Mitigations:**
1. **Disguise mode.** The handheld should have a configuration option that changes the boot screen and UI to look like something innocuous -- a temperature/humidity sensor, a step counter, a generic "IoT device." No "Chasing Your Tail" branding visible.
2. **SD card encryption.** Session data on the SD card should be encrypted with a user-set PIN. If the card is removed and read on another device, it shows nothing useful.
3. **Quick-wipe button.** A specific button combination (e.g., hold all 3 buttons for 5 seconds) should wipe all session data and reset to factory appearance. This is a last resort.
4. **Cloud backup option.** If the device is confiscated or destroyed, the evidence should already be somewhere safe. Consider an optional encrypted upload to a cloud service via the base station, or automatic sync when connected to a trusted WiFi network.
5. **Physical appearance.** The current hardware plan includes two SMA antenna connectors protruding from the top of the enclosure. This looks like a radio device. Consider internal antennas with reduced range but increased discretion, or a form factor that looks like a common object (portable battery pack, small Bluetooth speaker).

### False Positives Leading to Confrontation

**Risk:** The tool alerts the user that they are being followed. The user confronts the wrong person. Violence ensues.

**Mitigations:**
1. **Never present alerts as certainties.** Language matters. "DETECTED: You are being stalked" is dangerous. "A device has been near you in multiple locations. This may warrant attention." is safer.
2. **Require multi-factor confirmation before critical alerts.** A single WiFi MAC seen twice is not enough for a critical alert. Require: multiple sightings + multiple locations + significant time span + ideally cross-source confirmation.
3. **Include probability language in all alerts.** "Moderate confidence" / "High confidence" language sets appropriate expectations.
4. **Explicitly advise against confrontation in every alert.** This cannot be stated too many times.

### False Negatives Creating False Sense of Security

**Risk:** The tool says "all clear" but the user is actually being tracked by a method the tool cannot detect (cellular IMSI catcher, visual surveillance, GPS tracker on a frequency the handheld does not cover).

**Mitigations:**
1. **State limitations clearly during onboarding.** "This tool monitors WiFi, Bluetooth, and [other enabled scanners]. It cannot detect all forms of surveillance. If you believe you are in danger, contact law enforcement regardless of what this tool shows."
2. **Never display "You are safe."** The absence of alerts should be presented as "No suspicious devices detected" not "You are not being tracked." The difference is critical.
3. **Show scanner coverage.** The status screen should show what the device IS monitoring, so the user understands the scope. "Active: WiFi, BLE. Not available: Sub-GHz, ADS-B, LoRa." This sets expectations.

### Data as Evidence vs. Data as Liability

**Risk:** The session data could be subpoenaed and used against the user, or could reveal the user's own movements to an adversary.

**Mitigations:**
1. **Configurable data retention.** Auto-delete session data older than N days (user-configurable, default 30).
2. **Selective export.** When generating a report for law enforcement, allow the user to select a date range and specific devices, not dump everything.
3. **Do not log the user's GPS coordinates continuously by default.** Log GPS only when an alert-worthy event occurs, or give the user a clear opt-in with an explanation of the tradeoff.

### The Tool Itself as a Tracking Device

**Risk:** If a stalker gains access to the base station (e.g., an abusive partner who lives in the same home), they could use CYT's capabilities to track the victim's phone, not the other way around.

**Mitigations:**
1. **Authentication on the base station.** The GUI and all analysis tools should require a PIN or password.
2. **Audit logging.** All queries and report generations should be logged with timestamps. If the system is being misused, there is a trail.
3. **Consider this in marketing and documentation.** CYT is a dual-use tool. The documentation should include a clear ethical use statement and a warning that using it to track someone without their consent is illegal in most jurisdictions.

---

## Summary of Priority Recommendations

| Priority | Recommendation | Effort | Impact |
|----------|---------------|--------|--------|
| **P0** | Define "Level 0" minimum viable setup (T-Display-S3 only, no config) | Low | Unlocks Persona A |
| **P0** | Build alert response guidance into every alert | Low | Prevents dangerous user behavior |
| **P0** | Never display certainty language ("You are being stalked") | Low | Safety-critical |
| **P0** | Add disguise mode to handheld firmware | Medium | Protects Persona A if discovered |
| **P1** | Replace buzzer-default with vibration-motor-default on handheld | Low (hardware change) | Discretion |
| **P1** | Implement 3-tier alert hierarchy with movement-gated escalation | Medium | Solves alert fatigue |
| **P1** | Auto-detect connected hardware and enable only relevant scanners | Medium | Simplifies onboarding |
| **P1** | Encrypt SD card session data | Medium | Protects evidence |
| **P2** | First-run wizard in GUI | Medium | Onboarding for Personas A and C |
| **P2** | Dashboard-first session review (replace log dump) | Medium | Usability for all personas |
| **P2** | Automatic handheld data import on USB connection | Medium | Reduces friction |
| **P2** | "Simple mode" for base station GUI (1 big status + 1 button) | Low | Cognitive accessibility |
| **P2** | Accessible color scheme and screen-reader support in GUI | Low | Vision accessibility |
| **P3** | Pre-built SD card images for Pi | Medium | Onboarding for Persona C |
| **P3** | Embedded map view in base station GUI | High | Replaces Google Earth dependency |
| **P3** | Law enforcement report generator (clean PDF, no jargon) | Medium | Evidence usability |
| **P3** | Guided bug sweep mode with Geiger-counter UX | Medium | Bug sweep usability |
| **P3** | Familiar device learning and context-aware baselines | High | Long-term alert fatigue reduction |

---

## Closing Note

CYT-NG is technically impressive -- 9 scanner types, cross-source data fusion, multi-location correlation. The engineering is sound. The gap is in the translation layer between that engineering and the human who needs it most. A stalking victim with an AirTag in their bag does not need a spectrum analyzer. They need a device that vibrates twice and shows four words: "Something is following you." Everything else is details they can access later, when they are safe, with someone who can help them interpret it. Design for that moment first.
