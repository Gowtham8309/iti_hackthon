from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class SelfieStorageError(ValueError):
    pass


def _parse_data_url(data_url: str) -> tuple[str, bytes]:
    """
    Parses browser canvas data URL.

    Expected:
    data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ...
    """
    if not data_url:
        raise SelfieStorageError("Selfie image is empty.")

    match = re.match(
        r"^data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$",
        data_url,
        re.DOTALL,
    )

    if not match:
        raise SelfieStorageError("Invalid selfie image format. Expected base64 data URL.")

    mime_type = match.group("mime").lower().strip()
    encoded_data = match.group("data").strip()

    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise SelfieStorageError(
            f"Unsupported selfie image type: {mime_type}. "
            f"Allowed: {sorted(SUPPORTED_IMAGE_MIME_TYPES)}"
        )

    try:
        image_bytes = base64.b64decode(encoded_data, validate=True)
    except Exception as exc:
        raise SelfieStorageError("Invalid base64 selfie image data.") from exc

    if not image_bytes:
        raise SelfieStorageError("Decoded selfie image is empty.")

    max_size_bytes = int(settings.MAX_FACE_IMAGE_SIZE_MB) * 1024 * 1024

    if len(image_bytes) > max_size_bytes:
        raise SelfieStorageError(
            f"Selfie image too large. Max allowed size is "
            f"{settings.MAX_FACE_IMAGE_SIZE_MB} MB."
        )

    return mime_type, image_bytes


def save_attendance_selfie(
    *,
    student_id: int,
    attendance_event_id: int,
    selfie_image_base64: str | None,
) -> dict[str, Any]:
    """
    Saves selfie image for attendance evidence.

    For POC:
    - Stores image locally under UPLOAD_DIR/attendance_selfies/
    - Returns relative path and metadata
    - Later this can move to S3/NIC object storage with encryption
    """
    if not selfie_image_base64:
        return {
            "saved": False,
            "reason": "No selfie image provided.",
            "relative_path": None,
            "size_bytes": 0,
            "mime_type": None,
        }

    mime_type, image_bytes = _parse_data_url(selfie_image_base64)
    extension = SUPPORTED_IMAGE_MIME_TYPES[mime_type]

    now = datetime.now(timezone.utc)
    date_folder = now.strftime("%Y-%m-%d")

    base_dir = settings.upload_path / "attendance_selfies" / date_folder / f"student_{student_id}"
    base_dir.mkdir(parents=True, exist_ok=True)

    filename = (
        f"event_{attendance_event_id}_"
        f"{now.strftime('%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}.{extension}"
    )

    out_path = base_dir / filename
    out_path.write_bytes(image_bytes)

    relative_path = str(out_path.relative_to(settings.upload_path)).replace("\\", "/")

    return {
        "saved": True,
        "reason": "Selfie saved successfully.",
        "relative_path": relative_path,
        "absolute_path": str(out_path),
        "size_bytes": len(image_bytes),
        "mime_type": mime_type,
        "file_extension": extension,
    }


def save_profile_selfie(
    *,
    student_code: str,
    selfie_image_base64: str | None,
) -> dict[str, Any]:
    if not selfie_image_base64:
        return {
            "saved": False,
            "reason": "No profile selfie image provided.",
            "relative_path": None,
            "size_bytes": 0,
            "mime_type": None,
        }

    mime_type, image_bytes = _parse_data_url(selfie_image_base64)
    extension = SUPPORTED_IMAGE_MIME_TYPES[mime_type]
    now = datetime.now(timezone.utc)
    base_dir = settings.upload_path / "student_profiles" / student_code
    base_dir.mkdir(parents=True, exist_ok=True)

    filename = f"profile_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{extension}"
    out_path = base_dir / filename
    out_path.write_bytes(image_bytes)

    relative_path = str(out_path.relative_to(settings.upload_path)).replace("\\", "/")
    return {
        "saved": True,
        "reason": "Profile selfie saved successfully.",
        "relative_path": relative_path,
        "absolute_path": str(out_path),
        "size_bytes": len(image_bytes),
        "mime_type": mime_type,
        "file_extension": extension,
    }


def run_selfie_storage_self_test() -> dict[str, Any]:
    """
    Self-test using a tiny 1x1 PNG data URL.
    Writes a real image file into UPLOAD_DIR.
    """
    tiny_png_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )

    result = save_attendance_selfie(
        student_id=1,
        attendance_event_id=999999,
        selfie_image_base64=tiny_png_data_url,
    )

    if not result["saved"]:
        raise RuntimeError("Selfie storage self-test failed.")

    path = Path(result["absolute_path"])

    if not path.exists():
        raise RuntimeError("Selfie file was not created.")

    return {
        "selfie_storage_self_test": "passed",
        "saved": result["saved"],
        "relative_path": result["relative_path"],
        "size_bytes": result["size_bytes"],
        "mime_type": result["mime_type"],
        "file_exists": path.exists(),
    }


if __name__ == "__main__":
    result = run_selfie_storage_self_test()
    print(result)
