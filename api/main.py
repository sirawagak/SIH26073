"""
SIH26073 — FastAPI service wrapping the frozen weather-sensor fault detector.

This is a thin transport layer. It does not train, tune, score, or interpret anything:
it validates the request, hands it to the existing
``src.inference.WeatherFaultDetector.predict()``, and returns that method's output
unchanged.

Endpoints
---------
    GET  /health    liveness probe
    POST /predict   score a window of weather observations

Run
---
    uvicorn api.main:app --reload --port 8000     (from the repository root)

Interactive docs are served at /docs once running.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

# --- make the frozen inference module importable -------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
MODEL_DIR = REPO_ROOT / "models"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from inference import WeatherFaultDetector  # noqa: E402  (needs the sys.path line above)

logger = logging.getLogger("sih26073.api")

# Guard rails. Deliberately WIDE: a faulty sensor is exactly what this service exists to
# detect, so a 45 C spike or a 60 hPa pressure offset must pass validation and reach the
# model. These bounds reject only physically impossible values, unit mix-ups and garbage.
LIMITS = {
    "temp_c": (-100.0, 100.0),
    "slp_hpa": (500.0, 1200.0),
    "rh_pct": (-50.0, 200.0),   # module clips to [0, 100]; out-of-range input is a sensor fault, not a client bug
    "dew_c": (-100.0, 100.0),
}
MAX_OBSERVATIONS = 20_000
# Below this many observations no row can be free of edge effects (see docs/INFERENCE_API.md §4).
CONTEXT_ADVISORY_MIN = 15


# --------------------------------------------------------------------------------------
# request models
# --------------------------------------------------------------------------------------
class ObservationIn(BaseModel):
    """One weather observation. Mirrors the contract in docs/INFERENCE_API.md §2."""

    model_config = ConfigDict(extra="forbid")

    time: str | Any = Field(..., description="ISO-8601 timestamp, e.g. 2023-09-24T00:00:00Z")
    temp_c: float | None = Field(None, description="Air temperature, degrees C")
    slp_hpa: float | None = Field(None, description="Sea-level pressure, hPa")
    rh_pct: float | None = Field(None, description="Relative humidity, %")
    dew_c: float | None = Field(None, description="Dew point, degrees C (alternative to rh_pct)")

    @model_validator(mode="after")
    def _check(self):
        if self.temp_c is None:
            raise ValueError("'temp_c' is required")
        if self.slp_hpa is None:
            raise ValueError("'slp_hpa' is required")
        if self.rh_pct is None and self.dew_c is None:
            raise ValueError("supply either 'rh_pct' or 'dew_c' (humidity is derived from dew point)")

        for field, (lo, hi) in LIMITS.items():
            v = getattr(self, field)
            if v is not None and not (lo <= v <= hi):
                raise ValueError(
                    f"'{field}' = {v} is outside the plausible range [{lo}, {hi}]. "
                    "These bounds catch unit errors and corrupt values; genuine sensor "
                    "faults fall well inside them and are meant to reach the model."
                )
        return self


class PredictRequest(BaseModel):
    """Request envelope. Matches examples/sample_input.json."""

    model_config = ConfigDict(extra="forbid")

    observations: list[ObservationIn] = Field(
        ..., min_length=1, max_length=MAX_OBSERVATIONS,
        description="Window of observations, ideally >= 7 days at the native 3-hourly cadence.",
    )
    include_features: bool = Field(
        False, description="Attach the 16 model features to each result (debugging only).",
    )


class HealthResponse(BaseModel):
    status: str


# --------------------------------------------------------------------------------------
# application
# --------------------------------------------------------------------------------------
STATE: dict[str, Any] = {"detector": None, "load_count": 0, "loaded_at": None, "load_seconds": None}


def _configure_logging() -> None:
    """Emit our log lines through uvicorn's handlers, else fall back to basicConfig.

    Without this the service's own INFO records (notably the one-time model load) are
    silently dropped, because uvicorn configures its loggers but not ours.
    """
    if logger.handlers:
        return
    uv = logging.getLogger("uvicorn")
    if uv.handlers:
        logger.handlers = uv.handlers
        logger.setLevel(uv.level or logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s:     %(name)s - %(message)s",
        )
        logger.setLevel(logging.INFO)
    logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the frozen detector exactly once, at startup."""
    _configure_logging()
    t0 = time.perf_counter()
    logger.info("loading frozen detector from %s", MODEL_DIR)
    try:
        STATE["detector"] = WeatherFaultDetector.load(str(MODEL_DIR))
    except Exception:
        logger.exception("detector failed to load; /predict will return 503")
        STATE["detector"] = None
    else:
        STATE["load_count"] += 1
        STATE["load_seconds"] = round(time.perf_counter() - t0, 3)
        STATE["loaded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logger.info(
            "detector loaded in %.3fs (load #%d) | %d features | %d trees",
            STATE["load_seconds"], STATE["load_count"],
            len(STATE["detector"].features), STATE["detector"].model.n_estimators,
        )
    yield
    STATE["detector"] = None
    logger.info("shutdown: detector released")


