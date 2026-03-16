"""Data retention — auto-deletion of old unflagged data.

Unflagged sightings older than the TTL (default 48 h) are deleted.
Flagged sightings (with a matching alert) are retained up to the flagged TTL
(default 90 days), after which both the sighting and the alert are removed.
Sessions with no remaining sightings are cleaned up.
"""
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class DataRetentionManager:
    """Periodically purges stale data from the session database."""

    def __init__(self, session_db, config: dict = None):
        config = config or {}
        dr_cfg = config.get("data_retention", {})

        self._db = session_db
        self._unflagged_ttl_s: float = dr_cfg.get("unflagged_ttl_hours", 48) * 3600
        self._flagged_ttl_s: float = dr_cfg.get("flagged_ttl_days", 90) * 86400
        self._interval_s: float = dr_cfg.get("cleanup_interval_hours", 1) * 3600

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- background thread ---------------------------------------------------

    def start(self) -> None:
        """Start the background cleanup thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_cleanup()
            except Exception:
                logger.exception("data retention cleanup failed")
            self._stop_event.wait(self._interval_s)

    # -- core cleanup --------------------------------------------------------

    def run_cleanup(self) -> dict:
        """Execute one cleanup pass and return deletion counts.

        Returns a dict with keys ``sightings_deleted``, ``alerts_deleted``,
        ``sessions_deleted``.
        """
        now = time.time()
        conn = self._db._conn
        unflagged_cutoff = now - self._unflagged_ttl_s
        flagged_cutoff = now - self._flagged_ttl_s

        # 1. Delete unflagged sightings older than the unflagged TTL.
        #    "Unflagged" means no matching alert exists for (session_id, device_id).
        cursor = conn.execute(
            """DELETE FROM device_sightings
               WHERE timestamp < ?
                 AND NOT EXISTS (
                     SELECT 1 FROM alerts a
                      WHERE a.session_id = device_sightings.session_id
                        AND a.device_id  = device_sightings.device_id
                 )""",
            (unflagged_cutoff,),
        )
        sightings_unflagged = cursor.rowcount

        # 2. Delete flagged sightings older than the flagged TTL.
        cursor = conn.execute(
            """DELETE FROM device_sightings
               WHERE timestamp < ?
                 AND EXISTS (
                     SELECT 1 FROM alerts a
                      WHERE a.session_id = device_sightings.session_id
                        AND a.device_id  = device_sightings.device_id
                 )""",
            (flagged_cutoff,),
        )
        sightings_flagged = cursor.rowcount

        # 3. Delete alerts whose sightings have all been removed.
        #    (i.e., no remaining sighting for that session+device pair.)
        cursor = conn.execute(
            """DELETE FROM alerts
               WHERE NOT EXISTS (
                   SELECT 1 FROM device_sightings ds
                    WHERE ds.session_id = alerts.session_id
                      AND ds.device_id  = alerts.device_id
               )""",
        )
        alerts_deleted = cursor.rowcount

        # 4. Delete sessions with no remaining sightings.
        cursor = conn.execute(
            """DELETE FROM sessions
               WHERE NOT EXISTS (
                   SELECT 1 FROM device_sightings ds
                    WHERE ds.session_id = sessions.session_id
               )""",
        )
        sessions_deleted = cursor.rowcount

        conn.commit()

        total_sightings = sightings_unflagged + sightings_flagged
        logger.info(
            "retention cleanup: %d sightings, %d alerts, %d sessions deleted",
            total_sightings, alerts_deleted, sessions_deleted,
        )

        return {
            "sightings_deleted": total_sightings,
            "alerts_deleted": alerts_deleted,
            "sessions_deleted": sessions_deleted,
        }
