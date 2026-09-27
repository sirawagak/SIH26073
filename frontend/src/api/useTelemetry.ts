/**
 * Loads a real NOAA ISD observation window and scores it through the authenticated
 * /api/v1/predict. Everything returned here originates from the API or from the
 * shipped real observation file — nothing is generated in the browser.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type Observation, type PredictResponse } from "./client";

export interface StationMeta { code: string; id: string; name: string }

export function useTelemetry(file = "/station_window.json") {
  const [obs, setObs] = useState<Observation[]>([]);
  const [station, setStation] = useState<StationMeta | null>(null);
  const [source, setSource] = useState<string>("");
  const [data, setData] = useState<PredictResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);

  const score = useCallback(async (rows: Observation[]) => {
    setBusy(true); setErr(null);
    try { setData(await api.predict(rows)); }
    catch (e: any) { setErr(e.message ?? "Scoring failed"); }
    finally { setBusy(false); }
  }, []);

  useEffect(() => {
    let live = true;
    fetch(file)
      .then((r) => r.json())
      .then((j) => {
        if (!live) return;
        setObs(j.observations);
        setStation(j.station ?? null);
        setSource(j.source ?? "");
        return score(j.observations);
      })
      .catch(() => live && setErr("Could not load the observation window."));
    return () => { live = false; };
  }, [file, score]);

  return { obs, station, source, data, err, busy, score, setData };
}

export const VAR_LABEL: Record<string, string> = {
  temp_c: "Temperature", slp_hpa: "Pressure", rh_pct: "Humidity",
};
export const VAR_UNIT: Record<string, string> = { temp_c: "°C", slp_hpa: " hPa", rh_pct: "%" };
export const FAULT_LABEL: Record<string, string> = {
  spike: "Spike", stuck_at: "Stuck value", bias: "Bias / step offset",
  drift: "Drift", noise_burst: "Noise burst",
};
export const DETECTOR_LABEL: Record<string, string> = {
  isolation_forest: "Isolation Forest", flat_run_rule: "Stuck-sensor rule",
};
