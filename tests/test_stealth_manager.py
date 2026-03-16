"""TDD tests for StealthManager -- stealth mode, path obfuscation, duress wipe.

These tests define the acceptance criteria for stealth_manager.py.
They should FAIL against the current stub and PASS once implemented.
"""
import hashlib
import os
import pytest

from stealth_manager import StealthManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(enabled=False, seed="test-seed-42",
                 normal_password="correct-horse", duress_password="battery-staple",
                 salt="nacl-16bytes!!", app_name_override=None, wipe_paths=None):
    """Build a stealth_mode config section."""
    cfg = {
        "stealth_mode": {
            "enabled": enabled,
            "seed": seed,
            "salt": salt,
            "normal_password_hash": hashlib.sha256(
                (salt + normal_password).encode()
            ).hexdigest(),
            "duress_password_hash": hashlib.sha256(
                (salt + duress_password).encode()
            ).hexdigest(),
            "wipe_paths": wipe_paths or [],
        }
    }
    if app_name_override:
        cfg["stealth_mode"]["app_name"] = app_name_override
    return cfg


@pytest.fixture
def stealth_off_config():
    return _make_config(enabled=False)


@pytest.fixture
def stealth_on_config():
    return _make_config(enabled=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStealthManager:
    """StealthManager acceptance tests."""

    # -- path obfuscation ---------------------------------------------------

    def test_stealth_off_passthrough(self, stealth_off_config):
        """Stealth disabled: get_db_path returns the original path unchanged."""
        sm = StealthManager(stealth_off_config)
        assert sm.get_db_path("cyt_sessions.db") == "cyt_sessions.db"

    def test_stealth_obfuscates_paths(self, stealth_on_config):
        """Stealth enabled: get_db_path returns a hex string that does NOT contain 'cyt'."""
        sm = StealthManager(stealth_on_config)
        result = sm.get_db_path("cyt_sessions.db")
        assert "cyt" not in result.lower()
        # Should still end with .db
        assert result.endswith(".db")

    def test_stealth_consistent_obfuscation(self, stealth_on_config):
        """Same input + same seed always produces the same obfuscated path."""
        sm1 = StealthManager(stealth_on_config)
        sm2 = StealthManager(stealth_on_config)
        assert sm1.get_db_path("cyt_sessions.db") == sm2.get_db_path("cyt_sessions.db")

    # -- is_active property -------------------------------------------------

    def test_is_active_reflects_config(self):
        """is_active mirrors the enabled flag in config."""
        sm_on = StealthManager(_make_config(enabled=True))
        sm_off = StealthManager(_make_config(enabled=False))
        assert sm_on.is_active is True
        assert sm_off.is_active is False

    # -- display config -----------------------------------------------------

    def test_display_config_stealth(self, stealth_on_config):
        """Stealth on: app_name is NOT 'CYT-NG'."""
        sm = StealthManager(stealth_on_config)
        dc = sm.get_display_config()
        assert dc["app_name"] != "CYT-NG"
        assert dc["show_branding"] is False

    def test_display_config_normal(self, stealth_off_config):
        """Stealth off: app_name is 'CYT-NG'."""
        sm = StealthManager(stealth_off_config)
        dc = sm.get_display_config()
        assert dc["app_name"] == "CYT-NG"
        assert dc["show_branding"] is True

    # -- wipe ---------------------------------------------------------------

    def test_wipe_deletes_files(self, tmp_path, stealth_on_config):
        """wipe_all_data overwrites and deletes the listed files."""
        f1 = tmp_path / "secret.db"
        f2 = tmp_path / "logs.txt"
        f1.write_bytes(b"sensitive data here")
        f2.write_bytes(b"log entries")

        stealth_on_config["stealth_mode"]["wipe_paths"] = [str(f1), str(f2)]
        sm = StealthManager(stealth_on_config)
        sm.wipe_all_data()

        assert not f1.exists()
        assert not f2.exists()

    # -- authentication -----------------------------------------------------

    def test_authenticate_normal(self, stealth_on_config):
        """Correct normal password returns 'normal'."""
        sm = StealthManager(stealth_on_config)
        assert sm.authenticate("correct-horse") == "normal"

    def test_authenticate_duress(self, tmp_path, stealth_on_config):
        """Duress password returns 'duress' and triggers wipe."""
        target = tmp_path / "wipe_me.db"
        target.write_bytes(b"evidence")
        stealth_on_config["stealth_mode"]["wipe_paths"] = [str(target)]

        sm = StealthManager(stealth_on_config)
        result = sm.authenticate("battery-staple")

        assert result == "duress"
        assert not target.exists()

    def test_authenticate_invalid(self, stealth_on_config):
        """Wrong password returns 'invalid'."""
        sm = StealthManager(stealth_on_config)
        assert sm.authenticate("wrong-password") == "invalid"
