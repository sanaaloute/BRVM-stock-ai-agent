"""Deliver OTP login codes: email (SMTP), SMS (Twilio), or mock (dev/tests).

AUTH_PROVIDER:
  mock  — never sends; the code is returned in the API response (dev/tests only)
  smtp  — email codes via SMTP; phone codes need SMS_PROVIDER=twilio
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import config

logger = logging.getLogger(__name__)

_SUBJECT = "Votre code de connexion BRVM"
_BODY = (
    "Bonjour,\n\nVotre code de connexion : {code}\n\n"
    "Il est valable {minutes} minutes. Ne le partagez avec personne.\n\n"
    "— Équipe BRVM Stock AI"
)


def deliver_otp(channel: str, identifier: str, code: str) -> bool:
    """Send a login code to an email or phone number. True when dispatched."""
    if config.AUTH_PROVIDER == "mock":
        logger.info("[mock] OTP for %s: %s", identifier, code)
        return True
    if channel == "email":
        return _send_email(identifier, code)
    if channel == "phone":
        return _send_sms(identifier, code)
    return False


def _send_email(to: str, code: str) -> bool:
    if not (config.SMTP_HOST and config.SMTP_FROM):
        logger.error("SMTP_HOST/SMTP_FROM not configured; cannot send email OTP.")
        return False
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = _SUBJECT
    msg.set_content(_BODY.format(code=code, minutes=config.OTP_TTL_SECONDS // 60))
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            if config.SMTP_USER:
                smtp.starttls()
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception:
        logger.exception("Email OTP delivery failed to %s", to)
        return False


def _send_sms(to: str, code: str) -> bool:
    if config.SMS_PROVIDER != "twilio":
        logger.error("SMS_PROVIDER not configured; cannot send SMS OTP.")
        return False
    try:
        from twilio.rest import Client

        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        client.messages.create(
            to=to,
            from_=config.TWILIO_FROM_NUMBER,
            body=_BODY.format(code=code, minutes=config.OTP_TTL_SECONDS // 60),
        )
        return True
    except Exception:
        logger.exception("SMS OTP delivery failed to %s", to)
        return False
