from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.database_models import Student, User, UserRole
from app.schemas.api_schemas import AdminCreateAccountRequest, StudentSignupRequest
from app.services.auth_service import (
    get_user_by_email,
    get_user_by_mobile,
    get_user_by_username,
    hash_password,
    validate_role,
)
from app.services.crud_service import get_student_by_code
from app.services.faculty_service import get_profile_for_user
from app.services.face_service import FaceServiceError, extract_face_embedding_from_base64
from app.services.selfie_storage_service import save_profile_selfie


def _validate_user_uniqueness(db: Session, *, username: str, email: str | None, mobile: str | None) -> None:
    if get_user_by_username(db, username):
        raise ValueError(f"Username already exists: {username}")
    if email and get_user_by_email(db, email):
        raise ValueError(f"Email already exists: {email}")
    if mobile and get_user_by_mobile(db, mobile):
        raise ValueError(f"Mobile already exists: {mobile}")


def _validate_student_uniqueness(db: Session, *, student_code: str) -> None:
    if get_student_by_code(db, student_code):
        raise ValueError(f"Student already exists with code: {student_code}")


def _enroll_student_face(student: Student, *, selfie_image_base64: str, enrolled_by_user_id: int | None) -> dict:
    try:
        embedding_result = extract_face_embedding_from_base64(selfie_image_base64)
    except FaceServiceError as exc:
        raise ValueError(str(exc)) from exc

    if embedding_result["face_count"] != 1:
        raise ValueError(
            "Face enrollment requires exactly one clear face. "
            f"Detected faces: {embedding_result['face_count']}."
        )

    if embedding_result["det_score"] < 0.70:
        raise ValueError(
            "Face detection confidence is too low for registration. "
            f"Current score: {embedding_result['det_score']}."
        )

    profile_selfie = save_profile_selfie(
        student_code=student.student_code,
        selfie_image_base64=selfie_image_base64,
    )

    student.face_embedding = {
        "model": "insightface_buffalo_l",
        "embedding": embedding_result["embedding"],
        "embedding_dim": embedding_result["embedding_dim"],
        "det_score": embedding_result["det_score"],
        "bbox": embedding_result["bbox"],
        "face_count": embedding_result["face_count"],
        "enrolled_by_user_id": enrolled_by_user_id,
        "profile_photo": profile_selfie,
    }
    student.face_enrolled = True
    return {
        "embedding_dim": embedding_result["embedding_dim"],
        "det_score": embedding_result["det_score"],
        "bbox": embedding_result["bbox"],
        "face_count": embedding_result["face_count"],
        "profile_photo": profile_selfie,
    }


def create_profile_signup_account(db: Session, payload: StudentSignupRequest) -> tuple[User, Student, dict]:
    role = validate_role(payload.role or UserRole.STUDENT.value)
    if role != UserRole.STUDENT.value:
        raise ValueError("Faculty accounts must be created by admin. Public self-signup is allowed only for students.")

    if payload.consent_status is not True:
        raise ValueError("Profile signup requires consent_status=true for initial face enrollment.")

    _validate_student_uniqueness(db, student_code=payload.student_code)
    _validate_user_uniqueness(
        db,
        username=payload.student_code,
        email=str(payload.email) if payload.email else None,
        mobile=payload.mobile,
    )

    student = Student(
        student_code=payload.student_code,
        full_name=payload.full_name,
        iti_name=payload.iti_name,
        trade=payload.trade,
        batch=payload.batch,
        mobile=payload.mobile,
        email=str(payload.email) if payload.email else None,
        consent_status=payload.consent_status,
        is_active=True,
    )
    db.add(student)
    db.flush()

    user = User(
        full_name=payload.full_name,
        username=payload.student_code,
        hashed_password=hash_password(payload.password),
        role=role,
        email=str(payload.email) if payload.email else None,
        mobile=payload.mobile,
        is_active=True,
    )
    db.add(user)
    db.flush()

    enrollment = _enroll_student_face(student, selfie_image_base64=payload.selfie_image_base64, enrolled_by_user_id=user.id)
    db.commit()
    db.refresh(student)
    db.refresh(user)
    return user, student, enrollment


def create_student_signup_account(db: Session, payload: StudentSignupRequest) -> tuple[User, Student, dict]:
    payload.role = UserRole.STUDENT.value
    return create_profile_signup_account(db, payload)


def admin_create_account(db: Session, payload: AdminCreateAccountRequest) -> tuple[User, Student | None, dict | None]:
    role = validate_role(payload.role)
    username = payload.username.strip() if payload.username else (payload.student_code or "").strip()

    if not username:
        raise ValueError("username is required. For student accounts, student_code can be used as username.")

    _validate_user_uniqueness(
        db,
        username=username,
        email=str(payload.email) if payload.email else None,
        mobile=payload.mobile,
    )

    student = None
    enrollment = None
    if role in {UserRole.STUDENT.value, UserRole.FACULTY.value}:
        if not all([payload.student_code, payload.iti_name, payload.trade, payload.batch, payload.selfie_image_base64]):
            raise ValueError("Profile-linked account creation requires student_code, iti_name, trade, batch, and selfie_image_base64.")
        if username != payload.student_code:
            raise ValueError("For profile-linked accounts, username must match student_code.")
        if payload.consent_status is not True:
            raise ValueError("Profile-linked account creation with initial face enrollment requires consent_status=true.")

        _validate_student_uniqueness(db, student_code=payload.student_code)
        student = Student(
            student_code=payload.student_code,
            full_name=payload.full_name,
            iti_name=payload.iti_name,
            trade=payload.trade,
            batch=payload.batch,
            mobile=payload.mobile,
            email=str(payload.email) if payload.email else None,
            consent_status=payload.consent_status,
            is_active=True,
        )
        db.add(student)
        db.flush()

    user = User(
        full_name=payload.full_name,
        username=username,
        hashed_password=hash_password(payload.password),
        role=role,
        email=str(payload.email) if payload.email else None,
        mobile=payload.mobile,
        is_active=True,
    )
    db.add(user)
    db.flush()

    if student and payload.selfie_image_base64:
        enrollment = _enroll_student_face(student, selfie_image_base64=payload.selfie_image_base64, enrolled_by_user_id=user.id)

    db.commit()
    db.refresh(user)
    if student:
        db.refresh(student)
    return user, student, enrollment


def get_student_for_user(db: Session, user: User) -> Student | None:
    return get_profile_for_user(db, user)
