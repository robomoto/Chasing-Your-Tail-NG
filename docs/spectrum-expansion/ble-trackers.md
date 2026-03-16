# BLE Tracker Detection Design

## Problem Statement

BLE-based trackers (AirTags, SmartTags, Tile) are the #1 consumer stalking tool today. CYT currently has zero visibility into BLE. Adding BLE scanning is the highest-impact single improvement to CYT's surveillance detection capability.

## How BLE Trackers Work

### Apple AirTag / Find My Network
- Broadcasts BLE advertisements every ~2 seconds
- Advertisement contains manufacturer-specific data: company ID `0x004C`, type byte `0x12`
- MAC address rotates every ~15 minutes (anti-tracking measure by Apple)
- Payload includes a rotating public key derived from the owner's Apple ID
- A 2-byte "hint" field can distinguish between distinct nearby AirTags within a single rotation window
- Any Apple device (iPhone, iPad, Mac) in range relays the AirTag's location to Apple's servers

### Samsung SmartTag / SmartThings Find
- Company ID `0x0075` in advertisement data
- Uses Samsung's SmartThings Find network
- SmartTag2 adds UWB for precise finding
- MAC rotation behavior similar to AirTag

### Tile
- Service UUID `0xFFFE` in advertisement data
- Smaller relay network than Apple/Samsung
- Less aggressive MAC rotation than AirTag

### Chipolo ONE Spot
- Uses Apple Find My network (same company ID 0x004C, type 0x12)
- Indistinguishable from AirTag at the BLE advertisement level

## Detection Strategy

### Challenge: MAC Rotation
Cannot use MAC address as a persistent identifier (unlike WiFi). AirTags rotate MAC every ~15 minutes.

### Approach: Payload Fingerprinting
1. Scan for BLE advertisements matching known tracker manufacturer IDs
2. Extract payload signature (manufacturer data structure, excluding rotating fields)
3. Track "a Find My device is persistently nearby" rather than a specific MAC
4. Use the 2-byte hint field to distinguish between multiple nearby AirTags within a rotation window
5. Feed detection events into CYT's persistence scoring engine

### Persistence Detection
- If Find My advertisements are detected in multiple consecutive CYT time windows (5/10/15/20 min): suspicious
- If Find My advertisements are detected across multiple GPS locations: highly suspicious
- Combine with WiFi persistence data — a device that shows up as both a WiFi MAC and a nearby BLE tracker is a stronger signal

## Implementation: Pi Version

### Library
`bleak` — cross-platform Python BLE library. Works on Linux (BlueZ), macOS, Windows.

### Scanner Design
```python
class BLETrackerScanner:
    APPLE_FIND_MY = (0x004C, 0x12)    # (company_id, type_byte)
    SAMSUNG_SMARTTAG = (0x0075, None)
    TILE_SERVICE_UUID = "0000fffe-0000-1000-8000-00805f9b34fb"

    async def scan_window(self, duration_seconds=10):
        """Run a BLE scan window, return detected trackers"""
        devices = await BleakScanner.discover(timeout=duration_seconds)
        trackers = []
        for device in devices:
            tracker_type = self._identify_tracker(device)
            if tracker_type:
                trackers.append(DeviceAppearance(
                    mac=device.address,  # Rotates, but logged for reference
                    source_type="ble",
                    device_type=tracker_type,
                    timestamp=time.time(),
                    location_id=current_location,
                    signal_strength=device.rssi,
                    payload_hash=self._fingerprint(device)
                ))
        return trackers
```

### Integration with CYT Pipeline
- `DeviceAppearance.mac` still set (for logging) but not used as primary key
- New field `payload_hash` used as device identifier for persistence tracking
- `SurveillanceDetector` modified to accept non-MAC identifiers

## Implementation: ESP32

### API
ESP-IDF BLE GAP scanning. Register callback for `ESP_GAP_BLE_SCAN_RESULT_EVT`.

### Scan Windows
Alternate with WiFi: 45s WiFi promiscuous -> 10s BLE scan -> repeat.
10 seconds captures most nearby tracker advertisements (AirTag beacons at ~2s intervals = ~5 advertisements per window).

### Manufacturer ID Filtering
```c
// In GAP event callback
if (event == ESP_GAP_BLE_SCAN_RESULT_EVT) {
    uint8_t *adv_data = param->scan_rst.ble_adv;
    uint8_t adv_len = param->scan_rst.adv_data_len;

    // Parse advertisement for manufacturer-specific data (type 0xFF)
    // Check company_id against known tracker IDs
    // If match: extract fingerprint, enqueue for persistence analysis
}
```

## Open Questions

- [ ] How to handle the 15-minute MAC rotation window for counting distinct devices? If 3 AirTags are nearby, they look like a stream of rotating MACs all with the same manufacturer ID.
- [ ] Apple's anti-stalking updates — iOS periodically alerts users about unknown AirTags. Does this change the detection value? (Yes for iPhone users; no for Android users or users without smartphones)
- [ ] Google Find My Device network is new and expanding — need to identify their advertisement format once it stabilizes
- [ ] Should CYT alert on ALL nearby trackers or only persistent ones? Recommendation: log all, alert only on persistence.
