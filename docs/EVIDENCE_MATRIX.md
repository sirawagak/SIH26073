# SkyGuard AI — Evidence Matrix

**Purpose.** The source of truth for what SkyGuard may claim in Round 2, and in what words.
Every entry is graded and traceable. If a claim is not in this file at level A or B, it should not
appear in the PPT, README, demo script, or an answer to a judge.

**Status.** Evidence audit only. No code, model, schema, API, frontend or configuration was changed
to produce it.

## Evidence levels

| | Meaning |
|---|---|
| **A** | **Directly verified** — observed and reproducible from a committed artefact |
| **B** | **Strongly supported** — multiple experiments agree, one important limitation remains |
| **C** | **Promising / partial** — real evidence, incomplete or narrow |
| **D** | **Hypothesis** — reasonable, not demonstrated |
| **E** | **Rejected** — tested and not supported |

## The single most important caveat

**Every detection number in this document comes from *synthetic injected faults*.** No real,
field-labelled sensor failure has ever been scored by this system. That is a property of the
available data, not an oversight — and it caps the strongest honest claim at
*"validated under controlled simulation"*.

---

## Domain 1 — Core detection

| Claim | Source | Metric | Dataset | Limitation | Level |
|---|---|---|---|---|---|
| Detects injected sensor anomalies | nb02 Stage 6 | P 0.2588 · R 0.4074 · **F1 0.3165** · alert 9.9 % | Safdarjung 2023, 30 % hold-out | Synthetic faults; `contamination` set from the true rate (oracle) | **A** |
| Every injected episode detected on the hold-out | nb02 Stage 6 | episode recall **1.00** (5/5 classes) | same | Chance floor 0.35–0.45 at this alert rate — roughly half is reachable at random | **B** |
| Spike detection | nb03, nb06 | episode recall 0.875–0.917 | challenge set, 5 seeds | Single-point; easiest class | **A** |
| Stuck-at detection | nb03, nb09 | 0.833–0.967 | challenge, 8 stations | **Blind to freezes shorter than the run threshold on high-precision variables** (rh_pct) | **A** |
| Drift detection | nb03, nb08 | 0.604 → **0.736** with `clim_short` | station-OOD | Slow drift is the hardest persistent class | **B** |
| Bias detection | nb04, nb08 | 0.326 → **0.444** with `clim_short` | station-OOD | Was **below chance** (0.500 vs 0.638) in the baseline; still the weakest class | **B** |
| Noise-burst detection | nb03, nb06 | 0.660–0.867 | challenge, 5 seeds | Degraded slightly by `acc_w4`; unaffected by `clim_short` | **B** |
| Compound faults (drift+noise, bias+spikes) | nb03, nb06 | 0.800–1.000 | challenge, 5 seeds | Detected via their *transient* component, not the persistent one | **B** |
| Adaptive rolling-quantile threshold beats a fixed one | nb06 | alert-rate sd **9.32 pp → 2.85 pp**; FP 175 → 63 | Safdarjung test split | Threshold **rises with a persistent fault**, absorbing 24–30 % of the signal | **A** |
| Flat-run rule catches frozen sensors the forest cannot | nb04, nb05 | rule recall **1.00** at 93 % precision; IF recall **0.00** | challenge set | Hard minimum-length rule; misses short freezes | **A** |
| Isolation Forest is structurally blind to a constant offset | nb04 | 15 of 16 features unmoved; only `clim_dev` responds (3.3–5.1σ, consistency **1.00**) | bias sweep, 1080 episodes | — | **A** |

---

## Domain 2 — Cross-sensor context

**Claim under test:** *"SkyGuard uses cross-sensor contextual information rather than treating each
variable independently."*

`clim_short = max over {temperature, pressure, RH} of |climatological deviation|`.

### The decisive test — single-variable ablation (station-OOD, nb08)

| Condition | F1 | Δ vs baseline | Episode recall |
|---|---|---|---|
| **max over all three (`clim_short`)** | **0.4356** | **+0.0152** | **0.7559** |
| temperature only | 0.4171 | −0.0033 | 0.6989 |
| pressure only | 0.4139 | −0.0065 | 0.6732 |
| RH only | 0.4086 | −0.0118 | 0.6919 |

**Every single-variable variant is *worse than baseline*. Only the cross-sensor maximum improves it.**
The benefit is in the aggregation, not in any one sensor. **Level A.**

### Contribution share — no variable dominates

