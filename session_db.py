"""SQLite session database for cross-session analysis."""
import json
import sqlite3
import time
from typing import List, Optional, Dict, Any

SCHEMA_VERSION = 1


class SessionDB:
    """Historical session database backed by SQLite."""

    def __init__(self, db_path: str = "cyt_sessions.db"):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_schema()

    # -- context manager -----------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # -- internal helpers ----------------------------------------------------

    def _connect(self):
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row

    def _create_schema(self):
        c = self._conn
        c.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                session_id  TEXT PRIMARY KEY,
                start_time  REAL,
                end_time    REAL,
                device_count INTEGER DEFAULT 0,
                gps_lat     REAL DEFAULT 0.0,
                gps_lon     REAL DEFAULT 0.0
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS device_sightings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT,
                device_id   TEXT,
                source_type TEXT,
                timestamp   REAL,
                lat         REAL DEFAULT 0.0,
                lon         REAL DEFAULT 0.0,
                rssi        REAL DEFAULT 0.0,
                metadata    TEXT
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS alerts (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id        TEXT,
                device_id         TEXT,
                persistence_score REAL,
                reasons           TEXT,
                locations         TEXT
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER
            )"""
        )
        # Seed schema version if empty
        row = c.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            c.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        c.commit()

    # -- public API ----------------------------------------------------------

    def start_session(self, session_id: str, lat: float = 0.0,
                      lon: float = 0.0) -> None:
        self._conn.execute(
            "INSERT INTO sessions (session_id, start_time, gps_lat, gps_lon) VALUES (?, ?, ?, ?)",
            (session_id, time.time(), lat, lon),
        )
        self._conn.commit()

    def end_session(self, session_id: str, device_count: int = 0) -> None:
        self._conn.execute(
            "UPDATE sessions SET end_time = ?, device_count = ? WHERE session_id = ?",
            (time.time(), device_count, session_id),
        )
        self._conn.commit()

    def record_sighting(self, session_id: str, device_id: str, source_type: str,
                        timestamp: float, lat: float = 0.0, lon: float = 0.0,
                        rssi: float = 0.0, metadata: Optional[Dict] = None) -> None:
        meta_json = json.dumps(metadata) if metadata is not None else None
        self._conn.execute(
            """INSERT INTO device_sightings
               (session_id, device_id, source_type, timestamp, lat, lon, rssi, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, device_id, source_type, timestamp, lat, lon, rssi, meta_json),
        )
        self._conn.commit()

    def record_alert(self, session_id: str, device_id: str, persistence_score: float,
                     reasons: List[str] = None, locations: List[str] = None) -> None:
        self._conn.execute(
            """INSERT INTO alerts
               (session_id, device_id, persistence_score, reasons, locations)
               VALUES (?, ?, ?, ?, ?)""",
            (
                session_id,
                device_id,
                persistence_score,
                json.dumps(reasons or []),
                json.dumps(locations or []),
            ),
        )
        self._conn.commit()

    def get_device_history(self, device_id: str, days: int = 30) -> List[Dict[str, Any]]:
        cutoff = time.time() - (days * 86400)
        rows = self._conn.execute(
            """SELECT * FROM device_sightings
               WHERE device_id = ? AND timestamp >= ?
               ORDER BY timestamp DESC""",
            (device_id, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cross_session_devices(self, min_sessions: int = 2) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT device_id, COUNT(DISTINCT session_id) AS session_count
               FROM device_sightings
               GROUP BY device_id
               HAVING COUNT(DISTINCT session_id) >= ?
               ORDER BY session_count DESC""",
            (min_sessions,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
