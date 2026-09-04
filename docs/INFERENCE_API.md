# Inference API — dashboard integration guide

**Audience:** Saurabh (dashboard) · **Status:** frozen for the internal SIH presentation

The detector is frozen. This document is everything needed to call it. No ML knowledge required.

---

## 1. Quick start

```bash
pip install scikit-learn==1.9.0 pandas numpy joblib
```

```python
import sys
sys.path.insert(0, "src")
from inference import WeatherFaultDetector

detector = WeatherFaultDetector.load("models/")   # load once at startup, reuse
payload = detector.predict(observations)          # call per request
```

`WeatherFaultDetector.load()` reads ~2.9 MB from disk and takes about a second. **Load it once**
when the dashboard process starts and keep the object around — do not reload per request.

---

## 2. Input format

A list of observations. Each needs a `time` plus the three sensor readings:

```json
[
  {"time": "2023-09-24T00:00:00Z", "temp_c": 42.8, "slp_hpa": 1005.8, "rh_pct": 98.23},
  {"time": "2023-09-24T03:00:00Z", "temp_c": 25.6, "slp_hpa": 1006.2, "rh_pct": 94.51}
]
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `time` | ISO-8601 string / datetime | **yes** | Parsed as UTC. Any offset is converted. |
| `temp_c` | float | yes | Air temperature, °C |
| `slp_hpa` | float | yes | Sea-level pressure, hPa |
| `rh_pct` | float | yes* | Relative humidity, % |
| `dew_c` | float | no | *Send this instead of `rh_pct` and humidity is derived (Magnus), exactly as the training data was built.* |

Accepted as a list of dicts, a list of `Observation` objects, or a `pandas.DataFrame`.
Rows are sorted by time and duplicate timestamps dropped automatically.

The model was trained on **3-hourly** data. Steps between observations at other intervals are
neutralised (set to 0) and the result carries a note.

---

## 3. Output format

See [`examples/sample_output.json`](../examples/sample_output.json) for a complete real response.

```json
{
  "model": { "name": "...", "station": {...}, "frozen_test_metrics": {...}, "scored_at": "..." },
  "results": [ /* one entry per observation, in time order */ ],
  "summary": { "n_observations": 37, "n_anomalies": 18, "alert_rate": 0.4865, "n_degraded": 11,
               "by_fault_type": {...}, "by_variable": {...} }
}
```

Each entry in `results`:

| Field | Type | Meaning |
|---|---|---|
| `timestamp` | string | ISO-8601 UTC, matches the input observation |
| `anomaly` | bool | **The headline verdict.** `true` = flag it |
| `anomaly_score` | float | Higher = more anomalous. Typical range 0.42–0.60 |
| `threshold` | float | The adaptive threshold at this timestamp. `anomaly` is `score > threshold` OR the flat-run rule firing |
| `detector_used` | `"isolation_forest"` \| `"flat_run_rule"` \| `null` | Which detector fired. `null` when not an anomaly |
| `detectors_fired` | array | Both, when both fired. `detector_used` reports `flat_run_rule` in that case (see §5) |
| `fault_type` | string \| `null` | `spike` \| `stuck_at` \| `bias` \| `drift` \| `noise_burst`. **Heuristic — see §6** |
| `fault_type_basis` | string \| `null` | Always `"heuristic_unvalidated"` when a type is given |
| `variable` | string \| `null` | `temp_c` \| `slp_hpa` \| `rh_pct` — the sensor implicated |
| `degraded` | bool | **Read this.** `true` = insufficient context, result is provisional (§4) |
| `notes` | array of strings | Human-readable explanation of any caveat |
| `observation` | object | The input readings echoed back, for display |

---

## 4. The one thing that will surprise you: this is a **batch** detector

The frozen model is **not** a streaming detector. Two parts of it read observations *after*
the point being scored:

- the 24-hour rolling window is **centred** → needs ±12 h;
- the flat-run rule flags a run of ≥8 identical readings → needs up to ±21 h.

**Consequence:** to score a point at full fidelity you must supply roughly **a day of data on
each side of it**.

### What this means in practice

**Send a window, not a point.** A good default is 7 days ending at "now":

```python
window = readings_between(now - timedelta(days=7), now)
payload = detector.predict(window)
```

Observations within 21 h of either end of the batch come back with `degraded: true`.
Everything in the interior is exact.

> **Verified guarantee:** for the interior (non-degraded) rows, this module reproduces the
> notebook's full-series result **exactly**. Confirmed on all 2861 evaluation rows.

### How to render `degraded`

Show the row, but visually distinguish it — greyed out, or an "provisional" badge — and re-score
it once later data arrives. The most recent ~7 observations will always be degraded; that is
inherent to the frozen model, not a bug.

If the dashboard needs a hard verdict with no provisional rows, **display results with a ~24 h
delay**. Making the detector genuinely real-time would require changing the features, which is
outside the frozen scope.

---

## 5. `detector_used` precedence

When both detectors fire on the same row, `detector_used` reports **`flat_run_rule`**, because it
is the more specific and far more precise signal (93 % precision, and it identifies the fault type
definitively). `detectors_fired` always lists everything that fired, if you want to show both.

| Detector | Catches | Precision |
|---|---|---|
| `flat_run_rule` | stuck-at / frozen sensor | 0.93 |
| `isolation_forest` | spikes, offsets, drift, noise | 0.26 |

---

## 6. `fault_type` is a display hint, not a measurement

**Please read this before putting fault labels in front of a judge.**

The frozen model is a **binary** detector: anomaly or not. It was never evaluated as a fault-type
classifier. The `fault_type` field comes from a small rule-based attributor that inspects the
features after the fact, and it has **no measured accuracy**.

- `stuck_at` is trustworthy — it comes directly from the flat-run rule that defines it.
- The other four (`spike`, `bias`, `drift`, `noise_burst`) are informed guesses.
- `fault_type` may be `null` even when `anomaly` is `true`. Render that as "anomaly — type
  unknown", not as an error.

Suggested UI wording: *"likely spike"* rather than *"spike detected"*.

The same applies to `variable`: it is the sensor with the largest deviation, which is usually but
not always the faulty one.

---

## 7. Single-observation convenience

```python
result = detector.predict_one(observation, context=recent_observations)
```

Returns the single result dict rather than the envelope. **Without `context` the result will be
`degraded`** — there is no way around this given the frozen feature set. Prefer `predict()` with a
window.

---

## 8. Suggested dashboard wiring

```python
# --- startup ---------------------------------------------------------------
from inference import WeatherFaultDetector
DETECTOR = WeatherFaultDetector.load("models/")

