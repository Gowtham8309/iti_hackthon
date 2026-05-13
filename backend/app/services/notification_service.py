from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.database_models import AuditLog
from app.services.sms_service import send_sms_bulk


def _append_unique(items: list[str], value: str | None) -> None:
    text = (value or "").strip()
    if text and text not in items:
        items.append(text)


def build_notification_targets(*, student=None, industry=None) -> dict[str, list[str]]:
    emails: list[str] = []
    mobiles: list[str] = []

    for value in settings.default_notification_emails_list:
        _append_unique(emails, value)

    for value in settings.default_notification_mobiles_list:
        _append_unique(mobiles, value)

    if student is not None:
        _append_unique(emails, getattr(student, "email", None))
        _append_unique(mobiles, getattr(student, "mobile", None))

    if industry is not None:
        _append_unique(emails, getattr(industry, "hr_email", None))
        _append_unique(emails, getattr(industry, "supervisor_email", None))
        _append_unique(mobiles, getattr(industry, "hr_mobile", None))
        _append_unique(mobiles, getattr(industry, "supervisor_mobile", None))

    return {
        "emails": emails,
        "mobiles": mobiles,
    }


def create_notification_audit_log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict[str, Any],
    user_id: int | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata,
    )
    db.add(log)
    db.flush()
    return log


def queue_notification(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    subject: str,
    message: str,
    student=None,
    industry=None,
    user_id: int | None = None,
) -> dict[str, Any]:
    targets = build_notification_targets(student=student, industry=industry)

    payload = {
        "subject": subject,
        "message": message,
        "targets": targets,
        "channels": {
            "email_enabled": settings.EMAIL_NOTIFICATIONS_ENABLED,
            "sms_enabled": settings.SMS_NOTIFICATIONS_ENABLED,
        },
        "delivery_mode": "audit_only",
    }

    if settings.EMAIL_NOTIFICATIONS_ENABLED and settings.SMTP_HOST and targets["emails"]:
        email_result = send_email_notification(
            subject=subject,
            message=message,
            recipients=targets["emails"],
        )
        payload["email_delivery"] = email_result
        payload["delivery_mode"] = "smtp_email"

    if settings.SMS_NOTIFICATIONS_ENABLED and targets["mobiles"]:
        sms_text = f"{subject}: {message}"[:160]
        sms_results = send_sms_bulk(targets["mobiles"], sms_text)
        payload["sms_delivery"] = sms_results
        payload["delivery_mode"] = (
            "smtp_email_and_sms"
            if payload["delivery_mode"] == "smtp_email"
            else "sms"
        )

    log = create_notification_audit_log(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=payload,
        user_id=user_id,
    )

    payload["audit_log_id"] = log.id
    return payload


def send_email_notification(
    *,
    subject: str,
    message: str,
    recipients: list[str],
) -> dict[str, Any]:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME or "no-reply@example.com"
    msg["To"] = ", ".join(recipients)
    msg.set_content(message)

    server = None
    try:
        if settings.SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)

        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            server.starttls()

        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")

        server.send_message(msg)

        return {
            "sent": True,
            "recipients": recipients,
            "smtp_host": settings.SMTP_HOST,
        }
    except Exception as exc:
        return {
            "sent": False,
            "recipients": recipients,
            "smtp_host": settings.SMTP_HOST,
            "error": str(exc),
        }
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass
