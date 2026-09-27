"""Quality checks for src/fault_injection.py.

Run from the repository root:   python3 tests/test_fault_injection.py
Exit code 0 = all checks pass.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from fault_injection import (  # noqa: E402
    CHALLENGE_CONFIG, VARS, FaultSimulator, legacy_inject, local_scale,
)

CLEAN = os.path.join(ROOT, "data", "processed", "vidd_2023_clean.csv")
_checks = []


def check(name, cond, detail=""):
    _checks.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def load_clean():
    raw = pd.read_csv(CLEAN, parse_dates=["time"])
    df = raw.drop(columns=["station", "dew_c", "dew_qc"]).sort_values("time").reset_index(drop=True)
    df[VARS] = df.set_index("time")[VARS].interpolate(
        method="time", limit=2, limit_direction="both").to_numpy()
    return df


def main():
    df = load_clean()
    clean = {v: df[v].to_numpy(copy=True) for v in VARS}

    print("\n[1] original benchmark still reproduces Round-1 exactly")
    f0, l0, e0 = legacy_inject(df, seed=42)
    check("legacy: 27 episodes", len(e0) == 27, f"got {len(e0)}")
    check("legacy: 179 faulty rows", int(l0.is_fault.sum()) == 179, f"got {int(l0.is_fault.sum())}")

    print("\n[2] challenge set injects and self-validates")
    sim = FaultSimulator(df, seed=42)
    f1, l1, e1 = sim.inject(CHALLENGE_CONFIG)   # internal assertions run here
    check("challenge: episodes generated", len(e1) > 0, f"{len(e1)} episodes")
    check("all 8 fault kinds present", e1.fault_type.nunique() == 8,
          f"{sorted(e1.fault_type.unique())}")

    print("\n[3] no label leakage / no rows touched outside episodes")
    changed = np.zeros(len(df), dtype=bool)
    for v in VARS:
        changed |= ~np.isclose(clean[v], f1[v].to_numpy(), rtol=0, atol=1e-12)
    lab = l1.is_fault.to_numpy().astype(bool)
    check("every modified row is labelled", not (changed & ~lab).any(),
          f"{int((changed & ~lab).sum())} unlabelled modifications")
    check("every labelled row is modified", not (lab & ~changed).any(),
          f"{int((lab & ~changed).sum())} unlearnable positives")

    print("\n[4] episode ids and boundaries")
    ids = l1.loc[lab, "episode_id"].to_numpy()
    check("no labelled row without an episode", (ids >= 0).all())
    check("label ids == episode-log ids", set(np.unique(ids)) == set(e1.episode_id))
    iv = e1.sort_values("start_idx")[["start_idx", "end_idx"]].to_numpy()
    check("episode windows do not overlap",
          all(iv[i, 1] < iv[i + 1, 0] for i in range(len(iv) - 1)))
    inside = all(
        e.start_idx <= l1.index[l1.episode_id == e.episode_id].min()
        and l1.index[l1.episode_id == e.episode_id].max() <= e.end_idx
        for e in e1.itertuples())
    check("all labelled rows lie inside their episode window", inside)

    print("\n[5] reproducibility with a fixed seed")
    f2, l2, e2 = FaultSimulator(df, seed=42).inject(CHALLENGE_CONFIG)
    same = all(np.allclose(f1[v], f2[v], equal_nan=True) for v in VARS)
    check("same seed -> identical data", same)
    check("same seed -> identical labels", l1.equals(l2))
    f3, _, _ = FaultSimulator(df, seed=7).inject(CHALLENGE_CONFIG)
    diff = any(not np.allclose(f1[v], f3[v], equal_nan=True) for v in VARS)
    check("different seed -> different data", diff)

    print("\n[6] drift begins continuously from the baseline")
    ok_cont, ok_grow = True, True
    for e in e1[e1.fault_type == "drift"].itertuples():
        v = e.variable
        s = e.start_idx
        # the last PRE-episode sample must be untouched -> no step at onset
        if not np.isclose(clean[v][s - 1], f1[v].to_numpy()[s - 1], atol=1e-12):
            ok_cont = False
        off = f1[v].to_numpy()[s:e.end_idx + 1] - clean[v][s:e.end_idx + 1]
        # first labelled offset is small relative to the final offset (a ramp, not a step)
        if abs(off[0]) > abs(off[-1]) * 0.6 or abs(off[0]) == 0.0:
            ok_grow = False
    check("drift: sample before onset untouched (continuous)", ok_cont)
    check("drift: ramps from a small nonzero first step", ok_grow)

    print("\n[7] stuck-at freezes the LAST OBSERVED value")
    ok_stuck = True
    for e in e1[e1.fault_type == "stuck_at"].itertuples():
        v, s = e.variable, e.start_idx
        seg = f1[v].to_numpy()[s:e.end_idx + 1]
        if not (np.allclose(seg, seg[0]) and np.isclose(seg[0], clean[v][s - 1], atol=1e-9)):
            ok_stuck = False
    check("stuck_at: constant and equal to the pre-onset value", ok_stuck)

    print("\n[8] noise burst preserves the local baseline")
    worst = 0.0
    for e in e1[e1.fault_type == "noise_burst"].itertuples():
        v, s = e.variable, e.start_idx
        off = f1[v].to_numpy()[s:e.end_idx + 1] - clean[v][s:e.end_idx + 1]
        worst = max(worst, abs(off.mean()) / max(off.std(), 1e-9))
    check("noise: mean offset ~0 relative to its own spread", worst < 0.15,
          f"worst |mean|/sigma = {worst:.3f}")

    print("\n[9] positive / negative variants both fire")
    pos = neg = 0
    for e in e1[e1.fault_type == "spike"].itertuples():
        v, s = e.variable, e.start_idx
        d = f1[v].to_numpy()[s] - clean[v][s]
        pos += d > 0
        neg += d < 0
    check("spike: both signs produced", pos > 0 and neg > 0, f"{pos} positive / {neg} negative")

    print("\n[10] intermittent + combined faults label correctly")
    ok_int = True
    for e in e1[e1.fault_type == "intermittent_spikes"].itertuples():
        idx = l1.index[(l1.episode_id == e.episode_id) & (l1.is_fault == 1)].to_numpy()
        # sparse (fewer labels than the window) and non-consecutive
        if not (len(idx) < e.window_obs and (np.diff(idx) >= 2).all()):
            ok_int = False
    check("intermittent: sparse, non-consecutive labels only", ok_int)
    ok_comb = True
    for kind in ("drift_plus_noise", "bias_plus_spikes"):
        for e in e1[e1.fault_type == kind].itertuples():
            idx = l1.index[(l1.episode_id == e.episode_id) & (l1.is_fault == 1)].to_numpy()
            if len(idx) != e.window_obs:          # both components modify every row
                ok_comb = False
    check("combined faults: every window row labelled", ok_comb)

    print("\n[11] magnitudes are variable-relative, not one absolute number")
    med = {v: float(np.median([e.local_sigma for e in e1.itertuples() if e.variable == v]))
           for v in VARS}
    check("local sigma differs per variable", len(set(round(x, 3) for x in med.values())) == 3,
          " ".join(f"{v}={med[v]:.2f}" for v in VARS))
    check("local_scale is positive and finite",
          all(np.isfinite(local_scale(clean[v], 100, 12)) and local_scale(clean[v], 100, 12) > 0
              for v in VARS))

    n_fail = sum(1 for _, ok, _ in _checks if not ok)
    print("\n" + "=" * 66)
    print(f"{len(_checks) - n_fail}/{len(_checks)} checks passed")
    print("=" * 66)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
