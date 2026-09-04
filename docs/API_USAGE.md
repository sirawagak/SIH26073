# API usage guide

**Audience:** Saurabh (frontend) · **Status:** frozen model, thin HTTP layer

HTTP wrapper around the frozen weather-sensor fault detector. Two endpoints. The API validates
your request, calls the existing detector, and returns its output unchanged.

For what the fields *mean* and the modelling caveats, see
[`INFERENCE_API.md`](INFERENCE_API.md). This document covers only calling it over HTTP.

---

## 1. Install

From the repository root:

```bash
pip install -r api/requirements.txt
```

`scikit-learn` is pinned to `1.9.0` because the frozen model is unpickled with it. If you change
that version, re-run `python3 src/inference.py` before trusting any prediction.

---

## 2. Start the server

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Add `--reload` while developing. On startup you should see:

```
INFO:     loading frozen detector from /path/to/models
INFO:     detector loaded in 0.624s (load #1) | 16 features | 200 trees
INFO:     Application startup complete.
```

**`load #1` should appear exactly once.** The model is loaded at startup and reused for every
request; if you ever see `load #2`, something is restarting the app.

Interactive docs (Swagger UI) are generated automatically at <http://127.0.0.1:8000/docs>.

---

## 3. `GET /health`

Liveness probe. No body.

```bash
curl http://127.0.0.1:8000/health
```

```json
{ "status": "ok" }
```

Always `200` while the process is up. It does **not** check whether the model loaded — if loading
failed, `/health` still returns `ok` but `/predict` returns `503`. Poll `/predict` if you need a
readiness signal.

---

## 4. `POST /predict`

### Request

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  -d @examples/sample_input.json
```

```json
{
  "observations": [
    {"time": "2023-09-24T00:00:00Z", "temp_c": 42.8, "slp_hpa": 1005.8, "rh_pct": 98.23},
    {"time": "2023-09-24T03:00:00Z", "temp_c": 25.6, "slp_hpa": 1006.2, "rh_pct": 94.51}
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `observations` | array | **yes** | 1 to 20,000 items |
| `observations[].time` | ISO-8601 string | **yes** | Parsed as UTC |
| `observations[].temp_c` | float | **yes** | °C |
| `observations[].slp_hpa` | float | **yes** | hPa |
| `observations[].rh_pct` | float | yes\* | % — \*or send `dew_c` instead |
| `observations[].dew_c` | float | no | °C; humidity derived via Magnus if `rh_pct` absent |
| `include_features` | bool | no | Attach the 16 model features per row (debugging) |

Unknown fields are rejected, so a typo like `tempc` fails loudly rather than being silently ignored.

### Send a window, not a point

This is a **batch** detector. Rows within 21 hours of either end of your window come back with
`degraded: true`, because their features are computed from a truncated context window.

**Send about 7 days per call.** The interior rows are then exact — verified to reproduce the
notebook's full-series result. If you send fewer than 15 observations, every row will be degraded
and the response carries a `summary.warnings` entry saying so.

### Response

`200 OK`. The body is the detector's own output, unchanged:

```json
{
  "model": {
    "name": "sih26073-weather-fault-detector",
    "detector": "isolation_forest + flat_run_rule (hybrid)",
    "threshold_mode": "adaptive_rolling_quantile",
    "station": { "id": "42182099999", "name": "New Delhi / Safdarjung (VIDD)" },
    "frozen_test_metrics": { "precision": 0.2588, "recall": 0.4074, "f1": 0.3165,
                             "alert_rate": 0.099, "episode_recall_all_classes": 1.0 },
    "scored_at": "2026-09-04T12:13:35Z"
  },
  "results": [
    {
      "timestamp": "2023-09-25T21:00:00Z",
      "anomaly": true,
      "anomaly_score": 0.439837,
      "threshold": 0.502695,
      "detector_used": "flat_run_rule",
      "detectors_fired": ["flat_run_rule"],
      "fault_type": "stuck_at",
      "fault_type_basis": "heuristic_unvalidated",
      "variable": "temp_c",
      "degraded": false,
      "notes": [],
      "observation": { "temp_c": 27.0, "slp_hpa": 1006.0, "rh_pct": 85.71 }
    }
  ],
  "summary": {
    "n_observations": 37, "n_anomalies": 18, "alert_rate": 0.4865, "n_degraded": 11,
    "window": { "start": "2023-09-24T00:00:00Z", "end": "2023-09-28T21:00:00Z" },
    "by_fault_type": { "stuck_at": 15, "spike": 1, "bias": 1, "unattributed": 1 },
    "by_variable": { "temp_c": 16, "rh_pct": 2 }
  }
}
```

A full example lives at [`examples/sample_output.json`](../examples/sample_output.json).

`results` is in time order and always the same length as `observations`, unless duplicate
timestamps were sent (they are de-duplicated, first kept).

---

## 5. Errors

Every error body has the same shape: an `error` code, a human `message`, and often a `hint`.

| Status | `error` | When |
|---|---|---|
| `422` | `validation_failed` | Missing/invalid field, empty list, unknown field, malformed JSON |
| `400` | `bad_observations` | Body was well-formed but the detector rejected it (e.g. unparseable `time`) |
| `404` | — | Unknown route |
| `405` | — | Wrong HTTP verb |
| `500` | `inference_failed` | Unexpected error inside the detector |
| `503` | `model_unavailable` | Model failed to load at startup |

`422` responses list every problem at once, with the offending path:

```json
{
  "error": "validation_failed",
  "message": "1 problem(s) in the request body.",
  "problems": [
    { "field": "observations.0", "message": "'temp_c' is required", "type": "value_error" }
  ],
  "expected_format": { "observations": [ { "time": "...", "temp_c": 25.8, "slp_hpa": 1005.1, "rh_pct": 90.36 } ] },
  "docs": "docs/API_USAGE.md"
}
```

### Validation is deliberately permissive on magnitude

Range checks are wide (`temp_c` −100…100 °C, `slp_hpa` 500…1200 hPa) because **a faulty sensor is
what this service exists to detect**. A 42.8 °C spike or a 60 hPa offset must reach the model, not
be rejected at the door. The bounds catch unit errors and corrupt values only.

---

## 6. Calling it from the frontend

```javascript
const API = "http://127.0.0.1:8000";

async function fetchAnomalies(observations) {
  const res = await fetch(`${API}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ observations }),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.message ?? `Request failed: ${res.status}`);
  }
  return res.json();
}
```

Rendering suggestion:

```javascript
const { results, summary } = await fetchAnomalies(weekOfObservations);