| Station | temp % | pressure % | RH % | ties |
|---|---|---|---|---|
| Safdarjung | 30.8 | 38.3 | 30.8 | 0 |
| Patiala | 28.3 | 38.7 | 33.0 | 0 |
| Guwahati | 30.2 | 37.0 | 32.8 | 0 |
| Ahmedabad | 31.8 | 35.5 | 32.7 | 0 |
| Kolkata | 33.1 | 35.2 | 31.7 | 0 |
| Mumbai | 31.3 | 37.7 | 31.0 | 0 |
| Chennai | 34.4 | 32.8 | 32.8 | 0 |
| Thiruvananthapuram | 31.6 | 35.5 | 32.9 | 0 |

Across eight stations spanning 8.5°N–30.3°N the three sensors contribute **28–39 % each**. This
directly refutes *"it is a disguised temperature-anomaly score."* **Level A.**

### Station stability — and the caveat that must travel with it

| Year | mean of per-station medians | sd | **CV** |
|---|---|---|---|
| **2023** (climatology fitted here) | 1.084 | 0.026 | **0.024** |
| **2024** (out-of-sample) | 1.850 | 0.150 | **0.081** |

**Stable across stations within the fitted year. It roughly doubles out-of-sample.** The
"CV = 0.024" figure is in-sample and must never be quoted without the 2024 row. **Level B.**

### OOD performance (nb08)

| Condition | in-domain | temporal OOD | station OOD |
|---|---|---|---|
| baseline16 | 0.4627 | 0.4214 | 0.4204 |
| **clim_short17** | **0.5064** | **0.4334** | **0.4356** |
| dual18 (ref) | 0.5513 | 0.4206 | 0.4263 |

Improves in all three regimes. **Level B** (synthetic faults; 8 Indian stations; 2 years).

> **Wording.** Call this **a SkyGuard design feature**. No literature comparison was performed, so
> "novel", "first", or "state of the art" are **unsupported**.

---

## Domain 3 — Station-aware calibration

**Claim:** *"Station-specific calibration is necessary because climatological behaviour differs
materially between stations."* — **Level A.**

Transferring Delhi's climatology to another station inflates mean `|clim_dev|` by:

| Station | inflation | | Station | inflation |
|---|---|---|---|---|
| Patiala | **1.45×** | | Kolkata | 2.14× |
| Guwahati | 1.90× | | Chennai | 2.83× |
| Ahmedabad | 2.51× | | Mumbai | 3.31× |
| | | | Thiruvananthapuram | **3.61×** |

That inflation is a constant geographic offset, not an anomaly signal — a transferred climatology
would measure geography.

**Exactly what the held-out station may contribute at inference (nb07/08/09 protocol):**

| Allowed | Forbidden |
|---|---|
| Its own **prior-year (2023)** climatology (per day-of-year × hour) | Any test-year (2024) row in any fitting step |
| Its own prior-year `roll_std` NaN-fill constants | Any fault label, ever |
| Trailing, past-only threshold history within the scored window | Any future row relative to the scored point |

This is site calibration from history — the same thing you would do when commissioning a sensor —
and it contains no test-period information.

**Pipeline parity:** the multi-station feature builder reproduces production **exactly**
(max |diff| = **0.00e+00** with the frozen climatology). **Level A.**

---

## Domain 4 — Generalization

| Condition | in-domain | temporal OOD | station OOD | gap (temporal) | gap (station) |
|---|---|---|---|---|---|
| **baseline16** | 0.4627 | 0.4214 | 0.4204 | **0.0413** | **0.0423** |
| **clim_short17** | **0.5064** | **0.4334** | **0.4356** | 0.0730 | 0.0708 |
| **dual18** | 0.5513 | 0.4206 | 0.4263 | **0.1307** | **0.1250** |

**Three statements that must always travel together:**

1. **`dual18` is REJECTED as a general improvement (Level E).** Its in-domain gain (+0.090) collapses
   to +0.009 OOD, its gap is ~3× baseline's, and it raises false alarms on unseen data.
2. **`clim_short17` improves all three regimes (Level B)** — and is significant at every training
   size (p = 0.0013–0.026, nb09).
3. **`clim_short17` still has a LARGER generalization gap than baseline** (0.071 vs 0.042). It is
   smaller than `dual18`'s, not smaller than baseline's. Stating otherwise is an overclaim.

**Station-count sweep (nb09) — Level A, negative result.** Training on 2 → 7 stations changes OOD F1
by **+0.006** (baseline, p = 0.022) and **+0.003** (clim_short, **p = 0.17, not significant**), against
a within-cell sd of 0.0297. Cross-station spread does not shrink. **More stations do not close the gap
— this is a representation limit, not a data-volume limit.**

