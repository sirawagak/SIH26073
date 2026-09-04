"""
SIH26073 — frozen weather-sensor fault detector, inference module.

Wraps the model frozen in ``notebooks/02_ml_anomaly_detection.ipynb`` (Stage 6) behind a
small API for the dashboard. It does not train, tune, or modify anything: it replays the
exact feature pipeline and decision rules that were evaluated.

Detector
--------
    Isolation Forest (200 trees, 16 stationary features)
      + adaptive trailing 30-day rolling-quantile threshold
      OR flat-run rule (>= 8 identical consecutive readings) for stuck-at faults

Frozen test performance (synthetic faults, 2023 hold-out):
    precision 0.259 | recall 0.407 | F1 0.317 | alert rate 9.9%
    episode recall 1.00 on all five fault classes

IMPORTANT — this is a BATCH detector, not a streaming one
---------------------------------------------------------
Two parts of the frozen pipeline read observations *after* the point being scored:

  * the 24-hour rolling window is **centred**, so it needs up to 8 later observations (+/-12 h);
  * the flat-run rule flags every row of a run of >= 8 identical values, which for the first
    row of a run requires 7 later observations.

Scoring a point at full fidelity therefore requires ~12 hours of data after it. The module
still returns a result when that context is missing, but marks it ``degraded: true`` and says
why in ``notes``. Making the detector causal would require changing the features, which is out
of scope for the frozen prototype.

Usage
-----
    from inference import WeatherFaultDetector

    detector = WeatherFaultDetector.load("models/")
    payload = detector.predict(observations)   # list of dicts, or a DataFrame

See ``docs/INFERENCE_API.md`` for the dashboard integration guide.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import joblib
import numpy as np
import pandas as pd

__all__ = ["WeatherFaultDetector", "Observation", "DEFAULT_MODEL_DIR"]

DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

# Constants frozen with the model. Mirrors notebook 01 (Magnus) and notebook 02 (pipeline).
MAGNUS_A = 17.625
MAGNUS_B = 243.04
NOMINAL_STEP_H = 3.0
ROLL_WINDOW = "24h"
ROLL_MIN_PERIODS = 4
FLAT_RUN_MIN_LEN = 8
RH_LIMITS = (0.0, 100.0)

# Context needed on EACH side of a point for full-fidelity scoring:
#   * centred 24h rolling window      -> +/-12 h
#   * flat-run rule, 8 readings @ 3 h -> +/-21 h
# Rows closer than this to either end of the supplied batch are marked ``degraded``,
# because their features are computed from a truncated window. Rows further inside the
# batch reproduce the full-series result exactly.
REQUIRED_CONTEXT_HOURS = 21.0


# --------------------------------------------------------------------------------------
# input
# --------------------------------------------------------------------------------------
@dataclass
class Observation:
    """One weather observation.

    ``rh_pct`` may be supplied directly or derived from ``dew_c`` via the Magnus formula,
    exactly as notebook 01 derived it.
    """

    time: Any
    temp_c: float | None = None
    slp_hpa: float | None = None
    rh_pct: float | None = None
    dew_c: float | None = None

    def as_dict(self) -> dict:
        return {"time": self.time, "temp_c": self.temp_c, "slp_hpa": self.slp_hpa,
                "rh_pct": self.rh_pct, "dew_c": self.dew_c}


def _derive_rh(temp_c: pd.Series, dew_c: pd.Series) -> pd.Series:
    """Relative humidity from temperature and dew point (Magnus), as in notebook 01."""
    rh = 100.0 * np.exp(
        (MAGNUS_A * dew_c) / (MAGNUS_B + dew_c) - (MAGNUS_A * temp_c) / (MAGNUS_B + temp_c)
    )
    return rh.clip(upper=RH_LIMITS[1])


def _to_frame(observations) -> pd.DataFrame:
    """Normalise dicts / Observations / DataFrame into the canonical input frame."""
    if isinstance(observations, pd.DataFrame):
        df = observations.copy()
    else:
        if isinstance(observations, (dict, Observation)):
            observations = [observations]
        rows = [o.as_dict() if isinstance(o, Observation) else dict(o) for o in observations]
        if not rows:
            raise ValueError("no observations supplied")
        df = pd.DataFrame(rows)

    if "time" not in df.columns:
        raise ValueError("observations must contain a 'time' field")
    df["time"] = pd.to_datetime(df["time"], utc=True, format="mixed").dt.tz_localize(None)

    for col in ("temp_c", "slp_hpa", "rh_pct", "dew_c"):
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    need_rh = df["rh_pct"].isna() & df["temp_c"].notna() & df["dew_c"].notna()
    if need_rh.any():
        df.loc[need_rh, "rh_pct"] = _derive_rh(df.loc[need_rh, "temp_c"], df.loc[need_rh, "dew_c"])
    df["rh_pct"] = df["rh_pct"].clip(*RH_LIMITS)

    df = df.sort_values("time").drop_duplicates("time", keep="first").reset_index(drop=True)
    return df


# --------------------------------------------------------------------------------------
# detector
# --------------------------------------------------------------------------------------
class WeatherFaultDetector:
    """Frozen Isolation Forest + flat-run hybrid detector.

    Load with :meth:`load`, then call :meth:`predict`. Nothing here fits or tunes.
    """

    def __init__(self, model, state: dict, manifest: dict,
                 score_history: pd.DataFrame | None = None):
        self.model = model
        self.manifest = manifest
        self.climatology = state["climatology"]
        self.roll_std_fill = state["roll_std_fill"]
        self.features: list[str] = list(state["features"])
        self.vars: list[str] = list(state["vars"])

        thr = manifest["threshold"]
        self.threshold_window = thr["window"]
        self.threshold_q = float(thr["q"])
        self.threshold_min_periods = int(thr["min_periods"])
        self.threshold_fixed = float(thr["fixed_fallback"])

        if score_history is None or len(score_history) == 0:
            score_history = pd.DataFrame({"time": pd.to_datetime([]), "score": []})
        self.score_history = score_history.sort_values("time").reset_index(drop=True)

    # -- construction -------------------------------------------------------------
    @classmethod
    def load(cls, model_dir: str = DEFAULT_MODEL_DIR, *, with_history: bool = True):
        """Load the frozen artifacts written by the notebook appendix."""
        model_dir = os.path.abspath(model_dir)
        model = joblib.load(os.path.join(model_dir, "isolation_forest.joblib"))
        state = joblib.load(os.path.join(model_dir, "pipeline_state.joblib"))
        with open(os.path.join(model_dir, "manifest.json")) as fh:
            manifest = json.load(fh)

        history = None
        hist_path = os.path.join(model_dir, "score_history.csv")
        if with_history and os.path.exists(hist_path):
            history = pd.read_csv(hist_path, parse_dates=["time"])

        det = cls(model, state, manifest, history)
        det.model_dir = model_dir
        return det

    # -- feature pipeline (mirrors notebook Stage 1 exactly) ----------------------
    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        # 1.2 impute the small holes, on the real time axis
        interp = out.set_index("time")[self.vars].interpolate(
            method="time", limit=2, limit_direction="both")
        out[self.vars] = interp.to_numpy()

        # 1.3 gap-aware steps: a step only means something across a nominal 3 h interval
        out["gap_hours"] = out["time"].diff().dt.total_seconds() / 3600.0
        valid = out["gap_hours"].eq(NOMINAL_STEP_H)
        for v in self.vars:
            out[f"{v}_step"] = out[v].diff().where(valid)

        # 1.4 cyclical time
        hour = out["time"].dt.hour.to_numpy()
        doy = out["time"].dt.dayofyear.to_numpy()
        out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
        out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
        out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

        # 1.5 centred 24 h rolling statistics  (NOTE: reads future observations)
        s = out.set_index("time")
        for v in self.vars:
            r = s[v].rolling(ROLL_WINDOW, center=True, min_periods=ROLL_MIN_PERIODS)
            med = r.median().to_numpy()
            std = r.std().to_numpy()
            med = np.where(np.isnan(med), out[v].to_numpy(), med)
            out[f"{v}_roll_med"] = med
            out[f"{v}_roll_std"] = std
            out[f"{v}_resid"] = out[v].to_numpy() - med

        # 1.6 day-of-year x hour-of-day climatology deviation
        key = pd.MultiIndex.from_arrays(
            [out["time"].dt.dayofyear.astype("int64"), out["time"].dt.hour.astype("int64")],
            names=["doy", "hour"])
        for v in self.vars:
            mu = self.climatology[v]["mean"].reindex(key).to_numpy()
            sd = self.climatology[v]["std"].reindex(key).to_numpy()
            out[f"{v}_clim_dev"] = (out[v].to_numpy() - mu) / sd

        # 1.7 NaN policy — frozen fills, not frame-dependent ones
        for v in self.vars:
            out[f"{v}_step"] = out[f"{v}_step"].fillna(0.0)
            c = f"{v}_roll_std"
            out[c] = out[c].fillna(self.roll_std_fill[c])
            out[f"{v}_clim_dev"] = out[f"{v}_clim_dev"].fillna(0.0)
            out[f"{v}_resid"] = out[f"{v}_resid"].fillna(0.0)

        missing = [f for f in self.features if f not in out.columns]
        if missing:
            raise RuntimeError(f"feature pipeline did not produce: {missing}")
        return out

    # -- rules --------------------------------------------------------------------
    def _flat_run_flags(self, df: pd.DataFrame) -> tuple[np.ndarray, list[str | None]]:
        """Runs of >= 8 identical consecutive readings. Returns (flags, variable per row)."""
        flag = np.zeros(len(df), dtype=bool)
        which: list[str | None] = [None] * len(df)
        for v in self.vars:
            s = df[v]
            run_id = s.ne(s.shift()).cumsum()
            size = s.groupby(run_id).transform("size")
            hit = (size >= FLAT_RUN_MIN_LEN).to_numpy() & s.notna().to_numpy()
            for i in np.flatnonzero(hit & ~flag):
                which[i] = v
            flag |= hit
        return flag, which

    def _adaptive_threshold(self, times: pd.Series, scores: np.ndarray) -> np.ndarray:
        """Trailing rolling-quantile threshold; ``closed='left'`` => strictly past data."""
        # Only history strictly BEFORE the batch is usable. Anything at or after the first
        # batch timestamp would double-count the very rows being scored (the warm-start file
        # covers 2023, so re-scoring a 2023 window would otherwise see each point twice).
        hist = self.score_history
        if len(hist) and len(times):
            hist = hist[hist["time"] < pd.Timestamp(min(times))]

        all_t = pd.DatetimeIndex(pd.concat([hist["time"], pd.Series(times)], ignore_index=True))
        all_s = np.concatenate([hist["score"].to_numpy(), scores])

        combined = pd.Series(all_s, index=all_t).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
        thr = (combined.rolling(self.threshold_window, closed="left",
                                min_periods=self.threshold_min_periods)
               .quantile(self.threshold_q))
        thr = thr[~thr.index.duplicated(keep="last")]
        return thr.reindex(pd.DatetimeIndex(times)).fillna(self.threshold_fixed).to_numpy()

    # -- heuristic attribution ----------------------------------------------------
    def _attribute(self, feats: pd.DataFrame, i: int, flat_var: str | None
                   ) -> tuple[str | None, str | None]:
        """Guess (fault_type, variable) for a flagged row.

        HEURISTIC AND UNVALIDATED. The frozen model is a binary detector; it was never
        evaluated as a fault-type classifier. Treat this as a display hint for the
        dashboard, not as a measured capability.
        """
        if flat_var is not None:
            return "stuck_at", flat_var

        row = feats.iloc[i]
        cand = max(self.vars, key=lambda v: abs(row[f"{v}_clim_dev"]))
        dev = abs(row[f"{cand}_clim_dev"])

        resid_z = {v: abs(row[f"{v}_resid"]) / max(self.roll_std_fill[f"{v}_roll_std"], 1e-9)
                   for v in self.vars}
        spike_var = max(resid_z, key=resid_z.get)
        if resid_z[spike_var] > 2.5:
            return "spike", spike_var

        std_ratio = {v: row[f"{v}_roll_std"] / max(self.roll_std_fill[f"{v}_roll_std"], 1e-9)
                     for v in self.vars}
        noisy = max(std_ratio, key=std_ratio.get)
        if std_ratio[noisy] > 1.8:
            return "noise_burst", noisy

        if dev > 1.5:
            lo, hi = max(0, i - 4), min(len(feats), i + 5)
            seg = feats[f"{cand}_clim_dev"].iloc[lo:hi].to_numpy()
            if len(seg) >= 3 and np.ptp(seg) > 1.0 and abs(seg[-1] - seg[0]) > 0.8 * np.ptp(seg):
                return "drift", cand
            return "bias", cand

        return None, (cand if dev > 0.5 else None)

    # -- public API ---------------------------------------------------------------
    def predict(self, observations, *, include_features: bool = False) -> dict:
        """Score a sequence of observations.

        Parameters
        ----------
        observations
            A single observation or a sequence, as dicts, :class:`Observation` objects,
            or a DataFrame. Requires ``time`` plus ``temp_c``, ``slp_hpa`` and either
            ``rh_pct`` or ``dew_c``.
        include_features
            Attach the 16 model features to each result (debugging only).

        Returns
        -------
        dict
            ``{"model": {...}, "results": [...], "summary": {...}}`` — JSON-serialisable.
        """
        df = _to_frame(observations)
        feats = self._build_features(df)

        X = feats[self.features]
        scores = -self.model.score_samples(X)
        thresholds = self._adaptive_threshold(feats["time"], scores)
        if_pred = scores > thresholds
        flat_pred, flat_var = self._flat_run_flags(feats)
        anomaly = if_pred | flat_pred

        times = feats["time"]
        span_start, span_end = times.min(), times.max()
        results = []
        for i in range(len(feats)):
            t = times.iloc[i]
            future_h = (span_end - t).total_seconds() / 3600.0
            past_h = (t - span_start).total_seconds() / 3600.0
            notes: list[str] = []
            degraded = False

            if future_h < REQUIRED_CONTEXT_HOURS:
                degraded = True
                notes.append(
                    f"only {future_h:.1f}h of later data in this batch; the centred 24h window and "
                    f"flat-run rule need ~{REQUIRED_CONTEXT_HOURS:.0f}h. Rescore once more data arrives."
                )
            if past_h < REQUIRED_CONTEXT_HOURS:
                degraded = True
                notes.append(
                    f"only {past_h:.1f}h of earlier data in this batch; features use a truncated "
                    f"window. Extend the batch backwards for a full-fidelity result."
                )
            if i == 0 or feats["gap_hours"].iloc[i] != NOMINAL_STEP_H:
                notes.append("preceding interval is not the nominal 3h; step features set to 0.")

            fault_type, variable = (None, None)
            if anomaly[i]:
                fault_type, variable = self._attribute(feats, i, flat_var[i] if flat_pred[i] else None)

            rec = {
                "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "anomaly": bool(anomaly[i]),
                "anomaly_score": round(float(scores[i]), 6),
                "threshold": round(float(thresholds[i]), 6),
                "detector_used": ("flat_run_rule" if flat_pred[i]
                                  else "isolation_forest" if if_pred[i] else None),
                "detectors_fired": ([("flat_run_rule") ] if flat_pred[i] else [])
                                   + (["isolation_forest"] if if_pred[i] else []),
                "fault_type": fault_type,
                "fault_type_basis": "heuristic_unvalidated" if fault_type else None,
                "variable": variable,
                "degraded": degraded,
                "notes": notes,
                "observation": {
                    "temp_c": _num(df["temp_c"].iloc[i]),
                    "slp_hpa": _num(df["slp_hpa"].iloc[i]),
                    "rh_pct": _num(df["rh_pct"].iloc[i]),
                },
            }
            if include_features:
                rec["features"] = {f: round(float(X[f].iloc[i]), 6) for f in self.features}
            results.append(rec)

        n_anom = int(anomaly.sum())
        return {
            "model": {
                "name": "sih26073-weather-fault-detector",
                "version": self.manifest.get("frozen_on_data", "unknown"),
                "detector": "isolation_forest + flat_run_rule (hybrid)",
                "threshold_mode": self.manifest["threshold"]["mode"],
                "station": self.manifest["station"],
                "frozen_test_metrics": self.manifest["test_metrics_hybrid_adaptive"],
                "scored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "results": results,
            "summary": {
                "n_observations": len(results),
                "n_anomalies": n_anom,
                "alert_rate": round(n_anom / len(results), 4) if results else 0.0,
                "n_degraded": int(sum(r["degraded"] for r in results)),
                "window": {
                    "start": times.min().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": span_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                "by_fault_type": _counts([r["fault_type"] for r in results if r["anomaly"]]),
                "by_variable": _counts([r["variable"] for r in results if r["anomaly"]]),
            },
        }

    def predict_one(self, observation, context: Sequence | None = None) -> dict:
        """Score a single observation, optionally with surrounding context.

        Without ~12 h of later observations in ``context`` the result is marked
        ``degraded``. Returns the single result dict, not the envelope.
        """
        batch = list(context) if context else []
        batch.append(observation.as_dict() if isinstance(observation, Observation)
                     else dict(observation))
        payload = self.predict(batch)
        target = _to_frame([observation])["time"].iloc[0].strftime("%Y-%m-%dT%H:%M:%SZ")
        for r in payload["results"]:
            if r["timestamp"] == target:
                return r
        return payload["results"][-1]

    # -- verification --------------------------------------------------------------
    def verify_parity(self, fixture_path: str | None = None, *, verbose: bool = True) -> bool:
        """Replay the notebook's own outputs and assert this module reproduces them.

        This is what makes "frozen" a verified property rather than a claim: if the feature
        pipeline here ever drifts from the evaluated one, this fails loudly.
        """
        if fixture_path is None:
            fixture_path = os.path.join(getattr(self, "model_dir", DEFAULT_MODEL_DIR),
                                        "parity_fixture.csv")
        fx = pd.read_csv(fixture_path, parse_dates=["time"])

        det = WeatherFaultDetector(self.model,
                                   {"climatology": self.climatology,
                                    "roll_std_fill": self.roll_std_fill,
                                    "features": self.features, "vars": self.vars},
                                   self.manifest, score_history=None)  # cold start, as in the notebook

        df = fx[["time"] + self.vars].copy()
        feats = det._build_features(df)
        X = feats[det.features]
        scores = -det.model.score_samples(X)
        thr = det._adaptive_threshold(feats["time"], scores)
        if_pred = (scores > thr).astype(int)
        flat_pred, _ = det._flat_run_flags(feats)
        hybrid = ((if_pred + flat_pred.astype(int)) > 0).astype(int)

        # Tolerance note: float64 rolling-variance over a CONSTANT run (a stuck-at fault)
        # is catastrophic cancellation - the true value is 0 but pandas returns ~1e-6, and
        # two mathematically identical computations can differ by ~1e-9 there. Features are
        # therefore compared with a float-appropriate tolerance; the outputs that actually
        # drive the dashboard (predictions) are required to match EXACTLY.
        feat_tol = dict(atol=1e-8, rtol=1e-6)

        checks, devs = [], {}
        for f in det.features:
            a, b = X[f].to_numpy(), fx[f"expected__{f}"].to_numpy()
            devs[f] = float(np.abs(a - b).max())
            checks.append((f"feature {f}", bool(np.allclose(a, b, **feat_tol))))
        checks += [
            ("anomaly_score", bool(np.allclose(scores, fx["expected__score"].to_numpy(), **feat_tol))),
            ("adaptive_threshold", bool(np.allclose(thr, fx["expected__adapt_threshold"].to_numpy(), **feat_tol))),
            ("isolation_forest_pred (exact)", bool((if_pred == fx["expected__if_pred"].to_numpy()).all())),
            ("flat_run_rule (exact)", bool((flat_pred.astype(int) == fx["expected__flat_run"].to_numpy()).all())),
            ("hybrid_pred (exact)", bool((hybrid == fx["expected__hybrid_pred"].to_numpy()).all())),
        ]
        ok = all(passed for _, passed in checks)
        if verbose:
            feats_ok = all(p for n, p in checks if n.startswith("feature"))
            worst = max(devs, key=devs.get)
            print(f"parity check against {len(fx)} notebook rows")
            print(f"  {'PASS' if feats_ok else 'FAIL'}  all {len(det.features)} features "
                  f"(largest deviation {devs[worst]:.2e} on {worst})")
            for name, passed in checks:
                if not name.startswith("feature"):
                    print(f"  {'PASS' if passed else 'FAIL'}  {name}")
            print("\nPARITY OK — module reproduces the frozen notebook model"
                  if ok else "\nPARITY FAILED — module has diverged from the frozen model")
        return ok


def _num(x):
    return None if pd.isna(x) else round(float(x), 4)


def _counts(values: Iterable) -> dict:
    out: dict[str, int] = {}
    for v in values:
        k = v if v is not None else "unattributed"
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    det = WeatherFaultDetector.load()
    ok = det.verify_parity()
    raise SystemExit(0 if ok else 1)
