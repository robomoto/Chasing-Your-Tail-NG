"""TDD tests for BLETrackerClassifier — pure logic for identifying BLE tracker types."""
import pytest

from scanners.ble_scanner import BLETrackerClassifier


@pytest.fixture
def classifier():
    return BLETrackerClassifier()


# ---------------------------------------------------------------------------
# Realistic payloads
# ---------------------------------------------------------------------------

def _airtag_payload(length: int = 27) -> bytes:
    """Apple Find My advertisement: type 0x12, length byte, then rotating public key.

    Real AirTag advertisements are >=25 bytes total (type + length + 23-byte key).
    """
    # type=0x12, length=len-2, then pseudo-random key bytes
    body_len = length - 2
    return bytes([0x12, body_len]) + bytes(range(body_len))


def _airpods_payload() -> bytes:
    """Apple nearby / AirPods advertisement: type 0x07, length, then payload."""
    return bytes([0x07, 0x10]) + b"\xaa\xbb\xcc\xdd" * 4


def _smarttag_payload(length: int = 8) -> bytes:
    """Samsung SmartTag advertisement: at least 4 bytes of manufacturer data."""
    return bytes(range(length))


TILE_UUID = "0000feed-0000-1000-8000-00805f9b34fb"


# ---------------------------------------------------------------------------
# 1. AirTag detection
# ---------------------------------------------------------------------------

def test_airtag_detection(classifier):
    """Apple manufacturer data with type byte 0x12 and >=25 bytes -> 'findmy'."""
    mfr = {0x004C: _airtag_payload(27)}
    result = classifier.classify(manufacturer_data=mfr, service_data={})

    assert result is not None
    assert result["tracker_type"] == "findmy"
    assert "payload_hash" in result and isinstance(result["payload_hash"], str)


# ---------------------------------------------------------------------------
# 2. AirPods / Find My accessory detection
# ---------------------------------------------------------------------------

def test_airpods_detection(classifier):
    """Apple manufacturer data with type byte 0x07 -> 'findmy_nearby'."""
    mfr = {0x004C: _airpods_payload()}
    result = classifier.classify(manufacturer_data=mfr, service_data={})

    assert result is not None
    assert result["tracker_type"] == "findmy_nearby"
    assert "payload_hash" in result


# ---------------------------------------------------------------------------
# 3. Samsung SmartTag detection
# ---------------------------------------------------------------------------

def test_smarttag_detection(classifier):
    """Samsung manufacturer data (0x0075) with >=4 bytes -> 'smarttag'."""
    mfr = {0x0075: _smarttag_payload(8)}
    result = classifier.classify(manufacturer_data=mfr, service_data={})

    assert result is not None
    assert result["tracker_type"] == "smarttag"
    assert "payload_hash" in result


# ---------------------------------------------------------------------------
# 4. Tile detection
# ---------------------------------------------------------------------------

def test_tile_detection(classifier):
    """Service data with UUID containing 'feed' -> 'tile'."""
    svc = {TILE_UUID: b"\x01\x02\x03\x04\x05\x06"}
    result = classifier.classify(manufacturer_data={}, service_data=svc)

    assert result is not None
    assert result["tracker_type"] == "tile"
    assert "payload_hash" in result


# ---------------------------------------------------------------------------
# 5. Google Find My detection
# ---------------------------------------------------------------------------

def test_google_findmy_detection(classifier):
    """Google manufacturer data (0x00E0) -> 'google_findmy'."""
    mfr = {0x00E0: b"\x01\x02\x03\x04\x05\x06\x07\x08"}
    result = classifier.classify(manufacturer_data=mfr, service_data={})

    assert result is not None
    assert result["tracker_type"] == "google_findmy"
    assert "payload_hash" in result


# ---------------------------------------------------------------------------
# 6. Unknown device returns None
# ---------------------------------------------------------------------------

def test_unknown_device_returns_none(classifier):
    """Unrecognized manufacturer ID should return None."""
    mfr = {0xBEEF: b"\xff\xfe\xfd\xfc\xfb\xfa"}
    result = classifier.classify(manufacturer_data=mfr, service_data={})

    assert result is None


# ---------------------------------------------------------------------------
# 7. Empty inputs returns None
# ---------------------------------------------------------------------------

def test_empty_inputs_returns_none(classifier):
    """Empty dicts for both inputs should return None."""
    result = classifier.classify(manufacturer_data={}, service_data={})

    assert result is None


# ---------------------------------------------------------------------------
# 8. Apple short payload ignored
# ---------------------------------------------------------------------------

def test_apple_short_payload_ignored(classifier):
    """Apple 0x12 type byte but only 10 bytes total -> None (too short for Find My)."""
    mfr = {0x004C: _airtag_payload(10)}
    result = classifier.classify(manufacturer_data=mfr, service_data={})

    assert result is None


# ---------------------------------------------------------------------------
# 9. Payload hash is deterministic
# ---------------------------------------------------------------------------

def test_payload_hash_deterministic(classifier):
    """Same input bytes must always produce the same payload_hash."""
    mfr = {0x004C: _airtag_payload(27)}

    result_a = classifier.classify(manufacturer_data=mfr, service_data={})
    result_b = classifier.classify(manufacturer_data=mfr, service_data={})

    assert result_a is not None and result_b is not None
    assert result_a["payload_hash"] == result_b["payload_hash"]


# ---------------------------------------------------------------------------
# 10. Different payloads produce different hashes
# ---------------------------------------------------------------------------

def test_different_payloads_different_hashes(classifier):
    """Two distinct AirTag payloads must produce different payload_hash values."""
    payload_a = bytes([0x12, 0x19]) + bytes(range(25))
    payload_b = bytes([0x12, 0x19]) + bytes(range(25, 50))

    result_a = classifier.classify(manufacturer_data={0x004C: payload_a}, service_data={})
    result_b = classifier.classify(manufacturer_data={0x004C: payload_b}, service_data={})

    assert result_a is not None and result_b is not None
    assert result_a["payload_hash"] != result_b["payload_hash"]
