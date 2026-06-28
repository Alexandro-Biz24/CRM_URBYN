from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Impossible d'envoyer l'email (configuration ou fournisseur)."""


def _plain_body(*, code: str, ttl_minutes: int) -> str:
    return (
        f"Bonjour,\n\n"
        f"Votre code de confirmation Urbyn est : {code}\n\n"
        f"Ce code est valable {ttl_minutes} minutes.\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.\n\n"
        f"L'équipe Urbyn"
    )


def _html_body(*, code: str, ttl_minutes: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:32px 16px;">
    <tr><td align="center">
      <table width="100%" style="max-width:480px;background:#ffffff;border-radius:12px;padding:32px;">
        <tr><td style="text-align:center;padding-bottom:24px;">
          <span style="font-size:22px;font-weight:bold;color:#111111;">Urbyn</span>
        </td></tr>
        <tr><td style="color:#333333;font-size:15px;line-height:1.5;">
          <p>Bonjour,</p>
          <p>Voici votre code de confirmation :</p>
        </td></tr>
        <tr><td align="center" style="padding:16px 0 24px;">
          <span style="display:inline-block;font-size:36px;font-weight:bold;letter-spacing:10px;
            color:#111111;background:#f9f9f9;border:1px solid #e5e5e5;border-radius:10px;
            padding:16px 24px;">{code}</span>
        </td></tr>
        <tr><td style="color:#666666;font-size:13px;line-height:1.5;text-align:center;">
          <p>Ce code expire dans <strong>{ttl_minutes} minutes</strong>.</p>
          <p>Si vous n'avez pas demandé ce code, ignorez cet email.</p>
        </td></tr>
        <tr><td style="padding-top:24px;color:#999999;font-size:12px;text-align:center;">
          L'équipe Urbyn
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _resend_error_message(http_code: int, detail: str, *, to_email: str) -> str:
    """Message lisible côté front selon la réponse Resend."""
    try:
        data = json.loads(detail)
        msg = data.get("message") or data.get("error") or detail
    except json.JSONDecodeError:
        msg = detail or f"HTTP {http_code}"

    lowered = msg.lower()
    if "only send" in lowered or "testing" in lowered or "verified" in lowered:
        return (
            "En mode test Resend, l'email de destination doit être celui de ton compte Resend. "
            f"Tu as utilisé : {to_email}."
        )
    if http_code == 403 and "1010" in detail:
        return "Erreur technique d'envoi (Resend). Réessayez ou contactez le support."
    return f"L'envoi de l'email a échoué : {msg}"


def _send_via_resend(*, to_email: str, subject: str, html: str, text: str) -> None:
    payload = json.dumps(
        {
            "from": settings.mail_from,
            "to": [to_email],
            "subject": subject,
            "html": html,
            "text": text,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "urbyn-crm/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status >= 400:
                raise EmailDeliveryError(f"Resend HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("Resend error %s: %s", exc.code, detail)
        user_message = _resend_error_message(exc.code, detail, to_email=to_email)
        raise EmailDeliveryError(user_message) from exc
    except urllib.error.URLError as exc:
        logger.error("Resend network error: %s", exc)
        raise EmailDeliveryError("Impossible de joindre le service d'envoi d'emails.") from exc


def _send_via_smtp(*, to_email: str, subject: str, html: str, text: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.mail_from
    message["To"] = to_email
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except smtplib.SMTPException as exc:
        logger.error("SMTP error: %s", exc)
        raise EmailDeliveryError(
            "L'envoi SMTP a échoué. Vérifiez identifiants et paramètres SMTP."
        ) from exc


def send_verification_email(*, to_email: str, code: str, ttl_minutes: int) -> None:
    if not settings.email_configured:
        raise EmailDeliveryError(
            "Aucun service email configuré. Ajoutez RESEND_API_KEY ou les variables SMTP dans .env."
        )

    subject = "Urbyn — Code de confirmation"
    text = _plain_body(code=code, ttl_minutes=ttl_minutes)
    html = _html_body(code=code, ttl_minutes=ttl_minutes)

    if settings.resend_configured:
        _send_via_resend(to_email=to_email, subject=subject, html=html, text=text)
    else:
        _send_via_smtp(to_email=to_email, subject=subject, html=html, text=text)

    logger.info("Email de vérification envoyé à %s", to_email)


def send_shipping_quote_email(
    *,
    buyer_email: str,
    buyer_company: str,
    product_name: str,
    product_id: int,
    quantity: int,
    seller_company: str,
    delivery_street: str,
    delivery_zip_code: str,
    delivery_city: str,
    delivery_state: str | None,
    buyer_message: str | None,
) -> None:
    if not settings.email_configured:
        logger.warning("DEV — devis livraison pour produit %s (email non configuré)", product_id)
        return

    subject = f"Urbyn — Demande de devis livraison ({product_name})"
    addr = f"{delivery_street}, {delivery_zip_code} {delivery_city}"
    if delivery_state:
        addr += f" ({delivery_state})"
    text = (
        f"Demande de devis livraison\n\n"
        f"Acheteur : {buyer_email} ({buyer_company})\n"
        f"Produit : {product_name} (id {product_id})\n"
        f"Quantité : {quantity}\n"
        f"Fournisseur : {seller_company}\n"
        f"Adresse : {addr}\n"
        f"Message : {buyer_message or '—'}\n"
    )
    html = f"<pre>{text}</pre>"

    if settings.resend_configured:
        _send_via_resend(to_email=buyer_email, subject=subject, html=html, text=text)
    else:
        _send_via_smtp(to_email=buyer_email, subject=subject, html=html, text=text)

    logger.info("Demande de devis livraison envoyée pour produit %s", product_id)
