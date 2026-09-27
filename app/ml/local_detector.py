"""In-process adapter over the frozen WeatherFaultDetector.

This module is a THIN WRAPPER. It does not re-implement features, scoring,
thresholding or the flat-run rule, and it does not alter the response contract:
``predict`` returns exactly what ``src/inference.py`` returns.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT, get_settings

# src/ holds the frozen, validated pipeline. It is imported, never modified.
_SRC = REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from inference import WeatherFaultDetector  # noqa: E402

# Files that define model behaviour. Their combined digest IS the model version,
# so no frozen artifact needs a version field added to it.
_VERSIONED_ARTIFACTS = ("isolation_forest.joblib", "pipeline_state.joblib", "manifest.json")


def compute_model_version(model_dir: Path) -> str:
    h = hashlib.sha256()
    for name in _VERSIONED_ARTIFACTS:
        h.update((model_dir / name).read_bytes())
    return h.hexdigest()[:12]


class LocalDetectorService:
    """MLService backed by the frozen detector loaded once into this process."""

    def __init__(self, model_dir: Path | None = None):
        self._dir = Path(model_dir or get_settings().model_dir)
        self._detector = WeatherFaultDetector.load(str(self._dir))
        self._version = compute_model_version(self._dir)

    @property
    def model_version(self) -> str:
        return self._version

    @property
    def detector(self) -> WeatherFaultDetector:
        return self._detector

    def describe(self) -> dict[str, Any]:
        m = self._detector.manifest
        return {
            "model_version": self._version,
            "detector": "isolation_forest + flat_run_rule (hybrid)",
            "n_features": len(self._detector.features),
            "n_estimators": m["model"]["n_estimators"],
            "threshold_mode": m["threshold"]["mode"],
            "station": m["station"],
            "frozen_test_metrics": m["test_metrics_hybrid_adaptive"],
            "caveats": m.get("caveats", []),
            "assessment_note": "Automated anomaly assessment - requires human verification.",
        }

    def predict(self, observations: list[dict], *, include_features: bool = False) -> dict:
        """Delegate verbatim to the frozen pipeline, then stamp the model version."""
        payload = self._detector.predict(observations, include_features=include_features)
        payload["model"]["model_version"] = self._version
        return payload

    def verify_parity(self) -> bool:
        return self._detector.verify_parity(verbose=False)
