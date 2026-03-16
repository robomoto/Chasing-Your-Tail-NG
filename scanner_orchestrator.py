"""Scanner orchestrator — manages scanner threads and consumption queue. STUB."""
from queue import Queue
from typing import Callable, Dict, Optional
from scanners.base_scanner import BaseScanner, DeviceAppearance, ScannerState


class ScannerOrchestrator:
    """Manages all scanner threads and consumes their output. STUB."""

    def __init__(self, config: dict, on_appearance: Optional[Callable] = None):
        raise NotImplementedError("ScannerOrchestrator not yet implemented")

    def register_scanner(self, scanner: BaseScanner) -> None:
        raise NotImplementedError

    def get_scanner_states(self) -> Dict[str, str]:
        raise NotImplementedError

    def start_all(self) -> None:
        raise NotImplementedError

    def stop_all(self) -> None:
        raise NotImplementedError

    @property
    def appearances_processed(self) -> int:
        raise NotImplementedError
