# -*- coding: utf-8 -*-
"""
Auto-Revoke Worker
Background thread that checks for pending AutoRevokeSchedule entries
and executes them when their scheduled time arrives.
"""

import time
import threading
from datetime import datetime


class AutoRevokeWorker:
    """Checks every 30 seconds for auto-revoke schedules that are due."""

    def __init__(self, app):
        self.app = app
        self._stop_event = threading.Event()
        self._thread = None

    # ── public ──
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="auto-revoke-worker")
        self._thread.start()
        print("[AUTO-REVOKE] Worker started")

    def stop(self):
        self._stop_event.set()

    # ── loop ──
    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._check_and_execute()
            except Exception as exc:
                print(f"[AUTO-REVOKE] Error: {exc}")
            # Check every 30 seconds
            self._stop_event.wait(30)

    def _check_and_execute(self):
        with self.app.app_context():
            from models import db, Number, AutoRevokeSchedule, ActivityLog

            now = datetime.utcnow()
            due = AutoRevokeSchedule.query.filter(
                AutoRevokeSchedule.is_executed == False,
                AutoRevokeSchedule.revoke_at <= now,
            ).all()

            for schedule in due:
                # Build filter
                q = Number.query.filter(Number.allocated_to_id.isnot(None))
                if schedule.target_user_id:
                    q = q.filter_by(allocated_to_id=schedule.target_user_id)

                revoked = q.update({
                    "allocated_to_id": None,
                    "allocated_by_id": None,
                    "allocated_at": None,
                })

                schedule.is_executed = True
                schedule.executed_at = now

                scope = f"user {schedule.target_user_id}" if schedule.target_user_id else "ALL users"
                db.session.add(ActivityLog(
                    user_id=schedule.created_by_id,
                    action="auto_revoke_executed",
                    details=f"Auto-revoked {revoked} numbers from {scope} (schedule #{schedule.id})",
                ))
                db.session.commit()
                print(f"[AUTO-REVOKE] Executed schedule #{schedule.id}: revoked {revoked} numbers from {scope}")
