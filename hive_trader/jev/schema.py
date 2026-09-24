"""Jev decision schema: one request, all finalists, five questions each.

Wire format verified against @ai-sdk/typesafe-ai v3.0.6 (dist/index.js):
    POST {base}/systemone  {"model": ..., "state": ..., "questions": {...}}
    question types: "choice" {instructions, criteria: {key: desc}},
                    "score"  {instructions, criteria: [levels...]},
                    "noul"   {instructions}   (the SDK's "boolean")
    answers: choice -> {type, choice, probabilities, confidence?}
             noul   -> {type, noul: P(true)}

Design choices:
  * setup_quality is a 4-way ordered CHOICE ("q0".."q3"), not a "score". The score type
    returns a fractional score whose level indexing (0- or 1-based) is not documented
    [CONFIRM with TypeSafe]; a choice parses unambiguously and still gives full probabilities.
  * risk_state is asked of Jev but is ADVISORY: code computes its own risk_state and
    the policy takes the more severe of the two. Jev can only make the system more cautious.
  * toxic_flow is a veto input only.
Any edit to this file changes SCHEMA_HASH, which the approval gate checks at startup.
"""
from __future__ import annotations

import hashlib
import json

from ..finalists import Finalist

SCHEMA_VERSION = "2026-09-24.1"

SEP = "__"  # question id = f"{symbol}{SEP}{field}"
FIELDS = ("regime", "direction", "toxic_flow", "setup_quality", "risk_state")

GOAL = ("Score each crypto perp independently from its own snapshot. The decision horizon is "
        "the next {horizon_min} minutes. A trade pays ~{cost_bps:.0f} bps round trip in fees and "
        "slippage, so a direction only counts if the move should clearly exceed that. All "
        "numbers are precomputed; do not recompute them. Prefer neutral when unsure.")

REGIME = {
    "trending": "Persistent directional drift: 1h and 4h returns agree, flow (cvd) confirms.",
    "mean_reverting": "Range-bound: returns oscillate, spread and depth normal, no flow persistence.",
    "high_vol": "Volatility expanding (vol_ratio well above 1) without a clear direction.",
    "crisis": "Disorderly: gap moves, spread blown out, depth vanished, one-sided liquidation flow.",
}
DIRECTION = {
    "long": "Mid more likely to finish the horizon higher by more than round-trip cost.",
    "short": "Mid more likely to finish the horizon lower by more than round-trip cost.",
    "neutral": "No edge larger than cost, or signals conflict.",
}
QUALITY = {
    "q0": "No setup.",
    "q1": "Weak: one signal only.",
    "q2": "Good: trend/flow/book agree and the context supports it.",
    "q3": "Excellent: strong multi-signal agreement in a supportive regime.",
}
RISK = {
    "safe": "Position, drawdown and liquidity leave room to add risk.",
    "near_limit": "Position or drawdown already meaningful; adding risk is marginal.",
    "reduce": "Conditions argue for cutting exposure now.",
}


def build_questions(finalists: tuple[Finalist, ...]) -> dict:
    q: dict = {}
    for f in finalists:
        s = f.symbol
        base = {"asset": s, "context": f.context}
        q[f"{s}{SEP}regime"] = {"type": "choice", "instructions": {**base, "question": f"Market regime of {s} right now?"}, "criteria": REGIME}
        q[f"{s}{SEP}direction"] = {"type": "choice", "instructions": {**base, "question": f"Direction for {s} over the horizon?"}, "criteria": DIRECTION}
        q[f"{s}{SEP}toxic_flow"] = {"type": "noul", "instructions": {**base, "question": (
            f"Is {s} order flow toxic (informed or liquidation-driven one-sided taker flow that "
            "would run over a new position)?")}}
        q[f"{s}{SEP}setup_quality"] = {"type": "choice", "instructions": {**base, "question": f"Quality of the {s} setup?"}, "criteria": QUALITY}
        q[f"{s}{SEP}risk_state"] = {"type": "choice", "instructions": {**base, "question": f"Risk state for adding {s} exposure?"}, "criteria": RISK}
    return q


def build_state(snapshots: dict[str, dict], horizon_min: int, cost_bps: float) -> dict:
    return {"goal": GOAL.format(horizon_min=horizon_min, cost_bps=cost_bps), "assets": snapshots}


def schema_hash(finalists: tuple[Finalist, ...]) -> str:
    blob = json.dumps({"v": SCHEMA_VERSION, "goal": GOAL, "q": build_questions(finalists)},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()
