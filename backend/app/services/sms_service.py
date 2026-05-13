"""
SMS gateway service.

Supports Fast2SMS (India) as the default provider.
Set SMS_PROVIDER=fast2sms and FAST2SMS_API_KEY in .env to activate.

Adding a new provider: implement a function matching the signature
  _send_<provider>(mobile, message) -> dict
and register it in PROVIDERS.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


def _send_fast2sms(mobile: str, message: str) -> dict[str, Any]:
    """
    Sends SMS via Fast2SMS DLT/Quick-send API.
    https://docs.fast2sms.com
    """
    if not settings.FAST2SMS_API_KEY:
        return {"sent": False, "error": "FAST2SMS_API_KEY not configured."}

    # Normalise: strip leading +91 or 91 prefix, keep 10 digits
    number = mobile.strip().lstrip("+")
    if number.startswith("91") and len(number) == 12:
        number = number[2:]

    if len(number) != 10:
        return {"sent": False, "error": f"Invalid mobile number format: {mobile}"}

    try:
        response = httpx.post(
            "https://www.fast2sms.com/dev/bulkV2",
            headers={
                "authorization": settings.FAST2SMS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "route": "q",
                "message": message[:160],
                "language": "english",
                "flash": 0,
                "numbers": number,
            },
            timeout=10.0,
        )
        data = response.json()
        if data.get("return") is True:
            return {"sent": True, "provider": "fast2sms", "mobile": number, "response": data}
        return {"sent": False, "provider": "fast2sms", "mobile": number, "error": data.get("message", str(data))}
    except Exception as exc:
        return {"sent": False, "provider": "fast2sms", "mobile": number, "error": str(exc)}


PROVIDERS: dict[str, Any] = {
    "fast2sms": _send_fast2sms,
}


def send_sms(mobile: str, message: str) -> dict[str, Any]:
    """
    Dispatches an SMS using the configured provider.
    Returns a result dict with at minimum {"sent": bool}.
    """
    if not settings.SMS_NOTIFICATIONS_ENABLED:
        return {"sent": False, "reason": "SMS_NOTIFICATIONS_ENABLED is False."}

    provider_fn = PROVIDERS.get(settings.SMS_PROVIDER.lower())
    if not provider_fn:
        return {
            "sent": False,
            "error": f"Unknown SMS provider: {settings.SMS_PROVIDER}. Supported: {list(PROVIDERS)}",
        }

    return provider_fn(mobile, message)


def send_sms_bulk(mobiles: list[str], message: str) -> list[dict[str, Any]]:
    """Sends the same message to multiple numbers. Returns one result per number."""
    return [send_sms(m, message) for m in mobiles if m]