for (const r of results) {
  if (!r.anomaly)                                 style = "normal";
  else if (r.detector_used === "flat_run_rule")   style = "red";    // high confidence
  else                                            style = "amber";  // lower precision
  if (r.degraded) style += " provisional";        // reduced opacity + badge
}
```

Two points worth honouring in the UI:

- **`degraded: true` means provisional.** The most recent ~7 observations will always be degraded.
  Grey them out or badge them, and re-fetch once later data arrives — do not hide them.
- **`fault_type` is a display hint, not a measurement.** It carries
  `fault_type_basis: "heuristic_unvalidated"` and was never evaluated. Prefer *"likely spike"* over
  *"spike detected"*. It can be `null` on a real anomaly — render that as "type unknown", not as an
  error.

### CORS

Not enabled. If the frontend is served from a different origin, add:

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
```

I have left it out rather than guess your dev-server origin, and a blanket `allow_origins=["*"]`
is not something to ship by default.

### Performance

Measured on this machine, model already warm:

| Payload | Latency |
|---|---|
| 37 observations (~5 days) | ~0.010 s |
| 2861 observations (full year) | ~0.124 s |

Batch generously. One call with a week of data is faster *and* more accurate than 56 single-point
calls, which would each lack context and return `degraded`.

---

## 7. Limitations

- **Single worker assumed.** Running `uvicorn --workers N` loads a separate copy of the model per
  worker (~2.9 MB each). Fine, but each process loads once.
- **No authentication, no rate limiting, no HTTPS.** Prototype for the internal presentation; bind
  to `127.0.0.1` and do not expose it publicly.
- **Stateless.** The API keeps no history between calls. Each request is scored using only the
  observations in that request, plus the 2023 score history frozen into `models/`.
- **Trained on one station** (Safdarjung/VIDD) and one year. Applying it to another station's feed
  is untested.
- **Row-level precision is 0.26** — roughly 3 in 4 row-level alerts are false positives. The
  defensible headline is **episode recall 1.00**: every injected fault episode was detected. See
  [`INFERENCE_API.md`](INFERENCE_API.md) §11.
