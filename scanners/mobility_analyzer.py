"""Mobility analyzer — stationary vs mobile discrimination."""
import math
from typing import Optional


class MobilityAnalyzer:
    """Analyzes whether detected signals come from stationary or mobile sources."""

    # Earth radius in meters
    _EARTH_RADIUS_M = 6_371_000.0

    def classify_by_protocol(self, model: str, protocol_table: dict) -> bool | None:
        """Returns True=stationary, False=mobile, None=unknown based on protocol type.

        Case-insensitive substring match: if any key in protocol_table appears
        as a substring of model (case-insensitive), return the classification.
        """
        model_lower = model.lower()
        for key, value in protocol_table.items():
            if key.lower() in model_lower:
                if value == "stationary":
                    return True
                elif value == "mobile":
                    return False
        return None

    def classify_by_multi_location(
        self, locations_seen: list, min_distance_m: float = 500.0
    ) -> bool | None:
        """If device seen at distant locations, it's mobile.

        Args:
            locations_seen: List of (lat, lon) tuples where device was observed.
            min_distance_m: Minimum distance between any two observations to
                consider the device mobile.

        Returns True=stationary, False=mobile, None=insufficient data.
        """
        if len(locations_seen) < 2:
            return None

        max_distance = 0.0
        for i in range(len(locations_seen)):
            for j in range(i + 1, len(locations_seen)):
                d = self._haversine(locations_seen[i], locations_seen[j])
                if d > max_distance:
                    max_distance = d

        if max_distance > min_distance_m:
            return False  # mobile
        return True  # stationary

    def classify_by_rssi_pattern(
        self, rssi_history: list, gps_history: list
    ) -> bool | None:
        """Analyze RSSI over time + GPS to determine if signal source is stationary.

        Logic:
        - If RSSI variance is low (< 9.0, i.e. std dev < 3 dB) AND the receiver
          GPS is NOT changing significantly, the source is likely stationary.
        - If RSSI variance is low AND receiver GPS IS changing, the source is
          co-traveling (mobile).
        - Otherwise, stationary (signal varies as we move past it).

        Returns True=stationary, False=mobile, None=insufficient data.
        """
        if len(rssi_history) < 3:
            return None

        # Calculate RSSI variance
        mean_rssi = sum(rssi_history) / len(rssi_history)
        variance = sum((r - mean_rssi) ** 2 for r in rssi_history) / len(rssi_history)

        # Determine if receiver GPS is changing
        receiver_moving = self._is_receiver_moving(gps_history)

        if variance < 9.0:
            # Low RSSI variance
            if receiver_moving:
                # Constant signal while we move = source is co-traveling = mobile
                return False
            else:
                # Constant signal while stationary = stationary source
                return True
        else:
            # High RSSI variance = signal changes as we move = stationary source
            return True

    def _is_receiver_moving(self, gps_history: list, threshold_m: float = 50.0) -> bool:
        """Determine if the receiver has moved significantly during observations."""
        if len(gps_history) < 2:
            return False

        max_distance = 0.0
        for i in range(len(gps_history)):
            for j in range(i + 1, len(gps_history)):
                d = self._haversine(gps_history[i], gps_history[j])
                if d > max_distance:
                    max_distance = d

        return max_distance > threshold_m

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
