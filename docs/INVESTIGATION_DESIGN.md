# Investigation workflow — design proposal

**Status:** DESIGN ONLY, for independent review. Nothing here is implemented. No migration, model or
route exists yet.
**Scope:** DETECT → INVESTIGATE → HUMAN VERIFY → RECORD OUTCOME, built around the frozen detector.
**Out of scope:** changes to `src/inference.py`, `models/`, the `/api/v1/predict` contract, the
existing `users` / `roles` / `user_roles` tables, and the security findings in
`EVIDENCE_MATRIX.md` Domain 11 (they are noted where they affect this design, not fixed).

---

## 0. What the current application gives us

Read from the code, not assumed:

| Fact | Where | Consequence for this design |
|---|---|---|
| Identity is resolved server-side from the SuperTokens session to a `users` row on every request | `app/core/deps.py::current_user` | Reviewer and creator ids can come from the session alone |
| Roles are read from PostgreSQL on every request, never from headers or token claims | `deps.py`, `test_role_is_not_client_controllable` | A revoked role takes effect on the next request |
| Four roles already exist: `ADMIN`, `SCIENTIST_REVIEWER`, `STATION_OPERATOR`, `VIEWER` | `app/rbac/roles.py` | **No new reviewer role is needed** (see §4) |
| Sign-up assigns `VIEWER` by default | `repository.py::create_user` | Anyone who can register is a VIEWER, so VIEWER must stay read-only |
| `ADMIN` is granted `set(Permission)` — every permission, including any added later | `roles.py` | Must change to an explicit set, or ADMIN silently gains review rights |
| Placeholder permissions `VIEW_INVESTIGATIONS`, `REVIEW_ASSIGNED`, `MANAGE_INVESTIGATIONS`, `VIEW_AUDIT` exist but nothing enforces them | `grep` across `app/`, `tests/`, `frontend/src` | They can be re-used or retired without breaking callers |
| `/predict` scores **whatever observations the browser sends** | `app/api/v1/predict.py` | Evidence must **not** be accepted from the browser (§6, §9) |
| The server holds its own real observations: 8 NOAA ISD stations × 2023–2024, 3-hourly, full precision, with a manifest | `data/processed/stations/` | The server can rebuild the evidence window itself |
| The browser's demo window is the 2023 VIDD file rounded to 1 decimal of RH | `frontend/public/station_window.json` vs `42182099999_2023.csv` | A browser-side detection is a *pointer*, not evidence |
| Real sampling irregularities exist in that file: 37 × 6 h, 3 × 12 h and 1 × 42 h intervals | same CSV | Data-quality flags have real cases to show |
| The detector marks `degraded` and writes free-text `notes` (context too short; "preceding interval is not the nominal 3h") | `src/inference.py` L345–361 | Data-quality facts should be computed as structured fields, not parsed from note text |

### A measured fact that drives the evidence design

The detector's **verdict depends on the window it is given**, because the adaptive threshold is a
trailing 30-day quantile over the scores in that window. I checked this read-only, without changing
any code (method in Appendix A):

| Window rebuilt around a flagged 2023 VIDD reading | Verdict matches the full-year (parity-verified) result | Threshold identical |
|---|---|---|
| ±84 h (the "send ~7 days" guidance in `API_USAGE.md`) | **41 / 60** | 5 / 60 |
| 31 days before → 24 h after | 60 / 60 | 60 / 60 |
| **31 days before → 48 h after** | **60 / 60** | **60 / 60** |

Also measured: re-running the same window twice gives byte-identical result rows (31/31), and of
the 31 readings the dashboard currently flags, 30 are flagged by the full-year series.

So an investigation cannot just say "the model flagged this reading". It has to say **which window**
produced the flag, and that window should reproduce the frozen full-series result. The proposal
below uses a fixed **[t − 31 d, t + 48 h]** window. This was verified only on VIDD 2023, the one
station with a full-series reference. For the other stations it is a reasoned choice, not a measured
one (§6.4).

---

## 1. Data model

Two new tables. Neither changes an existing table; both reference `users.id`.

### 1.1 `investigations`

One row per investigation. Every column is either **evidence** (written once at creation and
immutable), **human review** (changed only by state transitions), or **bookkeeping**.

