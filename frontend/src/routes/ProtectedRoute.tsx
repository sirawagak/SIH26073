/**
 * Route guard. UX only - it hides what the user cannot use.
 * Every permission is re-checked server-side in FastAPI; this is never the
 * security boundary.
 */
import { SessionAuth } from "supertokens-auth-react/recipe/session";
import type { ReactNode } from "react";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  return <SessionAuth>{children}</SessionAuth>;
}

export function RoleGate({
  roles,
  userRoles,
  children,
  fallback = null,
}: {
  roles: string[];
  userRoles: string[];
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const allowed = roles.some((r) => userRoles.includes(r));
  return <>{allowed ? children : fallback}</>;
}
