/**
 * Single API client. Every backend call goes through here.
 *
 * `credentials: "include"` carries the SuperTokens session cookie; the SDK's
 * fetch interceptor handles token refresh transparently. No token is ever read
 * or stored by application code.
 */
import { API_DOMAIN } from "../auth/config";

export class ApiError extends Error {
  status: number;
  payload: unknown;
  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_DOMAIN}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg =
      (body && (body.message || body.detail?.message)) ??
      `Request failed with status ${res.status}`;
    throw new ApiError(res.status, msg, body);
  }
  return body as T;
}

export interface Me {
  id: number;
  auth_user_id: string;
  email: string;
  name: string | null;
  roles: string[];
  permissions: string[];
  created_at: string;
}

export interface PredictResult {
  timestamp: string;
  anomaly: boolean;
  anomaly_score: number;
  threshold: number;
  detector_used: string | null;
  detectors_fired: string[];
  fault_type: string | null;
  fault_type_basis: string | null;
  variable: string | null;
  degraded: boolean;
  notes: string[];
  observation: { temp_c: number | null; slp_hpa: number | null; rh_pct: number | null };
}

export interface PredictResponse {
  model: Record<string, any> & { model_version: string };
  results: PredictResult[];
  summary: {
    n_observations: number;
    n_anomalies: number;
    alert_rate: number;
    n_degraded: number;
    window: { start: string; end: string };
    by_fault_type: Record<string, number>;
    by_variable: Record<string, number>;
    warnings?: string[];
  };
}

export interface Observation {
  time: string;
  temp_c: number;
  slp_hpa: number;
  rh_pct?: number;
  dew_c?: number;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  me: () => request<Me>("/api/v1/me"),
  modelInfo: () => request<Record<string, any>>("/api/v1/model"),
  predict: (observations: Observation[]) =>
    request<PredictResponse>("/api/v1/predict", {
      method: "POST",
      body: JSON.stringify({ observations }),
    }),
  adminUsers: () =>
    request<{ users: { id: number; email: string; name: string | null; roles: string[]; is_active: boolean }[] }>(
      "/api/v1/admin/users",
    ),
};
