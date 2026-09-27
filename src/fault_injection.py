"""
SIH26073 / SkyGuard AI — synthetic weather-sensor fault simulator.

Round-2 replacement for the five-class injector that lived inline in
``notebooks/02_ml_anomaly_detection.ipynb``. That injector is preserved here
verbatim in behaviour as :data:`BASELINE_CONFIG`, so the original benchmark can
still be reproduced exactly; :data:`CHALLENGE_CONFIG` adds the harder, more
realistic fault models.

IMPORTANT — what these faults are and are not
---------------------------------------------
These are *simulated* faults used to stress-test the detector. They are NOT
real-world ground truth. No field-labelled sensor failures exist for this
station, which is precisely why synthetic injection is used; the challenge set
is a more plausible simulation, not evidence of real-world performance.

Three fixes carried over from the original injector (do not regress these)
-------------------------------------------------------------------------
1. ``labels.iloc[...]`` not ``labels.loc[...]``. On a RangeIndex ``.loc`` with a
   slice is LABEL-based and end-INCLUSIVE, so it would label one extra,
   uncorrupted row per episode and silently cap precision.
2. Drift does not start at offset 0 *on a labelled row*. See ``_drift`` — the
   ramp is anchored so offset 0 falls on the last PRE-episode sample, which
   keeps the onset continuous while guaranteeing every labelled row is really
   modified.
3. No unlearnable positives: a row is labelled faulty only if it was actually
   changed. Enforced by assertion in :meth:`FaultSimulator.inject`.

Fault magnitudes are expressed as multiples of the variable's LOCAL scale
(rolling std around the episode), never as one absolute number shared across
temperature, pressure and humidity — those live on completely different scales.

Usage
-----
    from fault_injection import FaultSimulator, BASELINE_CONFIG, CHALLENGE_CONFIG

    sim = FaultSimulator(clean_df, seed=42)
    faulty, labels, episodes = sim.inject(CHALLENGE_CONFIG)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "FaultSimulator", "BASELINE_CONFIG", "CHALLENGE_CONFIG",
    "VARS", "PHYSICAL_LIMITS", "FAULT_KINDS", "SEVERITY",
]

VARS = ["temp_c", "slp_hpa", "rh_pct"]

# Humidity sensors saturate; temperature and pressure are left unclipped so a
# fault is never silently swallowed.
PHYSICAL_LIMITS = {"rh_pct": (0.0, 100.0)}

# Keep episodes clear of the series ends (the detector needs context either side).
EDGE_MARGIN = 8

# Global severity multipliers applied to every magnitude range.
SEVERITY = {"mild": 0.6, "moderate": 1.0, "severe": 1.6}

FAULT_KINDS = [
    "spike", "drift", "bias", "stuck_at", "noise_burst",
    "intermittent_spikes", "drift_plus_noise", "bias_plus_spikes",
]


# ----------------------------------------------------------------------------
# scale helpers — magnitudes are relative, never absolute
# ----------------------------------------------------------------------------
def _robust_scale(x: np.ndarray) -> float:
    """Median-absolute-deviation scale, robust to the faults already injected."""
    x = x[np.isfinite(x)]
    if x.size == 0:
        return 1.0
    mad = float(np.median(np.abs(x - np.median(x))))
    return max(mad * 1.4826, 1e-6)


def local_scale(values: np.ndarray, start: int, length: int,
                half_window: int = 40, floor_frac: float = 0.25) -> float:
    """Local variability of `values` around [start, start+length).

    Using the LOCAL spread rather than a global constant is what makes the
    challenge set harder: in a calm stretch a "4 sigma" spike is a much smaller
    absolute jump than the fixed magnitudes the original benchmark used.

    Floored at ``floor_frac`` of the global robust scale so an unusually flat
    window cannot collapse the magnitude to nothing.
    """
    lo = max(0, start - half_window)
    hi = min(len(values), start + length + half_window)
    seg = values[lo:hi]
    seg = seg[np.isfinite(seg)]
    glob = _robust_scale(values)
    if seg.size < 4:
        return glob
    return max(float(np.std(seg)), floor_frac * glob, 1e-6)


def _rng_range(rng, rng_pair, severity_mult: float) -> float:
    lo, hi = rng_pair
    return float(rng.uniform(lo, hi)) * severity_mult


# ----------------------------------------------------------------------------
# individual fault models
#
# Each returns (offsets_or_values, mode, modified_offsets, detail) where:
#   mode == "add"     -> `payload` is added to the window
#   mode == "replace" -> `payload` replaces the window
#   modified_offsets  -> indices WITHIN the window that were actually changed
# ----------------------------------------------------------------------------
def _spike(rng, length, scale, p, sev):
    """Transient excursion: single point, or a short decaying transient.

    Variants (``shape``):
      * ``point``     - one observation (classic)
      * ``transient`` - 2-3 observations, first large then decaying
    Sign is configurable: ``direction`` in {"positive", "negative", "random"}.
    """
    mag = _rng_range(rng, p.get("magnitude", (4.0, 10.0)), sev) * scale
    sign = _direction(rng, p.get("direction", "random"))
    shape = p.get("shape", "point")
    off = np.zeros(length)
    if shape == "point" or length == 1:
        off[0] = sign * mag
        detail = f"{sign*mag:+.2f} single point ({mag/scale:.1f}x local sigma)"
    else:
        decay = p.get("decay", 0.45)
        for i in range(length):
            off[i] = sign * mag * (decay ** i)
        detail = (f"transient {sign*mag:+.2f} decaying x{decay} over {length} obs "
                  f"({mag/scale:.1f}x local sigma)")
    return off, "add", np.flatnonzero(off != 0.0), detail


def _drift(rng, length, scale, p, sev):
    """Gradual ramp away from truth.

    Continuity: the ramp is anchored so that offset 0 lands on the last
    PRE-episode sample. The first labelled row therefore carries the first real
    increment - the onset is continuous (no artificial step) while every
    labelled row is genuinely modified.

    ``exponent`` > 1 gives slow acceleration (a failing element that worsens).
    """
    total = _rng_range(rng, p.get("magnitude", (2.5, 6.0)), sev) * scale
    sign = _direction(rng, p.get("direction", "random"))
    exponent = float(p.get("exponent", 1.0))
    t = np.arange(1, length + 1, dtype=float) / length      # (0, 1], excludes 0
    off = sign * total * (t ** exponent)
    kind = "linear" if exponent == 1.0 else f"accelerating(^{exponent})"
    detail = (f"{kind} ramp -> {sign*total:+.2f} over {length} obs "
              f"({total/scale:.1f}x local sigma)")
    return off, "add", np.arange(length), detail


def _bias(rng, length, scale, p, sev):
    """Persistent calibration offset.

    ``onset`` in {"step", "ramp"}: an instant jump, or a short ramp-in over
    ``onset_len`` observations before holding - closer to how a recalibration
    error or a slowly seating connector actually appears.
    """
    mag = _rng_range(rng, p.get("magnitude", (1.2, 3.0)), sev) * scale
    sign = _direction(rng, p.get("direction", "random"))
    onset = p.get("onset", "step")
    off = np.full(length, sign * mag, dtype=float)
    if onset == "ramp":
        k = int(min(max(1, p.get("onset_len", 3)), length))
        off[:k] = sign * mag * (np.arange(1, k + 1) / k)
        detail = (f"{sign*mag:+.2f} offset, ramped in over {k} obs, held {length} obs "
                  f"({mag/scale:.1f}x local sigma)")
    else:
        detail = (f"{sign*mag:+.2f} step offset held {length} obs "
                  f"({mag/scale:.1f}x local sigma)")
    return off, "add", np.arange(length), detail


def _stuck_at(rng, length, scale, p, sev, *, prior_values=None):
    """Frozen sensor: repeat the LAST VALID observed value from fault onset.

    Never an arbitrary constant. Walks backwards past NaNs to find a finite
    value, so a hole immediately before onset cannot freeze the sensor at NaN.
    """
    held = None
    if prior_values is not None:
        for v in prior_values[::-1]:
            if np.isfinite(v):
                held = float(v)
                break
    if held is None:
        raise ValueError("stuck_at: no valid prior value before onset")
    vals = np.full(length, held, dtype=float)
    detail = f"frozen at last valid value {held:.2f} for {length} obs"
    return vals, "replace", np.arange(length), detail


def _noise_burst(rng, length, scale, p, sev):
    """Variance inflation that PRESERVES the underlying signal.

    Zero-mean additive noise, so the local mean stays on the true baseline and
    only the spread grows - the signature of a failing connector or EMI, and
    much harder than replacing the signal with random values.
    """
    level = p.get("level", "medium")
    mult = {"low": 0.8, "medium": 1.8, "high": 3.2}.get(level, 1.8)
    sigma = mult * scale * _rng_range(rng, p.get("magnitude", (0.9, 1.3)), sev)
    off = rng.normal(0.0, sigma, size=length)
    off -= off.mean()                      # keep the burst genuinely zero-mean
    detail = (f"{level} noise, sigma={sigma:.2f} ({sigma/scale:.1f}x local sigma), "
              f"{length} obs, mean preserved")
    return off, "add", np.arange(length), detail


def _intermittent_spikes(rng, length, scale, p, sev):
    """Sparse spikes at non-consecutive positions inside the window.

    Represents intermittent electrical / communication interference. Only the
    spiked rows are modified, so only those rows are labelled faulty - labelling
    the quiet rows in between would manufacture unlearnable positives.
    """
    n_spikes = int(rng.integers(*p.get("n_spikes", (3, 6))))
    min_gap = int(p.get("min_gap", 2))
    mag_rng = p.get("magnitude", (4.0, 9.0))
    direction = p.get("direction", "random")

    chosen: list[int] = []
    for _ in range(400):
        if len(chosen) >= n_spikes:
            break
        c = int(rng.integers(0, length))
        if all(abs(c - k) >= min_gap for k in chosen):
            chosen.append(c)
    chosen = sorted(set(chosen))
    if not chosen:
        chosen = [0]

    off = np.zeros(length)
    for c in chosen:
        off[c] = _direction(rng, direction) * _rng_range(rng, mag_rng, sev) * scale
    detail = (f"{len(chosen)} intermittent spikes at offsets {chosen} "
              f"(min gap {min_gap}) over a {length}-obs window")
    return off, "add", np.array(chosen), detail


def _drift_plus_noise(rng, length, scale, p, sev):
    """Slowly drifting baseline that also becomes progressively noisier."""
    d_off, _, _, d_detail = _drift(rng, length, scale, p.get("drift", {}), sev)
    level = p.get("noise", {}).get("level", "medium")
    mult = {"low": 0.6, "medium": 1.2, "high": 2.2}.get(level, 1.2)
    sigma = mult * scale
    ramp = np.linspace(0.3, 1.0, length)              # noise grows with the drift
    noise = rng.normal(0.0, 1.0, size=length) * sigma * ramp
    noise -= noise.mean()
    off = d_off + noise
    detail = f"{d_detail} + {level} noise growing to sigma={sigma:.2f}"
    return off, "add", np.arange(length), detail


def _bias_plus_spikes(rng, length, scale, p, sev):
    """Persistent calibration offset with occasional transients on top."""
    b_off, _, _, b_detail = _bias(rng, length, scale, p.get("bias", {}), sev)
    s_off, _, s_idx, s_detail = _intermittent_spikes(
        rng, length, scale, p.get("spikes", {"n_spikes": (2, 4), "min_gap": 3}), sev)
    off = b_off + s_off
    detail = f"{b_detail} + {s_detail}"
    return off, "add", np.arange(length), detail       # bias modifies every row


def _direction(rng, spec: str) -> float:
    if spec == "positive":
        return 1.0
    if spec == "negative":
        return -1.0
    return float(rng.choice([-1.0, 1.0]))


_MODELS = {
    "spike": _spike,
    "drift": _drift,
    "bias": _bias,
    "stuck_at": _stuck_at,
    "noise_burst": _noise_burst,
    "intermittent_spikes": _intermittent_spikes,
    "drift_plus_noise": _drift_plus_noise,
    "bias_plus_spikes": _bias_plus_spikes,
}


# ----------------------------------------------------------------------------
# simulator
# ----------------------------------------------------------------------------
class FaultSimulator:
    """Reproducible fault injector with exact ground-truth labels.

    The input frame is never mutated; :meth:`inject` returns a deep copy.
    """

    def __init__(self, frame: pd.DataFrame, variables=None, seed: int = 42,
                 edge_margin: int = EDGE_MARGIN, severity: str = "moderate"):
        if severity not in SEVERITY:
            raise ValueError(f"severity must be one of {sorted(SEVERITY)}")
        self.frame = frame
        self.vars = list(variables) if variables else list(VARS)
        self.seed = int(seed)
        self.edge_margin = int(edge_margin)
        self.severity = severity
        missing = [v for v in self.vars + ["time"] if v not in frame.columns]
        if missing:
            raise ValueError(f"frame is missing columns: {missing}")

    # -- window reservation ---------------------------------------------------
    def _reserve(self, rng, occupied, length):
        n = len(occupied)
        lo, hi = self.edge_margin, n - length - self.edge_margin
        if hi <= lo:
            return None
        for _ in range(800):
            start = int(rng.integers(lo, hi))
            sl = slice(start, start + length)
            if not occupied[sl].any():
                occupied[sl] = True
                return sl
        return None

    # -- main -----------------------------------------------------------------
    def inject(self, config, verbose: bool = False):
        """Inject every episode described by `config`.

        Returns ``(faulty_frame, labels, episodes)``.

        ``labels`` columns: ``is_fault``, ``fault_type``, ``fault_var``,
        ``episode_id`` — the same semantics the original notebook used.
        ``is_fault`` marks rows that were ACTUALLY modified, so intermittent
        faults label only their spiked rows while sharing one ``episode_id``.
        """
        rng = np.random.default_rng(self.seed)
        out = self.frame.copy(deep=True)
        clean = {v: self.frame[v].to_numpy(copy=True) for v in self.vars}
        n = len(out)

        labels = pd.DataFrame({
            "is_fault": np.zeros(n, dtype=int),
            "fault_type": np.array(["none"] * n, dtype=object),
            "fault_var": np.array(["none"] * n, dtype=object),
            "episode_id": np.full(n, -1, dtype=int),
        })
        occupied = np.zeros(n, dtype=bool)
        episodes = []
        ep_id = 0
        sev_mult = SEVERITY[self.severity]

        for entry in config:
            kind = entry["type"]
            if kind not in _MODELS:
                raise ValueError(f"unknown fault type {kind!r}")
            variables = entry.get("variables", self.vars)
            n_per_var = int(entry.get("n_per_var", 1))
            len_lo, len_hi = entry.get("length", (8, 14))
            params = entry.get("params", {})

            for var in variables:
                for _ in range(n_per_var):
                    length = int(rng.integers(len_lo, len_hi + 1))
                    sl = self._reserve(rng, occupied, length)
                    if sl is None:
                        if verbose:
                            print(f"  ! no free window for {kind}/{var}, skipped")
                        continue

                    vals = out[var].to_numpy(copy=True)
                    scale = local_scale(clean[var], sl.start, length)

                    if kind == "stuck_at":
                        payload, mode, mod_off, detail = _stuck_at(
                            rng, length, scale, params, sev_mult,
                            prior_values=vals[max(0, sl.start - 12):sl.start])
                    else:
                        payload, mode, mod_off, detail = _MODELS[kind](
                            rng, length, scale, params, sev_mult)

                    before = vals.copy()
                    if mode == "add":
                        vals[sl] = vals[sl] + payload
                    else:
                        vals[sl] = payload

                    abs_idx = sl.start + np.asarray(mod_off, dtype=int)

                    # Clip ONLY inside the episode, so clipping can never touch a
                    # row outside the intended window.
                    if var in PHYSICAL_LIMITS:
                        lo_lim, hi_lim = PHYSICAL_LIMITS[var]
                        w = np.arange(sl.start, sl.stop)
                        vals[w] = np.clip(vals[w], lo_lim, hi_lim)

                    # Rows the model was told to leave alone must be untouched.
                    keep = np.ones(n, dtype=bool)
                    keep[sl.start:sl.stop] = False
                    assert np.allclose(vals[keep], before[keep], rtol=0, atol=0,
                                       equal_nan=True), \
                        f"{kind}/{var}: wrote outside the episode window"

                    out[var] = vals
                    changed = ~np.isclose(vals, before, rtol=0, atol=1e-12,
                                          equal_nan=True)
                    # Only rows that genuinely changed are labelled - a row that
                    # clipping or a zero-magnitude draw left identical would be an
                    # unlearnable positive.
                    label_idx = np.intersect1d(abs_idx, np.flatnonzero(changed))
                    if label_idx.size == 0:
                        occupied[sl] = False           # release the window
                        if verbose:
                            print(f"  ! {kind}/{var} produced no change, skipped")
                        continue

                    labels.iloc[label_idx, labels.columns.get_loc("is_fault")] = 1
                    labels.iloc[label_idx, labels.columns.get_loc("fault_type")] = kind
                    labels.iloc[label_idx, labels.columns.get_loc("fault_var")] = var
                    labels.iloc[label_idx, labels.columns.get_loc("episode_id")] = ep_id

                    episodes.append({
                        "episode_id": ep_id,
                        "fault_type": kind,
                        "variable": var,
                        "start_idx": int(sl.start),
                        "end_idx": int(sl.stop - 1),
                        "first_modified_idx": int(label_idx.min()),
                        "last_modified_idx": int(label_idx.max()),
                        "start": out["time"].iloc[sl.start],
                        "end": out["time"].iloc[sl.stop - 1],
                        "window_obs": length,
                        "n_modified": int(label_idx.size),
                        "local_sigma": round(scale, 4),
                        "detail": detail,
                    })
                    ep_id += 1

        episodes = pd.DataFrame(episodes)
        self._validate(clean, out, labels, episodes)
        return out, labels, episodes

    # -- quality gate ---------------------------------------------------------
    def _validate(self, clean, faulty, labels, episodes):
        """Assertions that must hold for the labels to mean anything."""
        n = len(faulty)
        changed = np.zeros(n, dtype=bool)
        for v in self.vars:
            changed |= ~np.isclose(clean[v], faulty[v].to_numpy(),
                                   rtol=0, atol=1e-12, equal_nan=True)
        lab = labels["is_fault"].to_numpy().astype(bool)

        assert not (changed & ~lab).any(), (
            f"{int((changed & ~lab).sum())} rows were modified but not labelled "
            "- corruption leaked outside a labelled episode")
        assert not (lab & ~changed).any(), (
            f"{int((lab & ~changed).sum())} rows were labelled but not modified "
            "- unlearnable positives")

        if len(episodes):
            ids = labels.loc[lab, "episode_id"].to_numpy()
            assert (ids >= 0).all(), "labelled row with no episode_id"
            assert set(np.unique(ids)) == set(episodes["episode_id"]), \
                "episode_id mismatch between labels and episode log"
            # one (type, variable) per episode
            g = labels[lab].groupby("episode_id")[["fault_type", "fault_var"]].nunique()
            assert (g["fault_type"] == 1).all() and (g["fault_var"] == 1).all(), \
                "an episode mixes fault types or variables"
            # episodes must not overlap
            iv = episodes.sort_values("start_idx")[["start_idx", "end_idx"]].to_numpy()
            assert all(iv[i, 1] < iv[i + 1, 0] for i in range(len(iv) - 1)), \
                "episode windows overlap"


# ----------------------------------------------------------------------------
# configurations
# ----------------------------------------------------------------------------
# A. BASELINE — reproduces the original notebook benchmark's fault mix.
#    Magnitudes here are deliberately LARGE and absolute-ish (via generous
#    sigma multipliers) to mirror the original controlled test.
BASELINE_CONFIG = [
    {"type": "spike",       "variables": VARS, "n_per_var": 5, "length": (1, 1),
     "params": {"magnitude": (5.0, 12.0), "shape": "point", "direction": "random"}},
    {"type": "stuck_at",    "variables": VARS, "n_per_var": 1, "length": (8, 14),
     "params": {}},
    {"type": "bias",        "variables": VARS, "n_per_var": 1, "length": (8, 16),
     "params": {"magnitude": (2.0, 5.0), "onset": "step", "direction": "random"}},
    {"type": "drift",       "variables": VARS, "n_per_var": 1, "length": (12, 20),
     "params": {"magnitude": (3.0, 7.0), "exponent": 1.0, "direction": "random"}},
    {"type": "noise_burst", "variables": VARS, "n_per_var": 1, "length": (8, 14),
     "params": {"level": "high", "magnitude": (1.0, 1.4)}},
]

# B. CHALLENGE — harder and more realistic. Smaller magnitudes relative to local
#    variability, transient shapes, ramped onsets, intermittency and combinations.
CHALLENGE_CONFIG = [
    # --- transients -------------------------------------------------------
    {"type": "spike", "variables": VARS, "n_per_var": 3, "length": (1, 1),
     "params": {"magnitude": (3.0, 6.0), "shape": "point", "direction": "positive"}},
    {"type": "spike", "variables": VARS, "n_per_var": 3, "length": (1, 1),
     "params": {"magnitude": (3.0, 6.0), "shape": "point", "direction": "negative"}},
    {"type": "spike", "variables": VARS, "n_per_var": 2, "length": (2, 3),
     "params": {"magnitude": (3.5, 7.0), "shape": "transient", "decay": 0.45,
                "direction": "random"}},

    # --- gradual degradation ---------------------------------------------
    {"type": "drift", "variables": VARS, "n_per_var": 1, "length": (10, 16),
     "params": {"magnitude": (1.5, 3.5), "exponent": 1.0, "direction": "random"}},
    {"type": "drift", "variables": VARS, "n_per_var": 1, "length": (10, 16),
     "params": {"magnitude": (2.0, 4.0), "exponent": 1.6, "direction": "random"}},

    # --- persistent offsets ----------------------------------------------
    {"type": "bias", "variables": VARS, "n_per_var": 1, "length": (8, 14),
     "params": {"magnitude": (0.8, 1.8), "onset": "step", "direction": "positive"}},
    {"type": "bias", "variables": VARS, "n_per_var": 1, "length": (8, 14),
     "params": {"magnitude": (0.8, 1.8), "onset": "ramp", "onset_len": 4,
                "direction": "negative"}},

    # --- frozen sensor ----------------------------------------------------
    {"type": "stuck_at", "variables": VARS, "n_per_var": 1, "length": (6, 9),
     "params": {}},
    {"type": "stuck_at", "variables": VARS, "n_per_var": 1, "length": (10, 14),
     "params": {}},

    # --- variance inflation ----------------------------------------------
    {"type": "noise_burst", "variables": VARS, "n_per_var": 1, "length": (8, 12),
     "params": {"level": "low", "magnitude": (0.9, 1.2)}},
    {"type": "noise_burst", "variables": VARS, "n_per_var": 1, "length": (8, 12),
     "params": {"level": "medium", "magnitude": (0.9, 1.2)}},

    # --- intermittent -----------------------------------------------------
    {"type": "intermittent_spikes", "variables": VARS, "n_per_var": 2, "length": (12, 18),
     "params": {"n_spikes": (3, 5), "min_gap": 2, "magnitude": (3.0, 6.0),
                "direction": "random"}},

    # --- combinations -----------------------------------------------------
    {"type": "drift_plus_noise", "variables": VARS, "n_per_var": 1, "length": (10, 16),
     "params": {"drift": {"magnitude": (1.5, 3.0), "exponent": 1.0,
                          "direction": "random"},
                "noise": {"level": "medium"}}},
    {"type": "bias_plus_spikes", "variables": VARS, "n_per_var": 1, "length": (10, 16),
     "params": {"bias": {"magnitude": (0.8, 1.6), "onset": "step",
                         "direction": "random"},
                "spikes": {"n_spikes": (2, 4), "min_gap": 3,
                           "magnitude": (3.0, 5.5), "direction": "random"}}},
]


# ----------------------------------------------------------------------------
# A. LEGACY BENCHMARK — verbatim port of the original notebook injector
#
# This exists so the Round-1 result (27 episodes, 179 faulty rows, episode
# recall 1.00, test F1 0.3165) stays exactly reproducible. Do NOT "improve" it:
# its whole value is that it is frozen. The RNG call sequence is preserved
# call-for-call, so seed 42 yields the identical dataset.
# ----------------------------------------------------------------------------
LEGACY_MAGNITUDE = {
    "temp_c":  {"spike": (8.0, 20.0),  "bias": (3.0, 8.0),   "drift": (4.0, 10.0),  "noise": (2.0, 5.0)},
    "slp_hpa": {"spike": (10.0, 25.0), "bias": (3.0, 8.0),   "drift": (4.0, 10.0),  "noise": (2.0, 5.0)},
    "rh_pct":  {"spike": (30.0, 60.0), "bias": (10.0, 25.0), "drift": (15.0, 35.0), "noise": (8.0, 15.0)},
}

LEGACY_PLAN = {
    "spike":       {"n_per_var": 5, "len": (1, 1)},
    "stuck_at":    {"n_per_var": 1, "len": (8, 14)},
    "bias":        {"n_per_var": 1, "len": (8, 16)},
    "drift":       {"n_per_var": 1, "len": (12, 20)},
    "noise_burst": {"n_per_var": 1, "len": (8, 14)},
}


def legacy_inject(frame, plan=None, seed: int = 42, variables=None):
    """The original five-class injector, unchanged. `frame` is not modified."""
    plan = plan or LEGACY_PLAN
    variables = list(variables) if variables else list(VARS)
    rng = np.random.default_rng(seed)
    out = frame.copy(deep=True)
    n = len(out)

    labels = pd.DataFrame({
        "is_fault": np.zeros(n, dtype=int),
        "fault_type": np.array(["none"] * n, dtype=object),
        "fault_var": np.array(["none"] * n, dtype=object),
        "episode_id": np.full(n, -1, dtype=int),
    })
    occupied = np.zeros(n, dtype=bool)
    episodes = []

    def reserve(length):
        for _ in range(500):
            start = int(rng.integers(EDGE_MARGIN, n - length - EDGE_MARGIN))
            sl = slice(start, start + length)
            if not occupied[sl].any():
                occupied[sl] = True
                return sl
        return None

    ep_id = 0
    for ftype, spec in plan.items():
        for var in variables:
            for _ in range(spec["n_per_var"]):
                length = int(rng.integers(spec["len"][0], spec["len"][1] + 1))
                sl = reserve(length)
                if sl is None:
                    continue

                vals = out[var].to_numpy(copy=True)
                sign = float(rng.choice([-1.0, 1.0]))
                mag = LEGACY_MAGNITUDE[var]

                if ftype == "spike":
                    amount = sign * rng.uniform(*mag["spike"])
                    vals[sl] += amount
                    detail = f"{amount:+.1f} single-point"
                elif ftype == "stuck_at":
                    held = vals[sl.start - 1]
                    vals[sl] = held
                    detail = f"held at {held:.1f} for {length} obs"
                elif ftype == "bias":
                    amount = sign * rng.uniform(*mag["bias"])
                    vals[sl] += amount
                    detail = f"{amount:+.1f} offset for {length} obs"
                elif ftype == "drift":
                    amount = sign * rng.uniform(*mag["drift"])
                    # ramp anchored so offset 0 lands on the last pre-episode
                    # sample: continuous onset, no unlearnable first row
                    vals[sl] += np.linspace(amount / length, amount, length)
                    detail = f"ramp -> {amount:+.1f} over {length} obs"
                elif ftype == "noise_burst":
                    sigma = rng.uniform(*mag["noise"])
                    vals[sl] += rng.normal(0.0, sigma, size=length)
                    detail = f"added N(0, {sigma:.1f}) for {length} obs"
                else:
                    raise ValueError(ftype)

                if var in PHYSICAL_LIMITS:
                    lo, hi = PHYSICAL_LIMITS[var]
                    vals = np.clip(vals, lo, hi)

                out[var] = vals
                # .iloc not .loc - see module docstring, fix #1
                labels.iloc[sl, labels.columns.get_loc("is_fault")] = 1
                labels.iloc[sl, labels.columns.get_loc("fault_type")] = ftype
                labels.iloc[sl, labels.columns.get_loc("fault_var")] = var
                labels.iloc[sl, labels.columns.get_loc("episode_id")] = ep_id

                episodes.append({
                    "episode_id": ep_id, "fault_type": ftype, "variable": var,
                    "start_idx": int(sl.start), "end_idx": int(sl.stop - 1),
                    "first_modified_idx": int(sl.start),
                    "last_modified_idx": int(sl.stop - 1),
                    "start": out["time"].iloc[sl.start],
                    "end": out["time"].iloc[sl.stop - 1],
                    "window_obs": length, "n_modified": length,
                    "local_sigma": float("nan"), "detail": detail,
                })
                ep_id += 1

    return out, labels, pd.DataFrame(episodes)
