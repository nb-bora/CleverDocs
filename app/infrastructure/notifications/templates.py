"""Email templates (HTML + text)."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class InvitationEmail:
    subject: str
    html: str
    text: str


def _safe_host(url: str) -> str:
    try:
        p = urlparse(url)
        return p.netloc or ""
    except Exception:
        return ""


def render_invitation_email(
    *,
    organization_name: str,
    inviter_name: str | None,
    role: str,
    accept_url: str,
    expires_human: str,
) -> InvitationEmail:
    org = (organization_name or "CleverDocs").strip()
    inv_by = (inviter_name or "un administrateur").strip()
    role_clean = (role or "member").strip()
    accept = (accept_url or "").strip()
    exp = (expires_human or "").strip()
    host = _safe_host(accept)

    # Escape everything that can be user-provided.
    org_e = escape(org)
    inv_by_e = escape(inv_by)
    role_e = escape(role_clean)
    accept_e = escape(accept, quote=True)
    host_e = escape(host)
    exp_e = escape(exp)

    subject = f"Invitation à rejoindre {org}"

    text = (
        f"Bonjour,\n\n"
        f"{inv_by} vous a invité(e) à rejoindre l’organisation {org} (rôle : {role_clean}).\n\n"
        f"Pour accepter, ouvrez ce lien :\n"
        f"{accept}\n\n"
        f"{('Expiration : ' + exp) if exp else ''}\n"
        f"\n"
        f"Si vous n’êtes pas à l’origine de cette demande, ignorez cet email.\n"
    ).strip() + "\n"

    # Transactional, deliverable HTML:
    # - table layout for email clients
    # - inline CSS only
    # - includes “copy/paste link” fallback
    html = f"""
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="x-apple-disable-message-reformatting" />
    <title>{escape(subject)}</title>
  </head>
  <body style="margin:0;padding:0;background:#0b1020;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
      <tr>
        <td align="center" style="padding:28px 12px;">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="640" style="width:640px;max-width:100%;">
            <tr>
              <td style="padding:0 0 14px 0;">
                <div style="font-family:Arial,Helvetica,sans-serif;color:#cbd5e1;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;">
                  CleverDocs
                </div>
              </td>
            </tr>
            <tr>
              <td style="background:#ffffff;border-radius:16px;overflow:hidden;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                  <tr>
                    <td style="padding:26px 26px 8px 26px;">
                      <div style="font-family:Arial,Helvetica,sans-serif;color:#0f172a;font-size:22px;font-weight:700;line-height:1.25;">
                        Invitation à rejoindre {org_e}
                      </div>
                      <div style="font-family:Arial,Helvetica,sans-serif;color:#475569;font-size:14px;line-height:1.5;margin-top:10px;">
                        <b>{inv_by_e}</b> vous a invité(e) à rejoindre <b>{org_e}</b> avec le rôle <b>{role_e}</b>.
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:18px 26px 8px 26px;">
                      <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                        <tr>
                          <td bgcolor="#111827" style="border-radius:10px;">
                            <a href="{accept_e}" style="display:inline-block;padding:12px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;">
                              Accepter l’invitation
                            </a>
                          </td>
                        </tr>
                      </table>
                      <div style="font-family:Arial,Helvetica,sans-serif;color:#64748b;font-size:12px;line-height:1.5;margin-top:10px;">
                        {('Ce lien expire le ' + exp_e + '.') if exp else ''}
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:10px 26px 22px 26px;">
                      <div style="font-family:Arial,Helvetica,sans-serif;color:#94a3b8;font-size:12px;line-height:1.6;">
                        Si le bouton ne fonctionne pas, copiez/collez ce lien dans votre navigateur{(' (' + host_e + ')') if host else ''} :<br/>
                        <span style="color:#334155;word-break:break-all;">{accept_e}</span>
                      </div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:14px 4px 0 4px;">
                <div style="font-family:Arial,Helvetica,sans-serif;color:#94a3b8;font-size:12px;line-height:1.6;text-align:center;">
                  Si vous n’êtes pas à l’origine de cette demande, ignorez cet email.
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()
    return InvitationEmail(subject=subject, html=html, text=text)