**Replication caveat — Level A.** nb08 reported `clim_short` improving **8/8** stations. With new
fault seeds in nb09 it was **6/8**. Per-station sd is 0.0206 against a +0.0093 effect, so a single
station carries a 95 % interval of **±0.0404 — 4.3× the effect**. **The "8/8" claim must be retired;**
the pooled paired effect is what replicates.

---

## Domain 5 — Fault-injection validity

| Property | Evidence | Level |
|---|---|---|
| 8 fault classes | spike, drift, bias, stuck_at, noise_burst, intermittent_spikes, drift+noise, bias+spikes | **A** |
| Realistic variants | transient decay, accelerating drift, ramped-onset bias, low/med/high noise, sign control | **A** |
| Magnitudes are variable-relative | local σ: temp 4.78 · pressure 2.41 · RH 17.73 — never one absolute number | **A** |
| Reproducible | fixed seed → identical data and labels; different seed → different data | **A** |
| Multi-seed evaluation | 3–5 seeds per experiment; nb09 used 768 OOD evaluations | **A** |
| Labelling correctness | **22/22** checks in `tests/test_fault_injection.py` | **A** |
| No label leakage | every modified row labelled; every labelled row modified; no writes outside an episode | **A** |
| Round-1 benchmark preserved | 27 episodes / 179 rows reproduced bit-for-bit | **A** |
| Chance-floor honesty | episode recall floor 0.35–0.45 reported alongside every figure | **A** |

### What this evidence can and cannot prove

| **CONTROLLED SIMULATION EVIDENCE** (what we have) | **REAL MAINTENANCE VALIDATION** (what we do not have) |
|---|---|
| The detector separates injected corruption from this station's normal behaviour | That it detects a real failing thermistor, radiation-shield fault, or ageing hygrometer |
| Relative comparison between feature sets is sound | Any absolute real-world precision or recall |
| Failure *mechanisms* are diagnosed (e.g. constant offsets cancel in 15 of 16 features) | That real faults resemble the injected ones |
| Behaviour transfers across 8 Indian stations and 2 years | Behaviour outside that envelope |

> **Never say** "X % accurate at detecting sensor faults." **Say** "validated on controlled injected
> faults across 8 stations; real-world performance is unmeasured."

---

## Domain 6 — Explainability

What a single result can honestly explain **today**, with no new work and no invented attribution:

| Element | Present | What it honestly supports | Level |
|---|---|---|---|
| `anomaly_score` + `threshold` | yes | "how far past its own moving decision line" | **A** |
| `detector_used` / `detectors_fired` | yes | which of the two mechanisms fired | **A** |
| `variable` | yes | which sensor carried the largest deviation | **B** — largest ≠ definitively faulty |
| `observation` | yes | the raw readings behind the alert | **A** |
| `notes` | yes | plain-language context caveats (truncated window, non-nominal interval) | **A** |
| `degraded` | yes | whether the verdict is provisional | **A** |
| `fault_type` | yes | a **heuristic** label, tagged `heuristic_unvalidated` | **C** — never evaluated as a classifier |
| Per-feature attribution | **no** | — | **D** — would need SHAP or similar; none exists |
| Counterfactual ("it would be normal if…") | **no** | — | **D** |

**Level B overall.** SkyGuard can explain *which mechanism fired, on which sensor, how far past
threshold, and how reliable the verdict is*. It **cannot** currently say *which feature drove the
score*. Do not imply otherwise.

---

## Domain 7 — Fault evolution

| Capability | Evidence today | Level |
|---|---|---|
| Fault onset is detectable | nb04: onset row flagged **1.6–2.9×** more often than a persistent row | **A** |
| Persistent state is also detectable | persistent rows above the 0.077 floor from ~1σ | **A** |
| Detection delay measurable per family | nb06/07: transient median **0 obs**; persistent median **1 obs** (×3 = 3 h) | **B** |
| Delay as a headline metric | **Uninformative as currently aggregated** — 0.0 in every headline row because transients dominate the median | **C** |
| Drift progression measurable | nb04: dose-response across 0.5σ–4σ, monotonic | **A** |
| Early warning before threshold crossing | **not demonstrated** | **D** |
| **"Fault evolution timeline" UI** | **not implemented** | **D — hypothesis** |

Everything needed for a timeline (per-row score, threshold, degraded, detector, notes) is already in
the `/predict` payload, so a timeline view needs **no detector change**. But "early warning" — flagging
a fault *before* it crosses threshold — is unbuilt and unvalidated.

---

## Domain 8 — Data quality vs sensor fault

