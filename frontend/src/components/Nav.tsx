import { Link, useLocation } from "react-router-dom";
import { signOut } from "supertokens-auth-react/recipe/session";
import type { Me } from "../api/client";

const LINKS = [
  { to: "/", label: "Overview" },
  { to: "/sensors", label: "Sensors" },
  { to: "/investigations", label: "Investigations" },
  { to: "/live", label: "Live Station" },
  { to: "/faults", label: "Fault Library" },
  { to: "/lab", label: "Fault Lab" },
  { to: "/about", label: "About" },
];

export function Nav({ me }: { me: Me | null }) {
  const { pathname } = useLocation();
  const isAdmin = !!me?.roles.includes("ADMIN");
  const on = (to: string) => (to === "/" ? pathname === "/" : pathname.startsWith(to));

  return (
    <header className="topbar">
      <div className="container topbar-in">
        <Link to="/" className="brand">
          <b>SKYGUARD<em> AI</em></b>
          <span>WEATHER SENSOR INTELLIGENCE</span>
        </Link>
        <nav className="mainnav">
          {LINKS.map((l) => (
            <Link key={l.to} to={l.to} className={on(l.to) ? "on" : ""}>{l.label}</Link>
          ))}
          {/* Admin is rendered only for admins; the API enforces this independently. */}
          {isAdmin && (
            <Link to="/admin" className={`admin${on("/admin") ? " on" : ""}`}>Admin</Link>
          )}
        </nav>
        <div className="userbox">
          {me && (
            <>
              <div className="idblock">
                <b>{me.email}</b>
                <span>{me.roles.join(" · ")}</span>
              </div>
              <button className="btn-ghost"
                      onClick={async () => { await signOut(); window.location.href = "/auth"; }}>
                Sign out
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
