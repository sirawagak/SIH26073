/**
 * Operator console. Historical replay of real NOAA ISD observations scored by the
 * live detector — explicitly not production streaming.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useTelemetry, VAR_LABEL, VAR_UNIT, FAULT_LABEL, DETECTOR_LABEL } from "../api/useTelemetry";
import { TimeSeries, type Pt } from "../components/TimeSeries";
import { Metric, Panel, Pill, type Status } from "../components/ui";

export function LiveStation() {
  const { obs, station, source, data, err, busy, score } = useTelemetry();
  const [playing, setPlaying] = useState(true);
  const [cursor, setCursor] = useState(0);
  const timer = useRef<number | null>(null);

  const n = data?.results.length ?? 0;
  useEffect(() => { if (n) setCursor(n); }, [n]);

  useEffect(() => {
    if (!playing || n === 0) return;
    timer.current = window.setInterval(() => {
      setCursor((c) => (c >= n ? 24 : c + 1));
    }, 260);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [playing, n]);

  const shown = Math.max(8, Math.min(cursor, n));
  const results = data?.results.slice(0, shown) ?? [];

  const scorePts: Pt[] = results.map((r) => ({
    t: r.timestamp, v: r.anomaly_score, thr: r.threshold,
    anomaly: r.anomaly, degraded: r.degraded, detector: r.detector_used,
  }));

  // The newest reliably scorable reading — the last rows of any window are provisional.
  const head = useMemo(() => {
    for (let i = results.length - 1; i >= 0; i--) if (!results[i].degraded) return results[i];
    return results[results.length - 1] ?? null;
  }, [results]);

  const live = results[results.length - 1] ?? null;
  const status: Status = head ? (head.anomaly ? "alert" : "ok") : "mute";

  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between",
                    gap: 24, flexWrap: "wrap" }}>
        <div>
          <div className="eyebrow">Operator console</div>
          <h1 className="display" style={{ fontSize: 40 }}>Live Station</h1>
          <p className="lede" style={{ marginTop: 10, fontSize: 15 }}>
            {station?.name ?? "—"} · {station?.code ?? "VIDD"} · station {station?.id ?? "—"}
          </p>
        </div>
        <div className="controls">
          <button className={`ctl${playing ? " on" : ""}`} onClick={() => setPlaying((p) => !p)}>
            {playing ? "Pause replay" : "Resume replay"}
          </button>
          <button className="ctl" onClick={() => obs.length && score(obs)} disabled={busy}>
            {busy ? "Scoring…" : "Re-score"}
          </button>
        </div>
      </div>

      <div className="simbar">
        <b>Live replay</b>
        <span>
          Historical 2023 observations replayed through the live detector. This is
          <b> not production streaming</b> — the detector needs roughly 21 hours of context on each
          side of a reading, so it is an offline/batch design by nature.
        </span>
      </div>

      {err && <p className="err" style={{ marginTop: 16 }}>{err}</p>}

      <div className="console">
        <div>
          <Panel
            title="Anomaly score vs adaptive threshold"
            detail={`${shown} / ${n} observations · ${source}`}
            right={<Pill status={status}>{status === "alert" ? "anomaly" : "nominal"}</Pill>}
            pad={false}
          >
            <TimeSeries points={scorePts} mode="score" height={330}
                        label="SCORE (SOLID) vs THRESHOLD (DASHED)" />
          </Panel>

          <Panel pad={false}>
            {(["temp_c", "slp_hpa", "rh_pct"] as const).map((v) => {
              const flagged = results.filter((r) => r.anomaly && r.variable === v).length;
              const val = (obs[shown - 1] as any)?.[v] as number | undefined;
              const st: Status = flagged === 0 ? "ok" : flagged <= 3 ? "watch" : "alert";
              return (
                <div className="sensor" key={v}>
                  <div className="nm">{VAR_LABEL[v]}<small>{v}</small></div>
                  <div className="val">{val?.toFixed(1) ?? "—"}<u>{VAR_UNIT[v]}</u></div>
                  <div className="mono" style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
                    {flagged} flagged so far in replay
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <Pill status={st}>{st === "ok" ? "healthy" : st === "watch" ? "watch" : "anomaly"}</Pill>
                  </div>
                </div>
              );
            })}
          </Panel>
        </div>

        <div>
          <section className="panel" style={{ marginTop: 22,
                    borderColor: status === "alert" ? "rgba(255,107,107,.4)" : "var(--line)" }}>
            <header className="panel-hd">
              <span className="t">{status === "alert" ? "Anomaly detected" : "Sensor nominal"}</span>
              <Pill status={status}>{status === "alert" ? "action" : "ok"}</Pill>
            </header>
            <div className="panel-bd">
              {head ? (
                <>
                  <div className="metrics-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
                    <Metric value={head.anomaly_score.toFixed(4)} label="Anomaly score"
                            tone={head.anomaly ? "alert" : undefined} />
                    <Metric value={head.threshold.toFixed(4)} label="Adaptive threshold" />
                  </div>
                  <dl className="kv" style={{ marginTop: 20 }}>
                    <dt>Detection path</dt>
                    <dd>{head.detector_used ? DETECTOR_LABEL[head.detector_used] ?? head.detector_used : "—"}</dd>
                    <dt>Variable</dt>
                    <dd>{head.variable ? VAR_LABEL[head.variable] ?? head.variable : "—"}</dd>
                    <dt>Timestamp</dt><dd>{head.timestamp}</dd>
                    <dt>{head.fault_type === "stuck_at" ? "Fault" : "Likely fault"}</dt>
                    <dd>{head.fault_type ? FAULT_LABEL[head.fault_type] ?? head.fault_type
                        : head.anomaly ? "type unknown" : "—"}</dd>
                    <dt>Degraded</dt><dd>{String(head.degraded)}</dd>
                  </dl>
                </>
              ) : <span className="muted">Waiting for the first scored reading…</span>}
            </div>
          </section>

          {head && (
            <Panel title="Why was this flagged?">
              <p style={{ fontSize: 13, color: "var(--ink-2)", fontWeight: 300, margin: "0 0 12px" }}>
                Exactly what the API returned — no feature attribution is produced by this model,
                so none is displayed.
              </p>
              <dl className="kv">
                <dt>Margin</dt>
                <dd style={{ color: head.anomaly ? "var(--alert)" : "var(--ok)" }}>
                  {(head.anomaly_score - head.threshold >= 0 ? "+" : "")}
                  {(head.anomaly_score - head.threshold).toFixed(6)}
                </dd>
                <dt>Fired</dt><dd>{head.detectors_fired.join(", ") || "none"}</dd>
              </dl>
              {head.fault_type && head.fault_type !== "stuck_at" && (
                <div className="note">
                  Heuristic label ({head.fault_type_basis}) — the model is a binary detector,
                  not a trained fault classifier.
                </div>
              )}
              {head.notes.length > 0 && <div className="note mute">{head.notes.join(" ")}</div>}
              {live && live !== head && (
                <div className="note">
                  The newest reading ({live.timestamp.slice(11, 16)}) is still provisional; the status
                  above refers to the most recent reliably scorable observation.
                </div>
              )}
              <div className="note accent">
                Automated anomaly assessment — requires human verification.
              </div>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
