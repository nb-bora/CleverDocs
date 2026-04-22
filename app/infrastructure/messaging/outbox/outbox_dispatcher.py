"""Dispatcher: poll outbox, publish, mark sent (idempotent)."""

from __future__ import annotations

import time

from app.infrastructure.db.session import SessionLocal
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.messaging.outbox.outbox_publisher import get_pending_events, publish_one


def main() -> None:
    bus = EventBus()
    while True:
        db = SessionLocal()
        try:
            pending = get_pending_events(db, limit=50)
            if not pending:
                time.sleep(0.5)
                continue
            for ev in pending:
                try:
                    publish_one(db=db, bus=bus, ev=ev)
                    ev.status = "sent"
                    ev.last_error = None
                    db.add(ev)
                    db.commit()
                except Exception as e:
                    ev.attempts = int(ev.attempts or 0) + 1
                    ev.status = "failed" if ev.attempts >= 5 else "pending"
                    ev.last_error = f"{type(e).__name__}: {e}"
                    db.add(ev)
                    db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    main()
