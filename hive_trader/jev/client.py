"""Jev (TypeSafe System One) client. Scores only: returns JevAnswer objects, nothing else.

Failure policy: any transport error, timeout, schema mismatch, or late answer yields
an EMPTY result for the affected symbols. The policy treats a missing answer as REJECT.
The client never retries inside the decision window (a retried answer is a stale answer).

Latency: TypeSafe advertises 70-500 ms end to end; one public integration measured
~80 ms inference / ~100 ms loop p50 on a mock-shaped pipeline. NEITHER is our number.
Every call's wall-clock latency is recorded in the ledger; the nightly review reports
p50/p95 and the go-live gate requires measured p95 < RiskLimits.max_jev_latency_ms.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Protocol

from ..finalists import Finalist
from ..types import JevAnswer
from .schema import SEP, build_questions, build_state

DEFAULT_BASE_URL = "https://api.typesafe.ai/v1"
DEFAULT_MODEL = "jev-latest"


class JevModel(Protocol):
    def evaluate(self, snapshots: dict[str, dict], finalists: tuple[Finalist, ...],
                 horizon_min: int, cost_bps: float) -> tuple[dict[str, JevAnswer], dict]: ...


def parse_answers(raw: dict, finalists: tuple[Finalist, ...], latency_ms: float) -> dict[str, JevAnswer]:
    """Map the /systemone response onto per-symbol JevAnswer. Incomplete symbols are dropped."""
    answers = raw.get("answers") or {}
    model_id = raw.get("model") or DEFAULT_MODEL
    out: dict[str, JevAnswer] = {}
    for f in finalists:
        s = f.symbol
        try:
            reg = answers[f"{s}{SEP}regime"]
            dirn = answers[f"{s}{SEP}direction"]
            tox = answers[f"{s}{SEP}toxic_flow"]
            q = answers[f"{s}{SEP}setup_quality"]
            rs = answers[f"{s}{SEP}risk_state"]
            if not (reg["type"] == dirn["type"] == q["type"] == rs["type"] == "choice" and tox["type"] == "noul"):
                continue
            quality_key = q["choice"]
            if quality_key not in ("q0", "q1", "q2", "q3"):
                continue
            out[s] = JevAnswer(
                symbol=s,
                regime=reg["choice"], regime_probs=dict(reg["probabilities"]),
                direction=dirn["choice"], direction_probs=dict(dirn["probabilities"]),
                direction_confidence=dirn.get("confidence"),
                toxic_flow_p=float(tox["noul"]),
                setup_quality=int(quality_key[1]), setup_quality_probs=dict(q["probabilities"]),
                risk_state=rs["choice"], risk_state_probs=dict(rs["probabilities"]),
                latency_ms=latency_ms, model_id=model_id,
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


class TypeSafeJev:
    def __init__(self, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL,
                 model: str = DEFAULT_MODEL, timeout_s: float = 1.5) -> None:
        self.api_key = api_key or os.environ.get("TYPESAFE_AI_API_KEY")
        if not self.api_key:
            raise RuntimeError("TYPESAFE_AI_API_KEY not set")
        self.url = base_url.rstrip("/") + "/systemone"
        self.model = model
        self.timeout_s = timeout_s

    def evaluate(self, snapshots, finalists, horizon_min, cost_bps):
        body = {"model": self.model,
                "state": build_state(snapshots, horizon_min, cost_bps),
                "questions": build_questions(tuple(f for f in finalists if f.symbol in snapshots))}
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "User-Agent": "hive-trader/0.1"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            return {}, {"error": type(e).__name__, "detail": str(e)[:200],
                        "latency_ms": (time.perf_counter() - t0) * 1e3}
        latency_ms = (time.perf_counter() - t0) * 1e3
        meta = {"latency_ms": latency_ms, "model": raw.get("model"), "usage": raw.get("usage")}
        return parse_answers(raw, finalists, latency_ms), meta


class MockJev:
    """Deterministic stand-in for tests and paper runs without a key.

    Emits the exact wire shape of /systemone so parse_answers is exercised end to end.
    The 'signal' is trivial (momentum + flow); it has NO edge and must never be used live.
    """
    model_id = "mock-jev"

    def __init__(self, overrides: dict[str, dict] | None = None) -> None:
        self.overrides = overrides or {}

    def raw_response(self, snapshots: dict[str, dict]) -> dict:
        answers: dict = {}
        for s, snap in snapshots.items():
            ov = self.overrides.get(s, {})
            r1h = (snap.get("ret_bps") or {}).get("1h") or 0.0
            cvd = (snap.get("cvd") or {}).get("1h") or 0.0
            score = r1h / 50 + cvd * 2
            p_long = max(0.02, min(0.98, 0.5 + score / 4))
            p_long = ov.get("p_long", p_long)
            p_short = round(1 - p_long, 2)
            dirn = ov.get("direction", "long" if p_long > 0.55 else "short" if p_long < 0.45 else "neutral")
            answers[f"{s}{SEP}regime"] = {"type": "choice", "choice": ov.get("regime", "trending"),
                                          "probabilities": {"trending": 0.6, "mean_reverting": 0.2, "high_vol": 0.15, "crisis": 0.05},
                                          "confidence": 0.7}
            answers[f"{s}{SEP}direction"] = {"type": "choice", "choice": dirn,
                                             "probabilities": {"long": round(p_long, 2), "short": p_short, "neutral": 0.0},
                                             "confidence": ov.get("confidence", 0.75)}
            answers[f"{s}{SEP}toxic_flow"] = {"type": "noul", "noul": ov.get("toxic_p", 0.1)}
            answers[f"{s}{SEP}setup_quality"] = {"type": "choice", "choice": ov.get("quality", "q2"),
                                                 "probabilities": {"q0": 0.1, "q1": 0.2, "q2": 0.5, "q3": 0.2},
                                                 "confidence": 0.7}
            answers[f"{s}{SEP}risk_state"] = {"type": "choice", "choice": ov.get("risk_state", "safe"),
                                              "probabilities": {"safe": 0.8, "near_limit": 0.15, "reduce": 0.05},
                                              "confidence": 0.8}
        return {"model": self.model_id, "answers": answers, "usage": {"input_tokens": 0, "output_tokens": 0}}

    def evaluate(self, snapshots, finalists, horizon_min, cost_bps):
        raw = self.raw_response(snapshots)
        return parse_answers(raw, tuple(f for f in finalists if f.symbol in snapshots), 1.0), {"latency_ms": 1.0, "model": self.model_id}
