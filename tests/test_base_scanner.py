"""TDD tests for scanners/base_scanner.py — Phase 1 acceptance criteria.

All tests that exercise BaseScanner lifecycle (tests 7-11) should FAIL
until the stub is replaced with the real implementation from the upgrade plan.
Tests 1-5 exercise already-defined enums/dataclasses and should PASS now.
Test 6 verifies the ABC contract.
"""
import threading
import time
from queue import Queue

import pytest

from scanners.base_scanner import (
    BaseScanner,
    DeviceAppearance,
    ScannerState,
    SourceType,
)


# ---------------------------------------------------------------------------
# Helper: concrete subclass for testing the abstract base class
# ---------------------------------------------------------------------------

class DummyScanner(BaseScanner):
    """Minimal concrete scanner for testing BaseScanner behaviour."""

    def __init__(self, config, output_queue, location_id="test",
                 scan_fn=None):
        super().__init__(config, output_queue, location_id)
        self._scan_fn = scan_fn

    @property
    def scanner_name(self) -> str:
        return "dummy"

    def _scan_loop(self) -> None:
        if self._scan_fn is not None:
            self._scan_fn(self)
            return
        # Default: loop until told to stop, yielding to pause
        while not self._stop_event.is_set():
            self._pause_event.wait()
            self._stop_event.wait(timeout=0.05)


# ---------------------------------------------------------------------------
# 1. SourceType enum completeness (should PASS — enum already defined)
# ---------------------------------------------------------------------------

def test_source_type_enum_has_all_types():
    expected = {
        "WIFI", "BLE", "BT_CLASSIC", "SUBGHZ", "LORA",
        "DRONE", "AIRCRAFT", "RF_SWEEP", "HANDHELD_IMPORT",
    }
    actual = {member.name for member in SourceType}
    assert actual == expected


# ---------------------------------------------------------------------------
# 2. ScannerState enum values (should PASS — enum already defined)
# ---------------------------------------------------------------------------

def test_scanner_state_enum_values():
    expected = {"STOPPED", "STARTING", "RUNNING", "PAUSED", "ERROR"}
    actual = {member.name for member in ScannerState}
    assert actual == expected


# ---------------------------------------------------------------------------
# 3. DeviceAppearance creation with WiFi fields (should PASS — dataclass exists)
# ---------------------------------------------------------------------------

def test_device_appearance_creation_wifi():
    now = time.time()
    da = DeviceAppearance(
        device_id="AA:BB:CC:DD:EE:FF",
        source_type=SourceType.WIFI,
        timestamp=now,
        location_id="home",
        mac="AA:BB:CC:DD:EE:FF",
        ssids_probed=["MyNetwork"],
        signal_strength=-42.0,
    )
    assert da.device_id == "AA:BB:CC:DD:EE:FF"
    assert da.source_type == SourceType.WIFI
    assert da.mac == "AA:BB:CC:DD:EE:FF"
    assert da.ssids_probed == ["MyNetwork"]
    assert da.signal_strength == -42.0
    assert da.location_id == "home"


# ---------------------------------------------------------------------------
# 4. device_id is the primary identifier
# ---------------------------------------------------------------------------

def test_device_appearance_device_id_is_primary():
    da = DeviceAppearance(
        device_id="drone-0x1234",
        source_type=SourceType.DRONE,
        timestamp=time.time(),
        location_id="field",
    )
    # device_id should be set even when mac is absent
    assert da.device_id == "drone-0x1234"
    assert da.mac is None


# ---------------------------------------------------------------------------
# 5. BLE appearance with mac=None is valid (should PASS — dataclass allows it)
# ---------------------------------------------------------------------------

def test_device_appearance_ble_no_mac():
    da = DeviceAppearance(
        device_id="ble-randomised-xyz",
        source_type=SourceType.BLE,
        timestamp=time.time(),
        location_id="office",
        mac=None,
        payload_hash="abc123",
    )
    assert da.mac is None
    assert da.payload_hash == "abc123"
    assert da.source_type == SourceType.BLE


# ---------------------------------------------------------------------------
# 6. BaseScanner cannot be instantiated directly (ABC contract)
# ---------------------------------------------------------------------------

def test_base_scanner_is_abstract():
    with pytest.raises((TypeError, NotImplementedError)):
        BaseScanner(config={}, output_queue=Queue(), location_id="x")


# ---------------------------------------------------------------------------
# 7. Full lifecycle: start -> RUNNING, pause -> PAUSED, resume -> RUNNING,
#    stop -> STOPPED.  (FAILS until stub is implemented)
# ---------------------------------------------------------------------------

def test_concrete_scanner_lifecycle():
    q = Queue()
    scanner = DummyScanner(config={}, output_queue=q)

    assert scanner.state == ScannerState.STOPPED

    scanner.start()
    # Give the thread a moment to transition through STARTING -> RUNNING
    time.sleep(0.15)
    assert scanner.state == ScannerState.RUNNING

    scanner.pause()
    assert scanner.state == ScannerState.PAUSED

    scanner.resume()
    assert scanner.state == ScannerState.RUNNING

    scanner.stop()
    assert scanner.state == ScannerState.STOPPED


# ---------------------------------------------------------------------------
# 8. _emit() puts DeviceAppearance on the output queue
# ---------------------------------------------------------------------------

def test_scanner_emit_puts_on_queue():
    q = Queue()
    scanner = DummyScanner(config={}, output_queue=q)

    da = DeviceAppearance(
        device_id="AA:BB:CC:DD:EE:01",
        source_type=SourceType.WIFI,
        timestamp=time.time(),
        location_id="test",
    )
    scanner._emit(da)

    assert not q.empty()
    result = q.get_nowait()
    assert result.device_id == "AA:BB:CC:DD:EE:01"
    assert result.source_type == SourceType.WIFI


# ---------------------------------------------------------------------------
# 9. _scan_loop exits when stop_event is set
# ---------------------------------------------------------------------------

def test_scanner_stop_event_checked():
    q = Queue()
    iterations = []

    def counting_loop(self):
        while not self._stop_event.is_set():
            iterations.append(1)
            self._stop_event.wait(timeout=0.05)

    scanner = DummyScanner(config={}, output_queue=q, scan_fn=counting_loop)
    scanner.start()
    time.sleep(0.2)
    scanner.stop()
    time.sleep(0.1)

    # The loop should have run some iterations, then exited
    assert len(iterations) > 0
    assert scanner.state == ScannerState.STOPPED


# ---------------------------------------------------------------------------
# 10. If _scan_loop raises, state becomes ERROR
# ---------------------------------------------------------------------------

def test_scanner_crash_sets_error_state():
    q = Queue()

    def crashing_loop(self):
        raise RuntimeError("simulated scanner crash")

    scanner = DummyScanner(config={}, output_queue=q, scan_fn=crashing_loop)
    scanner.start()
    time.sleep(0.2)

    assert scanner.state == ScannerState.ERROR


# ---------------------------------------------------------------------------
# 11. Calling start() twice doesn't create two threads
# ---------------------------------------------------------------------------

def test_scanner_double_start_is_noop():
    q = Queue()
    scanner = DummyScanner(config={}, output_queue=q)

    scanner.start()
    time.sleep(0.15)
    assert scanner.state == ScannerState.RUNNING

    first_thread = scanner._thread
    scanner.start()  # second call — should be a no-op
    time.sleep(0.1)

    assert scanner._thread is first_thread
    assert scanner.state == ScannerState.RUNNING

    scanner.stop()
