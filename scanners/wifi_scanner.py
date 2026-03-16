"""WiFi scanner wrapping existing Kismet DB polling. STUB — Phase 1 implementation pending."""
from scanners.base_scanner import BaseScanner


class WiFiScanner(BaseScanner):
    """Wraps existing Kismet SQLite polling as a BaseScanner. STUB."""

    @property
    def scanner_name(self) -> str:
        return "wifi"

    def _scan_loop(self) -> None:
        raise NotImplementedError("WiFiScanner not yet implemented")
