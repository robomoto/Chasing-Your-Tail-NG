"""Scanner orchestrator — manages scanner threads and consumption queue."""
import logging
import threading
from queue import Queue, Empty
from typing import Callable, Dict, Optional

from scanners.base_scanner import BaseScanner, DeviceAppearance, ScannerState

logger = logging.getLogger(__name__)


class ScannerOrchestrator:
    """Manages all scanner threads and consumes their output."""

    def __init__(self, config: dict, on_appearance: Optional[Callable] = None):
        self.config = config
        self.queue: Queue = Queue(maxsize=10_000)
        self.on_appearance = on_appearance
        self._scanners: Dict[str, BaseScanner] = {}
        self._consumer_thread: Optional[threading.Thread] = None
        self._running = False
        self._appearances_processed = 0

    def register_scanner(self, scanner: BaseScanner) -> None:
        """Add a scanner, keyed by its scanner_name."""
        self._scanners[scanner.scanner_name] = scanner

    def get_scanner_states(self) -> Dict[str, str]:
        """Return {name: state_string} for all registered scanners."""
        return {name: scanner.state.value for name, scanner in self._scanners.items()}

    def start_all(self) -> None:
        """Start the consumer thread, then start each enabled scanner."""
        self._running = True
        self._consumer_thread = threading.Thread(
            target=self._consumer_loop, daemon=True
        )
        self._consumer_thread.start()

        scanners_cfg = self.config.get("scanners", {})
        for name, scanner in self._scanners.items():
            scanner_cfg = scanners_cfg.get(name, {})
            if scanner_cfg.get("enabled", False):
                scanner.start()

    def stop_all(self) -> None:
        """Stop all scanners and the consumer thread."""
        for scanner in self._scanners.values():
            scanner.stop()
        self._running = False
        if self._consumer_thread is not None:
            self._consumer_thread.join(timeout=2.0)
            self._consumer_thread = None

    def _consumer_loop(self) -> None:
        """Daemon thread: read from queue, dispatch to callback, increment counter."""
        while self._running:
            try:
                appearance = self.queue.get(timeout=0.1)
            except Empty:
                continue
            try:
                if self.on_appearance is not None:
                    self.on_appearance(appearance)
            except Exception:
                logger.exception("on_appearance callback raised an exception")
            self._appearances_processed += 1

    @property
    def appearances_processed(self) -> int:
        """Return the number of appearances consumed so far."""
        return self._appearances_processed
