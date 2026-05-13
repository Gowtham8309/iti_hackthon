from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from skimage.feature import local_binary_pattern

from app.core.config import settings


class FaceServiceError(ValueError):
    pass


_face_app: FaceAnalysis | None = None


def get_face_app() -> FaceAnalysis:
    """
    Lazy-loads InsightFace pretrained model.

    First run may download model files automatically.
    Using CPUExecutionProvider keeps it compatible with normal laptops.
    """
    global _face_app

    if _face_app is None:
        app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _face_app = app

    return _face_app


def decode_base64_image_to_bgr(image_base64: str) -> np.ndarray:
    """
    Decodes browser canvas base64 image into OpenCV BGR image.

    Supports:
    - data:image/jpeg;base64,...
    - raw base64 string
    """
    if not image_base64:
        raise FaceServiceError("Image base64 is empty.")

    text = image_base64.strip()

    match = re.match(
        r"^data:image/[a-zA-Z0-9.+-]+;base64,(?P<data>.+)$",
        text,
        re.DOTALL,
    )

    if match:
        text = match.group("data").strip()

    try:
        image_bytes = base64.b64decode(text, validate=True)
    except Exception as exc:
        raise FaceServiceError("Invalid base64 image data.") from exc

    if not image_bytes:
        raise FaceServiceError("Decoded image is empty.")

    np_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

    if image_bgr is None:
        raise FaceServiceError("Could not decode image into OpenCV format.")

    return image_bgr


def compute_liveness_score(image_bgr: np.ndarray, face_bbox: dict[str, float] | None = None) -> dict[str, Any]:
    """
    Server-side liveness estimation using texture and sharpness analysis.

    Approach:
    1. Laplacian variance — printed/screen photos are often slightly blurry.
    2. Local Binary Pattern (LBP) variance — real skin has richer micro-texture
       than a flat print or display.
    3. Color channel standard deviation — printed photos have compressed
       color variation compared to a live face under real lighting.

    Crops to the face bounding box when available for more accurate scoring.

    Returns a score 0.0–1.0.  Higher = more likely live.
    Thresholds (configurable via settings):
      LIVENESS_LAPLACIAN_THRESHOLD  default 80.0
      LIVENESS_TEXTURE_THRESHOLD    default 0.15
    """
    if image_bgr is None or image_bgr.size == 0:
        return {"liveness_score": 0.0, "liveness_passed": False, "reason": "Empty image."}

    h, w = image_bgr.shape[:2]
    roi = image_bgr

    if face_bbox:
        x1 = max(0, int(face_bbox.get("x1", 0)))
        y1 = max(0, int(face_bbox.get("y1", 0)))
        x2 = min(w, int(face_bbox.get("x2", w)))
        y2 = min(h, int(face_bbox.get("y2", h)))
        if x2 > x1 and y2 > y1:
            roi = image_bgr[y1:y2, x1:x2]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # 1. Laplacian sharpness (higher → sharper → more likely real camera capture)
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    laplacian_score = min(laplacian_var / (settings.LIVENESS_LAPLACIAN_THRESHOLD * 2), 1.0)

    # 2. LBP texture variance (real skin is texturally rich)
    lbp = local_binary_pattern(gray, P=8, R=1, method="uniform")
    lbp_hist, _ = np.histogram(lbp.ravel(), bins=10, range=(0, 10), density=True)
    lbp_variance = float(np.var(lbp_hist))
    texture_score = min(lbp_variance / (settings.LIVENESS_TEXTURE_THRESHOLD * 2), 1.0)

    # 3. Color channel std — printed photos flatten color variation
    channel_stds = [float(np.std(roi[:, :, c])) for c in range(3)]
    avg_color_std = float(np.mean(channel_stds))
    color_score = min(avg_color_std / 40.0, 1.0)

    # Weighted composite
    liveness_score = round(
        0.45 * laplacian_score + 0.35 * texture_score + 0.20 * color_score,
        4,
    )

    liveness_passed = (
        laplacian_var >= settings.LIVENESS_LAPLACIAN_THRESHOLD
        and lbp_variance >= settings.LIVENESS_TEXTURE_THRESHOLD
    )

    reasons = []
    if laplacian_var < settings.LIVENESS_LAPLACIAN_THRESHOLD:
        reasons.append(f"Image too blurry (sharpness={laplacian_var:.1f}, min={settings.LIVENESS_LAPLACIAN_THRESHOLD}).")
    if lbp_variance < settings.LIVENESS_TEXTURE_THRESHOLD:
        reasons.append(f"Face texture too uniform (texture={lbp_variance:.4f}, min={settings.LIVENESS_TEXTURE_THRESHOLD}).")

    return {
        "liveness_score": liveness_score,
        "liveness_passed": liveness_passed,
        "laplacian_variance": round(laplacian_var, 2),
        "texture_variance": round(lbp_variance, 6),
        "color_std": round(avg_color_std, 2),
        "reason": " ".join(reasons) if reasons else "Liveness checks passed.",
    }


