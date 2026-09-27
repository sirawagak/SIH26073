"""SkyGuard AI application backend.

  React  ->  FastAPI (this app)  ->  SuperTokens (authN)
                                 ->  PostgreSQL (application data)
                                 ->  MLService  ->  frozen WeatherFaultDetector

The ML pipeline in ``src/inference.py`` and ``models/`` is imported unchanged.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from supertokens_python import get_all_cors_headers
from supertokens_python.framework.fastapi import get_middleware

from app.api.v1 import admin as admin_router
from app.api.v1 import me as me_router
from app.api.v1 import predict as predict_router
from app.auth.supertokens_init import init_supertokens
from app.core.config import get_settings
from app.db.repository import ensure_roles
from app.db.session import SessionLocal
from app.ml.local_detector import LocalDetectorService

logger = logging.getLogger("skyguard.api")
settings = get_settings()

init_supertokens()


def _configure_logging() -> None:
    if logger.handlers:
        return
    uv = logging.getLogger("uvicorn")
    if uv.handlers:
        logger.handlers = uv.handlers
        logger.setLevel(uv.level or logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO,
                            format="%(levelname)s:     %(name)s - %(message)s")
        logger.setLevel(logging.INFO)
    logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    # 1. seed roles (idempotent)
    db = SessionLocal()
    try:
        ensure_roles(db)
        logger.info("roles seeded")
    except Exception:
        logger.exception("role seeding failed - is PostgreSQL running and migrated?")
    finally:
        db.close()

    # 2. load the frozen detector once
    t0 = time.perf_counter()
    try:
        app.state.ml = LocalDetectorService()
        logger.info("detector loaded in %.3fs | model_version %s | %d features",
                    time.perf_counter() - t0, app.state.ml.model_version,
                    len(app.state.ml.detector.features))
    except Exception:
        app.state.ml = None
        logger.exception("detector failed to load; /api/v1/predict will return 503")
    yield
    app.state.ml = None


app = FastAPI(
    title="SkyGuard AI",
    description="Weather-sensor anomaly detection with human-in-the-loop verification.",
    version="0.1.0-slice1",
    lifespan=lifespan,
)

# SuperTokens middleware must come before CORS matters; allow_credentials is
# required for cookie sessions, and the origin must be explicit (never "*").
app.add_middleware(get_middleware())
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.website_domain],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", *get_all_cors_headers()],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    problems = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p != "body"]
        problems.append({"field": ".".join(loc) or "body",
                         "message": err.get("msg", "").removeprefix("Value error, "),
                         "type": err.get("type")})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "validation_failed",
                 "message": f"{len(problems)} problem(s) in the request body.",
                 "problems": problems})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Unwrap structured detail dicts so clients get a flat, consistent error shape."""
    detail = exc.detail
    if not isinstance(detail, dict):
        detail = {"error": "http_error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(detail))


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/health", tags=["ops"])
async def health_detail(request: Request) -> dict:
    ml = getattr(request.app.state, "ml", None)
    db_ok = True
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("select 1"))
        db.close()
    except Exception:
        db_ok = False
    return {"status": "ok",
            "database": "up" if db_ok else "down",
            "model": ml.model_version if ml else None,
            "environment": settings.environment}


app.include_router(me_router.router, prefix="/api/v1")
app.include_router(predict_router.router, prefix="/api/v1")
app.include_router(admin_router.router, prefix="/api/v1")