| Column | Type | Null | Group | Notes |
|---|---|---|---|---|
| `id` | `bigint identity` | no | — | PK |
| `station_id` | `varchar(16)` | no | evidence | Must exist in `station_manifest.csv` |
| `observed_at` | `timestamptz` | no | evidence | Timestamp of the flagged observation |
| `variable` | `varchar(16)` | yes | evidence | Verbatim `variable` (may be null) |
| `model_version` | `varchar(12)` | no | evidence | Content hash from `LocalDetectorService` |
| `anomaly_score` | `double precision` | no | evidence | Verbatim |
| `threshold` | `double precision` | no | evidence | Verbatim |
| `detector_used` | `varchar(32)` | no | evidence | Always non-null for an anomaly |
| `likely_fault` | `varchar(32)` | yes | evidence | Verbatim `fault_type`. **Heuristic** |
| `likely_fault_basis` | `varchar(32)` | yes | evidence | Verbatim `fault_type_basis` (`heuristic_unvalidated`) |
| `degraded` | `boolean` | no | evidence | Verbatim |
| `dq_flags` | `text[]` | no | evidence | Structured data-quality flags (§7); `{}` if none |
| `evidence` | `jsonb` | no | evidence | Full immutable snapshot (§6) |
| `evidence_sha256` | `char(64)` | no | evidence | SHA-256 of canonical JSON of `evidence` |
| `created_by_user_id` | `bigint → users.id` | no | evidence | From the session. `ON DELETE RESTRICT` |
| `creation_note` | `varchar(2000)` | yes | evidence | Why the creator opened it |
| `status` | `varchar(16)` | no | review | §2; default `OPEN` |
| `reviewer_user_id` | `bigint → users.id` | yes | review | From the session at claim time |
| `reviewer_decision` | `varchar(32)` | yes | review | What the human concluded (table below) |
| `human_fault_type` | `varchar(32)` | yes | review | Only when decision = `SENSOR_FAULT` |
| `reviewer_notes` | `varchar(4000)` | yes | review | Required on every resolution |
| `created_at` | `timestamptz` | no | bookkeeping | DB `now()` |
| `updated_at` | `timestamptz` | no | bookkeeping | DB `now()` on each transition |
| `claimed_at` | `timestamptz` | yes | review | Set on claim |
| `reviewed_at` | `timestamptz` | yes | review | Set on resolution |

Everything the brief listed is covered. ML `notes` stay inside `evidence` (a list of strings is
not useful to filter on). "Observation/window timestamp" becomes `observed_at` plus the window
bounds held in `evidence.window`.

**Promoted columns and the JSONB snapshot are written once, in one transaction, from the same
Python dict.** The promoted columns exist for filtering and indexing. The snapshot exists for
reproducibility. A trigger (§1.4) stops either from changing afterwards, so they cannot disagree.

**Why `reviewer_decision` is not a copy of `status`.** If the decision were just
`CONFIRMED`/`REJECTED`, it would duplicate `status` and the two could drift apart. Instead it records
the human's *classification*, which is the part status cannot hold. It is also where "data quality"
and "sensor fault" get separated by a person rather than by the machine:

| `status` | allowed `reviewer_decision` |
|---|---|
| `CONFIRMED` | `SENSOR_FAULT`, `DATA_QUALITY_ISSUE` |
| `REJECTED` | `GENUINE_WEATHER`, `NO_ISSUE_FOUND` |
| `NEEDS_DATA` | `NULL` |
| `OPEN`, `IN_REVIEW` | `NULL` |

`human_fault_type` ∈ `spike | drift | stuck_at | bias | noise_burst | other | unknown`, allowed only
when the decision is `SENSOR_FAULT`. It is the one field here that goes beyond the minimum, and it
earns its place. `EVIDENCE_MATRIX.md` records that **no field-labelled sensor failure has ever been
scored**. Every confirmed review adds a human label kept separate from the model's heuristic
`likely_fault`. That turns the workflow into the only honest route to real-world evaluation data.

### 1.2 Constraints (all enforced by the database, not only the API)

- `CHECK status IN ('OPEN','IN_REVIEW','CONFIRMED','REJECTED','NEEDS_DATA')`
- `CHECK` for the decision/status compatibility table above, and for `human_fault_type` only with `SENSOR_FAULT`
- `CHECK (status = 'OPEN') = (reviewer_user_id IS NULL)`, so there is never an unowned review
- `CHECK (status IN ('CONFIRMED','REJECTED','NEEDS_DATA')) = (reviewed_at IS NOT NULL)`
- `CHECK reviewer_user_id IS DISTINCT FROM created_by_user_id` (separation of duties, §2.2)
- `CHECK detector_used IN ('isolation_forest','flat_run_rule')`
- `CHECK octet_length(evidence_sha256) = 64`

### 1.3 Indexes

- `(status, created_at DESC)` for the queue
- `(station_id, observed_at)` for per-station history
- `(reviewer_user_id) WHERE status = 'IN_REVIEW'` for "my reviews"
- **Partial unique** `(station_id, observed_at) WHERE status IN ('OPEN','IN_REVIEW','NEEDS_DATA')`,
  so there is at most one *active* investigation per reading. Closed investigations do not block a
  new one, which is the "second opinion" path, and it is fully audited.

### 1.4 Immutability trigger

`BEFORE UPDATE ON investigations`: raise if any **evidence**-group column is `IS DISTINCT FROM` its old
value, or if `OLD.status IN ('CONFIRMED','REJECTED')`.
`BEFORE DELETE ON investigations`: always raise.

This protects against application bugs and future code paths. It does **not** protect against
someone holding the database owner's credentials, who can disable triggers. See §9.4.

### 1.5 `audit_events` — see §5

---

## 2. State machine

### 2.1 States and transitions