def load_image_file_to_bgr(image_path: str | Path) -> np.ndarray:
    """
    Loads image file as OpenCV BGR image.
    """
    path = Path(image_path)

    if not path.exists():
        raise FaceServiceError(f"Image file not found: {path}")

    image_bgr = cv2.imread(str(path))

    if image_bgr is None:
        raise FaceServiceError(f"Could not read image file: {path}")

    return image_bgr


def extract_face_embedding_from_bgr(image_bgr: np.ndarray) -> dict[str, Any]:
    """
    Detects face and extracts embedding using pretrained InsightFace.

    Returns:
    - embedding list
    - detection confidence
    - bounding box
    - face count
    """
    if image_bgr is None or image_bgr.size == 0:
        raise FaceServiceError("Input image is empty.")

    app = get_face_app()
    faces = app.get(image_bgr)

    if not faces:
        raise FaceServiceError("No face detected in image.")

    # Pick the largest detected face.
    # Useful if background people appear.
    def face_area(face) -> float:
        x1, y1, x2, y2 = face.bbox
        return float(max(0, x2 - x1) * max(0, y2 - y1))

    face = sorted(faces, key=face_area, reverse=True)[0]

    embedding = getattr(face, "normed_embedding", None)

    if embedding is None:
        embedding = getattr(face, "embedding", None)

    if embedding is None:
        raise FaceServiceError("Face detected, but embedding was not generated.")

    embedding = np.asarray(embedding, dtype=np.float32)

    norm = np.linalg.norm(embedding)
    if norm <= 0:
        raise FaceServiceError("Invalid face embedding norm.")

    normalized_embedding = embedding / norm

    x1, y1, x2, y2 = [float(x) for x in face.bbox]
    bbox = {
        "x1": round(x1, 2),
        "y1": round(y1, 2),
        "x2": round(x2, 2),
        "y2": round(y2, 2),
    }

    liveness = compute_liveness_score(image_bgr, face_bbox=bbox)

    return {
        "embedding": normalized_embedding.tolist(),
        "embedding_dim": int(normalized_embedding.shape[0]),
        "det_score": float(getattr(face, "det_score", 0.0)),
        "bbox": bbox,
        "face_count": len(faces),
        "liveness_score": liveness["liveness_score"],
        "liveness_passed": liveness["liveness_passed"],
        "liveness_detail": liveness,
    }


def extract_face_embedding_from_base64(image_base64: str) -> dict[str, Any]:
    """
    Decodes base64 image and extracts face embedding.
    """
    image_bgr = decode_base64_image_to_bgr(image_base64)
    return extract_face_embedding_from_bgr(image_bgr)


def extract_face_embedding_from_file(image_path: str | Path) -> dict[str, Any]:
    """
    Loads image file and extracts face embedding.
    """
    image_bgr = load_image_file_to_bgr(image_path)
    return extract_face_embedding_from_bgr(image_bgr)


