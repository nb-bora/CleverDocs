"""Dispatcher: poll outbox, publish, mark sent (idempotent)."""

from __future__ import annotations

import json
import time

from app.infrastructure.db.session import SessionLocal
from app.infrastructure.messaging.event_bus import EventBus
from app.infrastructure.messaging.outbox.outbox_publisher import get_pending_events, publish_one
from app.interfaces.api.deps import Settings
from app.infrastructure.notifications.email_service import EmailService, gmail_smtp_config
from app.infrastructure.notifications.templates import render_invitation_email


def main() -> None:
    settings = Settings()
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
                    if (ev.event_type or "").upper() == "INVITATION_EMAIL":
                        if not getattr(settings, "mail_enabled", False):
                            raise RuntimeError("MAIL_DISABLED")
                        payload = json.loads(ev.payload_json or "{}")
                        to_email = str(payload.get("email") or "").strip().lower()
                        accept_url = str(payload.get("accept_url") or "").strip()
                        org_name = str(payload.get("organization_name") or "").strip() or "CleverDocs"
                        role = str(payload.get("role") or "member")
                        expires_at = str(payload.get("expires_at") or "")
                        inviter_name = payload.get("inviter_display_name")
                        inviter_name = str(inviter_name) if inviter_name else None

                        if not to_email or not accept_url:
                            raise RuntimeError("INVALID_EMAIL_PAYLOAD")

                        tpl = render_invitation_email(
                            organization_name=org_name,
                            inviter_name=inviter_name,
                            role=role,
                            accept_url=accept_url,
                            expires_human=expires_at,
                        )
                        svc = EmailService(
                            gmail_smtp_config(
                                username=str(getattr(settings, "mail_username", "")),
                                app_password=str(getattr(settings, "mail_app_password", "")),
                                mail_from=str(getattr(settings, "mail_from", "")) or str(getattr(settings, "mail_username", "")),
                                mail_from_name=str(getattr(settings, "mail_from_name", "CleverDocs")),
                                reply_to=str(getattr(settings, "mail_reply_to", "")) or None,
                            )
                        )
                        suffix = f"invitation.{payload.get('invitation_id')}"
                        svc.send_html(
                            to_email=to_email,
                            subject=tpl.subject,
                            html=tpl.html,
                            text=tpl.text,
                            message_id_suffix=suffix,
                        )
                    else:
                        # Default: publish to bus (no-op in MVP).
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
