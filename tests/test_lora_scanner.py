"""TDD tests for scanners/lora_scanner.py — LoRa/Meshtastic scanning via
serial-connected LoRa board.

All tests should FAIL until the LoRaScanner stub is replaced with the real
implementation.
"""
import time
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from scanners.base_scanner import DeviceAppearance, SourceType
from scanners.lora_scanner import LoRaScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lora_scanner(config: dict | None = None, location_id: str = "test-loc"):
    """Create a LoRaScanner with a fresh output queue."""
    if config is None:
        config = {}
    q = Queue()
    scanner = LoRaScanner(config=config, output_queue=q, location_id=location_id)
    return scanner, q


def _drain_queue(q: Queue) -> list[DeviceAppearance]:
    """Pull all items from a queue into a list."""
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def _make_position_packet(from_id: int = 0xA1B2C3D4,
                          to_id: int = 0xFFFFFFFF,
                          lat: float = 33.45,
                          lon: float = -112.07,
                          rssi: int = -65,
                          snr: float = 10.5) -> dict:
    """Build a fake Meshtastic position packet."""
    return {
        "from": from_id,
        "to": to_id,
        "decoded": {
            "portnum": "POSITION_APP",
            "position": {
                "latitude": lat,
                "longitude": lon,
            },
        },
        "rxRssi": rssi,
        "rxSnr": snr,
    }


