"""Transactional email helpers.

The service is configuration-driven: if SMTP is not configured, calls are
logged and skipped so registration never breaks the product.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


def send_email(*, to_email: str, subject: str, text: str) -> bool:
    if not email_configured():
        logger.info("SMTP is not configured; skipping email to %s", to_email)
        return False

    message = EmailMessage()
    sender = settings.SMTP_FROM_EMAIL
    if settings.SMTP_FROM_NAME:
        sender = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)
    return True


def send_welcome_email(to_email: str) -> bool:
    return send_email(
        to_email=to_email,
        subject="Добро пожаловать в AI Platform",
        text=(
            "Вы зарегистрировались в AI Platform.\n\n"
            "Теперь можно сохранять чаты, проекты, файлы и управлять тарифом.\n"
            "Если это были не вы, просто проигнорируйте это письмо."
        ),
    )


def send_password_reset_email(*, to_email: str, reset_url: str, reset_token: str) -> bool:
    return send_email(
        to_email=to_email,
        subject="AI Platform password reset",
        text=(
            "We received a password reset request for AI Platform.\n\n"
            f"Open this link: {reset_url}\n\n"
            f"Or use this token manually: {reset_token}\n\n"
            "If this was not you, you can ignore this email."
        ),
    )
