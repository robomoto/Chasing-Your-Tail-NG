"""LoRa/Meshtastic scanner via serial connection to LoRa board."""
import math
import time
from typing import Optional

from scanners.base_scanner import BaseScanner, DeviceAppearance, SourceType


class LoRaScanner(BaseScanner):
    """Monitors LoRa/Meshtastic traffic via a serial-connected LoRa board."""

    _EARTH_RADIUS_M = 6_371_000.0

    def __init__(self, config: dict, output_queue, location_id: str = "unknown"):
        super().__init__(config=config, output_queue=output_queue, location_id=location_id)
        lora_cfg = config.get("scanners", {}).get("lora", {})
        self.serial_port: Optional[str] = lora_cfg.get("serial_port", None)
        self.poll_interval: float = lora_cfg.get("poll_interval", 5)
        self._node_positions: dict[str, list[tuple[float, float]]] = {}
        self._node_roles: dict[str, str] = {}

    @property
    def scanner_name(self) -> str:
        return "lora"

    @property
    def source_type(self) -> SourceType:
        return SourceType.LORA

    def _parse_meshtastic_packet(self, packet: dict) -> dict | None:
        """Parse a Meshtastic packet dict into a normalized dict, or None if invalid."""
        if "from" not in packet:
            return None
        decoded = packet.get("decoded")
        if not decoded or not isinstance(decoded, dict):
            return None
        portnum = decoded.get("portnum")
        if not portnum:
            return None

        node_id = f"!{packet['from']:08x}"
        rssi = packet.get("rxRssi")
        snr = packet.get("rxSnr")

        result: dict = {
            "node_id": node_id,
            "portnum": portnum,
            "rssi": rssi,
            "snr": snr,
        }

        if portnum == "POSITION_APP":
            position = decoded.get("position", {})
            result["lat"] = position.get("latitude")
            result["lon"] = position.get("longitude")
        elif portnum == "NODEINFO_APP":
            user = decoded.get("user", {})
            result["long_name"] = user.get("longName")
            result["short_name"] = user.get("shortName")
            result["role"] = user.get("role")

        return result

    def _classify_node_mobility(
        self, node_id: str, role: str | None, positions: list | None
    ) -> bool | None:
        """Classify node mobility. True=stationary, False=mobile, None=unknown."""
        if role in ("ROUTER", "REPEATER"):
            return True
        if role == "TRACKER":
            return False

        # CLIENT or unknown role: use positions if available
        if positions and len(positions) >= 2:
            max_dist = 0.0
            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    d = self._haversine(positions[i], positions[j])
                    if d > max_dist:
                        max_dist = d
            if max_dist > 100.0:
                return False  # mobile
            return True  # stationary

        return None

    @staticmethod
    def _haversine(coord1: tuple, coord2: tuple) -> float:
        """Calculate distance in meters between two (lat, lon) coordinates."""
        lat1, lon1 = coord1
        lat2, lon2 = coord2
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return 6_371_000.0 * c

    def _read_packets(self) -> list:
        """Read packets from the Meshtastic serial interface.

        Returns a list of raw packet dicts. In production this would
        communicate with a serial-connected LoRa board; tests mock this.
        """
        return []

    def _scan_loop(self) -> None:
        """Main scan loop: read packets, parse, classify, and emit appearances."""
        while not self._stop_event.is_set():
            packets = self._read_packets()
            for packet in packets:
                parsed = self._parse_meshtastic_packet(packet)
                if parsed is None:
                    continue

                node_id = parsed["node_id"]
                portnum = parsed.get("portnum")

                # Update node positions
                if portnum == "POSITION_APP" and parsed.get("lat") is not None:
                    if node_id not in self._node_positions:
                        self._node_positions[node_id] = []
                    self._node_positions[node_id].append(
                        (parsed["lat"], parsed["lon"])
                    )

                # Update node roles
                if portnum == "NODEINFO_APP" and parsed.get("role"):
                    self._node_roles[node_id] = parsed["role"]

                # Classify mobility
                role = self._node_roles.get(node_id)
                positions = self._node_positions.get(node_id)
                is_stationary = self._classify_node_mobility(
                    node_id, role, positions
                )

                # Build metadata from parsed fields
                metadata = {
                    k: v for k, v in parsed.items()
                    if k not in ("node_id",) and v is not None
                }

                appearance = DeviceAppearance(
                    device_id=f"lora:{node_id}",
                    source_type=SourceType.LORA,
                    timestamp=time.time(),
                    location_id=self.location_id,
                    signal_strength=parsed.get("rssi"),
                    metadata=metadata,
                    is_stationary=is_stationary,
                )
                self._emit(appearance)

            self._stop_event.wait(timeout=self.poll_interval)
