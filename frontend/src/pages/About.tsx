/**
 * ABOUT — editorial hub over the presentation copy ported from the original dashboard.
 * Every string comes from content.ts, which was transcribed verbatim from dashboard/index.html.
 * Routes /overview, /problem, /how and /plan each land on their own section.
 */
import { Link, useLocation } from "react-router-dom";
import { PAGES, PIPELINE, TIMELINE, RUBRIC } from "./content";

const TABS = [
  { to: "/about", id: "home", label: "The idea" },
  { to: "/problem", id: "problem", label: "The problem" },
  { to: "/how", id: "how", label: "How it works" },
  { to: "/plan", id: "plan", label: "Status & plan" },
];

export function About() {
  const { pathname } = useLocation();
  const tab = TABS.find((t) => t.to === pathname) ?? TABS[0];
  const page = PAGES[tab.id];

  return (
    <>
      <div className="eyebrow">About the system</div>
      <h1 className="display" style={{ fontSize: 40 }}>SkyGuard<em> AI</em></h1>

      <nav className="tabs">
        {TABS.map((t) => (
          <Link key={t.to} to={t.to} className={`tab${t.id === tab.id ? " on" : ""}`}>
            {t.label}
          </Link>
        ))}
      </nav>

      {page && (
        <article className="editorial">
          <div className="eyebrow">{page.eyebrow}</div>
          <h1>{page.h1}</h1>
          {page.lede.map((l, i) => <p className="lede" key={i}>{l}</p>)}

          {page.cards.length > 0 && (
            <div className="ed-grid">
              {page.cards.map((c, i) => (
                <div className="ed-card" key={i}><h3>{c.h3}</h3><p>{c.p}</p></div>
              ))}
            </div>
          )}

          {page.paras.length > 0 && (
            <div style={{ marginTop: 30, maxWidth: "76ch" }}>
              {page.paras.map((p, i) => <p key={i}>{p}</p>)}
            </div>
          )}

          {tab.id === "how" && (
            <>
              <h3 style={{ marginTop: 34 }}>Detection pipeline</h3>
              <div className="ed-grid" style={{ marginTop: 14 }}>
                {PIPELINE.map((s) => (
                  <div className="ed-card" key={s.title}>
                    <h3>{s.title}</h3>
                    <p style={{ margin: 0 }}>{s.sub}</p>
                  </div>
                ))}
              </div>
            </>
          )}

          {tab.id === "plan" && (
            <>
              <h3 style={{ marginTop: 34 }}>Where the work stands</h3>
              <div className="timeline">
                {TIMELINE.map((t, i) => (
                  <div className="tlrow" key={i}><span className="d">{t.d}</span><span>{t.w}</span></div>
                ))}
              </div>
              <h3 style={{ marginTop: 34 }}>Evaluation rubric</h3>
              <div className="timeline">
                {RUBRIC.map((r) => (
                  <div className="tlrow" key={r.label}>
                    <span className="d">{r.points} PTS</span>
                    <span>{r.label}</span>
                    <span style={{ marginLeft: "auto", fontSize: 11.5, letterSpacing: ".1em",
                                   fontFamily: "var(--mono)", opacity: .75 }}>
                      {r.strength ? "STRENGTH" : "TO STRENGTHEN"}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </article>
      )}

      <div className="note accent" style={{ marginTop: 26 }}>
        <b>Honest scope.</b> Detection performance was measured against <b>synthetic</b> faults on
        NOAA ISD data. Reported row-level precision is 0.26 — roughly three in four row-level alerts
        are false positives — against episode recall of 1.00 on the frozen test period. Fault-type
        labels carry <span className="mono">fault_type_basis: heuristic_unvalidated</span> and have
        no measured accuracy. This is a prototype, not a production monitoring system.
      </div>
    </>
  );
}
