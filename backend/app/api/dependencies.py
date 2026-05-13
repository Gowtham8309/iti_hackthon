from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_db
from app.models.database_models import User, UserRole
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    get_user_by_username,
)


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Reads Bearer token, validates JWT, and returns current active user.
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    username = payload.get("sub")

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user = get_user_by_username(db, username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    return user


def require_roles(*allowed_roles: str) -> Callable:
    """
    Role-based dependency.

    Usage:
        current_user: User = Depends(require_roles("admin"))
        current_user: User = Depends(require_roles("admin", "iti_coordinator"))
    """
    normalized_roles = {role.strip().lower() for role in allowed_roles if role.strip()}

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Required role(s): {sorted(normalized_roles)}. "
                    f"Current role: {current_user.role}"
                ),
            )

        return current_user

    return role_checker


def require_admin(current_user: User = Depends(require_roles(UserRole.ADMIN.value))) -> User:
    """
    Shortcut dependency for admin-only APIs.
    """
    return current_user


def require_supervisor_or_above(
    current_user: User = Depends(
        require_roles(
            UserRole.SUPERVISOR.value,
            UserRole.HR.value,
            UserRole.ITI_COORDINATOR.value,
            UserRole.DISTRICT_OFFICER.value,
            UserRole.ADMIN.value,
        )
    )
) -> User:
    """
    Allows operational/admin users to access review and dashboard APIs.
    """
    return current_user


def require_attendance_user(
    current_user: User = Depends(
        require_roles(
            UserRole.FACULTY.value,
            UserRole.STUDENT.value,
            UserRole.SUPERVISOR.value,
            UserRole.HR.value,
            UserRole.ITI_COORDINATOR.value,
            UserRole.ADMIN.value,
        )
    )
) -> User:
    """
    Allows student or authorized staff to use attendance-related APIs.
    """
    return current_user


def run_dependency_self_test() -> dict[str, Any]:
    """
    Real DB self-test:
    - Logs in existing demo admin
    - Creates JWT
    - Decodes JWT
    - Loads user from Neon
    - Verifies admin role
    """
    db = SessionLocal()

    try:
        user = authenticate_user(
            db,
            username="admin",
            password="admin123",
        )

        if not user:
            raise RuntimeError("Demo admin login failed. Run auth_service self-test first.")

        token = create_access_token(user=user)
        payload = decode_access_token(token)

        username = payload.get("sub")
        loaded_user = get_user_by_username(db, username)

        if not loaded_user:
            raise RuntimeError("User from token not found in DB.")

        if loaded_user.role != UserRole.ADMIN.value:
            raise RuntimeError(f"Expected admin role, got: {loaded_user.role}")

        return {
            "dependency_self_test": "passed",
            "token_valid": True,
            "loaded_user": {
                "id": loaded_user.id,
                "username": loaded_user.username,
                "role": loaded_user.role,
                "is_active": loaded_user.is_active,
            },
            "role_check": "admin role verified",
        }

    finally:
        db.close()


if __name__ == "__main__":
    result = run_dependency_self_test()
    print(result)