```
                 claim                    resolve
     ┌──────┐ ──────────▶ ┌───────────┐ ──────────▶ CONFIRMED   (terminal)
     │ OPEN │             │ IN_REVIEW │ ──────────▶ REJECTED    (terminal)
     └──────┘ ◀────────── └───────────┘ ──────────▶ NEEDS_DATA
                release        ▲                        │
                               └────────── claim ───────┘
```

| From | Action | To | Audit event |
|---|---|---|---|
| — | create | `OPEN` | `INVESTIGATION_CREATED` |
| `OPEN` | claim | `IN_REVIEW` | `REVIEW_STARTED` |
| `NEEDS_DATA` | claim | `IN_REVIEW` | `REVIEW_STARTED` (`from_status = NEEDS_DATA`) |
| `IN_REVIEW` | release | `OPEN` | `REVIEW_RELEASED` |
| `IN_REVIEW` | resolve = confirm | `CONFIRMED` | `INVESTIGATION_CONFIRMED` |
| `IN_REVIEW` | resolve = reject | `REJECTED` | `INVESTIGATION_REJECTED` |
| `IN_REVIEW` | resolve = needs data | `NEEDS_DATA` | `INVESTIGATION_NEEDS_DATA` |

Five states, which is the candidate set unchanged. The only addition to the brief is **release**.
Without it, a reviewer who claims an item and walks away blocks it for good.

**Deliberately not added:**
- **Reopening `CONFIRMED`/`REJECTED`.** Terminal means terminal. A disputed outcome gets a *new*
  investigation, so the original decision and its audit trail stay unchanged.
- **`CLOSED`/`ARCHIVED`/`ESCALATED`.** Nothing in the current product needs them.
- **Assignment by a manager.** The model is claim-based. Assignment can be added later as an
  `ASSIGNED` sub-step of `IN_REVIEW` without changing the terminal states.
- **Free editing of notes.** Notes are written only as part of a transition, so no
  `NOTES_UPDATED` event and no edit history are needed. Unsent drafts stay in the browser.

When `NEEDS_DATA` is claimed again, the row's `reviewer_decision` / `reviewer_notes` are cleared for
the new review. The previous reviewer's notes are **not lost**, because they live in that
`INVESTIGATION_NEEDS_DATA` event's `details` (§5). The row holds current state; the audit log holds
history.

### 2.2 Who may do what

| Action | Permission | Extra server-side condition |
|---|---|---|
| create | `CREATE_INVESTIGATION` | The detection must reproduce on the canonical window (§3) |
| read list / detail / its timeline | `VIEW_INVESTIGATIONS` | — |
| claim | `REVIEW_INVESTIGATIONS` | status ∈ {`OPEN`,`NEEDS_DATA`}; **user ≠ creator** |
| resolve | `REVIEW_INVESTIGATIONS` | status = `IN_REVIEW`; **user = `reviewer_user_id`** |
| release own claim | `REVIEW_INVESTIGATIONS` | user = `reviewer_user_id` |
| release anyone's claim | `MANAGE_INVESTIGATIONS` | — |
| read global audit log | `VIEW_AUDIT` | (endpoint deferred, §3.3) |

**Can the creator review their own investigation? No, and that includes admins.** The whole point
of the layer is a *second* human judgement on an uncertain detection. It is enforced twice: at
claim in the API, and by a DB `CHECK`. Since resolve requires the claimer, a creator can never
resolve their own item either. The cost: a demo needs two accounts, e.g. an operator who creates and
a reviewer who reviews. That is the correct demo anyway.

### 2.3 Concurrency

Every transition is a single conditional update:
`UPDATE investigations SET … WHERE id = :id AND status = :expected_from [AND reviewer_user_id = :me] RETURNING …`.
Zero rows returned → `409 invalid_transition` with the current status. If two reviewers claim at
once, exactly one wins. The audit event is inserted **in the same transaction**, so a state change
never exists without its event, or the other way round.

---

## 3. API proposal

All under `/api/v1`. All mutating endpoints are `POST` with a JSON body and `extra="forbid"`
Pydantic models. **No endpoint accepts** `status`, `reviewer_user_id`, `created_by_user_id`, any
score or threshold, `model_version`, any timestamp other than `observed_at`, or any audit field.
Sending one is a loud `422`, not a silent ignore.

Explicit action endpoints are used instead of `PATCH /investigations/{id} {status: …}`. Each
endpoint maps to exactly one transition and one audit event, and a generic patch could never be
tricked into setting an arbitrary field.

### 3.1 Create

`POST /investigations` — `CREATE_INVESTIGATION`

```json
{ "station_id": "42182099999", "observed_at": "2023-10-18T06:00:00Z", "creation_note": "RH jump without a matching temp change" }
```

Server steps, in one transaction:
1. `station_id` must be in the manifest → else `404 unknown_station`.
2. Load `[observed_at − 31 d, observed_at + 48 h]` from the **server's** station store (crossing
   the year boundary into both files if needed). The target row must exist → else
   `404 observation_not_found`.
3. `app.state.ml.predict(window)`, the existing call, unchanged.
4. Find the result row at `observed_at`. If `anomaly` is false →
   **`409 detection_not_reproduced`**, returning that row's score/threshold so the UI can explain
   why. Nothing is stored.
5. Compute data-quality flags (§7) from the window's timestamps.
6. Build the snapshot (§6), hash it, then insert the investigation and `INVESTIGATION_CREATED`.
7. On a partial-unique violation → `409 investigation_exists` with the existing `id`.

→ `201` with the full investigation (as in 3.2).

### 3.2 Read

`GET /investigations?status=&station_id=&mine=&limit=&before_id=` — `VIEW_INVESTIGATIONS`
Returns summaries (promoted columns plus creator/reviewer email), newest first, with keyset pagination.

`GET /investigations/{id}` — `VIEW_INVESTIGATIONS`
Returns the promoted columns, `evidence`, `evidence_sha256`, `creator`, `reviewer`, the
**event timeline** for this investigation, and one derived, non-stored flag:
`model_version_is_current` (snapshot version vs `app.state.ml.model_version`). History is never
re-scored. The UI just says the model has changed since.

### 3.3 Transitions

| Endpoint | Body |
|---|---|
| `POST /investigations/{id}/claim` | `{}` |
| `POST /investigations/{id}/release` | `{ "reason": "…" }` (optional) |
| `POST /investigations/{id}/resolve` | `{ "outcome": "CONFIRMED" \| "REJECTED" \| "NEEDS_DATA", "decision": "…", "human_fault_type": "…", "reviewer_notes": "…" }` |

`resolve` validation: `reviewer_notes` is required (10–4000 chars) for every outcome. `decision`
must fit §1.1's table. `human_fault_type` is allowed only with `SENSOR_FAULT`.
Errors: `403 forbidden` (permission), `403 self_review_forbidden`, `403 not_claimant`,
`409 invalid_transition`, `422 validation_failed`.

**Deferred:** `GET /audit-events` (global, `VIEW_AUDIT`), comments (`COMMENT_OPERATIONAL`),
assignment, human-reported *missed* faults (opening an investigation on a reading the detector did
**not** flag). The last one matters, since bias is the measured blind spot, but it needs its own
evidence rules and would double this design.

### 3.4 Unchanged

`/predict`, `/model`, `/me`, `/admin/users` and their response shapes are not touched. The only
visible change is the permission list in `/me`, which reflects §4.

---

## 4. RBAC proposal

### 4.1 Naming

The brief suggests `investigations:read` style names. The codebase already uses an upper-snake
`Permission` StrEnum, and `/me` returns those strings. Two vocabularies in one system would be worse
than either one, so the proposal keeps the existing style:

| Brief | Proposed | Status |
|---|---|---|
| `investigations:read` | `VIEW_INVESTIGATIONS` | exists, becomes enforced |
| `investigations:create` | `CREATE_INVESTIGATION` | new |
| `investigations:review` | `REVIEW_INVESTIGATIONS` | new; **replaces unused `REVIEW_ASSIGNED`** (claim-based, not assignment-based) |
| `investigations:admin` | `MANAGE_INVESTIGATIONS` | exists, becomes enforced |
| — | `VIEW_AUDIT` | exists; global log (deferred endpoint) |

### 4.2 Matrix

| Permission | VIEWER | STATION_OPERATOR | SCIENTIST_REVIEWER | ADMIN |
|---|:-:|:-:|:-:|:-:|
| `VIEW_INVESTIGATIONS` | ✔ | ✔ | ✔ | ✔ |
| `CREATE_INVESTIGATION` | — | ✔ | ✔ | ✔ |
| `REVIEW_INVESTIGATIONS` | — | — | ✔ | **—** |
| `MANAGE_INVESTIGATIONS` | — | — | — | ✔ |
| `VIEW_AUDIT` | — | — | — | ✔ |

- **VIEWER: read-only.** Sign-up gives VIEWER to anyone who can reach the auth UI, and today that
  auth runs on a public demo core. If VIEWER could create, any stranger could fill the queue.
- **STATION_OPERATOR: triage.** They see the station and can raise a concern, but cannot rule on it.
- **SCIENTIST_REVIEWER: the reviewer role. It already exists, so no new role is needed.**
  Reviewers can also create, and separation of duties (§2.2) stops them reviewing their own items.
- **ADMIN: manage, not judge.** Admin controls accounts and can release stuck claims, but does
  **not** review by default. Administering the system and ruling on sensor behaviour are different
  jobs. An admin who is also a scientist is given both roles, which the schema already supports.

### 4.3 Required code change (flagged for review)

`ROLE_PERMISSIONS[Role.ADMIN] = set(Permission)` must become an **explicit set**. Otherwise
`REVIEW_INVESTIGATIONS`, and every future permission, would be granted to ADMIN automatically,
which breaks the matrix above without any visible change. Existing tests still pass:
`test_permissions_match_role` only checks a fresh VIEWER.

### 4.4 Demo accounts

`reviewer@skyguard.test` currently holds only `VIEWER`. The demo would need it granted
`SCIENTIST_REVIEWER` through the existing `grant_role`, and a separate operator or admin account to
create items. That is a data operation, not a schema change.

---

## 5. Audit model

### 5.1 `audit_events`

| Column | Type | Null | Answers |
|---|---|---|---|
| `id` | `bigint identity` | no | — |
| `occurred_at` | `timestamptz` default `now()` | no | **WHEN**, from the database clock, not the app or browser |
| `actor_user_id` | `bigint → users.id` `RESTRICT` | no | **WHO** |
| `actor_roles` | `text[]` | no | WHO, *as what*: a snapshot, since roles change later |
| `action` | `varchar(40)` `CHECK IN (…)` | no | **WHAT** |
| `investigation_id` | `bigint → investigations.id` `RESTRICT` | no | **WHICH** |
| `from_status` | `varchar(16)` | yes | transition start |
| `to_status` | `varchar(16)` | yes | transition end |
| `details` | `jsonb` default `'{}'` | no | Server-built context, below |

Index: `(investigation_id, occurred_at)` for the timeline, and `(actor_user_id, occurred_at)`.

Actions and their `details`:

| action | details |
|---|---|
| `INVESTIGATION_CREATED` | `creation_note`, `model_version`, `evidence_sha256` |
| `REVIEW_STARTED` | — |
| `REVIEW_RELEASED` | `released_reviewer_user_id`, `reason` |
| `INVESTIGATION_CONFIRMED` | `decision`, `human_fault_type`, `reviewer_notes` |
| `INVESTIGATION_REJECTED` | `decision`, `reviewer_notes` |
| `INVESTIGATION_NEEDS_DATA` | `reviewer_notes` |

### 5.2 Guarantees

- **Not client-generated.** No endpoint writes to this table. Events are written only by the service
  function that performs the transition, in the same transaction, from server-side values.
- **Append-only.** A `BEFORE UPDATE OR DELETE` trigger raises. FKs are `RESTRICT`, so deleting a
  user or investigation cannot orphan or cascade-delete history.
- **Survives an auth-provider reset.** Events point at `users.id`, not `auth_user_id`. If the demo
  SuperTokens core is wiped, logins break but attribution in our database stays intact.

### 5.3 Not proposed

- **Hash-chained events.** They detect a DB admin rewriting history, which the trigger cannot. That
  is disproportionate for this stage, but it is the upgrade path if tamper evidence is ever required.
- **A polymorphic `entity_type` / `entity_id`.** One concrete FK gives referential integrity now.
  Auditing role grants later is an additive migration: make the FK nullable and add entity columns.
- **Logging denied attempts** such as self-review. These belong in the application log for now.

---

## 6. Evidence snapshot strategy

### 6.1 Decision: A (JSONB snapshot) + promoted columns. Not B.

| Criterion | A. JSONB snapshot | B. normalised `observations` table |
|---|---|---|
| **Simplicity** | One insert. No new ingestion layer | Needs an ingestion pipeline for 8 stations × 2 years into PostgreSQL, plus dedup rules, *before* the first investigation exists |
| **Historical integrity** | Self-contained: the exact rows scored are frozen with the result | Integrity depends on the observations table never being corrected or re-ingested. Once it is, old investigations point at changed data unless rows are also versioned |
| **Reproducibility** | Re-run `predict(evidence.window.observations)` under `model_version` → identical row (verified deterministic) | Must rebuild the exact window by query and hope the bounds and rows match |
| **Queryability** | Everything a queue or report filters on is a promoted column. The JSONB is rarely queried | Rich time-series queries across stations |
| **Duplication** | ~25 KB of observations per investigation, less after TOAST compression. 1,000 investigations ≈ tens of MB | None |
| **Migration complexity** | 2 tables, both additive | 3+ tables, an ingestion job, and a backfill |
| **Future analytics** | Labels (`reviewer_decision`, `human_fault_type`) are columns, easy to aggregate. Raw series analytics stay on the CSV store | Better for fleet analytics, but that is not the current job |

B solves a problem the product does not have yet (querying raw telemetry in SQL) and makes the
problem it does have (a frozen, reproducible record) harder. When real ingestion exists,
`observations` becomes a *source* for windows. The snapshot still stays, because a snapshot is
exactly what an investigation must not lose.

### 6.2 Snapshot contents (`evidence`, `schema: "investigation-evidence/1"`)

```jsonc
{
  "schema": "investigation-evidence/1",
  "captured_at": "…",                              // server clock
  "target": { /* the result row at observed_at, VERBATIM from predict():
                 timestamp, anomaly, anomaly_score, threshold, detector_used, detectors_fired,
                 fault_type, fault_type_basis, variable, degraded, notes, observation */ },
  "model":  { /* the response's model block, VERBATIM, incl. model_version, station, frozen_test_metrics */ },
  "window": {
    "rule": "t-31d/t+48h",
    "start": "…", "end": "…", "n_rows": 263,
    "source": { "dataset": "data/processed/stations", "file": "42182099999_2023.csv", "file_sha256": "…" },
    "observations": [ { "time": "…", "temp_c": …, "slp_hpa": …, "rh_pct": … }, … ],
    "observations_sha256": "…"
  },
  "display_series": [ { "t": "…", "score": …, "threshold": …, "anomaly": …, "degraded": … }, … ],
                                                   // t ± 3.5 d only, for the score chart
  "data_quality": { "rules_version": "dq-1", "flags": [ … ], "facts": { … } },   // §7
  "summary": { /* the response's summary block, VERBATIM */ }
}
```

- `target`, `model` and `summary` are copied **verbatim**. No field is renamed, rounded or
  re-interpreted. Promoted columns are copied *out of* this object, never the reverse.
- The full 33-day `observations` array is kept for reproducibility. Only the ±3.5-day
  `display_series` of scores is kept, because the chart needs no more and full per-row results for
  33 days would be ~5× larger.
- `file_sha256` lets anyone detect that the station CSV was regenerated after capture.
- `evidence_sha256` is SHA-256 over canonical JSON (sorted keys, no whitespace), so any byte-level
  change to the snapshot is detectable.
- **Feature attribution is never stored**, because the API does not produce any. `include_features`
  stays `false`.

### 6.3 The model-changes-later rule

A new `model_version` does not touch existing rows (the trigger forbids it). The detail view shows
"Recorded with model `6ceeb2e79213` · current model differs" as a label only. Optional re-scoring
under a new model would be a **new, separate** record, never an overwrite. It is not proposed now.

### 6.4 Honest limits of the snapshot

- It proves **"this model produced this output on these rows"**. It does not prove the rows are what
  the physical station sent. They are NOAA ISD historical records processed by this project.
- The [t − 31 d, t + 48 h] rule was verified (60/60) only on VIDD 2023. For other stations and 2024
  there is no full-series reference yet. The snapshot records the window rule, so a later change is
  visible.
- Reading the code (not tested): 31 days of in-window pre-context means the target's 30-day
  threshold is built only from the same station's scores. The warm-start `score_history.csv` is
  VIDD-only, and a shorter window would mix VIDD history into another station's threshold.
- The model is trained on one station. `model.station` is kept verbatim, and the UI should mark
  investigations on other stations as **outside training scope**.
- The browser's current demo detections come from a 1-decimal-rounded, differently bounded window.
  So "Start investigation" can legitimately return `detection_not_reproduced` for near-threshold
  readings.

---

## 7. Data-quality representation

### 7.1 Principle

Two separate evidence panels, never merged into one diagnosis:

- **Detection:** what the ML returned (score, threshold, path, variable, likely fault).
- **Input conditions:** deterministic facts about the *timestamps* of the scored window.

The **human** decides which of the two explains the event (`SENSOR_FAULT` vs `DATA_QUALITY_ISSUE`).
The system never labels an investigation "data quality" or "sensor fault" by itself.

### 7.2 Flags (`rules_version: "dq-1"`)

Computed on the server at creation from the canonical window, stored in the snapshot, and never
recomputed. They are rules about the input, not ML output, so they do not touch the ML contract.

| Flag | Rule | Available evidence |
|---|---|---|
| `INSUFFICIENT_CONTEXT` | target `degraded = true` | verbatim from ML |
| `IRREGULAR_INTERVAL` | interval preceding target ≠ 3 h | timestamps; also stated in ML `notes` |
| `COMMUNICATION_GAP` | any interval ≥ 12 h within ±24 h of target | timestamps (the 2023 VIDD file has 3 × 12 h and 1 × 42 h) |
| `LOW_COVERAGE` | window rows < 90 % of the nominal 3-hourly count | timestamps |
| `DUPLICATES_DROPPED` | rows sent > rows returned | row counts |

`facts` records the raw numbers behind each flag (`gap_before_h`, `max_gap_near_target_h`,
`coverage_ratio`, `rows_sent`, `rows_returned`), so a reviewer sees the measurement and not just a
label. A flag can co-occur with a sensor anomaly, which is why it is an array.

### 7.3 What v1 cannot represent, stated plainly

- **Malformed input.** `/predict` rejects it with 400/422, so it never becomes a detection. The server
  store is already cleaned. This case does not exist in a detection-driven workflow.
- **Missing observations with no surrounding detection** ("the station went silent"). This needs an
  investigation type not triggered by a detection. It is deferred, together with human-reported
  missed faults (§3.3).
- **Sensor-fault classes.** `likely_fault` stays **the model's heuristic**, always shown with its
  verbatim basis `heuristic_unvalidated`. `stuck_at` from `flat_run_rule` is rule-defined (per
  `INFERENCE_API.md` §6), but its basis string is still displayed as the API returns it, never
  upgraded by the UI.

---

## 8. UI flow

Reuses the existing design system, `Panel`, `Metric`, `Pill`, `TimeSeries` (value and score modes)
and the `kv` / `note` styles. **No redesign, and no new nav item.** The detail view is laid out as
four stages: **OBSERVATION → EVIDENCE → REVIEW → OUTCOME**.

### 8.1 Entry points

| Where | Change |
|---|---|
| `/investigations` | Becomes the persisted queue, with filter tabs **Detections** (today's view) · **Open** · **In review** · **Needs data** · **Closed**. "Mine" toggle for reviewers |
| Detection row / Live Station anomaly panel | **Start investigation** button, shown only with `CREATE_INVESTIGATION` (the server enforces it regardless) |
| `/lab` (Fault Lab) | **No button.** The create endpoint only accepts `station_id` + `observed_at` and rebuilds evidence from the server store, so simulated data *structurally cannot* become an investigation |
| `/investigations/:id` | New detail route |

### 8.2 The judge-friendly path

1. **Open an anomaly.** Pick a detection on `/investigations` or Live Station.
2. **Start investigation.** A small sheet explains *"The server will re-run the detector on its own
   copy of this station's data (31 days before, 48 hours after) and freeze the result."* It has an
   optional note field. On `409 detection_not_reproduced` it shows *"Not flagged on the canonical
   window: score 0.5214 ≤ threshold 0.5251. No investigation created."* That is an honest outcome,
   not an error.
3. **Immutable evidence.** The detail page opens:
   - **OBSERVATION**: `TimeSeries` of `variable` from `evidence.window.observations` (±3.5 d),
     with the target marked. Degraded shading as elsewhere.
   - **EVIDENCE**: two side-by-side panels.
     *Detection*: `Metric` score / threshold / (score − threshold), then `kv` rows for path, fired,
     variable, timestamp, degraded, and ML notes verbatim. Likely fault is shown as
     `likely spike` + `Pill mute "heuristic · unvalidated"`. Below that, a score-mode `TimeSeries`
     from `display_series`.
     *Input conditions*: `dq_flags` pills plus the raw `facts`; "None detected" when empty.
     Footer: `🔒 Immutable snapshot · model 6ceeb2e79213 · sha256 3f9a…` and the out-of-scope /
     model-changed labels when they apply.
4. **Add reviewer decision.** The REVIEW panel shows *"Claim for review"* (or *"Claimed by X since
   14:02"* / *"You opened this investigation. Another reviewer must review it."*). Once claimed, it
   shows the decision radios grouped under the outcome they imply, plus `human_fault_type` when
   *Sensor fault* is chosen.
5. **Add reviewer notes.** Textarea, required.
6. **Confirm / Reject / Needs more data.** Three buttons, colour-coded with the existing status
   tokens: `--alert` confirm, `--ok` reject, `--watch` needs data.
7. **Audit history.** The OUTCOME panel shows the status pill, the human decision, and a
   **model-vs-human line**: *"Model suggested: likely spike (heuristic) · Reviewer recorded: drift"*.
   Agreement is displayed, never scored. Below it, a vertical timeline of events:
   `actor email · role snapshot · action · from → to · DB timestamp`, plus notes.

### 8.3 UI honesty rules (carried over)

- Every number shown comes from `evidence` or the event rows. Nothing is re-fetched from `/predict`
  for a stored investigation.
- There is no attribution panel. The text *"This model produces no feature attribution"* stays.
- Controls hidden by role are cosmetic. The server returns 403 regardless, and the UI shows the
  denial state already used on `/admin`.
- Notes and emails are rendered as text, never as HTML.

---

## 9. Security considerations

### 9.1 Required properties and how each is met

| Requirement | Mechanism |
|---|---|
| Reviewer identity comes from the authenticated session | `reviewer_user_id` / `created_by_user_id` / `actor_user_id` are taken only from `current_user` (SuperTokens session → `users.id`). Request models use `extra="forbid"`, so supplying one is a `422` |
| Reviewer role cannot be supplied by the browser | Roles are read from `user_roles` per request (existing, tested). `actor_roles` is snapshotted from the DB, never from `/me` or a header |
| Ownership cannot be forged | Creator fixed at insert; evidence-group trigger. Claimant fixed by conditional update from the session. Resolve requires `reviewer_user_id = session user` |
| Audit events cannot be client-generated | No write endpoint; written in-transaction by the service; append-only trigger |
| **Evidence cannot be forged** (added) | The client sends only `station_id` + `observed_at`. Score, threshold, verdict, model version and window are all produced server-side. This is the main reason not to reuse the browser's `/predict` result |
| Simulated output never becomes a record (added) | Follows from the line above. Fault Lab windows never reach the create endpoint |
| Self-review | API check at claim + DB `CHECK` |
| Race conditions | Conditional updates, unique partial index |

### 9.2 CSRF, for the new endpoints only

State-changing requests use cookie sessions. Today's defence is `SameSite=lax` alone
(`EVIDENCE_MATRIX.md` Domain 11: "anti-CSRF not explicit"). This design does **not** change the
SuperTokens config, but the new endpoints should not widen the exposure:
- **No state change on `GET`.** Every transition is `POST`.
- **Require `Content-Type: application/json`** and reject anything else with `415`. A cross-site HTML
  form cannot send `application/json`, and a script-driven cross-origin JSON POST triggers a CORS
  preflight, which the explicit single-origin CORS policy refuses.
- Enabling SuperTokens anti-CSRF remains the proper fix, tracked with the existing finding.

### 9.3 Input handling

`observed_at` must parse as a UTC timestamp that lines up with a stored row. `station_id` must match
the manifest allowlist, which also rules out path traversal into the CSV store. `creation_note` is
capped at 2,000 characters and `reviewer_notes` at 4,000, stored as text and rendered as text. The
create endpoint loads at most ~270 rows per call, so it cannot be used to make the server score
arbitrary volumes.

### 9.4 Known findings that weaken this design (not fixed here)

| Existing finding | Effect on investigations |
|---|---|
| Demo SuperTokens core (`try.supertokens.com`) | Accounts may be wiped. Investigation and audit rows survive because they key on `users.id`, but those users can no longer sign in. Anyone can register, which is why VIEWER is read-only |
| 12-month sessions | A stolen cookie acts as that reviewer for up to a year. Audit attribution is only as trustworthy as session hygiene |
| No `Secure` cookies (localhost) | Same attribution caveat on any non-HTTPS deployment |
| Default DB password in `config.py` | The triggers stop the *application* rewriting history, not someone holding the DB owner's credentials. A default password makes that easier |
| Single DB role owns all tables | `REVOKE UPDATE, DELETE` on `audit_events` has no effect on the owner. A separate least-privilege app role is the real fix, deferred |

These are the reasons this layer must be described as **auditable within the application**, not as
tamper-proof.

---

## 10. Migration implications

- **One new Alembic revision** (`slice2_investigations_audit`, `down_revision = c08f14933112`).
  It creates `investigations` and `audit_events` with their constraints, indexes, and three trigger
  functions (evidence immutability, no-delete, append-only audit).
- **Autogenerate will not capture everything.** CHECK constraints, partial unique indexes and
  PL/pgSQL triggers need hand-written `op.execute`. The revision should be reviewed as SQL, not
  trusted as generated output.
- **No existing table changes.** New FKs only *point at* `users.id` with `RESTRICT`. One side effect:
  **a user with investigations or audit events can no longer be hard-deleted.** Nothing deletes users
  today (`is_active` exists for disabling), and this is intended.
- **PostgreSQL-specific.** `jsonb`, `text[]`, partial indexes and triggers. Tests must keep running
  against real PostgreSQL, as `test_slice1.py` already does. No SQLite fallback.
- **Permissions are code, not data.** The RBAC changes in §4 (two new permissions, retiring
  `REVIEW_ASSIGNED`, making ADMIN explicit) need **no migration**. The four roles are already seeded.
  Granting `SCIENTIST_REVIEWER` to a demo account is a data step via `grant_role`.
- **Downgrade** drops triggers, functions and both tables, and **destroys all investigation and audit
  data**. Acceptable for the prototype; it must be stated in the revision docstring.
- **ML and API contracts untouched.** A new read-only module is needed to load windows from
  `data/processed/stations/` (the "station store"). It calls the existing `MLService.predict`.
  `src/inference.py`, `models/`, and the `/predict` request/response are unchanged.
- **Tests to add at implementation time**, listed so the review can judge coverage: evidence-trigger
  rejection · append-only audit rejection · self-review 403 · non-claimant resolve 403 · double-claim
  409 · VIEWER create 403 · ADMIN review 403 · forged fields → 422 · `detection_not_reproduced` 409 ·
  duplicate active 409 · snapshot re-runs byte-identical under the same `model_version` · window rule
  reproduces the full-year verdict on a VIDD 2023 sample (the Appendix A check, turned into a test).

---

## Open questions for the independent review

1. **Should ADMIN be able to review?** The proposal says no. The alternative is convenience for a
   small team, at the cost of separation of duties.
2. **Should `STATION_OPERATOR` create?** The proposal says yes (triage). The alternative is
   reviewers only.
3. **Is `human_fault_type` in scope for v1?** It is the only field beyond the minimum; the
   justification is in §1.1.
4. **Window rule [t − 31 d, t + 48 h]:** accept it on VIDD-only evidence, or require a
   multi-station check first?
5. **Human-reported missed faults** (no detection): defer as proposed, or bring into v1 given the
   known bias blind spot?

---

## Appendix A — how the window numbers were obtained

Read-only script run from a scratch directory. Nothing in the repository was modified.

1. Load the frozen detector (`WeatherFaultDetector.load("models/")`) and
   `data/processed/stations/42182099999_2023.csv`.
2. **Reference:** `predict()` on the full 2,861-row year. This is the series the parity gate
   verifies against the notebook.
3. **Sample:** every full-year anomaly that is not degraded and lies at least 32 days from the file
   start and at least 3 days from the file end, then 60 drawn with `random.seed(0)`.
4. For each window rule, rebuild the window from the CSV around each sampled timestamp, run
   `predict()`, and compare the target row's `anomaly` and `threshold` to the reference.
5. **Determinism:** each window was scored twice and the target rows compared as sorted JSON.
6. **Browser check:** the 31 readings flagged in `frontend/public/station_window.json` were compared
   with the full-year reference (30/31 agree).