| Condition | Handled today | How | Level |
|---|---|---|---|
| Missing values (isolated) | yes | time-interpolation, `limit=2` (≤ 6 h) | **A** |
| Irregular sampling | yes | `gap_hours`; step features **blanked** when the interval ≠ 3 h | **A** |
| Communication gaps / dropout | **partly** | missing rows are simply absent; affected rows carry the note *"preceding interval is not the nominal 3h; step features set to 0"* — verified by injecting an 18 h gap | **B** |
| Repeated / frozen values | yes | flat-run rule, ≥ 8 identical readings | **A** |
| Genuine sensor anomalies | yes | Isolation Forest on 16 features | **A** |
| **Explicit gap-vs-fault classification** | **no** | a gap is neutralised, never *reported as* a data-quality event | **D** |

**This is the cleanest low-risk differentiator available.** The distinguishing information already
exists inside the pipeline (`gap_hours`, the note text, the flat-run flag); what is missing is
*surfacing* it as a separate category. That is application work, not ML work — **no detector change
required**.

---

## Domain 9 — Working prototype

| Component | Evidence | Level |
|---|---|---|
| React 19 + TS + Vite frontend | builds clean; 5 static pages ported verbatim; verified in a real browser | **A** |
| FastAPI backend | running; `/health` 200; routers mounted | **A** |
| PostgreSQL 17.11 | db `skyguard`, 3 tables, 1 Alembic revision, FK + unique constraints verified | **A** |
| SuperTokens auth | signup/signin/signout verified; httpOnly cookies issued | **A** |
| ML service boundary | `LocalDetectorService` satisfies the `MLService` Protocol; delegates verbatim | **A** |
| Authenticated `/api/v1/predict` | **byte-identical** to `examples/sample_output.json` | **A** |
| RBAC enforced server-side | VIEWER → 403 on admin route; **role cannot be forged via headers** | **A** |
| Dashboard shows real ML values | browser: score 0.4428 vs threshold 0.5066, `model 6ceeb2e79213` | **A** |
| Model versioning | content hash of 3 artefacts → `6ceeb2e79213`; no frozen file modified | **A** |
| Test suite | **13/13 passing** (`tests/test_slice1.py`) | **A** |
| **Production readiness** | — | **E — explicitly unsupported.** Demo core, no HTTPS, no `Secure` cookies, 12-month sessions, default DB password |

---

## Domain 10 — Demo risks

| Item | Current state | Risk | Evidence | Recommended action |
|---|---|---|---|---|
| Degraded window | **30 %** of rows provisional (11/37) | Judges see caveats on the newest data | `summary.n_degraded` | Explain the ±21 h context need up front; show a historical window where the interior is exact |
| High alert rate | **48.6 %** on the demo sample | Looks broken | `summary.alert_rate` | Use a quiet window for the headline; keep the fault-dense one for the fault demo, labelled |
| Replay vs streaming | Historical replay only | "Is this live?" | centred 24 h window + flat-run need future rows | State plainly it is an offline/batch detector by design |
| Dashboard simulator | **Not ported to React** | The most persuasive interaction is missing | `dashboard/index.html` has fault buttons; React does not | Port as an explicitly labelled `DemoSimulator`, write-path disabled |
| API availability | Manual start | Demo-day failure | two processes + Postgres + `LC_ALL` | One documented start script; rehearse cold |
| Authentication demo | Works | Depends on `try.supertokens.com` | public demo core | Have a recorded fallback; register accounts before the demo |
| Cold start | Detector loads in ~1.1–1.6 s | First request slow | startup log | Warm it before presenting |
| Threshold warm-up | 80-observation `min_periods` | Early rows use a fixed fallback | `score_history.csv` warm start | Use a window long enough to be past warm-up |

---

## Domain 11 — Security

| Finding | Evidence | Risk | Level |
|---|---|---|---|
| Cookies lack `Secure` | `HttpOnly; Path=/; SameSite=lax` | High in production, N/A on localhost | **A** |
| anti-CSRF not explicit | only `cookie_same_site="lax"` | Medium — SameSite is the sole defence | **A** |
| Demo SuperTokens core | `try.supertokens.com` | High — shared, rate-limited, data wiped | **A** |
| Session lifetime 12 months | `sAccessToken expires 2027-09-16` | Medium | **A** |
| DB password default in source | `app/core/config.py:20` | Medium | **A** |
| CORS correct | foreign origin rejected; `localhost:5173` allowed with credentials | — verified sound | **A** |
| Role forgery blocked | `X-Role: ADMIN` header → still 403 | — verified sound | **A** |
| No credential exposure | zero token headers; no password/hash/token strings in `/me` | — verified sound | **A** |
| `.env` gitignored | `git check-ignore` confirms | — verified sound | **A** |

---

## Domain 12 — Differentiation

