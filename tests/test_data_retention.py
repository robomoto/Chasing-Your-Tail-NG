"""TDD tests for DataRetentionManager — auto-deletion of old data.

These tests define the acceptance criteria for data_retention.py.
Uses real SessionDB with tmp_path for all tests.
"""
import time
import pytest

from session_db import SessionDB
from data_retention import DataRetentionManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Yield a SessionDB backed by a temp file."""
    db_path = str(tmp_path / "retention_test.db")
    sdb = SessionDB(db_path=db_path)
    yield sdb
    sdb.close()


@pytest.fixture
def manager(db):
    """DataRetentionManager with default TTLs."""
    return DataRetentionManager(session_db=db, config={
        "data_retention": {
            "unflagged_ttl_hours": 48,
            "flagged_ttl_days": 90,
        }
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HOUR = 3600
DAY = 86400


def _count_sightings(db):
    """Count rows in device_sightings."""
    row = db._conn.execute("SELECT COUNT(*) FROM device_sightings").fetchone()
    return row[0]


def _count_alerts(db):
    row = db._conn.execute("SELECT COUNT(*) FROM alerts").fetchone()
    return row[0]


def _count_sessions(db):
    row = db._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDataRetention:

    def test_unflagged_deleted_after_ttl(self, db, manager):
        """Sighting at t-49h with no alert is deleted by run_cleanup."""
        now = time.time()
        db.start_session("s1")
        db.record_sighting("s1", "dev-A", "wifi", now - 49 * HOUR)

        manager.run_cleanup()
        assert _count_sightings(db) == 0

    def test_flagged_retained_within_ttl(self, db, manager):
        """Sighting + alert at t-49h is NOT deleted (flagged)."""
        now = time.time()
        db.start_session("s2")
        db.record_sighting("s2", "dev-B", "wifi", now - 49 * HOUR)
        db.record_alert("s2", "dev-B", 0.85, reasons=["persistent"])

        manager.run_cleanup()
        assert _count_sightings(db) == 1
        assert _count_alerts(db) == 1

    def test_flagged_deleted_after_90d(self, db, manager):
        """Sighting + alert at t-91d are both deleted."""
        now = time.time()
        db.start_session("s3")
        db.record_sighting("s3", "dev-C", "wifi", now - 91 * DAY)
        db.record_alert("s3", "dev-C", 0.85, reasons=["persistent"])

        manager.run_cleanup()
        assert _count_sightings(db) == 0
        assert _count_alerts(db) == 0

    def test_recent_unflagged_retained(self, db, manager):
        """Sighting at t-1h (no alert) is NOT deleted."""
        now = time.time()
        db.start_session("s4")
        db.record_sighting("s4", "dev-D", "wifi", now - 1 * HOUR)

        manager.run_cleanup()
        assert _count_sightings(db) == 1

    def test_stale_session_cleaned(self, db, manager):
        """Session with 0 remaining sightings is deleted."""
        now = time.time()
        db.start_session("s5")
        # Insert an old unflagged sighting that will be cleaned
        db.record_sighting("s5", "dev-E", "wifi", now - 49 * HOUR)

        manager.run_cleanup()
        assert _count_sightings(db) == 0
        assert _count_sessions(db) == 0

    def test_cleanup_returns_counts(self, db, manager):
        """run_cleanup returns a dict with deletion counts."""
        now = time.time()
        db.start_session("s6")
        db.record_sighting("s6", "dev-F", "wifi", now - 49 * HOUR)
        db.record_sighting("s6", "dev-G", "wifi", now - 49 * HOUR)

        # Old flagged that expires
        db.start_session("s7")
        db.record_sighting("s7", "dev-H", "wifi", now - 91 * DAY)
        db.record_alert("s7", "dev-H", 0.9)

        result = manager.run_cleanup()
        assert result["sightings_deleted"] == 3
        assert result["alerts_deleted"] == 1
        assert result["sessions_deleted"] == 2
