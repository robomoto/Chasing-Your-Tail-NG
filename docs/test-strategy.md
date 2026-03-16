# CYT-NG Test Strategy

TDD approach: tests before code, always.

## Framework

- **pytest** + pytest-cov, pytest-mock, pytest-asyncio, pytest-timeout
- Python 3.9 minimum, 3.11 preferred
- All tests run without hardware (mock Kismet DB, mock BLE, mock APIs)

## Directory Structure

```
tests/
    __init__.py
    conftest.py                    # Shared fixtures (mock_kismet_db, sample_config, etc.)
    fixtures/
        __init__.py
        kismet_fixtures.py         # Mock Kismet DB builder
        sample_data.py             # DeviceAppearance factories
        log_fixtures.py            # Sample CYT log file content
    # Existing code safety net
    test_input_validation.py       # ~45 cases
    test_secure_database.py        # ~30 cases
    test_surveillance_detector.py  # ~35 cases
    test_secure_main_logic.py      # ~25 cases
    test_secure_ignore_loader.py   # ~20 cases
    test_gps_tracker.py            # ~25 cases
    test_probe_analyzer.py         # ~12 cases
    test_secure_credentials.py     # ~15 cases
    # Phase 1 TDD (written before Phase 1 code)
    test_base_scanner.py           # 11 cases
    test_wifi_scanner.py           # 9 cases
    test_scanner_orchestrator.py   # 9 cases
    test_session_db.py             # 8 cases
    test_device_appearance_compat.py # 6 cases
    # Phase 2 TDD (written before Phase 2 code)
    test_ble_classifier.py         # 10 cases
    test_ble_scanner.py            # 11 cases
```

**Total: ~250 test cases**

## Implementation Order

1. Set up test framework (conftest.py, fixtures, pyproject.toml)
2. Write existing-code tests (safety net) — priority order:
   - `test_input_validation.py` (pure functions, easiest start)
   - `test_secure_database.py` (data layer)
   - `test_surveillance_detector.py` (core engine, refactored in Phase 1)
   - `test_secure_main_logic.py` (runtime loop)
   - `test_secure_ignore_loader.py`
   - `test_gps_tracker.py`
   - `test_probe_analyzer.py`
   - `test_secure_credentials.py`
3. All existing tests GREEN — refactor safety net established
4. Write Phase 1 TDD tests (all RED)
5. Implement Phase 1 — tests go GREEN
6. Verify existing tests still pass (regression)
7. Write Phase 2 TDD tests (all RED)
8. Implement Phase 2 — tests go GREEN

## Known Issues Found During Test Planning

1. **`sanitize_string` bug**: SQL keyword stripping removes `DROP` from `DROPLET`. Tests capture existing behavior for intentional fix later.
2. **`probe_analyzer.py` import side effects**: `secure_config_loader` runs at module import time, triggering file I/O. Tests need `CYT_TEST_MODE=true` before import.
3. **Time-dependent code**: `SecureTimeWindows`, `gps_tracker` use `datetime.now()` / `time.time()` — must freeze time in tests.

## Key Fixtures (conftest.py)

### mock_kismet_db
Real SQLite temp file with Kismet schema (`devices` table). Tests actual SQL, not mock objects.

### populated_kismet_db
Extends mock_kismet_db with sample rows: valid device JSON, malformed JSON, NULL fields.

### sample_config
Minimal valid CYT config dict with paths, timing, time_windows.

### appearance_factory
Factory function creating DeviceAppearance objects with controlled timestamps and locations.

## CI Configuration

```yaml
strategy:
  matrix:
    python-version: ["3.9", "3.11", "3.13"]
env:
  CYT_TEST_MODE: "true"
```

No hardware dependencies. All external services mocked.
