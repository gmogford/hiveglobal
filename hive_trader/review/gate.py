"""Approval gate for the live bundle (limits + policy + finalists + Jev schema + calibration).

The loop computes the bundle hash at startup and refuses to run unless it matches
config/approved.lock.json. There is no code path that writes the lock except approve(),
which requires a named human approver and evidence meeting the pass/fail criteria below.
Overnight self-modification is therefore impossible without a human signature.
"""
from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path

from ..config import PolicyConfig, RiskLimits, content_hash
from ..finalists import Finalist
from ..jev.schema import SCHEMA_VERSION, schema_hash
from ..policy import CalibrationMap

# ---- pass/fail criteria (docs/00_AGENKIT_PHASES.md, gates G4 and G5) ----
PAPER_CRITERIA = {"tests_passed": True}
LIVE_CRITERIA = {
    "tests_passed": True,
    "paper_days_min": 14,
    "scored_decisions_min": 500,        # NON-OVERLAPPING outcomes (nightly n_independent), not raw count
    "brier_skill_oos_min": 0.02,        # out-of-sample skill vs base rate
    "latency_p95_ms_max": None,         # filled from RiskLimits.max_jev_latency_ms
    "net_pnl_after_costs_min": 0.0,     # paper, after pessimistic fills
    "max_drawdown_paper_max": None,     # filled: half of RiskLimits.max_drawdown
    "calibration_fitted": True,
}


class GateError(RuntimeError):
    pass


def bundle(limits: RiskLimits, pcfg: PolicyConfig, finalists: tuple[Finalist, ...],
           cal: CalibrationMap) -> dict:
    return {"schema_version": SCHEMA_VERSION, "schema_hash": schema_hash(finalists),
            "limits": dataclasses.asdict(limits), "policy": dataclasses.asdict(pcfg),
            "finalists": [dataclasses.asdict(f) for f in finalists],
            "calibration": dataclasses.asdict(cal)}


def bundle_hash(b: dict) -> str:
    return content_hash(b)


def live_criteria(limits: RiskLimits) -> dict:
    c = dict(LIVE_CRITERIA)
    c["latency_p95_ms_max"] = limits.max_jev_latency_ms
    c["max_drawdown_paper_max"] = limits.max_drawdown / 2
    return c


def check_evidence(mode: str, ev: dict, limits: RiskLimits) -> list[str]:
    fails = []
    if ev.get("tests_passed") is not True:
        fails.append("tests_passed != true")
    if mode == "live":
        c = live_criteria(limits)
        if ev.get("paper_days", 0) < c["paper_days_min"]:
            fails.append(f"paper_days {ev.get('paper_days')} < {c['paper_days_min']}")
        if ev.get("scored_decisions", 0) < c["scored_decisions_min"]:
            fails.append(f"scored_decisions {ev.get('scored_decisions')} < {c['scored_decisions_min']}")
        if (ev.get("brier_skill_oos") or -1) < c["brier_skill_oos_min"]:
            fails.append(f"brier_skill_oos {ev.get('brier_skill_oos')} < {c['brier_skill_oos_min']}")
        if (ev.get("latency_p95_ms") or 1e9) > c["latency_p95_ms_max"]:
            fails.append(f"latency_p95_ms {ev.get('latency_p95_ms')} > {c['latency_p95_ms_max']}")
        if (ev.get("net_pnl_after_costs") if ev.get("net_pnl_after_costs") is not None else -1) <= c["net_pnl_after_costs_min"]:
            fails.append(f"net_pnl_after_costs {ev.get('net_pnl_after_costs')} <= 0")
        if (ev.get("max_drawdown_paper") if ev.get("max_drawdown_paper") is not None else 1) > c["max_drawdown_paper_max"]:
            fails.append(f"max_drawdown_paper {ev.get('max_drawdown_paper')} > {c['max_drawdown_paper_max']}")
    return fails


def approve(b: dict, mode: str, approver: str, evidence: dict, limits: RiskLimits,
            lock_path: str | Path) -> dict:
    if mode not in ("paper", "live"):
        raise GateError("mode must be paper or live")
    if not approver or approver.strip().lower() in {"auto", "bot", "claude", "system", "jev"}:
        raise GateError("approval requires a named human approver")
    if mode == "live" and not b["calibration"]["fitted"]:
        raise GateError("live mode requires a fitted, reviewed calibration map")
    fails = check_evidence(mode, evidence, limits)
    if fails:
        raise GateError("evidence fails gate: " + "; ".join(fails))
    lock = {"hash": bundle_hash(b), "mode": mode, "approved_by": approver.strip(),
            "approved_at_ms": int(time.time() * 1000), "schema_version": b["schema_version"],
            "evidence": evidence}
    Path(lock_path).write_text(json.dumps(lock, indent=2))
    return lock


def verify(b: dict, mode: str, lock_path: str | Path) -> dict:
    try:
        lock = json.loads(Path(lock_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise GateError(f"no valid approval lock at {lock_path}: {e}") from e
    h = bundle_hash(b)
    if lock.get("hash") != h:
        raise GateError(f"live bundle hash {h[:12]} != approved {str(lock.get('hash'))[:12]} — "
                        "config/schema/calibration changed without approval")
    if mode == "live" and lock.get("mode") != "live":
        raise GateError("bundle approved for paper only")
    return lock
