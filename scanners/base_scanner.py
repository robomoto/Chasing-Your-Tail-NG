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
    """Abstract base class for all scanner threads."""

    def __init__(self, config: dict, output_queue: Queue, location_id: str = "unknown"):
        self.config = config
        self._output_queue = output_queue
        self.location_id = location_id
        self._state = ScannerState.STOPPED
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused by default
        self._logger = logging.getLogger(f"{__name__}.{type(self).__name__}")

    @property
    @abstractmethod
    def scanner_name(self) -> str: ...

    @abstractmethod
    def _scan_loop(self) -> None: ...

    def start(self) -> None:
        if self._state != ScannerState.STOPPED:
            return
        self._state = ScannerState.STARTING
        self._stop_event.clear()
        self._pause_event.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()  # unblock if paused
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._state = ScannerState.STOPPED

    def pause(self) -> None:
        self._pause_event.clear()
        self._state = ScannerState.PAUSED

    def resume(self) -> None:
        self._pause_event.set()
        self._state = ScannerState.RUNNING

    def _run(self) -> None:
        try:
            self._state = ScannerState.RUNNING
            self._scan_loop()
        except Exception:
            self._logger.exception("Scanner %s crashed", self.scanner_name)
            self._state = ScannerState.ERROR
            return
        self._state = ScannerState.STOPPED

    @property
    def state(self) -> ScannerState:
        return self._state

    def _emit(self, appearance: DeviceAppearance) -> None:
        self._output_queue.put(appearance)