# --- request handler -------------------------------------------------------
@app.get("/api/anomalies")
def anomalies(start: str, end: str):
    obs = db.fetch_observations(start, end)      # your data source
    if not obs:
        return {"results": [], "summary": {"n_observations": 0, "n_anomalies": 0}}
    payload = DETECTOR.predict(obs)
    return payload                               # already JSON-serialisable
```

The returned payload contains only JSON-native types — pass it straight through
`json.dumps` / FastAPI / Flask `jsonify` with no conversion.

### Performance

Scoring is vectorised over the batch. A 7-day window (56 observations) returns in well under a
second on a laptop; a full year (2861 observations) takes about a second. Batch generously rather
than looping per observation — calling `predict()` 56 times is far slower *and* gives worse results,
because each call would lack context.

### Colour suggestion

| Condition | Treatment |
|---|---|
| `anomaly: false` | normal |
| `anomaly: true`, `detector_used: "flat_run_rule"` | red — high confidence |
| `anomaly: true`, `detector_used: "isolation_forest"` | amber — lower precision |
| `degraded: true` | reduced opacity + "provisional" badge, any of the above |

---

## 9. Verifying nothing has drifted

```bash
python3 src/inference.py
```

Replays all 2861 evaluation rows through the module and asserts it reproduces the notebook's
features, scores and predictions. Exit code 0 = frozen model intact. Run it after any dependency
change; it is the guard that "frozen" actually means frozen.

Expected output:

```
parity check against 2861 notebook rows
  PASS  all 16 features (largest deviation 1.56e-09 on temp_c_roll_std)
  PASS  anomaly_score
  PASS  adaptive_threshold
  PASS  isolation_forest_pred (exact)
  PASS  flat_run_rule (exact)
  PASS  hybrid_pred (exact)

PARITY OK — module reproduces the frozen notebook model
```

---

## 10. Files

| Path | Purpose |
|---|---|
| `src/inference.py` | The module. The only file the dashboard imports |
| `models/isolation_forest.joblib` | Frozen model (200 trees) |
| `models/pipeline_state.joblib` | Climatology, feature list, frozen fill constants |
| `models/score_history.csv` | 2023 scores, warm-starts the adaptive threshold |
| `models/manifest.json` | Model metadata, frozen metrics, caveats |
| `models/parity_fixture.csv` | Expected outputs for the parity check |
| `examples/sample_input.json` | Example request |
| `examples/sample_output.json` | Example response |

`models/` is regenerated only by the appendix cell of
`notebooks/02_ml_anomaly_detection.ipynb`. Do not hand-edit it.

---

## 11. Honest performance caveats

Numbers on the hold-out test period, against synthetic faults:

| Metric | Value |
|---|---|
| Precision | 0.259 |
| Recall | 0.407 |
| F1 | 0.317 |
| Alert rate | 9.9 % |
| **Episode recall (all 5 fault classes)** | **1.00** |

**Precision of 0.26 means roughly 3 in 4 alerts are false positives at the row level.** Do not
present this as a production-ready system.

The number worth quoting is **episode recall: every injected fault episode was detected**. Row-level
precision is low because the detector fires repeatedly around a fault and on ordinary weather
extremes; episode-level, it caught everything.

Also true, and worth stating if asked:

- `contamination` was set from the true injected fault rate — an oracle unavailable in production,
  so real precision would be lower.
- Evaluated on **synthetic** faults only, one station, one year, one random seed.
- The 13 candidate windows from the EDA are anomalous in the original data but labelled clean, so
  reported precision is slightly pessimistic.
