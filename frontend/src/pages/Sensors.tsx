import { useMemo, useState } from "react";
import { useTelemetry, VAR_LABEL, VAR_UNIT, DETECTOR_LABEL } from "../api/useTelemetry";
import { TimeSeries, type Pt } from "../components/TimeSeries";
import { Metric, Panel, Pill, type Status } from "../components/ui";

const VARS = ["temp_c", "slp_hpa", "rh_pct"] as const;
type V = (typeof VARS)[number];

export function Sensors() {
  const { obs, station, source, data, err } = useTelemetry();
  const [sel, setSel] = useState<V>("temp_c");

  const stats = useMemo(() => {
    if (!data) return null;
    const series = obs.map((o) => (o as any)[sel] as number);
    const flagged = data.results
      .map((r, i) => ({ r, i }))
      .filter(({ r }) => r.anomaly && r.variable === sel);
    const mean = series.reduce((a, b) => a + b, 0) / (series.length || 1);
    const sd = Math.sqrt(series.reduce((a, b) => a + (b - mean) ** 2, 0) / (series.length || 1));
    return {
      series, flagged, mean, sd,
      min: Math.min(...series), max: Math.max(...series),
      last: series[series.length - 1],
      status: (flagged.length === 0 ? "ok" : flagged.length <= 3 ? "watch" : "alert") as Status,
    };
  }, [data, obs, sel]);

  const points: Pt[] = useMemo(() => {
    if (!data) return [];
    return data.results.map((r, i) => ({
      t: r.timestamp, v: (obs[i] as any)?.[sel] ?? 0,
      anomaly: r.anomaly && r.variable === sel,
      degraded: r.degraded, detector: r.detector_used,
    }));
  }, [data, obs, sel]);

  return (
    <>
      <div className="eyebrow">Instrument view</div>
      <h1 className="display" style={{ fontSize: 40 }}>Sensors</h1>
      <p className="lede">
        Three instruments at {station?.name ?? "the station"}, each scored by the same detector.
        Select an instrument to inspect its signal and the readings that were flagged on it.
      </p>

      <div className="controls" style={{ marginTop: 26 }}>
        {VARS.map((v) => {
          const n = data?.results.filter((r) => r.anomaly && r.variable === v).length ?? 0;
          return (
            <button key={v} className={`ctl${sel === v ? " on" : ""}`} onClick={() => setSel(v)}>
              {VAR_LABEL[v]}{n > 0 ? ` · ${n}` : ""}
            </button>
          );
        })}
      </div>

      {err && <p className="err" style={{ marginTop: 16 }}>{err}</p>}

      {stats && (
        <>
          <Panel
            title={`${VAR_LABEL[sel]} — observed signal`}
            detail={`${obs.length} observations · ${source}`}
            right={<Pill status={stats.status}>{stats.flagged.length} flagged</Pill>}
            pad={false}
          >
            <TimeSeries points={points} unit={VAR_UNIT[sel]} height={360} label="OBSERVED SIGNAL" />
          </Panel>

          <Panel title="Window statistics" detail="computed from the observations shown above">
            <div className="metrics-row">
              <Metric value={stats.last.toFixed(1)} label={`Latest ${VAR_UNIT[sel].trim()}`} tone="accent" />
              <Metric value={stats.mean.toFixed(1)} label="Mean" small />
              <Metric value={stats.sd.toFixed(2)} label="Std dev" small />
              <Metric value={stats.min.toFixed(1)} label="Minimum" small />
              <Metric value={stats.max.toFixed(1)} label="Maximum" small />
              <Metric value={stats.flagged.length} label="Flagged"
                      small tone={stats.flagged.length ? "alert" : "ok"} />
            </div>
          </Panel>

          <Panel title={`Flagged readings — ${VAR_LABEL[sel]}`} pad={false}>
            {stats.flagged.length === 0 ? (
              <div style={{ padding: 30, textAlign: "center" }} className="muted">
                No readings flagged on this instrument in the current window.
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr><th>Timestamp</th><th>Observed</th><th>Score</th><th>Threshold</th>
                      <th>Detection path</th><th>Likely fault</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {stats.flagged.map(({ r, i }) => (
                    <tr key={r.timestamp}>
                      <td className="mono">{r.timestamp.replace("T", " ").replace("Z", "")}</td>
                      <td className="mono">{((obs[i] as any)?.[sel] ?? 0).toFixed(1)}{VAR_UNIT[sel]}</td>
                      <td className="mono" style={{ color: "var(--alert)" }}>{r.anomaly_score.toFixed(4)}</td>
                      <td className="mono muted">{r.threshold.toFixed(4)}</td>
                      <td>{r.detector_used ? DETECTOR_LABEL[r.detector_used] ?? r.detector_used : "—"}</td>
                      <td>{r.fault_type
                        ? <span title="heuristic label, not a trained classifier">{r.fault_type}</span>
                        : <span className="muted">type unknown</span>}</td>
                      <td>{r.degraded
                        ? <Pill status="mute">provisional</Pill>
                        : <Pill status="alert">anomaly</Pill>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </>
      )}
    </>
  );
}
