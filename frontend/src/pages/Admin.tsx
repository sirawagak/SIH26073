import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import { Metric, NotYet, Panel, Pill } from "../components/ui";

export function Admin() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  useEffect(() => {
    api.adminUsers()
      .then((d) => setRows(d.users))
      .catch((e) => {
        // 403 is the server doing its job, not a failure to report as an error.
        if (e instanceof ApiError && (e.status === 403 || e.status === 401)) setDenied(true);
        else setErr(e.message);
      });
  }, []);

  const active = rows?.filter((u) => u.is_active).length ?? 0;
  const admins = rows?.filter((u) => u.roles.includes("ADMIN")).length ?? 0;

  return (
    <>
      <div className="eyebrow">Administration</div>
      <h1 className="display" style={{ fontSize: 40 }}>Users &amp; roles</h1>
      <p className="lede">
        Every row here was returned by <span className="mono">/api/v1/admin/users</span>, which the
        server refuses without the admin permission. Hiding the link is cosmetic; the API is the
        actual control.
      </p>

      {err && <p className="err">{err}</p>}

      {denied && (
        <Panel title="Access denied" detail="403 from /api/v1/admin/users">
          <NotYet what="Your account does not hold the admin permission."
                  why="The server refused this request. Nothing on this page is hidden client-side only — the data was never sent." />
        </Panel>
      )}

      {rows && (
        <div className="strip" style={{ marginTop: 24 }}>
          <Metric value={rows.length} label="Accounts" />
          <Metric value={active} label="Active" tone="ok" />
          <Metric value={admins} label="Administrators" tone="accent" />
        </div>
      )}

      {!denied && <Panel title="Directory" detail="server-enforced RBAC" pad={false}
             right={<Pill status="mute">read only</Pill>}>
        {rows && (
          <table className="tbl">
            <thead><tr><th>ID</th><th>Email</th><th>Name</th><th>Roles</th><th>Active</th></tr></thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id}>
                  <td className="mono">{u.id}</td>
                  <td>{u.email}</td>
                  <td>{u.name ?? "—"}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{u.roles.join(" · ")}</td>
                  <td><Pill status={u.is_active ? "ok" : "mute"}>{u.is_active ? "active" : "disabled"}</Pill></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!rows && !err && <p className="muted" style={{ padding: "20px 22px" }}>Loading…</p>}
      </Panel>}

      <div className="note mute" style={{ marginTop: 20 }}>
        Role assignment is not yet exposed in the UI. Roles are seeded and changed through the
        database migration path.
      </div>
    </>
  );
}
