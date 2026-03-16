# CYT-NG Planning Docs

Planning documentation for Chasing Your Tail - Next Generation development.

## Contents

### Hardware
- [Base Station Hardware](base-station-hardware.md) - Full Pi 5 build: 7 simultaneous radios, BOM (~$454), antenna strategy
- [Handheld Hardware](esp32-port/hardware.md) - Full ESP32-S3 build: WiFi + BLE + LoRa, BOM (~$58), pin map

### Base Station Implementation
- [Architecture Overview](base-station-implementation.md) - Scanner abstraction, orchestration model, 9 scanner specs, data fusion
- [Detailed Upgrade Plan](base-station-upgrade-plan.md) - Code-level implementation: function stubs, class modifications, migration paths, testing criteria (1,534 lines)
- [Test Strategy](test-strategy.md) - TDD plan: ~250 test cases, framework setup, implementation order, CI config

### ESP32 Handheld Firmware
- [Firmware Architecture](esp32-port/firmware-architecture.md) - Task model, memory layout, data flow
- [Feature Parity Matrix](esp32-port/feature-parity.md) - What ports, what doesn't, what changes

### TODO
- [Base Station TODO](TODO-base-station.md) - Remaining GUI, reports, daily summary, hardware testing, docs

### Specialist Reviews
- [UI Design Review](reviews/ui-review.md) - Dashboard layouts, handheld screens, color system, discreet alerts
- [UX Design Review](reviews/ux-review.md) - User personas, critical flows, onboarding, alert fatigue, safety
- [DataViz Review](reviews/dataviz-review.md) - Dashboard charts, map strategy, RF spectrum plots, report generation
- [Social Psychology Review](reviews/social-psych-review.md) - Psychological impact, dual-use, alert language, ethical framework

### Spectrum Expansion
- [Spectrum Roadmap](spectrum-expansion/roadmap.md) - Priority-ordered plan for adding BLE, sub-GHz, LoRa, drones, aircraft, RF sweep
- [BLE Tracker Detection](spectrum-expansion/ble-trackers.md) - AirTag/SmartTag/Tile detection design
- [Device Spectrum Reference](spectrum-expansion/device-spectrum-reference.md) - Comprehensive RF frequency reference for all surveillance-relevant devices
