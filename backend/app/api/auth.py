from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.limiter import limiter

from app.api.dependencies import get_current_user, require_admin
from app.db.database import get_db
from app.models.database_models import Industry, User
from app.schemas.api_schemas import (
    AdminCreateAccountRequest,
    StudentSignupRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_password_reset_token,
    consume_password_reset_token,
    create_user,
    decode_access_token,
    get_user_by_username,
)
from app.services.faculty_service import profile_type_for_student
from app.services.onboarding_service import (
    admin_create_account,
    create_profile_signup_account,
    create_student_signup_account,
    get_student_for_user,
)
from app.services.crud_service import get_active_roster_for_student


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)

security = HTTPBearer()


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username,
        "role": user.role,
        "email": user.email,
        "mobile": user.mobile,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _serialize_linked_profile(db: Session, student) -> dict:
    profile_photo = (student.face_embedding or {}).get("profile_photo") or {}
    profile_type = profile_type_for_student(db, student)
    return {
        "id": student.id,
        "student_code": student.student_code,
        "profile_code": student.student_code,
        "full_name": student.full_name,
        "iti_name": student.iti_name,
        "trade": student.trade,
        "designation": student.trade,
        "batch": student.batch,
        "department": student.batch,
        "mobile": student.mobile,
        "email": student.email,
        "consent_status": student.consent_status,
        "face_enrolled": student.face_enrolled,
        "profile_type": profile_type,
        "profile_photo_available": bool(profile_photo.get("saved")),
        "profile_photo_relative_path": profile_photo.get("relative_path"),
    }


def _serialize_assigned_location(student, db: Session) -> dict | None:
    roster = get_active_roster_for_student(db, student.id)
    if not roster:
        return None

    location = db.get(Industry, roster.industry_id)
    if not location:
        return None

    return {
        "roster": {
            "id": roster.id,
            "start_date": roster.start_date.isoformat() if roster.start_date else None,
            "end_date": roster.end_date.isoformat() if roster.end_date else None,
            "shift_start_time": roster.shift_start_time,
            "shift_end_time": roster.shift_end_time,
            "is_active": roster.is_active,
        },
        "location": {
            "id": location.id,
            "industry_code": location.industry_code,
            "name": location.name,
            "address": location.address,
            "district": location.district,
            "city": location.city,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "geofence_radius_meters": location.geofence_radius_meters,
        },
    }


@router.post("/register", response_model=UserResponse)
@limiter.limit("5/minute")
def register_user(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    try:
        return create_user(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/student-signup")
@limiter.limit("5/minute")
def student_signup(request: Request, payload: StudentSignupRequest, db: Session = Depends(get_db)):
    try:
        user, student, enrollment = create_student_signup_account(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = create_access_token(user=user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _serialize_user(user),
        "student_profile": {
            **_serialize_linked_profile(db, student),
        },
        "face_enrollment": enrollment,
    }


@router.post("/profile-signup")
def profile_signup(payload: StudentSignupRequest, db: Session = Depends(get_db)):
    try:
        user, student, enrollment = create_profile_signup_account(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = create_access_token(user=user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _serialize_user(user),
        "student_profile": _serialize_linked_profile(db, student),
        "face_enrollment": enrollment,
    }


@router.post("/admin-create-account")
def create_account_by_admin(
    payload: AdminCreateAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        user, student, enrollment = admin_create_account(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "created_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
        "user": _serialize_user(user),
        "student_profile": (
            _serialize_linked_profile(db, student)
            if student
            else None
        ),
        "face_enrollment": enrollment,
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login_user(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(
        db,
        username=payload.username,
        password=payload.password,
    )

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user=user)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
    }


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    return user


@router.get("/my-profile")
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = get_student_for_user(db, current_user)
    if not student:
        raise HTTPException(status_code=404, detail="No attendance profile is linked to this account.")

    return {
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
            "full_name": current_user.full_name,
        },
        "student": _serialize_linked_profile(db, student),
        "profile": _serialize_linked_profile(db, student),
        "assigned_location": _serialize_assigned_location(student, db),
    }


@router.get("/my-student-profile")
def get_my_student_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_my_profile(current_user=current_user, db=db)


@router.get("/my-profile/photo")
def get_my_profile_photo(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = get_student_for_user(db, current_user)
    if not student:
        raise HTTPException(status_code=404, detail="No attendance profile is linked to this account.")

    profile_photo = (student.face_embedding or {}).get("profile_photo") or {}
    if profile_photo.get("saved") is not True or not profile_photo.get("absolute_path"):
        raise HTTPException(status_code=404, detail="No profile photo found for this profile.")

    return FileResponse(
        path=profile_photo["absolute_path"],
        media_type=profile_photo.get("mime_type") or "image/jpeg",
        filename=profile_photo["absolute_path"].split("\\")[-1].split("/")[-1],
    )


class _PasswordResetRequest(BaseModel):
    username: str


class _PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


@router.post("/request-password-reset")
@limiter.limit("3/minute")
def request_password_reset(
    request: Request,
    payload: _PasswordResetRequest,
    db: Session = Depends(get_db),
):
    """
    Generates a password reset token for the given username.

    The token is returned directly in the response for self-hosted / admin-assisted reset.
    In production, wire this to the email notification service to send the token
    to the user's registered email instead of returning it in the response.
    """
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required.")

    token = create_password_reset_token(db, username=username)
    if not token:
        # Return the same message whether user exists or not to prevent enumeration.
        return {"message": "If that username exists, a reset token has been generated."}

    return {
        "message": "Password reset token generated.",
        "reset_token": token.token,
        "expires_at": token.expires_at.isoformat(),
        "note": "In production this token is sent via email. Store it securely.",
    }


@router.post("/reset-password")
def reset_password(
    payload: _PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    """
    Resets the user's password using a valid reset token.

    Body: {"token": "<reset_token>", "new_password": "<min 6 chars>"}
    """
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="new_password must be at least 6 characters.")

    token_value = payload.token
    new_password = payload.new_password

    try:
        user = consume_password_reset_token(db, token_value=token_value, new_password=new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Password has been reset successfully.",
        "username": user.username,
    }


@router.get("/my-student-profile/photo")
def get_my_student_profile_photo(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_my_profile_photo(current_user=current_user, db=db)


if __name__ == "__main__":
    from app.services.auth_service import run_auth_self_test

    result = run_auth_self_test()
    print("Auth API module self-test passed.")
    print(result)