app = FastAPI(
    title="SIH26073 — Weather Sensor Fault Detection API",
    description=(
        "Thin HTTP wrapper around the frozen Isolation Forest + flat-run hybrid detector. "
        "See docs/API_USAGE.md and docs/INFERENCE_API.md."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# The dashboard is opened straight from disk (file://, which sends Origin: null) or from a
# local static server, so the browser needs CORS headers to reach this API. This adds response
# headers only - the request/response contract is unchanged. Scoped to localhost and file://
# rather than a blanket "*", and this service is meant to be bound to 127.0.0.1 regardless.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|null|file://.*)$",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def get_detector() -> WeatherFaultDetector:
    det = STATE["detector"]
    if det is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "model_unavailable",
                "message": "The detector failed to load at startup, so predictions cannot be served.",
                "hint": f"Check that {MODEL_DIR} contains the five frozen artifacts, then restart. "
                        f"Verify with: python3 src/inference.py",
            },
        )
    return det


# --------------------------------------------------------------------------------------
# error handling
# --------------------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic's output into something a frontend developer can act on."""
    problems = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p != "body"]
        where = ".".join(loc) if loc else "body"
        msg = err.get("msg", "")
        problems.append({
            "field": where,
            "message": msg.removeprefix("Value error, "),
            "type": err.get("type"),
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_failed",
            "message": f"{len(problems)} problem(s) in the request body.",
            "problems": problems,
            "expected_format": {
                "observations": [
                    {"time": "2023-09-24T00:00:00Z", "temp_c": 25.8,
                     "slp_hpa": 1005.1, "rh_pct": 90.36}
                ]
            },
            "docs": "docs/API_USAGE.md",
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if not isinstance(detail, dict):
        detail = {"error": "http_error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(detail))


# --------------------------------------------------------------------------------------
# endpoints
# --------------------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> dict:
    """Liveness probe. Returns 200 with ``{"status": "ok"}``."""
    return {"status": "ok"}


@app.post("/predict", tags=["inference"])
def predict(req: PredictRequest) -> dict:
    """Score a window of weather observations.

    The body is validated, then passed straight to the frozen detector's ``predict()``.
    The response is that method's output, returned unchanged.

    Note that this is a **batch** detector: rows within 21 hours of either end of the
    supplied window come back with ``degraded: true`` because their features are computed
    from a truncated context window. Send about a week of data per call.
    """
    detector = get_detector()

    observations = [o.model_dump(exclude_none=True) for o in req.observations]

    stamps = [o["time"] for o in observations]
    if len(set(stamps)) != len(stamps):
        logger.info("request contained %d duplicate timestamps", len(stamps) - len(set(stamps)))

    t0 = time.perf_counter()
    try:
        payload = detector.predict(observations, include_features=req.include_features)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "bad_observations", "message": str(exc),
                    "hint": "Check that every observation has a parseable 'time'."},
        ) from exc
    except Exception as exc:
        logger.exception("inference failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "inference_failed", "message": f"{type(exc).__name__}: {exc}"},
        ) from exc

    elapsed = time.perf_counter() - t0
    logger.info("scored %d observations in %.3fs -> %d anomalies",
                len(observations), elapsed, payload["summary"]["n_anomalies"])

    if len(observations) < CONTEXT_ADVISORY_MIN:
        payload["summary"].setdefault("warnings", []).append(
            f"Only {len(observations)} observations supplied. The centred 24h window and the "
            f"flat-run rule need ~21h of context on each side, so every row in this response is "
            f"likely 'degraded'. Send about 7 days of data for full-fidelity results."
        )

    return payload


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False)
