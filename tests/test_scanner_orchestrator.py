"""TDD tests for ScannerOrchestrator — Phase 1 base station upgrade.

These tests define the acceptance criteria for the orchestrator.
They should FAIL against the current stub and PASS once implemented.
"""
import threading
import time
import pytest
from queue import Queue
from unittest.mock import MagicMock, patch

from scanners.base_scanner import DeviceAppearance, SourceType, ScannerState
from scanner_orchestrator import ScannerOrchestrator


# ---------------------------------------------------------------------------
# FakeScanner — lightweight stand-in that does NOT call BaseScanner.__init__
# (the real BaseScanner.__init__ is a stub that raises NotImplementedError).
# ---------------------------------------------------------------------------

class FakeScanner:
    """Minimal scanner double that satisfies the orchestrator's interface."""

    def __init__(self, name: str, output_queue: Queue, enabled: bool = True):
        self._name = name
        self._output_queue = output_queue
        self._state = ScannerState.STOPPED
        self._enabled = enabled

    @property
    def scanner_name(self) -> str:
        return self._name

    @property
    def state(self) -> ScannerState:
        return self._state

    def start(self) -> None:
        self._state = ScannerState.RUNNING

    def stop(self) -> None:
        self._state = ScannerState.STOPPED

    def _emit(self, appearance: DeviceAppearance) -> None:
        self._output_queue.put(appearance)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_appearance(device_id: str = "AA:BB:CC:DD:EE:01") -> DeviceAppearance:
    return DeviceAppearance(
        device_id=device_id,
        source_type=SourceType.WIFI,
        timestamp=time.time(),
        location_id="test-loc",
        mac=device_id,
    )


def _make_config(**overrides) -> dict:
    cfg = {"scanners": {}}
    cfg.update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScannerOrchestrator:
    """Orchestrator acceptance tests."""

    def test_register_scanner(self):
        """Scanner appears in _scanners dict keyed by its name."""
        config = _make_config()
        orch = ScannerOrchestrator(config)
        fake = FakeScanner("wifi", orch.queue)
        orch.register_scanner(fake)
        assert "wifi" in orch._scanners
        assert orch._scanners["wifi"] is fake

    def test_get_scanner_states(self):
        """get_scanner_states returns {name: state_string} for all registered."""
        config = _make_config()
        orch = ScannerOrchestrator(config)
        orch.register_scanner(FakeScanner("wifi", orch.queue))
        orch.register_scanner(FakeScanner("ble", orch.queue))
        states = orch.get_scanner_states()
        assert states == {"wifi": "stopped", "ble": "stopped"}

    def test_start_all_starts_enabled_scanners(self):
        """Enabled scanners transition to RUNNING after start_all()."""
        config = _make_config(scanners={"wifi": {"enabled": True}})
        orch = ScannerOrchestrator(config)
        fake = FakeScanner("wifi", orch.queue)
        orch.register_scanner(fake)
        orch.start_all()
        try:
            assert fake.state == ScannerState.RUNNING
        finally:
            orch.stop_all()

    def test_start_all_skips_disabled_scanners(self):
        """Disabled scanner stays STOPPED after start_all()."""
        config = _make_config(scanners={"ble": {"enabled": False}})
        orch = ScannerOrchestrator(config)
        fake = FakeScanner("ble", orch.queue)
        orch.register_scanner(fake)
        orch.start_all()
        try:
            assert fake.state == ScannerState.STOPPED
        finally:
            orch.stop_all()

    def test_stop_all_stops_all_scanners(self):
        """All scanners reach STOPPED after stop_all()."""
        config = _make_config(scanners={"wifi": {"enabled": True}, "ble": {"enabled": True}})
        orch = ScannerOrchestrator(config)
        wifi = FakeScanner("wifi", orch.queue)
        ble = FakeScanner("ble", orch.queue)
        orch.register_scanner(wifi)
        orch.register_scanner(ble)
        orch.start_all()
        orch.stop_all()
        assert wifi.state == ScannerState.STOPPED
        assert ble.state == ScannerState.STOPPED

    def test_consumer_dispatches_to_callback(self):
        """An appearance placed on the queue triggers the on_appearance callback."""
        received = []
        config = _make_config()
        orch = ScannerOrchestrator(config, on_appearance=lambda a: received.append(a))
        orch.start_all()  # starts consumer thread
        try:
            appearance = _make_appearance()
            orch.queue.put(appearance)
            # Give the consumer thread time to pick it up
            deadline = time.time() + 2.0
            while not received and time.time() < deadline:
                time.sleep(0.05)
            assert len(received) == 1
            assert received[0] is appearance
        finally:
            orch.stop_all()

    def test_consumer_handles_callback_exception(self):
        """A callback that raises does not crash the consumer thread."""
        call_count = {"n": 0}

        def bad_then_good(appearance):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("boom")

        config = _make_config()
        orch = ScannerOrchestrator(config, on_appearance=bad_then_good)
        orch.start_all()
        try:
            orch.queue.put(_make_appearance("dev-1"))
            orch.queue.put(_make_appearance("dev-2"))
            deadline = time.time() + 2.0
            while call_count["n"] < 2 and time.time() < deadline:
                time.sleep(0.05)
            # Consumer survived the first exception and processed the second
            assert call_count["n"] == 2
        finally:
            orch.stop_all()

    def test_queue_has_maxsize(self):
        """The internal queue has a reasonable maxsize to prevent unbounded growth."""
        config = _make_config()
        orch = ScannerOrchestrator(config)
        assert orch.queue.maxsize > 0
        assert orch.queue.maxsize <= 100_000  # sane upper bound

    def test_appearances_processed_counter(self):
        """appearances_processed counter increments for each consumed appearance."""
        config = _make_config()
        orch = ScannerOrchestrator(config, on_appearance=lambda a: None)
        orch.start_all()
        try:
            for _ in range(3):
                orch.queue.put(_make_appearance())
            deadline = time.time() + 2.0
            while orch.appearances_processed < 3 and time.time() < deadline:
                time.sleep(0.05)
            assert orch.appearances_processed == 3
        finally:
            orch.stop_all()
