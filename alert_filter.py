"""Alert filter — false positive suppression.

Checks score threshold, familiar device store, and optional corroboration
before allowing an alert to surface to the user.
"""
from typing import Tuple, List, Optional, Dict
import json
from pathlib import Path


class FamiliarDeviceStore:
    """Persists a set of familiar (trusted) device IDs to a JSON file."""

    def __init__(self, path: str = "familiar_devices.json"):
        self._path = Path(path)
        self._devices: Dict[str, dict] = {}
        self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                if isinstance(data, dict):
                    self._devices = data
            except (json.JSONDecodeError, OSError):
                self._devices = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._devices, indent=2))

    # -- public API ----------------------------------------------------------

    def is_familiar(self, device_id: str, current_location: str = None) -> bool:
        """Return True if *device_id* is marked familiar for *current_location*.

        A device with location_context ``"all"`` matches any location.
        If *current_location* is ``None`` the check ignores location context.
        """
        entry = self._devices.get(device_id)
        if entry is None:
            return False
        loc = entry.get("location_context", "all")
        if loc == "all" or current_location is None:
            return True
        return loc == current_location

    def add(self, device_id: str, location_context: str = "all", label: str = "") -> None:
        self._devices[device_id] = {
            "location_context": location_context,
            "label": label,
        }
        self._save()

    def remove(self, device_id: str) -> None:
        self._devices.pop(device_id, None)
        self._save()

    def get_all(self) -> Dict[str, dict]:
        return dict(self._devices)


class AlertFilter:
    """Decides whether a suspicious-device alert should be surfaced to the user."""

    def __init__(self, config: dict, fusion_engine=None, session_db=None):
        af_cfg = config.get("alert_filter", {})
        self._min_score: float = af_cfg.get("min_score", 0.7)
        self._require_corroboration: bool = af_cfg.get("require_corroboration", False)
        familiar_path: str = af_cfg.get("familiar_devices_path", "familiar_devices.json")

        self._familiar = FamiliarDeviceStore(path=familiar_path)
        self._fusion = fusion_engine
        self._session_db = session_db

    # -- filtering -----------------------------------------------------------

    def should_surface(self, device, current_location: str = None) -> Tuple[bool, str]:
        """Return ``(should_surface, reason)`` for the given device.

        *device* must expose ``.persistence_score`` and ``.mac`` (or
        ``.device_id``).
        """
        device_id = getattr(device, "device_id", None) or device.mac
        score = device.persistence_score

        # 1. Score threshold
        if score < self._min_score:
            return False, "below threshold"

        # 2. Familiar device check
        if self._familiar.is_familiar(device_id, current_location=current_location):
            return False, "familiar device"

        # 3. Corroboration (optional)
        if self._require_corroboration and self._fusion is not None:
            groups = self._fusion.get_correlated_groups()
            device_in_group = any(
                device_id in members for members in groups.values()
            )
            if not device_in_group:
                return False, "corroboration required"

        return True, ""

    # -- familiar device helpers ---------------------------------------------

    def mark_familiar(self, device_id: str, location_context: str = "all") -> None:
        self._familiar.add(device_id, location_context=location_context)

    def unmark_familiar(self, device_id: str) -> None:
        self._familiar.remove(device_id)

    def get_familiar_devices(self) -> List[dict]:
        """Return a list of dicts with ``device_id``, ``location_context``, ``label``."""
        result = []
        for did, info in self._familiar.get_all().items():
            result.append({
                "device_id": did,
                "location_context": info.get("location_context", "all"),
                "label": info.get("label", ""),
            })
        return result
