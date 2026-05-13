from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.limiter import limiter

from app.api.anomalies import router as anomalies_router
from app.api.attendance import router as attendance_router
from app.api.auth import router as auth_router
from app.api.classroom import router as classroom_router
from app.api.dashboard import router as dashboard_router
from app.api.face import router as face_router
from app.api.master_data import router as master_data_router
from app.api.ops import router as ops_router
from app.core.config import settings
from app.models.database_models import create_all_tables


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered attendance, discipline monitoring, classroom quality, and anomaly intelligence for ITIs.",
    version=settings.APP_VERSION,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # FastAPI's default handler crashes when the error body contains raw binary
    # (e.g. JPEG bytes from a multipart upload). Strip non-serialisable values first.
    clean_errors = []
    for err in exc.errors():
        clean = {k: v for k, v in err.items() if k != "input"}
        inp = err.get("input")
        if inp is not None:
            clean["input"] = repr(inp)[:120] if isinstance(inp, bytes) else inp
        clean_errors.append(clean)
    return JSONResponse(status_code=422, content={"detail": clean_errors})
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth_router)
app.include_router(master_data_router)
app.include_router(attendance_router)
app.include_router(anomalies_router)
app.include_router(classroom_router)
app.include_router(dashboard_router)
app.include_router(face_router)
app.include_router(ops_router)


@app.on_event("startup")
def bootstrap_schema():
    create_all_tables()


@app.get("/")
def root():
    return {
        "message": f"{settings.APP_NAME} API is running",
        "environment": settings.APP_ENV,
        "version": settings.APP_VERSION,
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "iti-attendance-ai-backend",
        "environment": settings.APP_ENV,
    }
