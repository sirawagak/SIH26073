/**
 * Large, readable SVG time-series. Two modes:
 *   value  — an observed sensor signal with anomaly markers
 *   score  — anomaly score against its adaptive threshold
 *
 * Every point plotted comes from the API response. Nothing is synthesised here.
 */
import { useMemo, useRef, useState } from "react";

export interface Pt {
  t: string;            // ISO timestamp
  v: number;            // plotted value
  thr?: number;         // threshold (score mode)
  anomaly?: boolean;
  degraded?: boolean;
  detector?: string | null;
}

const PAD = { l: 62, r: 20, t: 18, b: 34 };

function niceTicks(lo: number, hi: number, n = 5): number[] {
  const span = hi - lo || 1;
  const raw = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const start = Math.ceil(lo / step) * step;
  const out: number[] = [];
  for (let v = start; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

const fmtTime = (iso: string) =>
  iso.replace("T", " ").replace("Z", "").slice(5, 16);

export function TimeSeries({
  points, mode = "value", unit = "", height = 340, label, sub, showArea = true,
}: {
  points: Pt[]; mode?: "value" | "score"; unit?: string; height?: number;
  label?: string; sub?: string; showArea?: boolean;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const W = 1000, H = height;

  const { xs, ys, lo, hi, path, area, thrPath } = useMemo(() => {
    const vals = points.flatMap((p) => (p.thr !== undefined ? [p.v, p.thr] : [p.v]));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo || 1) * 0.16;
    lo -= pad; hi += pad;
    const X = (i: number) =>
      PAD.l + (points.length < 2 ? 0 : ((W - PAD.l - PAD.r) * i) / (points.length - 1));
    const Y = (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - lo) / (hi - lo));
    const xs = points.map((_, i) => X(i));
    const ys = points.map((p) => Y(p.v));
    const thrs = points.map((p) => (p.thr !== undefined ? Y(p.thr) : null));
    const path = points.map((p, i) => `${i ? "L" : "M"}${X(i)},${Y(p.v)}`).join(" ");
    const area = `${path} L${X(points.length - 1)},${H - PAD.b} L${X(0)},${H - PAD.b} Z`;
    const thrPath = thrs.every((v) => v === null)
      ? ""
      : thrs.map((y, i) => (y === null ? "" : `${i ? "L" : "M"}${X(i)},${y}`)).join(" ");
    return { xs, ys, thrs, lo, hi, path, area, thrPath };
  }, [points, H]);

  if (points.length === 0)
    return <div className="muted" style={{ padding: 40, textAlign: "center" }}>No data</div>;

  const yTicks = niceTicks(lo, hi, 5);
  const xIdx = Array.from({ length: Math.min(6, points.length) }, (_, k) =>
    Math.round((k * (points.length - 1)) / Math.max(1, Math.min(6, points.length) - 1)));
  const h = hover !== null ? points[hover] : null;

  function onMove(e: React.MouseEvent) {
    const r = wrap.current?.getBoundingClientRect();
    if (!r) return;
    const px = ((e.clientX - r.left) / r.width) * W;
    let best = 0, bd = Infinity;
    xs.forEach((x, i) => { const d = Math.abs(x - px); if (d < bd) { bd = d; best = i; } });
    setHover(best);
  }

  return (
    <div ref={wrap} style={{ position: "relative" }} onMouseMove={onMove}
         onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height, display: "block" }}>
        <defs>
          <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity=".20" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {yTicks.map((v) => {
          const y = PAD.t + (H - PAD.t - PAD.b) * (1 - (v - lo) / (hi - lo));
          return (
            <g key={v}>
              <line x1={PAD.l} y1={y} x2={W - PAD.r} y2={y} stroke="var(--line-soft)" strokeWidth="1" />
              <text x={PAD.l - 11} y={y + 4} textAnchor="end" fontSize="11"
                    fontFamily="var(--mono)" fill="var(--ink-3)">{v}</text>
            </g>
          );
        })}

        {xIdx.map((i) => (
          <text key={i} x={xs[i]} y={H - 12} textAnchor="middle" fontSize="10.5"
                fontFamily="var(--mono)" fill="var(--ink-3)">{fmtTime(points[i].t)}</text>
        ))}

        {/* degraded region shading */}
        {points.map((p, i) =>
          p.degraded ? (
            <rect key={`d${i}`} x={xs[i] - 2} y={PAD.t} width="4" height={H - PAD.t - PAD.b}
                  fill="var(--ink-3)" opacity=".07" />
          ) : null)}

        {showArea && mode === "value" && <path d={area} fill="url(#fill)" />}

        {thrPath && (
          <path d={thrPath} fill="none" stroke="var(--alert)" strokeWidth="1.6"
                strokeDasharray="5 4" opacity=".85" />
        )}

        <path d={path} fill="none" stroke={mode === "score" ? "var(--ink)" : "var(--accent)"}
              strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

        {points.map((p, i) =>
          p.anomaly ? (
            <g key={`a${i}`}>
              <circle cx={xs[i]} cy={ys[i]} r="7" fill="var(--alert)" opacity=".16" />
              <circle cx={xs[i]} cy={ys[i]} r="3.4" fill="var(--alert)" />
            </g>
          ) : null)}

        {h && hover !== null && (
          <g>
            <line x1={xs[hover]} y1={PAD.t} x2={xs[hover]} y2={H - PAD.b}
                  stroke="var(--accent)" strokeWidth="1" opacity=".55" />
            <circle cx={xs[hover]} cy={ys[hover]} r="4.5" fill="var(--accent)"
                    stroke="var(--bg)" strokeWidth="2" />
          </g>
        )}
      </svg>

      {(label || sub) && (
        <div style={{ position: "absolute", top: 6, left: PAD.l + 4, pointerEvents: "none" }}>
          {label && <div style={{ fontSize: 11, letterSpacing: ".16em", textTransform: "uppercase",
                                  color: "var(--ink-3)", fontWeight: 700 }}>{label}</div>}
          {sub && <div style={{ fontSize: 11, color: "var(--ink-3)", fontFamily: "var(--mono)" }}>{sub}</div>}
        </div>
      )}

      {h && (
        <div style={{
          position: "absolute", top: 12, right: 12, background: "var(--bg-2)",
          border: "1px solid var(--line)", padding: "9px 12px", pointerEvents: "none",
          fontFamily: "var(--mono)", fontSize: 11.5, lineHeight: 1.65, minWidth: 176,
        }}>
          <div style={{ color: "var(--ink-3)" }}>{fmtTime(h.t)}</div>
          <div style={{ color: mode === "score" ? "var(--ink)" : "var(--accent)", fontSize: 15, fontWeight: 600 }}>
            {h.v.toFixed(mode === "score" ? 4 : 1)}{unit}
          </div>
          {h.thr !== undefined && <div style={{ color: "var(--alert)" }}>thr {h.thr.toFixed(4)}</div>}
          {h.anomaly && <div style={{ color: "var(--alert)", fontWeight: 600 }}>ANOMALY</div>}
          {h.detector && <div style={{ color: "var(--ink-3)" }}>{h.detector}</div>}
          {h.degraded && <div style={{ color: "var(--ink-3)" }}>provisional</div>}
        </div>
      )}
    </div>
  );
}

