import requests

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


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
            raise BrevoEmailError("Brevo API request failed.") from exc
