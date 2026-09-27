import type { ReactNode } from "react";

export type Status = "ok" | "watch" | "alert" | "mute";

export function Pill({ status, children }: { status: Status; children: ReactNode }) {
  return <span className={`pill ${status}`}><i className="dot" />{children}</span>;
}

export function Metric({ value, label, tone, small }:
  { value: ReactNode; label: string; tone?: Status | "accent"; small?: boolean }) {
  const color = tone === "ok" ? "var(--ok)" : tone === "watch" ? "var(--watch)"
    : tone === "alert" ? "var(--alert)" : tone === "accent" ? "var(--accent)" : "var(--ink)";
  return (
    <div className={`metric${small ? " sm" : ""}`}>
      <span className="num" style={{ color }}>{value}</span>
      <span className="lbl">{label}</span>
    </div>
  );
}

export function Panel({ title, detail, right, children, light, pad = true }:
  { title?: string; detail?: string; right?: ReactNode; children: ReactNode;
    light?: boolean; pad?: boolean }) {
  return (
    <section className={`panel${light ? " light" : ""}`}>
      {(title || right) && (
        <header className="panel-hd">
          <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
            {title && <span className="t">{title}</span>}
            {detail && <span className="d">{detail}</span>}
          </div>
          {right}
        </header>
      )}
      <div className={pad ? "panel-bd" : ""}>{children}</div>
    </section>
  );
}

export function Backdrop() {
  // Contour-inspired atmospheric lines. Decorative only.
  const bands = [0, 1, 2, 3, 4, 5];
  return (
    <div className="backdrop" aria-hidden="true">
      <div className="grid" />
      <svg viewBox="0 0 1200 420" preserveAspectRatio="none">
        <g className="drift" fill="none" stroke="var(--accent)" strokeWidth="1.1">
          {bands.map((b) => {
            const y = 60 + b * 58;
            let d = `M0,${y}`;
            for (let x = 0; x <= 1280; x += 40)
              d += ` Q${x + 20},${y + (b % 2 ? 22 : -22) * Math.sin((x + b * 90) / 150)} ${x + 40},${y}`;
            return <path key={b} d={d} opacity={1 - b * 0.13} />;
          })}
        </g>
      </svg>
    </div>
  );
}

/** Small state used when a feature exists but its data layer is not built yet. */
export function NotYet({ what, why }: { what: string; why: string }) {
  return (
    <div style={{ padding: "44px 24px", textAlign: "center" }}>
      <Pill status="mute">Not yet available</Pill>
      <p style={{ margin: "16px auto 0", maxWidth: "58ch", color: "var(--ink-2)",
                  fontWeight: 300, fontSize: 14 }}>
        <b style={{ color: "var(--ink)" }}>{what}</b> {why}
      </p>
    </div>
  );
}
