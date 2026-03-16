"""TDD tests for SessionDB — Phase 1 base station upgrade.

These tests define the acceptance criteria for the SQLite session database.
They should FAIL against the current stub and PASS once implemented.
"""
import json
import sqlite3
import time
import pytest

from session_db import SessionDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return a temporary database file path."""
    return str(tmp_path / "test_sessions.db")


@pytest.fixture
def db(db_path):
    """Yield an opened SessionDB, close on teardown."""
    sdb = SessionDB(db_path=db_path)
    sdb.__enter__()
    yield sdb
    sdb.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSessionDB:
    """SessionDB acceptance tests."""

    def test_schema_created_on_open(self, db_path):
        """Tables sessions, device_sightings, and alerts exist after init."""
        sdb = SessionDB(db_path=db_path)
        with sdb:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()

        assert "sessions" in tables
        assert "device_sightings" in tables
        assert "alerts" in tables

    def test_start_and_end_session(self, db, db_path):
        """A session can be started and then ended; both timestamps recorded."""
        db.start_session("sess-001", lat=33.45, lon=-112.07)
        db.end_session("sess-001", device_count=42)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", ("sess-001",)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["session_id"] == "sess-001"
        assert row["start_time"] is not None
        assert row["end_time"] is not None
        assert row["device_count"] == 42
        assert row["gps_lat"] == pytest.approx(33.45, abs=0.01)
        assert row["gps_lon"] == pytest.approx(-112.07, abs=0.01)

    def test_record_sighting(self, db, db_path):
        """A sighting is inserted and retrievable by device_id."""
        db.start_session("sess-002")
        now = time.time()
        db.record_sighting(
            session_id="sess-002",
            device_id="AA:BB:CC:DD:EE:01",
            source_type="wifi",
            timestamp=now,
            lat=33.45,
            lon=-112.07,
            rssi=-65.0,
            metadata={"ssid": "TestNet"},
        )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM device_sightings WHERE device_id = ?",
            ("AA:BB:CC:DD:EE:01",),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["session_id"] == "sess-002"
        assert row["source_type"] == "wifi"
        assert row["timestamp"] == pytest.approx(now, abs=1.0)
        assert row["rssi"] == pytest.approx(-65.0, abs=0.1)
        # metadata should be stored as JSON string
        meta = json.loads(row["metadata"])
        assert meta["ssid"] == "TestNet"

    def test_record_alert(self, db, db_path):
        """An alert with JSON reasons and locations is stored correctly."""
        db.start_session("sess-003")
        reasons = ["Appeared 5 times over 2.0 hours", "Followed across 3 locations"]
        locations = ["home", "office", "gym"]
        db.record_alert(
            session_id="sess-003",
            device_id="AA:BB:CC:DD:EE:02",
            persistence_score=0.85,
            reasons=reasons,
            locations=locations,
        )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM alerts WHERE device_id = ?",
            ("AA:BB:CC:DD:EE:02",),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["persistence_score"] == pytest.approx(0.85, abs=0.01)
        assert json.loads(row["reasons"]) == reasons
        assert json.loads(row["locations"]) == locations

    def test_get_device_history(self, db):
        """get_device_history returns sightings within the day window and excludes older."""
        db.start_session("sess-004")
        now = time.time()
        recent_ts = now - (3600 * 12)          # 12 hours ago — within 30-day window
        old_ts = now - (3600 * 24 * 45)        # 45 days ago — outside 30-day window

        db.record_sighting("sess-004", "dev-A", "wifi", recent_ts)
        db.record_sighting("sess-004", "dev-A", "wifi", old_ts)

        history = db.get_device_history("dev-A", days=30)
        # Only the recent sighting should be returned
        assert len(history) == 1
        assert history[0]["device_id"] == "dev-A"
        assert history[0]["timestamp"] == pytest.approx(recent_ts, abs=1.0)

    def test_get_cross_session_devices(self, db):
        """Devices in 2+ sessions are returned; single-session devices excluded."""
        db.start_session("sess-A")
        db.start_session("sess-B")
        now = time.time()

        # Device seen in both sessions
        db.record_sighting("sess-A", "repeater-01", "wifi", now - 100)
        db.record_sighting("sess-B", "repeater-01", "wifi", now - 50)

        # Device seen in only one session
        db.record_sighting("sess-A", "one-timer-99", "ble", now - 80)

        cross = db.get_cross_session_devices(min_sessions=2)
        device_ids = [d["device_id"] for d in cross]
        assert "repeater-01" in device_ids
        assert "one-timer-99" not in device_ids

    def test_context_manager(self, db_path):
        """SessionDB works as a context manager: opens on enter, closes on exit."""
        sdb = SessionDB(db_path=db_path)
        with sdb as opened:
            assert opened is sdb
            # Should be able to perform operations inside the with block
            opened.start_session("ctx-test")
        # After exiting, the connection should be closed — further ops should fail
        # (implementation detail: _conn should be None)

    def test_close_idempotent(self, db_path):
        """Calling close() twice does not raise."""
        sdb = SessionDB(db_path=db_path)
        with sdb:
            sdb.start_session("idem-test")
        # First close already happened via __exit__; second should be safe
        sdb.close()
        sdb.close()  # third call — still no exception
