import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.database_models import PasswordResetToken, User, UserRole
from app.schemas.api_schemas import UserCreate


pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)

def hash_password(password: str) -> str:
    """
    Hashes plain text password before storing in DB.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies login password against hashed password.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_user_by_username(db: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_email(db: Session, email: str | None) -> User | None:
    if not email:
        return None

    stmt = select(User).where(User.email == email)
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_mobile(db: Session, mobile: str | None) -> User | None:
    if not mobile:
        return None

    stmt = select(User).where(User.mobile == mobile)
    return db.execute(stmt).scalar_one_or_none()


def validate_role(role: str) -> str:
    """
    Ensures role is one of the supported roles.
    """
    role = role.strip().lower()

    allowed_roles = {item.value for item in UserRole}

    if role not in allowed_roles:
        raise ValueError(f"Invalid role. Allowed roles: {sorted(allowed_roles)}")

    return role


def create_user(db: Session, payload: UserCreate) -> User:
    """
    Creates a new user with hashed password.
    """
    existing_username = get_user_by_username(db, payload.username)
    if existing_username:
        raise ValueError(f"Username already exists: {payload.username}")

    existing_email = get_user_by_email(db, payload.email)
    if existing_email:
        raise ValueError(f"Email already exists: {payload.email}")

    existing_mobile = get_user_by_mobile(db, payload.mobile)
    if existing_mobile:
        raise ValueError(f"Mobile already exists: {payload.mobile}")

    role = validate_role(payload.role)

    user = User(
        full_name=payload.full_name,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=role,
        email=str(payload.email) if payload.email else None,
        mobile=payload.mobile,
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """
    Validates username + password.
    Returns user if valid, else None.
    """
    user = get_user_by_username(db, username)

    if not user:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


def create_access_token(
    *,
    user: User,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Creates JWT access token.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return token


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodes JWT token and returns payload.
    Raises ValueError for invalid token.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload

    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def create_password_reset_token(db: Session, *, username: str) -> PasswordResetToken | None:
    """
    Generates a secure reset token for the given username.
    Invalidates any previous unused tokens for the same user.
    Returns None when the user is not found.
    """
    user = get_user_by_username(db, username)
    if not user:
        return None

    # Invalidate old tokens
    old_tokens = db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id)
        .where(PasswordResetToken.used.is_(False))
    ).scalars().all()
    for t in old_tokens:
        t.used = True

    token_value = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )
    token = PasswordResetToken(
        user_id=user.id,
        token=token_value,
        expires_at=expires_at,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def consume_password_reset_token(
    db: Session,
    *,
    token_value: str,
    new_password: str,
) -> User:
    """
    Validates the token, updates the password, marks token as used.
    Raises ValueError on invalid / expired / already-used token.
    """
    record = db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token_value)
    ).scalar_one_or_none()

    if not record:
        raise ValueError("Invalid password reset token.")
    if record.used:
        raise ValueError("This reset token has already been used.")
    if datetime.now(timezone.utc) > record.expires_at:
        raise ValueError("Password reset token has expired.")

    user = db.get(User, record.user_id)
    if not user:
        raise ValueError("User associated with this token no longer exists.")

    user.hashed_password = hash_password(new_password)
    record.used = True
    db.commit()
    db.refresh(user)
    return user


def run_auth_self_test() -> dict[str, Any]:
    """
    Real Neon DB self-test.

    Creates or reuses a demo admin user:
    username: admin
    password: admin123

    Then:
    - verifies password
    - generates JWT token
    - decodes JWT token
    """
    db = SessionLocal()

    try:
        demo_payload = UserCreate(
            full_name="Demo Admin",
            username="admin",
            password="admin123",
            role=UserRole.ADMIN.value,
            email="admin@example.com",
            mobile="9999999999",
        )

        user = get_user_by_username(db, demo_payload.username)
        created_now = False

        if not user:
            user = create_user(db, demo_payload)
            created_now = True

        authenticated = authenticate_user(
            db,
            username="admin",
            password="admin123",
        )

        if not authenticated:
            raise RuntimeError("Authentication failed for demo admin user.")

        token = create_access_token(user=authenticated)
        decoded = decode_access_token(token)

        return {
            "auth_self_test": "passed",
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "created_now": created_now,
            },
            "password_verified": True,
            "jwt_created": bool(token),
            "jwt_decoded": {
                "sub": decoded.get("sub"),
                "user_id": decoded.get("user_id"),
                "role": decoded.get("role"),
            },
        }

    finally:
        db.close()


if __name__ == "__main__":
    result = run_auth_self_test()
    print(result)