"""Authenticated inference.

Identical contract to the legacy ``api/main.py`` ``/predict``; the only
differences are that a session is required and the response carries
``model_version``. No inference logic lives here.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.deps import require_permission
from app.db.models import User
from app.rbac.roles import Permission

router = APIRouter(tags=["inference"])

LIMITS = {"temp_c": (-100.0, 100.0), "slp_hpa": (500.0, 1200.0),
          "rh_pct": (-50.0, 200.0), "dew_c": (-100.0, 100.0)}
MAX_OBSERVATIONS = 20_000


class ObservationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: str | Any
    temp_c: float | None = None
    slp_hpa: float | None = None
    rh_pct: float | None = None
    dew_c: float | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.temp_c is None:
            raise ValueError("'temp_c' is required")
        if self.slp_hpa is None:
            raise ValueError("'slp_hpa' is required")
        if self.rh_pct is None and self.dew_c is None:
            raise ValueError("supply either 'rh_pct' or 'dew_c'")
        for field, (lo, hi) in LIMITS.items():
            v = getattr(self, field)
            if v is not None and not (lo <= v <= hi):
                raise ValueError(
                    f"'{field}' = {v} is outside the plausible range [{lo}, {hi}]. "
                    "These bounds catch unit errors; genuine sensor faults fall well "
                    "inside them and are meant to reach the model.")
        return self


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[ObservationIn] = Field(..., min_length=1, max_length=MAX_OBSERVATIONS)
    include_features: bool = False


@router.post("/predict")
async def predict(
    req: PredictRequest,
    request: Request,
    user: User = Depends(require_permission(Permission.RUN_PREDICTION)),
) -> dict:
    ml = getattr(request.app.state, "ml", None)
    if ml is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "model_unavailable",
                    "message": "The detector failed to load at startup.",
                    "hint": "Check models/ and restart; verify with python3 src/inference.py"})
    observations = [o.model_dump(exclude_none=True) for o in req.observations]
    try:
        payload = ml.predict(observations, include_features=req.include_features)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail={"error": "bad_observations", "message": str(exc)}) from exc
    payload["requested_by"] = {"user_id": user.id, "roles": user.role_names}
    return payload


@router.get("/model")
async def model_info(request: Request,
                     user: User = Depends(require_permission(Permission.RUN_PREDICTION))) -> dict:
    ml = getattr(request.app.state, "ml", None)
    if ml is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail={"error": "model_unavailable", "message": "not loaded"})
    return ml.describe()
