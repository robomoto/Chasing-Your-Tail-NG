"""Stealth mode -- path obfuscation, duress wipe, display config.

Provides:
- Deterministic path obfuscation (SHA-256 + seed) so filenames reveal nothing.
- Duress password that triggers immediate secure wipe of all data files.
- Display config toggling so the app can hide its identity.
"""
import hashlib
import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class StealthManager:
    """Manage stealth-mode features: path obfuscation, authentication, wipe."""

    def __init__(self, config: dict):
        stealth = config.get("stealth_mode", {})
        self._enabled: bool = stealth.get("enabled", False)
        self._seed: str = stealth.get("seed", "")
        self._salt: str = stealth.get("salt", "")
        self._normal_hash: str = stealth.get("normal_password_hash", "")
        self._duress_hash: str = stealth.get("duress_password_hash", "")
        self._wipe_paths: List[str] = list(stealth.get("wipe_paths", []))
        self._app_name: str = stealth.get("app_name", "Utility")

    # -- path obfuscation ---------------------------------------------------

    def _obfuscate(self, original: str) -> str:
        """Return a deterministic hex-based filename for *original*."""
        digest = hashlib.sha256((original + self._seed).encode()).hexdigest()[:8]
        ext = Path(original).suffix  # e.g. ".db"
        return digest + ext

    def get_db_path(self, original_path: str) -> str:
        """Return the on-disk database path (obfuscated when stealth is on)."""
        if not self._enabled:
            return original_path
        return self._obfuscate(original_path)

    def get_log_path(self, original_path: str) -> str:
        """Return the on-disk log path (obfuscated when stealth is on)."""
        if not self._enabled:
            return original_path
        return self._obfuscate(original_path)

    # -- authentication -----------------------------------------------------

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256((self._salt + password).encode()).hexdigest()

    def authenticate(self, password: str) -> str:
        """Authenticate a password.

        Returns:
            "normal"  -- correct everyday password.
            "duress"  -- duress password; triggers immediate wipe.
            "invalid" -- wrong password.
        """
        pw_hash = self._hash_password(password)

        if pw_hash == self._normal_hash:
            return "normal"

        if pw_hash == self._duress_hash:
            logger.warning("Duress password entered -- initiating wipe.")
            self.wipe_all_data()
            return "duress"

        return "invalid"

    # -- secure wipe --------------------------------------------------------

    def wipe_all_data(self) -> None:
        """Overwrite every file in *wipe_paths* with random bytes, then unlink."""
        for path_str in self._wipe_paths:
            p = Path(path_str)
            if not p.exists():
                continue
            try:
                size = p.stat().st_size
                # Overwrite with random bytes to hinder recovery
                with open(p, "wb") as f:
                    f.write(os.urandom(max(size, 1)))
                    f.flush()
                    os.fsync(f.fileno())
                p.unlink()
                logger.info("Wiped %s", path_str)
            except OSError as exc:
                logger.error("Failed to wipe %s: %s", path_str, exc)

    # -- display config -----------------------------------------------------

    def get_display_config(self) -> dict:
        """Return UI display settings appropriate for the current mode."""
        if self._enabled:
            return {
                "app_name": self._app_name,
                "show_branding": False,
            }
        return {
            "app_name": "CYT-NG",
            "show_branding": True,
        }

    # -- property -----------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """Whether stealth mode is currently enabled."""
        return self._enabled
