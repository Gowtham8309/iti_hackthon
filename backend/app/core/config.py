from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI-Powered ITI In-Plant Training Attendance System"
    APP_ENV: str = "development"
    APP_VERSION: str = "1.0.0"

    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 300
    DB_CONNECT_TIMEOUT_SECONDS: int = 10

    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # CORS
    CORS_ORIGINS: str = "*"

    # Attendance settings
    DEFAULT_GEOFENCE_RADIUS_METERS: int = 100
    MAX_ALLOWED_GPS_ACCURACY_METERS: int = 50

    # Face verification thresholds
    FACE_MATCH_ACCEPT_THRESHOLD: float = 0.75
    FACE_MATCH_REVIEW_THRESHOLD: float = 0.60

    # Upload settings
    MAX_FACE_IMAGE_SIZE_MB: int = 5
    UPLOAD_DIR: str = "storage/uploads"

    # Notifications
    SMS_NOTIFICATIONS_ENABLED: bool = False
    EMAIL_NOTIFICATIONS_ENABLED: bool = False
    DEFAULT_NOTIFICATION_EMAILS: str = ""
    DEFAULT_NOTIFICATION_MOBILES: str = ""
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    # Integration preview / export configuration
    ITI_PORTAL_BASE_URL: str = "https://iti.ap.gov.in"
    ITI_PORTAL_API_KEY: str | None = None
    ITI_PORTAL_SYNC_ENABLED: bool = False
    INDUSTRY_HR_SYNC_ENABLED: bool = False
    DISTRICT_DASHBOARD_SYNC_ENABLED: bool = False
    DISTRICT_DASHBOARD_WEBHOOK_URL: str | None = None

    # SMS notifications
    SMS_PROVIDER: str = "fast2sms"
    FAST2SMS_API_KEY: str | None = None
    SMS_SENDER_ID: str = "ITIATT"

    # Rate limiting
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_SIGNUP: str = "5/minute"

    # Password reset
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # Liveness detection
    LIVENESS_LAPLACIAN_THRESHOLD: float = 80.0
    LIVENESS_TEXTURE_THRESHOLD: float = 0.003

    # ML anomaly model
    ML_ANOMALY_MODEL_PATH: str = "storage/models/anomaly_model.joblib"
    ML_ANOMALY_RETRAIN_AFTER_EVENTS: int = 100

    # Compliance / retention
    ENCRYPT_BIOMETRICS_AT_REST: bool = True
    SELFIE_RETENTION_POLICY: str = "keep_until_manual_delete"
    ATTENDANCE_LOG_RETENTION_POLICY: str = "keep_permanently"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def upload_path(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def default_notification_emails_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.DEFAULT_NOTIFICATION_EMAILS.split(",")
            if item.strip()
        ]

    @property
    def default_notification_mobiles_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.DEFAULT_NOTIFICATION_MOBILES.split(",")
            if item.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
