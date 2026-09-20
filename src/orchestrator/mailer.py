from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from orchestrator.config import get_settings


async def send_password_reset(email: str, token: str) -> bool:
    """Send a reset link when SMTP is configured; never logs credentials/tokens."""
    settings = get_settings()
    if not settings.smtp_host:
        return False
    link = f"{settings.public_url.rstrip('/')}?reset_token={token}"
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = "Reset your Orbit password"
    message.set_content(f"Open this one-time link within 30 minutes:\n\n{link}\n")

    def deliver() -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)

    await asyncio.to_thread(deliver)
    return True


async def send_email_verification(email: str, token: str) -> bool:
    """Deliver a short-lived verification link without exposing its token in logs."""
    settings = get_settings()
    if not settings.smtp_host:
        return False
    link = f"{settings.public_url.rstrip('/')}?verify_email_token={token}"
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = "Confirm your Orbit email"
    message.set_content(f"Confirm your Orbit account within 24 hours:\n\n{link}\n")

    def deliver() -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)

    await asyncio.to_thread(deliver)
    return True