def _make_nodeinfo_packet(from_id: int = 0xA1B2C3D4,
                          long_name: str = "Node Alpha",
                          short_name: str = "NA",
                          role: str = "CLIENT") -> dict:
    """Build a fake Meshtastic NodeInfo packet."""
    return {
        "from": from_id,
        "to": 0xFFFFFFFF,
        "decoded": {
            "portnum": "NODEINFO_APP",
            "user": {
                "longName": long_name,
                "shortName": short_name,
                "role": role,
            },
        },
        "rxRssi": -70,
        "rxSnr": 8.0,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def lora_scanner():
    """Default LoRaScanner with empty config."""
    scanner, _ = _make_lora_scanner()
    return scanner


# ---------------------------------------------------------------------------
# 1. scanner_name == "lora"
# ---------------------------------------------------------------------------

def test_lora_scanner_name(lora_scanner):
    assert lora_scanner.scanner_name == "lora"


# ---------------------------------------------------------------------------
# 2. source_type == SourceType.LORA
# ---------------------------------------------------------------------------

def test_lora_scanner_source_type(lora_scanner):
    assert lora_scanner.source_type == SourceType.LORA


# ---------------------------------------------------------------------------
# 3. _parse_meshtastic_packet — position packet
# ---------------------------------------------------------------------------

def test_parse_meshtastic_packet_position(lora_scanner):
    packet = _make_position_packet(
        from_id=0xA1B2C3D4,
        lat=33.45,
        lon=-112.07,
        rssi=-65,
        snr=10.5,
    )

    result = lora_scanner._parse_meshtastic_packet(packet)

    assert result is not None
    assert result["node_id"] == "!a1b2c3d4"
    assert result["lat"] == 33.45
    assert result["lon"] == -112.07
    assert result["rssi"] == -65


# ---------------------------------------------------------------------------
# 4. _parse_meshtastic_packet — NodeInfo packet
# ---------------------------------------------------------------------------

def test_parse_meshtastic_packet_nodeinfo(lora_scanner):
    packet = _make_nodeinfo_packet(
        from_id=0xDEADBEEF,
        long_name="Base Station",
        short_name="BS",
        role="ROUTER",
    )

    result = lora_scanner._parse_meshtastic_packet(packet)

    assert result is not None
    assert result["node_id"] == "!deadbeef"
    assert result["long_name"] == "Base Station"
    assert result["short_name"] == "BS"
    assert result["role"] == "ROUTER"


# ---------------------------------------------------------------------------
# 5. _parse_meshtastic_packet — empty/invalid packet returns None
# ---------------------------------------------------------------------------

def test_parse_meshtastic_packet_empty(lora_scanner):
    assert lora_scanner._parse_meshtastic_packet({}) is None
    assert lora_scanner._parse_meshtastic_packet({"from": 123}) is None
    assert lora_scanner._parse_meshtastic_packet(
        {"from": 123, "decoded": {}}
    ) is None


# ---------------------------------------------------------------------------
# 6. _classify_node_mobility — ROUTER role is stationary
# ---------------------------------------------------------------------------

def test_classify_node_mobility_router(lora_scanner):
    result = lora_scanner._classify_node_mobility(
        node_id="!a1b2c3d4", role="ROUTER", positions=None
    )
    assert result is True  # stationary


# ---------------------------------------------------------------------------
# 7. _classify_node_mobility — REPEATER role is stationary
# ---------------------------------------------------------------------------

def test_classify_node_mobility_repeater(lora_scanner):
    result = lora_scanner._classify_node_mobility(
        node_id="!a1b2c3d4", role="REPEATER", positions=None
    )
    assert result is True  # stationary


# ---------------------------------------------------------------------------
# 8. _classify_node_mobility — CLIENT role is unknown (needs more data)
# ---------------------------------------------------------------------------

def test_classify_node_mobility_client(lora_scanner):
    result = lora_scanner._classify_node_mobility(
        node_id="!a1b2c3d4", role="CLIENT", positions=None
    )
    assert result is None  # unknown


# ---------------------------------------------------------------------------
# 9. _classify_node_mobility — TRACKER role is mobile
# ---------------------------------------------------------------------------

def test_classify_node_mobility_tracker(lora_scanner):
    result = lora_scanner._classify_node_mobility(
        node_id="!a1b2c3d4", role="TRACKER", positions=None
    )
    assert result is False  # mobile


# ---------------------------------------------------------------------------
# 10. _classify_node_mobility — positions that don't change => stationary
# ---------------------------------------------------------------------------

def test_classify_node_mobility_by_position(lora_scanner):
    # All positions within a few meters of each other
    positions = [
        (33.4500, -112.0700),
        (33.4500, -112.0700),
        (33.4500, -112.0701),  # ~1m offset
    ]
    result = lora_scanner._classify_node_mobility(
        node_id="!a1b2c3d4", role="CLIENT", positions=positions
    )
    assert result is True  # stationary


# ---------------------------------------------------------------------------
# 11. _classify_node_mobility — positions that change >100m => mobile
# ---------------------------------------------------------------------------

def test_classify_node_mobility_by_position_moving(lora_scanner):
    # Positions spread far apart (>100m)
    positions = [
        (33.4500, -112.0700),
        (33.4510, -112.0700),  # ~111m north
        (33.4520, -112.0700),  # ~222m north of start
    ]
    result = lora_scanner._classify_node_mobility(
        node_id="!a1b2c3d4", role="CLIENT", positions=positions
    )
    assert result is False  # mobile


# ---------------------------------------------------------------------------
# 12. _scan_loop emits DeviceAppearance for received packets
# ---------------------------------------------------------------------------

def test_scan_loop_emits_appearances():
    config = {
        "scanners": {
            "lora": {
                "serial_port": "/dev/ttyUSB0",
            }
        }
    }
    scanner, q = _make_lora_scanner(config=config, location_id="field-1")

    # Two packets: a position packet and a nodeinfo for a ROUTER
    position_packet = _make_position_packet(
        from_id=0xA1B2C3D4,
        lat=33.45,
        lon=-112.07,
        rssi=-65,
    )
    nodeinfo_packet = _make_nodeinfo_packet(
        from_id=0xBEEFCAFE,
        long_name="Relay Node",
        short_name="RN",
        role="ROUTER",
    )

    # Mock the internal packet reading to yield our packets then stop
    def fake_read_packets():
        return [position_packet, nodeinfo_packet]

    with patch.object(scanner, "_read_packets", side_effect=fake_read_packets), \
         patch.object(scanner._stop_event, "is_set", side_effect=[False, True]), \
         patch.object(scanner._stop_event, "wait", return_value=True):
        scanner._scan_loop()

    appearances = _drain_queue(q)

    assert len(appearances) >= 2

    # Check the position-based appearance
    pos_apps = [a for a in appearances if a.device_id == "lora:!a1b2c3d4"]
    assert len(pos_apps) == 1
    da = pos_apps[0]
    assert da.source_type == SourceType.LORA
    assert da.location_id == "field-1"
    assert da.signal_strength == -65
    assert da.metadata["lat"] == 33.45
    assert da.metadata["lon"] == -112.07

    # Check the ROUTER nodeinfo appearance — should be stationary
    router_apps = [a for a in appearances if a.device_id == "lora:!beefcafe"]
    assert len(router_apps) == 1
    da_router = router_apps[0]
    assert da_router.source_type == SourceType.LORA
    assert da_router.is_stationary is True
