from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
    connect_args={
        "sslmode": "require",
        "connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
    },
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency for database sessions.
    Every API route that needs DB access will use this.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_database_connection() -> dict:
    """
    Real Neon DB test.
    Runs actual SQL queries against the configured database.
    """
    with engine.connect() as connection:
        db_name = connection.execute(text("SELECT current_database();")).scalar()
        db_user = connection.execute(text("SELECT current_user;")).scalar()
        pg_version = connection.execute(text("SELECT version();")).scalar()

        postgis_result = connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_extension
                    WHERE extname = 'postgis'
                );
                """
            )
        ).scalar()

        return {
            "database_connected": True,
            "database": db_name,
            "user": db_user,
            "postgres_version": pg_version,
            "postgis_enabled": bool(postgis_result),
        }


if __name__ == "__main__":
    result = test_database_connection()
    print(result)