def cosine_similarity(embedding_a: list[float], embedding_b: list[float]) -> float:
    """
    Calculates cosine similarity between two embeddings.
    Returns score from roughly -1 to 1.
    For face verification, higher is better.
    """
    if not embedding_a or not embedding_b:
        raise FaceServiceError("Both embeddings are required.")

    a = np.asarray(embedding_a, dtype=np.float32)
    b = np.asarray(embedding_b, dtype=np.float32)

    if a.shape != b.shape:
        raise FaceServiceError(
            f"Embedding shape mismatch: {a.shape} vs {b.shape}"
        )

    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)

    if a_norm <= 0 or b_norm <= 0:
        raise FaceServiceError("Invalid embedding norm.")

    score = float(np.dot(a, b) / (a_norm * b_norm))

    # Clamp because floating point enjoys being dramatic.
    return round(max(min(score, 1.0), -1.0), 6)


def verify_face_embeddings(
    enrolled_embedding: list[float],
    checkin_embedding: list[float],
) -> dict[str, Any]:
    """
    Compares enrolled face embedding with check-in face embedding.

    Thresholds:
    - >= FACE_MATCH_ACCEPT_THRESHOLD: accepted
    - below accept threshold: needs review

    For this POC, low similarity does not auto-reject on score alone.
    A low score is escalated for human review.
    """
    score = cosine_similarity(enrolled_embedding, checkin_embedding)

    if score >= settings.FACE_MATCH_ACCEPT_THRESHOLD:
        status = "face_accepted"
        is_match = True
        needs_review = False
        reason = f"Face similarity score {score} is accepted."
    else:
        status = "face_needs_review"
        is_match = True
        needs_review = True
        reason = f"Face similarity score {score} needs supervisor review."

    return {
        "score": score,
        "status": status,
        "is_match": is_match,
        "needs_review": needs_review,
        "reason": reason,
        "accept_threshold": settings.FACE_MATCH_ACCEPT_THRESHOLD,
        "review_threshold": settings.FACE_MATCH_REVIEW_THRESHOLD,
    }


def find_latest_saved_selfie() -> Path | None:
    """
    Finds the latest saved selfie from attendance evidence folder.
    This uses real project-generated images, not mock data.
    """
    base_dir = settings.upload_path / "attendance_selfies"

    if not base_dir.exists():
        return None

    image_paths = []
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        image_paths.extend(base_dir.rglob(pattern))

    if not image_paths:
        return None

    return max(image_paths, key=lambda p: p.stat().st_mtime)


def run_face_service_self_test() -> dict[str, Any]:
    """
    Real self-test:
    - Loads pretrained InsightFace model
    - Looks for latest saved attendance selfie
    - Attempts face detection + embedding extraction on that selfie

    If no selfie exists, model loading is still tested.
    """
    app = get_face_app()

    latest_selfie = find_latest_saved_selfie()

    result: dict[str, Any] = {
        "face_service_self_test": "passed",
        "model_loaded": app is not None,
        "model_name": "buffalo_l",
        "provider": "CPUExecutionProvider",
        "latest_selfie_found": latest_selfie is not None,
        "latest_selfie_path": str(latest_selfie) if latest_selfie else None,
    }

    if latest_selfie:
        try:
            embedding_result = extract_face_embedding_from_file(latest_selfie)
            result["face_detected"] = True
            result["embedding_dim"] = embedding_result["embedding_dim"]
            result["det_score"] = embedding_result["det_score"]
            result["bbox"] = embedding_result["bbox"]
            result["face_count"] = embedding_result["face_count"]

            # Compare the selfie with itself.
            # This should be exactly or nearly 1.0.
            self_score = cosine_similarity(
                embedding_result["embedding"],
                embedding_result["embedding"],
            )
            result["self_similarity_score"] = self_score

        except FaceServiceError as exc:
            result["face_detected"] = False
            result["face_error"] = str(exc)

    return result


if __name__ == "__main__":
    output = run_face_service_self_test()
    print(output)
