import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { useTelemetry, VAR_LABEL, VAR_UNIT } from "../api/useTelemetry";
import { TimeSeries, type Pt } from "../components/TimeSeries";
import { Metric, Panel, Pill, type Status } from "../components/ui";
import type { Me } from "../api/client";

const VARS = ["temp_c", "slp_hpa", "rh_pct"] as const;

export function Overview({ me, model, onModel }:
  { me: Me | null; model: Record<string, any> | null;
    onModel?: (m: Record<string, any>) => void }) {
  const { obs, station, source, data, err, busy } = useTelemetry();

  // The model block is part of the real /predict response; lift it so the shell can show it.
  const meta = (data?.model as Record<string, any> | undefined) ?? model ?? null;
  useEffect(() => { if (data?.model && onModel) onModel(data.model as Record<string, any>); },
            [data, onModel]);

  const points: Pt[] = useMemo(() => {
    if (!data) return [];
    return data.results.map((r, i) => ({
      t: r.timestamp, v: obs[i]?.temp_c ?? 0,
      anomaly: r.anomaly && r.variable === "temp_c",
      degraded: r.degraded, detector: r.detector_used,
    }));
  }, [data, obs]);

  // Per-sensor state, derived strictly from the API response.
  const sensors = useMemo(() => {
    if (!data) return [];
    return VARS.map((v) => {
      const flagged = data.results.filter((r) => r.anomaly && r.variable === v).length;
      const series = obs.map((o) => (o as any)[v] as number);
      const last = series[series.length - 1];
      const prev = series[Math.max(0, series.length - 9)];
      const status: Status = flagged === 0 ? "ok" : flagged <= 3 ? "watch" : "alert";
      return { v, last, delta: last - prev, flagged, status, series };
    });
  }, [data, obs]);

  const alerts = data?.summary.n_anomalies ?? 0;
  const lastTs = data?.summary.window.end ?? "—";
  const overall: Status = alerts === 0 ? "ok" : alerts < 10 ? "watch" : "alert";

  return (
    <>
      <div className="eyebrow">SIH 26073 · AeroWatch</div>
      <h1 className="display">Weather sensor<br />intelligence<em>.</em></h1>
      <p className="lede">
        Detect abnormal sensor behaviour before it becomes a data-quality problem.
        Every value on this page is produced by the frozen SkyGuard detector from real
        NOAA ISD observations — nothing here is illustrative.
      </p>

      <div className="strip">
        <div className="cell">
          <div className="k">System status</div>
          <div className={`v ${overall}`}>{alerts === 0 ? "NOMINAL" : alerts < 10 ? "WATCH" : "ALERT"}</div>
          <div className="sub">{busy ? "scoring…" : "detector online"}</div>
        </div>
        <div className="cell">
          <div className="k">Stations in model scope</div>
          <div className="v accent">1</div>
          <div className="sub">{station?.name ?? meta?.station?.name ?? "—"}</div>
        </div>
        <div className="cell">
          <div className="k">Sensors monitored</div>
          <div className="v">3</div>
          <div className="sub">temperature · pressure · humidity</div>
        </div>
        <div className="cell">
          <div className="k">Flagged readings</div>
          <div className={`v ${alerts ? "alert" : "ok"}`}>{data ? alerts : "—"}</div>
          <div className="sub">of {data?.summary.n_observations ?? "—"} in window</div>
        </div>
        <div className="cell">
          <div className="k">Window ends</div>
          <div className="v" style={{ fontSize: 19 }}>{lastTs.slice(0, 10)}</div>
          <div className="sub mono">{lastTs.slice(11, 16)} UTC · historical</div>
        </div>
      </div>

      {err && <p className="err" style={{ marginTop: 18 }}>{err}</p>}

      <h2 className="sec" style={{ marginTop: 40 }}>Primary telemetry</h2>
      <Panel
        title="Air temperature"
        detail={`${station?.name ?? ""} · ${obs.length} observations · 3-hourly`}
        right={<Pill status={overall}>{alerts} flagged</Pill>}
        pad={false}
      >
        <TimeSeries points={points} unit="°C" height={360}
                    label="OBSERVED SIGNAL" sub={source} />
      </Panel>

      <h2 className="sec" style={{ marginTop: 40 }}>Sensor health</h2>
      <Panel pad={false}>
        {sensors.map((s) => (
          <div className="sensor" key={s.v}>
            <div className="nm">{VAR_LABEL[s.v]}<small>{s.v}</small></div>
            <div className="val">
              {s.last?.toFixed(1)}<u>{VAR_UNIT[s.v]}</u>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
              <span className="mono" style={{ fontSize: 12.5, color: "var(--ink-3)", minWidth: 118 }}>
                {s.delta >= 0 ? "▲" : "▼"} {Math.abs(s.delta).toFixed(1)}{VAR_UNIT[s.v]} / 24h
              </span>
              <span className="mono" style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
                {s.flagged} flagged reading{s.flagged === 1 ? "" : "s"}
              </span>
            </div>
            <div style={{ textAlign: "right" }}>
              <Pill status={s.status}>
                {s.status === "ok" ? "healthy" : s.status === "watch" ? "watch" : "anomaly"}
              </Pill>
            </div>
          </div>
        ))}
      </Panel>

      <div className="console" style={{ marginTop: 22 }}>
        <Panel title="Detector in service" detail={meta?.model_version}>
          {/* Every number below is read from the /predict response's own model block. */}
          <div className="metrics-row">
            <Metric value={meta?.frozen_test_metrics?.precision ?? "—"} label="Precision" small tone="watch" />
            <Metric value={meta?.frozen_test_metrics?.recall ?? "—"} label="Recall" small tone="watch" />
            <Metric value={meta?.frozen_test_metrics?.f1 ?? "—"} label="Hold-out F1" small tone="accent" />
            <Metric value={meta?.frozen_test_metrics?.episode_recall_all_classes ?? "—"}
                    label="Episode recall" small tone="accent" />
          </div>
          <dl className="kv" style={{ marginTop: 18 }}>
            <dt>Detector</dt><dd>{meta?.detector ?? "—"}</dd>
            <dt>Threshold</dt><dd>{meta?.threshold_mode ?? "—"}</dd>
            <dt>Training set</dt><dd>{meta?.version ?? "—"}</dd>
            <dt>Scored at</dt><dd className="mono">{meta?.scored_at ?? "—"}</dd>
          </dl>
          <div className="note accent" style={{ marginTop: 18 }}>
            {meta?.assessment_note ?? "Automated anomaly assessment — requires human verification."}
          </div>
          <div className="note mute">
            Hold-out metrics come from <b>controlled synthetic fault injection</b>, not from
            field-observed failures. Precision on the hold-out split is
            {" "}{meta?.frozen_test_metrics?.precision ?? "—"}.
          </div>
        </Panel>

        <Panel title="Next actions">
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <Link className="ctl" to="/investigations" style={{ textAlign: "center", textDecoration: "none" }}>
              Review flagged readings
            </Link>
            <Link className="ctl" to="/live" style={{ textAlign: "center", textDecoration: "none" }}>
              Open live station console
            </Link>
            <Link className="ctl" to="/lab" style={{ textAlign: "center", textDecoration: "none" }}>
              Open fault lab
            </Link>
          </div>
          <div className="note mute" style={{ marginTop: 16 }}>
            Signed in as <b>{me?.email}</b> with role{me && me.roles.length > 1 ? "s" : ""}{" "}
            <b>{me?.roles.join(", ")}</b>.
          </div>
        </Panel>
      </div>
    </>
  );
}
