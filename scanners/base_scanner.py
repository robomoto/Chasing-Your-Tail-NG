"""Abstract base class for all CYT scanners. STUB — Phase 1 implementation pending."""
import logging
import threading
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from queue import Queue

logger = logging.getLogger(__name__)


class SourceType(Enum):
    WIFI = "wifi"
    BLE = "ble"
    BT_CLASSIC = "bt_classic"
    SUBGHZ = "subghz"
    LORA = "lora"
    DRONE = "drone"
    AIRCRAFT = "aircraft"
    RF_SWEEP = "rf_sweep"
    HANDHELD_IMPORT = "handheld_import"


class ScannerState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class DeviceAppearance:
    """Universal device appearance record. STUB — fields defined, no logic yet."""
    device_id: str
    source_type: SourceType
    timestamp: float
    location_id: str
    signal_strength: Optional[float] = None
    device_type: Optional[str] = None
    mac: Optional[str] = None
    ssids_probed: List[str] = field(default_factory=list)
    payload_hash: Optional[str] = None
    frequency_mhz: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_stationary: Optional[bool] = None


class BaseScanner(ABC):
    """Abstract base class for all scanner threads. STUB."""

    def __init__(self, config: dict, output_queue: Queue, location_id: str = "unknown"):
        raise NotImplementedError("BaseScanner not yet implemented")

    @property
    @abstractmethod
    def scanner_name(self) -> str: ...

    @abstractmethod
    def _scan_loop(self) -> None: ...

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def resume(self) -> None:
        raise NotImplementedError

    @property
    def state(self) -> ScannerState:
        raise NotImplementedError

    def _emit(self, appearance: DeviceAppearance) -> None:
        raise NotImplementedError
