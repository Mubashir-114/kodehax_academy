import logging

import requests

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


logger = logging.getLogger(__name__)

BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


def _mask_address(address):
    """Mask an email local part for safe diagnostics (never log full addresses)."""
    if not address or "@" not in address:
        return address or ""
    local, domain = address.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[:1]}*"
    else:
        masked_local = f"{local[:2]}{'*' * max(len(local) - 2, 1)}"
    return f"{masked_local}@{domain}"


class BrevoEmailError(Exception):
    """Raised when Brevo cannot accept an email for delivery."""


class BrevoEmailBackend(BaseEmailBackend):
    """Deliver Django email messages through Brevo's transactional HTTPS API."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send(message)
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent

    def _send(self, message):
        recipients = message.recipients()
        if not recipients:
            return

        payload = {
            "sender": {
                "email": settings.BREVO_SENDER_EMAIL,
                "name": settings.BREVO_SENDER_NAME,
            },
            "to": [{"email": address} for address in message.to],
            "subject": message.subject,
            "textContent": message.body,
        }
        if message.cc:
            payload["cc"] = [{"email": address} for address in message.cc]
        if message.bcc:
            payload["bcc"] = [{"email": address} for address in message.bcc]

        for alternative in getattr(message, "alternatives", ()):
            if alternative.mimetype == "text/html":
                payload["htmlContent"] = alternative.content
                break

        try:
            response = requests.post(
                BREVO_EMAIL_URL,
                headers={
                    "accept": "application/json",
                    "api-key": settings.BREVO_API_KEY,
                    "content-type": "application/json",
                },
                json=payload,
                timeout=settings.BREVO_API_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(
                "brevo_email_request_failed recipients=%s subject=%s error=%s",
                [_mask_address(address) for address in message.to],
                message.subject,
                type(exc).__name__,
            )
            raise BrevoEmailError("Brevo API request failed.") from exc

        message_id = None
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = None
        if isinstance(response_payload, dict):
            message_id = response_payload.get("messageId")
        logger.info(
            "brevo_email_accepted recipients=%s subject=%s provider_message_id=%s",
            [_mask_address(address) for address in message.to],
            message.subject,
            message_id,
        )
