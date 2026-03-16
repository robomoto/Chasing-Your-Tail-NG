"""Cross-source correlation engine — links detections across sensor types."""
from typing import Dict, List, Optional, Callable
from scanners.base_scanner import DeviceAppearance, SourceType


class CorrelationRule:
    """A rule for correlating detections across source types."""

    def __init__(self, name: str, source_types: tuple, score_multiplier: float = 1.5,
                 time_window_s: float = 30.0):
        self.name = name
        self.source_types = source_types
        self.score_multiplier = score_multiplier
        self.time_window_s = time_window_s

    def check(self, a: DeviceAppearance, b: DeviceAppearance) -> bool:
        """Return True if a and b match this rule's source types within the time window."""
        if {a.source_type, b.source_type} != set(self.source_types):
            return False
        if abs(a.timestamp - b.timestamp) > self.time_window_s:
            return False
        return True


class FusionEngine:
    """Cross-source detection correlation and scoring."""

    def __init__(self, config: dict):
        self._config = config
        self._rules: List[CorrelationRule] = []
        self._window: List[DeviceAppearance] = []
        self._correlations: List[dict] = []
        self._correlated_groups: Dict[str, List[str]] = {}
        self._device_multipliers: Dict[str, float] = {}
        self._time_window_s: float = config.get("fusion", {}).get(
            "correlation_window_seconds",
            config.get("time_window_s", 30.0),
        )
        # Maps device_id -> group_id for quick lookup
        self._device_to_group: Dict[str, str] = {}
        self._next_group_id: int = 0

    def add_rule(self, rule: CorrelationRule) -> None:
        """Register a correlation rule."""
        self._rules.append(rule)

    def process_appearance(self, appearance: DeviceAppearance) -> List[dict]:
        """Process a new appearance, correlate against the sliding window, return new correlations."""
        # Prune old entries from the window
        cutoff = appearance.timestamp - self._time_window_s
        self._window = [a for a in self._window if a.timestamp >= cutoff]

        new_correlations: List[dict] = []

        # Check against every existing window entry with every rule
        for existing in self._window:
            for rule in self._rules:
                if rule.check(existing, appearance):
                    corr = {
                        "device_id_a": existing.device_id,
                        "device_id_b": appearance.device_id,
                        "rule_name": rule.name,
                    }
                    new_correlations.append(corr)
                    self._correlations.append(corr)

                    # Update multipliers (keep max)
                    for did in (existing.device_id, appearance.device_id):
                        current = self._device_multipliers.get(did, 1.0)
                        self._device_multipliers[did] = max(current, rule.score_multiplier)

                    # Merge groups
                    self._merge_devices(existing.device_id, appearance.device_id)

        # Add appearance to window
        self._window.append(appearance)

        return new_correlations

    def _merge_devices(self, id_a: str, id_b: str) -> None:
        """Ensure both device_ids are in the same correlation group."""
        group_a = self._device_to_group.get(id_a)
        group_b = self._device_to_group.get(id_b)

        if group_a is None and group_b is None:
            # New group
            gid = f"group-{self._next_group_id}"
            self._next_group_id += 1
            self._correlated_groups[gid] = [id_a, id_b]
            self._device_to_group[id_a] = gid
            self._device_to_group[id_b] = gid
        elif group_a is not None and group_b is None:
            # Add b to a's group
            self._correlated_groups[group_a].append(id_b)
            self._device_to_group[id_b] = group_a
        elif group_a is None and group_b is not None:
            # Add a to b's group
            self._correlated_groups[group_b].append(id_a)
            self._device_to_group[id_a] = group_b
        elif group_a != group_b:
            # Merge group_b into group_a
            for did in self._correlated_groups[group_b]:
                self._device_to_group[did] = group_a
            self._correlated_groups[group_a].extend(self._correlated_groups[group_b])
            del self._correlated_groups[group_b]
        # else: already in same group, nothing to do

    def get_correlated_groups(self) -> Dict[str, List[str]]:
        """Return mapping of group_id to list of device_ids."""
        return dict(self._correlated_groups)

    def get_score_multiplier(self, device_id: str) -> float:
        """Return the score multiplier for a device, or 1.0 if not correlated."""
        return self._device_multipliers.get(device_id, 1.0)

    @property
    def correlation_count(self) -> int:
        """Return total number of correlations found."""
        return len(self._correlations)
