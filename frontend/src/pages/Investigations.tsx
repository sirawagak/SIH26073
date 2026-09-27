/**
 * Detections from the current scored window.
 *
 * These are NOT persisted investigations — the investigations schema is a later
 * phase. That distinction is stated in the UI rather than glossed over.
 */
import { useMemo, useState } from "react";
import { useTelemetry, VAR_LABEL, VAR_UNIT, FAULT_LABEL, DETECTOR_LABEL } from "../api/useTelemetry";
import { TimeSeries, type Pt } from "../components/TimeSeries";
import { Metric, Panel, Pill } from "../components/ui";
import type { PredictResult } from "../api/client";

export function Investigations() {
  const { obs, station, data, err } = useTelemetry();
  const [sel, setSel] = useState<number | null>(null);

  const flagged = useMemo(
    () => (data?.results.map((r, i) => ({ r, i })).filter(({ r }) => r.anomaly) ?? []),
    [data]);

  const active = sel !== null ? data?.results[sel] : flagged[0]?.r;
  const activeIdx = sel !== null ? sel : flagged[0]?.i ?? null;

  const context: Pt[] = useMemo(() => {
    if (!data || activeIdx === null) return [];
    const v = active?.variable ?? "temp_c";
    const lo = Math.max(0, activeIdx - 16), hi = Math.min(data.results.length, activeIdx + 17);
    return data.results.slice(lo, hi).map((r, k) => ({
      t: r.timestamp, v: (obs[lo + k] as any)?.[v] ?? 0,
      anomaly: r.anomaly && r.variable === v, degraded: r.degraded, detector: r.detector_used,
    }));
  }, [data, activeIdx, active, obs]);

  return (
    <>
      <div className="eyebrow">Detection queue</div>
      <h1 className="display" style={{ fontSize: 40 }}>Investigations</h1>
      <p className="lede">
        Readings the detector flagged in the current window, newest context first. Each entry
        carries only what the model actually reported.
      </p>

      <div className="simbar">
        <b>Not yet persisted</b>
        <span>
          These are live detections from the scored window. Durable investigation records,
          reviewer assignment and independent review arrive with the investigations schema.
        </span>
      </div>

      {err && <p className="err" style={{ marginTop: 16 }}>{err}</p>}

      <div className="console">
        <div>
          <Panel title="Flagged readings" detail={`${flagged.length} of ${data?.summary.n_observations ?? 0}`} pad={false}>
            {flagged.length === 0 ? (
              <div style={{ padding: 34, textAlign: "center" }} className="muted">
                Nothing flagged in this window.
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr><th>Timestamp</th><th>Sensor</th><th>Score</th><th>Threshold</th>
                      <th>Path</th><th>Likely fault</th><th /></tr>
                </thead>
                <tbody>
                  {flagged.map(({ r, i }) => (
                    <tr key={r.timestamp + i} className="click" onClick={() => setSel(i)}
                        style={activeIdx === i ? { background: "var(--surface-2)" } : undefined}>
                      <td className="mono">{r.timestamp.replace("T", " ").replace("Z", "")}</td>
                      <td>{r.variable ? VAR_LABEL[r.variable] ?? r.variable : "—"}</td>
                      <td className="mono" style={{ color: "var(--alert)" }}>{r.anomaly_score.toFixed(4)}</td>
                      <td className="mono muted">{r.threshold.toFixed(4)}</td>
                      <td style={{ fontSize: 12 }}>
                        {r.detector_used ? DETECTOR_LABEL[r.detector_used] ?? r.detector_used : "—"}
                      </td>
                      <td style={{ fontSize: 12 }}>
                        {r.fault_type ? FAULT_LABEL[r.fault_type] ?? r.fault_type
                                      : <span className="muted">unknown</span>}
                      </td>
                      <td>{r.degraded && <Pill status="mute">prov.</Pill>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>

          {active && context.length > 0 && (
            <Panel title="Observed signal in context"
                   detail={`${VAR_LABEL[active.variable ?? "temp_c"]} · ±16 observations`} pad={false}>
              <TimeSeries points={context} height={280}
                          unit={VAR_UNIT[active.variable ?? "temp_c"]} label="OBSERVED SIGNAL" />
            </Panel>
          )}
        </div>

        <div>{active ? <DetailCard r={active} station={station?.name} /> : null}</div>
      </div>
    </>
  );
}

function DetailCard({ r, station }: { r: PredictResult; station?: string }) {
  return (
    <>
      <section className="panel" style={{ marginTop: 22, borderColor: "rgba(255,107,107,.4)" }}>
        <header className="panel-hd" style={{ borderColor: "rgba(255,107,107,.28)" }}>
          <span className="t">{r.variable ? VAR_LABEL[r.variable] ?? r.variable : "Sensor"}</span>
          <Pill status={r.degraded ? "mute" : "alert"}>{r.degraded ? "provisional" : "anomaly"}</Pill>
        </header>
        <div className="panel-bd">
          <div className="metrics-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Metric value={r.anomaly_score.toFixed(4)} label="Anomaly score" tone="alert" />
            <Metric value={r.threshold.toFixed(4)} label="Adaptive threshold" />
          </div>
          <div style={{ marginTop: 20 }}>
            <div className="lbl" style={{ fontSize: 9.5, letterSpacing: ".20em", color: "var(--ink-3)",
                                          textTransform: "uppercase", fontWeight: 700 }}>
              Detection path
            </div>
            <div style={{ fontSize: 15, fontWeight: 600, marginTop: 6 }}>
              {r.detector_used ? DETECTOR_LABEL[r.detector_used] ?? r.detector_used : "—"}
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
              {r.detector_used === "flat_run_rule"
                ? "Repeated identical readings — the forest cannot see a frozen sensor."
                : "Score exceeded the trailing 30-day quantile threshold."}
            </div>
          </div>
        </div>
      </section>

      <Panel title="Why was this flagged?">
        <p style={{ fontSize: 13, color: "var(--ink-2)", fontWeight: 300, margin: "0 0 14px" }}>
          The detector reports the following and nothing further. It does not produce per-feature
          attribution, so none is shown.
        </p>
        <dl className="kv">
          <dt>Score</dt><dd>{r.anomaly_score.toFixed(6)}</dd>
          <dt>Threshold</dt><dd>{r.threshold.toFixed(6)}</dd>
          <dt>Margin</dt>
          <dd style={{ color: r.anomaly_score > r.threshold ? "var(--alert)" : "var(--ink)" }}>
            {(r.anomaly_score - r.threshold >= 0 ? "+" : "") + (r.anomaly_score - r.threshold).toFixed(6)}
          </dd>
          <dt>Detectors fired</dt><dd>{r.detectors_fired.join(", ") || "—"}</dd>
          <dt>Variable</dt><dd>{r.variable ?? "—"}</dd>
          <dt>Timestamp</dt><dd>{r.timestamp}</dd>
          <dt>Station</dt><dd>{station ?? "—"}</dd>
          <dt>Degraded</dt><dd>{String(r.degraded)}</dd>
        </dl>

        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 9.5, letterSpacing: ".20em", textTransform: "uppercase",
                        color: "var(--ink-3)", fontWeight: 700 }}>
            {r.fault_type === "stuck_at" ? "Fault" : "Likely fault"}
          </div>
          <div style={{ fontSize: 17, fontWeight: 700, marginTop: 6 }}>
            {r.fault_type ? FAULT_LABEL[r.fault_type] ?? r.fault_type : "Type unknown"}
          </div>
        </div>

        {r.fault_type && r.fault_type !== "stuck_at" && (
          <div className="note">
            This label is a <b>heuristic</b> ({r.fault_type_basis}). The model is a binary detector
            and was never evaluated as a fault classifier.
          </div>
        )}
        {r.degraded && (
          <div className="note">
            Provisional — this reading sits near the edge of the scored window, so its features use a
            truncated context. It is re-scored as more data arrives.
          </div>
        )}
        {r.notes.length > 0 && <div className="note mute">{r.notes.join(" ")}</div>}

        <div className="note accent">
          Automated anomaly assessment — requires human verification.
        </div>
      </Panel>

      <Panel title="Observed readings">
        <dl className="kv">
          <dt>Temperature</dt><dd>{r.observation.temp_c ?? "—"} °C</dd>
          <dt>Pressure</dt><dd>{r.observation.slp_hpa ?? "—"} hPa</dd>
          <dt>Humidity</dt><dd>{r.observation.rh_pct ?? "—"} %</dd>
        </dl>
      </Panel>
    </>
  );
}