/** Tiny inline waveform used on fault-library cards. Pure illustration of a shape. */
export function Waveform({ kind, w = 272, h = 82 }: { kind: string; w?: number; h?: number }) {
  const pts = useMemo(() => {
    const n = 64, out: number[] = [];
    for (let i = 0; i < n; i++) {
      const base = Math.sin(i / 5) * 0.34 + Math.sin(i / 11) * 0.16;
      let v = base;
      if (kind === "spike" && (i === 30 || i === 31)) v = base + 1.5;
      if (kind === "drift") v = base + (i / n) * 1.5 - 0.42;
      if (kind === "stuck") v = i > 24 && i < 46 ? 0.28 : base;
      if (kind === "bias") v = i > 26 ? base + 0.95 : base;
      if (kind === "noise") v = base + (i > 22 && i < 48 ? (Math.sin(i * 7.3) + Math.cos(i * 3.1)) * 0.42 : 0);
      out.push(v);
    }
    return out;
  }, [kind]);
  const lo = Math.min(...pts) - 0.3, hi = Math.max(...pts) + 0.3;
  const X = (i: number) => 8 + ((w - 16) * i) / (pts.length - 1);
  const Y = (v: number) => 10 + (h - 20) * (1 - (v - lo) / (hi - lo));
  const d = pts.map((v, i) => `${i ? "L" : "M"}${X(i)},${Y(v)}`).join(" ");
  const hot = kind === "stuck" ? [25, 45] : kind === "spike" ? [29, 32]
            : kind === "drift" ? [30, 63] : kind === "bias" ? [27, 63] : [22, 48];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: h, display: "block" }}>
      <rect x={X(hot[0])} y="6" width={X(hot[1]) - X(hot[0])} height={h - 12}
            fill="var(--alert)" opacity=".07" />
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.8"
            strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
