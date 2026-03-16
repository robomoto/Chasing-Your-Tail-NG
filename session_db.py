"""SQLite session database for cross-session analysis. STUB."""
import sqlite3
from typing import List, Optional, Dict, Any


class SessionDB:
    """Historical session database. STUB."""

    def __init__(self, db_path: str = "cyt_sessions.db"):
        raise NotImplementedError("SessionDB not yet implemented")

    def __enter__(self):
        raise NotImplementedError

    def __exit__(self, exc_type, exc_val, exc_tb):
        raise NotImplementedError

    def start_session(self, session_id: str, location_lat: float = 0.0,
                      location_lon: float = 0.0) -> None:
        raise NotImplementedError

    def end_session(self, session_id: str, device_count: int = 0) -> None:
        raise NotImplementedError

    def record_sighting(self, session_id: str, device_id: str, source_type: str,
                        timestamp: float, lat: float = 0.0, lon: float = 0.0,
                        rssi: float = 0.0, metadata: Optional[Dict] = None) -> None:
        raise NotImplementedError

    def record_alert(self, session_id: str, device_id: str, persistence_score: float,
                     reasons: List[str] = None, locations: List[str] = None) -> None:
        raise NotImplementedError

    def get_device_history(self, device_id: str, days: int = 30) -> List[Dict]:
        raise NotImplementedError

    def get_cross_session_devices(self, min_sessions: int = 2) -> List[Dict]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
