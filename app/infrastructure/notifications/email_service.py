"""Email notification service (SMTP).

Gmail notes:
- Use an App Password (recommended) instead of "less secure apps".
- Keep emails transactional to reduce spam risk.
"""

from __future__ import annotations

import email.utils
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    mail_from: str
    mail_from_name: str
    reply_to: str | None = None


class EmailService:
    def __init__(self, cfg: SmtpConfig) -> None:
        self._cfg = cfg

    def send_html(
        self,
        *,
        to_email: str,
        subject: str,
        html: str,
        text: str,
        message_id_suffix: str | None = None,
    ) -> None:
        msg = EmailMessage()
        msg["To"] = to_email
        msg["From"] = email.utils.formataddr((self._cfg.mail_from_name, self._cfg.mail_from))
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        if self._cfg.reply_to:
            msg["Reply-To"] = self._cfg.reply_to
        if message_id_suffix:
            # Stable-ish message id helps threading/dedup on the provider side.
            msg["Message-ID"] = email.utils.make_msgid(idstring=message_id_suffix)

        msg.set_content(text)
        msg.add_alternative(html, subtype="html")

        ctx = ssl.create_default_context()
        with smtplib.SMTP(self._cfg.host, self._cfg.port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            if self._cfg.username and self._cfg.password:
                smtp.login(self._cfg.username, self._cfg.password)
            smtp.send_message(msg)


def gmail_smtp_config(
    *,
    username: str,
    app_password: str,
    mail_from: str,
    mail_from_name: str,
    reply_to: str | None,
) -> SmtpConfig:
    return SmtpConfig(
        host="smtp.gmail.com",
        port=587,
        username=username,
        password=app_password,
        mail_from=mail_from,
        mail_from_name=mail_from_name,
        reply_to=reply_to,
    )