| # | Candidate | What exists now | Evidence | What is missing | Dependency | Demo potential | Overclaim risk |
|---|---|---|---|---|---|---|---|
| 1 | **Station-aware calibration** | **Built and required** | **A** — 1.45–3.61× inflation if transferred | Nothing technical; only framing | none | Moderate | **Low** |
| 2 | **Cross-sensor contextual reasoning** | **Built** (`clim_short`, experimental) | **A** — every single-variable variant is worse than baseline; 28–39 % share each | Not in production; larger gap than baseline | integration only | Good | **Low–medium** |
| 3 | Fault evolution / early warning | Per-row score/threshold history | **A** onset vs persistent; **D** early warning | Timeline UI; predictive claim unvalidated | app work only | **Strong** | **High** if called "prediction" |
| 4 | Explainable anomaly reasoning | score, threshold, detector, variable, notes | **B** for mechanism; **D** for attribution | Feature attribution | SHAP or similar | **Strong** | **High** |
| 5 | **Data-quality vs sensor-fault separation** | `gap_hours`, notes, flat-run already distinguish them | **B** | Surfacing them as a category | **app work only — no ML change** | Good | **Low** |
| 6 | Confidence calibration | raw scores only | **D** | Reliability curves | needs labels for real calibration | Moderate | Medium |
| 7 | Operator-facing maintenance evidence | investigation schema designed | **D** | Everything | **real outcomes** | Good | High |
| 8 | Fault diagnosis after detection | heuristic `fault_type` | **C** | A validated classifier | **real labelled faults** | Good | **Highest** |

---

## CLAIM REGISTER

| Claim | Level | Source | **Safe wording** | **Do not say** |
|---|---|---|---|---|
| Detects sensor anomalies | **A** | nb02 | "Detects injected sensor anomalies; F1 0.3165 on a held-out split" | "Detects sensor faults with high accuracy" |
| Every fault episode caught | **B** | nb02 | "Episode recall 1.00 on the hold-out, against a 0.35–0.45 chance floor" | "Catches 100 % of faults" |
| Cross-sensor context helps | **A** | nb08 | "A cross-sensor design feature: the max over three sensors beats every single-variable variant, each of which is worse than baseline" | "Novel", "first", "state of the art" |
| Station calibration is required | **A** | nb07 | "Transferring one station's climatology inflates deviations 1.45–3.61×" | "Works anywhere out of the box" |
| Generalises across stations | **B** | nb07–09 | "Evaluated on 8 Indian stations and 2 years with leave-one-station-out; OOD F1 ≈ 0.42–0.44" | "Generalises to any weather station" |
| `clim_short` improves OOD | **B** | nb08, nb09 | "+0.009 to +0.015 OOD F1, significant at every training size, near-zero FPR cost" | "Large improvement" · "8/8 stations" |
| `clim_short` gap vs baseline | **A** | nb08 | "Smaller gap than dual18; **still larger than baseline** (0.071 vs 0.042)" | "Best generalization" |
| `dual18` is an improvement | **E** | nb07 | — rejected | "Dual-timescale improves the detector" |
| Training diversity closes the gap | **E** | nb09 | — rejected (p = 0.17) | "More stations will fix generalization" |
| Immune adaptive threshold | **E** | nb05 | — rejected (clean FPR 7.7 % → 36.8 %) | anything positive |
| Adaptive threshold helps | **A** | nb06 | "Alert-rate variability 9.32 → 2.85 pp; 64 % fewer false positives" | "Eliminates false alarms" |
| Flat-run rule catches frozen sensors | **A** | nb04–05 | "Recall 1.00 at 93 % precision, where the forest scores 0.00" | "Catches all stuck sensors" |
| Fault type identified | **C** | `fault_type_basis` | "A heuristic label, never evaluated as a classifier" | "Classifies the fault type" |
| Explains its alerts | **B** | payload | "Reports score, threshold, which detector fired, which sensor, and reliability" | "Explainable AI" · "shows why" |
| Real-time monitoring | **E** | design | "Offline/batch detector; needs ~21 h of context each side" | "Real-time" · "live streaming" |
| Predicts failures | **D** | — | — do not claim | "Predictive maintenance" · "forecasts failures" |
| Working full-stack prototype | **A** | 13/13 tests + browser | "Working prototype: React + FastAPI + PostgreSQL + SuperTokens, 13/13 tests" | "Production-ready" · "deployed" |
| Production ready | **E** | Domain 11 | — | "Production-grade" · "secure" · "scalable" |
| Validated on real sensor failures | **E** | — | "Validated under controlled simulation; real-world validation is outstanding" | "Field-validated" · "proven in production" |
