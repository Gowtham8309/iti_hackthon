from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin, require_attendance_user
from app.db.database import get_db
from app.models.database_models import User
from app.services.crud_service import get_student_by_id
from app.services.face_service import (
    FaceServiceError,
    extract_face_embedding_from_base64,
    verify_face_embeddings,
)


router = APIRouter(
    prefix="/api/v1/face",
    tags=["Face Recognition"],
)


class FaceEnrollRequest(BaseModel):
    student_id: int = Field(..., description="Student database ID")
    selfie_image_base64: str = Field(
        ...,
        description="Browser captured selfie as base64 image",
    )


class FaceEnrollResponse(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    face_enrolled: bool
    embedding_dim: int
    det_score: float
    face_count: int
    bbox: dict[str, Any]
    message: str


class FaceVerifyRequest(BaseModel):
    student_id: int = Field(..., description="Student database ID")
    selfie_image_base64: str = Field(
        ...,
        description="Check-in selfie as base64 image",
    )


class FaceVerifyResponse(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    face_enrolled: bool
    face_match_score: float
    status: str
    is_match: bool
    needs_review: bool
    reason: str
    checkin_det_score: float
    checkin_face_count: int
    checkin_bbox: dict[str, Any]


@router.post("/enroll", response_model=FaceEnrollResponse)
def enroll_student_face(
    payload: FaceEnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Enroll student face.

    Admin-only for POC:
    - Detects face from selfie
    - Requires exactly one clear face
    - Extracts 512-dimensional InsightFace embedding
    - Stores embedding in students.face_embedding
    - Marks face_enrolled = true
    """
    student = get_student_by_id(db, payload.student_id)

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if not student.consent_status:
        raise HTTPException(
            status_code=400,
            detail="Student consent_status is false. Face enrollment requires consent.",
        )

    try:
        embedding_result = extract_face_embedding_from_base64(
            payload.selfie_image_base64
        )
    except FaceServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if embedding_result["face_count"] != 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "Face enrollment requires exactly one clear face. "
                f"Detected faces: {embedding_result['face_count']}. "
                "Please retake the photo without background people."
            ),
        )

    if embedding_result["det_score"] < 0.70:
        raise HTTPException(
            status_code=400,
            detail=(
                "Face detection confidence is too low: "
                f"{embedding_result['det_score']}. "
                "Please retake the photo with better lighting and centered face."
            ),
        )

    student.face_embedding = {
        "model": "insightface_buffalo_l",
        "embedding": embedding_result["embedding"],
        "embedding_dim": embedding_result["embedding_dim"],
        "det_score": embedding_result["det_score"],
        "bbox": embedding_result["bbox"],
        "face_count": embedding_result["face_count"],
        "enrolled_by_user_id": current_user.id,
    }

    student.face_enrolled = True

    db.commit()
    db.refresh(student)

    return {
        "student_id": student.id,
        "student_code": student.student_code,
        "full_name": student.full_name,
        "face_enrolled": student.face_enrolled,
        "embedding_dim": embedding_result["embedding_dim"],
        "det_score": embedding_result["det_score"],
        "face_count": embedding_result["face_count"],
        "bbox": embedding_result["bbox"],
        "message": "Face enrolled successfully using InsightFace buffalo_l pretrained model.",
    }


@router.post("/verify", response_model=FaceVerifyResponse)
def verify_student_face(
    payload: FaceVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_attendance_user),
):
    """
    Verify student face against stored enrolled embedding.

    This does not mark attendance.
    It only tests face matching:
    - extracts check-in selfie embedding
    - compares it with enrolled embedding
    - returns cosine similarity score
    """
    student = get_student_by_id(db, payload.student_id)

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if not student.face_enrolled or not student.face_embedding:
        raise HTTPException(
            status_code=400,
            detail="Student face is not enrolled yet.",
        )

    enrolled_embedding = student.face_embedding.get("embedding")

    if not enrolled_embedding:
        raise HTTPException(
            status_code=400,
            detail="Stored face embedding is missing or invalid.",
        )

    try:
        checkin_embedding_result = extract_face_embedding_from_base64(
            payload.selfie_image_base64
        )

        verification = verify_face_embeddings(
            enrolled_embedding=enrolled_embedding,
            checkin_embedding=checkin_embedding_result["embedding"],
        )

    except FaceServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if checkin_embedding_result["face_count"] != 1:
        return {
            "student_id": student.id,
            "student_code": student.student_code,
            "full_name": student.full_name,
            "face_enrolled": student.face_enrolled,
            "face_match_score": verification["score"],
            "status": "multiple_faces_detected",
            "is_match": False,
            "needs_review": True,
            "reason": (
                "Multiple faces detected during verification: "
                f"{checkin_embedding_result['face_count']} faces. "
                "Verification requires exactly one clear student face."
            ),
            "checkin_det_score": checkin_embedding_result["det_score"],
            "checkin_face_count": checkin_embedding_result["face_count"],
            "checkin_bbox": checkin_embedding_result["bbox"],
        }

    return {
        "student_id": student.id,
        "student_code": student.student_code,
        "full_name": student.full_name,
        "face_enrolled": student.face_enrolled,
        "face_match_score": verification["score"],
        "status": verification["status"],
        "is_match": verification["is_match"],
        "needs_review": verification["needs_review"],
        "reason": verification["reason"],
        "checkin_det_score": checkin_embedding_result["det_score"],
        "checkin_face_count": checkin_embedding_result["face_count"],
        "checkin_bbox": checkin_embedding_result["bbox"],
    }


@router.post("/re-enroll", response_model=FaceEnrollResponse)
def re_enroll_student_face(
    payload: FaceEnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Re-enroll (overwrite) a student's face embedding.

    Admin-only. Used when the existing enrollment is outdated
    (e.g., student's appearance changed significantly).
    All fields are replaced; the enrolled_by_user_id is updated to the current admin.
    """
    student = get_student_by_id(db, payload.student_id)

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if not student.consent_status:
        raise HTTPException(
            status_code=400,
            detail="Student consent_status is false. Face re-enrollment requires consent.",
        )

    try:
        embedding_result = extract_face_embedding_from_base64(payload.selfie_image_base64)
    except FaceServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if embedding_result["face_count"] != 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Re-enrollment requires exactly one clear face. "
                f"Detected: {embedding_result['face_count']}."
            ),
        )

    if embedding_result["det_score"] < 0.70:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Face detection confidence too low: {embedding_result['det_score']}. "
                "Retake with better lighting."
            ),
        )

    existing_embedding = student.face_embedding or {}
    student.face_embedding = {
        **existing_embedding,
        "model": "insightface_buffalo_l",
        "embedding": embedding_result["embedding"],
        "embedding_dim": embedding_result["embedding_dim"],
        "det_score": embedding_result["det_score"],
        "bbox": embedding_result["bbox"],
        "face_count": embedding_result["face_count"],
        "enrolled_by_user_id": current_user.id,
        "re_enrolled": True,
    }
    student.face_enrolled = True

    db.commit()
    db.refresh(student)

    return {
        "student_id": student.id,
        "student_code": student.student_code,
        "full_name": student.full_name,
        "face_enrolled": student.face_enrolled,
        "embedding_dim": embedding_result["embedding_dim"],
        "det_score": embedding_result["det_score"],
        "face_count": embedding_result["face_count"],
        "bbox": embedding_result["bbox"],
        "message": "Face re-enrolled successfully. Previous embedding has been replaced.",
    }


@router.get("/self-test")
def face_api_self_test(
    current_user: User = Depends(require_attendance_user),
):
    """
    Confirms face API router is active.
    """
    return {
        "status": "passed",
        "message": "Face Recognition API is active.",
        "model": "InsightFace buffalo_l",
        "provider": "CPUExecutionProvider",
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }