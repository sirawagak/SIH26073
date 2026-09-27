/**
 * FAULT LAB — simulation environment.
 *
 * The fault is injected into a copy of a real observation window IN THE BROWSER.
 * The resulting window is then sent to the REAL /api/v1/predict, so the detection
 * is genuine even though the corruption is synthetic. Both halves are labelled.
 */
import { useMemo, useState } from "react";
import { api, type Observation, type PredictResponse } from "../api/client";
import { useTelemetry, VAR_LABEL, VAR_UNIT, FAULT_LABEL, DETECTOR_LABEL } from "../api/useTelemetry";
import { TimeSeries, type Pt } from "../components/TimeSeries";
import { Metric, Panel, Pill } from "../components/ui";

type Kind = "spike" | "drift" | "stuck" | "noise" | "bias";
const KINDS: { k: Kind; label: string; blurb: string }[] = [
  { k: "spike", label: "Inject Spike", blurb: "single reading leaps away and returns" },
  { k: "drift", label: "Inject Drift", blurb: "gradual departure from normal behaviour" },
  { k: "stuck", label: "Inject Stuck", blurb: "sensor value stops changing" },
  { k: "noise", label: "Inject Noise", blurb: "spread grows, mean stays put" },
  { k: "bias", label: "Inject Bias", blurb: "level shifts once and stays" },
];
const VARS = ["temp_c", "slp_hpa", "rh_pct"] as const;

function sigma(xs: number[]) {
  const m = xs.reduce((a, b) => a + b, 0) / (xs.length || 1);
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / (xs.length || 1)) || 1;
}

/** Deterministic pseudo-noise so a demo repeats identically. */
function rng(seed: number) {
  let s = seed;
  return () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff) * 2 - 1;
}

function inject(rows: Observation[], kind: Kind, v: (typeof VARS)[number], start: number, len: number) {
  const out = rows.map((r) => ({ ...r }));
  const series = rows.map((r) => (r as any)[v] as number);
  const sd = sigma(series);
  const rand = rng(1337);
  for (let i = 0; i < len; i++) {
    const j = start + i;
    if (j >= out.length) break;
    const cur = (out[j] as any)[v] as number;
    let next = cur;
    if (kind === "spike") next = i === 0 ? cur + 6 * sd : cur;
    if (kind === "drift") next = cur + ((i + 1) / len) * 3.2 * sd;
    if (kind === "bias") next = cur + 2.0 * sd;
    if (kind === "stuck") next = (out[start - 1] as any)?.[v] ?? cur;
    if (kind === "noise") next = cur + rand() * 2.6 * sd;
    (out[j] as any)[v] = Math.round(next * 100) / 100;
  }
  if (v === "rh_pct") out.forEach((r) => (r.rh_pct = Math.max(0, Math.min(100, r.rh_pct ?? 0))));
  return out;
}

export function FaultLab() {
  const { obs, station, data: clean, err } = useTelemetry();
  const [kind, setKind] = useState<Kind | null>(null);
  const [v, setV] = useState<(typeof VARS)[number]>("temp_c");
  const [res, setRes] = useState<PredictResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [fault, setFault] = useState<{ start: number; len: number } | null>(null);

  const start = Math.floor((obs.length || 60) * 0.62);

  async function run(k: Kind) {
    if (!obs.length) return;
    const len = k === "spike" ? 1 : k === "stuck" ? 12 : 16;
    setKind(k); setBusy(true); setFault({ start, len });
    try { setRes(await api.predict(inject(obs, k, v, start, len))); }
    catch (e: any) { setRes(null); alert(e.message); }
    finally { setBusy(false); }
  }
  function reset() { setKind(null); setRes(null); setFault(null); }

  const shownData = res ?? clean;
  const signal: Pt[] = useMemo(() => {
    if (!shownData) return [];
    const rows = kind && fault ? inject(obs, kind, v, fault.start, fault.len) : obs;
    return shownData.results.map((r, i) => ({
      t: r.timestamp, v: (rows[i] as any)?.[v] ?? 0,
      anomaly: r.anomaly && r.variable === v, degraded: r.degraded, detector: r.detector_used,
    }));
  }, [shownData, obs, kind, v, fault]);

  const scorePts: Pt[] = (shownData?.results ?? []).map((r) => ({
    t: r.timestamp, v: r.anomaly_score, thr: r.threshold,
    anomaly: r.anomaly, degraded: r.degraded, detector: r.detector_used,
  }));

  // Did detection land inside the injected episode?
  const caught = useMemo(() => {
    if (!res || !fault) return null;
    const win = res.results.slice(fault.start, fault.start + fault.len);
    const hit = win.find((r) => r.anomaly && (r.variable === v || fault.len === 1));
    return { any: win.some((r) => r.anomaly), first: hit, n: win.filter((r) => r.anomaly).length,
             total: win.length };
  }, [res, fault, v]);

  const baseN = clean?.summary.n_anomalies ?? 0;
  const nowN = shownData?.summary.n_anomalies ?? 0;

  return (
    <>
      <div className="eyebrow">Demonstration environment</div>
      <h1 className="display" style={{ fontSize: 40 }}>Fault Lab</h1>
      <p className="lede">
        Corrupt a real observation window and watch the live detector respond. The fault is
        synthetic; the detection is not.
      </p>

      <div className="simbar">
        <b>Simulation mode</b>
        <span>
          The fault is injected <b>in the browser</b> into a copy of real NOAA ISD observations.
          The corrupted window is then scored by the <b>real detector</b> through
          <span className="mono"> /api/v1/predict</span>. Output here is never real sensor data.
        </span>
      </div>

      <div className="controls" style={{ marginTop: 22 }}>
        {VARS.map((x) => (
          <button key={x} className={`ctl${v === x ? " on" : ""}`}
                  onClick={() => { setV(x); reset(); }}>{VAR_LABEL[x]}</button>
        ))}
      </div>
      <div className="controls" style={{ marginTop: 10 }}>
        {KINDS.map((f) => (
          <button key={f.k} className={`ctl danger${kind === f.k ? " on" : ""}`}
                  onClick={() => run(f.k)} disabled={busy || !obs.length} title={f.blurb}>
            {f.label}
          </button>
        ))}
        <button className="ctl" onClick={reset} disabled={!kind}>Clear</button>
      </div>

      {err && <p className="err" style={{ marginTop: 14 }}>{err}</p>}

      <div className="console">
        <div>
          <Panel title={`${VAR_LABEL[v]} — ${kind ? "with injected fault" : "clean signal"}`}
                 detail={station?.name} pad={false}
                 right={kind ? <Pill status="watch">simulated {kind}</Pill>
                             : <Pill status="ok">unmodified</Pill>}>
            <TimeSeries points={signal} unit={VAR_UNIT[v]} height={300}
                        label={kind ? "CORRUPTED SIGNAL" : "OBSERVED SIGNAL"} />
          </Panel>

          <Panel title="Detector response" detail="anomaly score vs adaptive threshold" pad={false}>
            <TimeSeries points={scorePts} mode="score" height={260}
                        label="SCORE (SOLID) vs THRESHOLD (DASHED)" />
          </Panel>
        </div>

        <div>
          <Panel title="Outcome">
            {!kind && (
              <p style={{ fontSize: 13.5, color: "var(--ink-2)", fontWeight: 300, margin: 0 }}>
                Choose an instrument, then inject a fault. The window is re-scored by the real
                detector and the result appears here.
              </p>
            )}
            {busy && <p className="muted" style={{ margin: 0 }}>Scoring corrupted window…</p>}
            {kind && res && caught && (
              <>
                <div style={{ marginBottom: 16 }}>
                  <Pill status={caught.any ? "alert" : "watch"}>
                    {caught.any ? "fault detected" : "not detected"}
                  </Pill>
                </div>
                <div className="metrics-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  <Metric value={`${caught.n}/${caught.total}`} label="Rows flagged in episode"
                          tone={caught.any ? "alert" : "watch"} />
                  <Metric value={nowN - baseN >= 0 ? `+${nowN - baseN}` : `${nowN - baseN}`}
                          label="Δ flagged vs clean" tone="accent" />
                </div>
                {caught.first && (
                  <dl className="kv" style={{ marginTop: 20 }}>
                    <dt>Score</dt><dd style={{ color: "var(--alert)" }}>
                      {caught.first.anomaly_score.toFixed(4)}</dd>
                    <dt>Threshold</dt><dd>{caught.first.threshold.toFixed(4)}</dd>
                    <dt>Path</dt><dd>{caught.first.detector_used
                      ? DETECTOR_LABEL[caught.first.detector_used] ?? caught.first.detector_used : "—"}</dd>
                    <dt>Variable</dt><dd>{caught.first.variable ?? "—"}</dd>
                    <dt>Likely fault</dt><dd>{caught.first.fault_type
                      ? FAULT_LABEL[caught.first.fault_type] ?? caught.first.fault_type : "unknown"}</dd>
                    <dt>Timestamp</dt><dd>{caught.first.timestamp}</dd>
                  </dl>
                )}
                {!caught.any && (
                  <div className="note">
                    The detector did not flag this episode. That is a real outcome, not a bug —
                    subtle bias and slow drift are the measured weak classes.
                  </div>
                )}
                <div className="note mute">
                  Injected: <b>{kind}</b> on <b>{VAR_LABEL[v]}</b>, {fault?.len} observation
                  {fault?.len === 1 ? "" : "s"} from index {fault?.start}. Magnitude is scaled to the
                  window's own standard deviation.
                </div>
              </>
            )}
          </Panel>

          <Panel title="Fault shapes">
            {KINDS.map((f) => (
              <div key={f.k} style={{ padding: "9px 0", borderBottom: "1px solid var(--line-soft)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: ".12em",
                              textTransform: "uppercase" }}>{f.k}</div>
                <div className="muted" style={{ fontSize: 12.5, marginTop: 3 }}>{f.blurb}</div>
              </div>
            ))}
          </Panel>
        </div>
      </div>
    </>
  );
}
