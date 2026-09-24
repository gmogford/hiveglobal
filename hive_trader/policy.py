"""Policy: turns (snapshot, Jev answer, risk state) into a Decision. Every gate is code.

Gate order (all failing reasons are collected and logged, not just the first):
  missing/late answer -> stale data -> ESCALATE checks -> direction/permission ->
  blackout -> setup_quality -> toxic_flow veto -> risk_state (max of code & model) ->
  calibrated probability -> cost/edge -> fractional Kelly sizing -> caps.

"Direction confidence > 0.80" is implemented as CALIBRATED PROBABILITY of the chosen
direction > min_direction_p. TypeSafe also returns a separate `confidence` statistic;
that one drives escalation (< 0.60 -> brain re-read), per the API docs' guidance that
confidence and probability are different quantities.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from .config import PolicyConfig, RiskLimits
from .finalists import Finalist
from .risk import RiskManager
from .types import RISK_SEVERITY, Decision, JevAnswer, Snapshot, Verdict


@dataclass(frozen=True)
class CalibrationMap:
    """Monotone piecewise-linear map raw_p -> calibrated_p, fitted offline by nightly review.

    `fitted=False` (identity) is allowed in paper mode only; live mode refuses to start
    without an approved fitted map (review/gate.py).
    """
    xs: tuple[float, ...] = (0.0, 1.0)
    ys: tuple[float, ...] = (0.0, 1.0)
    fitted: bool = False
    n_samples: int = 0

    def __post_init__(self) -> None:
        if len(self.xs) != len(self.ys) or len(self.xs) < 2:
            raise ValueError("calibration knots mismatch")
        if list(self.xs) != sorted(self.xs) or any(b < a for a, b in zip(self.ys, self.ys[1:])):
            raise ValueError("calibration map must be monotone non-decreasing")

    def __call__(self, p: float) -> float:
        p = min(max(p, self.xs[0]), self.xs[-1])
        i = bisect.bisect_right(self.xs, p) - 1
        if i >= len(self.xs) - 1:
            return self.ys[-1]
        x0, x1, y0, y1 = self.xs[i], self.xs[i + 1], self.ys[i], self.ys[i + 1]
        return y0 + (y1 - y0) * (p - x0) / (x1 - x0)


def kelly_fraction(p: float, b: float) -> float:
    """Full-Kelly fraction of bankroll to put AT RISK for a binary bet paying b:1."""
    if b <= 0:
        return 0.0
    return p - (1 - p) / b


def code_crisis(snap: Snapshot, cfg: PolicyConfig) -> list[str]:
    f = snap.fields
    why = []
    if (f.get("spread_bps") or 0) > cfg.crisis_spread_bps:
        why.append(f"spread {f['spread_bps']}bps > {cfg.crisis_spread_bps}")
    r1h = (f.get("ret_bps") or {}).get("1h")
    if r1h is not None and abs(r1h) > cfg.crisis_abs_ret1h_bps:
        why.append(f"|ret1h| {abs(r1h)}bps > {cfg.crisis_abs_ret1h_bps}")
    vr = f.get("vol_ratio")
    if vr is not None and vr > cfg.crisis_vol_ratio:
        why.append(f"vol_ratio {vr} > {cfg.crisis_vol_ratio}")
    return why


class Policy:
    def __init__(self, cfg: PolicyConfig, limits: RiskLimits, calibration: CalibrationMap) -> None:
        self.cfg = cfg
        self.limits = limits
        self.cal = calibration

    def decide(self, snap: Snapshot, ans: JevAnswer | None, fin: Finalist, risk: RiskManager,
               now_ms: int) -> Decision:
        cfg, L = self.cfg, self.limits
        d = Decision(symbol=snap.symbol, as_of=snap.as_of, verdict=Verdict.REJECT)
        R = d.reasons

        if ans is None:
            R.append("no_jev_answer")
            return d
        if ans.latency_ms > L.max_jev_latency_ms:
            R.append(f"jev_late {ans.latency_ms:.0f}ms > {L.max_jev_latency_ms}ms")
            return d
        age = snap.fields.get("age_ms", 10**9)
        if age > L.max_snapshot_age_ms or now_ms - snap.as_of > L.max_snapshot_age_ms:
            R.append(f"stale_snapshot age={age}ms")
            return d

        d.direction = ans.direction
        # --- escalation: brain must re-read before ANY action on this symbol
        esc = []
        if ans.direction_confidence is None or ans.direction_confidence < cfg.escalate_confidence_below:
            esc.append(f"jev_confidence {ans.direction_confidence} < {cfg.escalate_confidence_below}")
        if ans.regime == "crisis":
            esc.append("jev_regime=crisis")
        esc += [f"code_crisis: {w}" for w in code_crisis(snap, cfg)]
        if esc:
            d.verdict = Verdict.ESCALATE
            R.extend(esc)
            return d

        # --- permission gates (collect all)
        if ans.direction == "neutral":
            R.append("direction=neutral")
        elif ans.direction not in fin.allowed_directions:
            R.append(f"direction {ans.direction} not allowed for {fin.symbol}")
        if any(a <= now_ms < b for a, b in fin.blackouts):
            R.append("catalyst_blackout")
        if ans.setup_quality < cfg.min_setup_quality:
            R.append(f"setup_quality {ans.setup_quality} < {cfg.min_setup_quality}")
        if ans.toxic_flow_p >= cfg.max_toxic_flow_p:
            R.append(f"toxic_flow p={ans.toxic_flow_p:.2f}")
        code_rs = risk.code_risk_state(fin.symbol)
        model_rs = ans.risk_state if ans.risk_state in RISK_SEVERITY else "reduce"
        eff_rs = max(code_rs, model_rs, key=RISK_SEVERITY.__getitem__)
        if eff_rs != "safe":
            R.append(f"risk_state={eff_rs} (code={code_rs}, model={model_rs})")
        if abs(risk.position_frac(fin.symbol)) > 1e-9:
            R.append("already_positioned")

        # --- probability
        if ans.direction in ("long", "short"):
            p_long, p_short = ans.direction_probs.get("long", 0.0), ans.direction_probs.get("short", 0.0)
            denom = p_long + p_short
            p_raw = (p_long if ans.direction == "long" else p_short) / denom if denom > 0 else 0.0
            d.p_raw = p_raw
            d.p_calibrated = self.cal(p_raw)
            if d.p_calibrated <= cfg.min_direction_p:
                R.append(f"p_cal {d.p_calibrated:.3f} <= {cfg.min_direction_p}")

        # --- cost-aware bracket & Kelly (only meaningful if nothing failed so far)
        rv = snap.fields.get("rv1h_bps")
        if not rv:
            R.append("no_vol_estimate")
        if R:
            return d

        horizon_min = cfg.candle_ms * cfg.horizon_candles / 60_000
        sigma_h = rv * math.sqrt(horizon_min / 60.0)            # bps
        stop_bps, take_bps = cfg.stop_sigma * sigma_h, cfg.take_sigma * sigma_h
        cost = cfg.round_trip_cost_bps
        p = d.p_calibrated
        gross_edge = p * take_bps - (1 - p) * stop_bps
        if gross_edge < cfg.min_edge_over_cost * cost:
            R.append(f"edge {gross_edge:.1f}bps < {cfg.min_edge_over_cost}x cost {cost:.1f}bps")
            return d
        b = (take_bps - cost) / (stop_bps + cost)
        k = kelly_fraction(p, b)
        d.kelly_full = k
        if k <= 0:
            R.append(f"kelly {k:.3f} <= 0 after costs")
            return d

        risk_frac = min(cfg.kelly_fraction * k, L.max_risk_per_trade)
        loss_per_notional = (stop_bps + cost) / 1e4
        cap = min(L.max_position_frac, fin.max_position_frac or L.max_position_frac)
        eq = risk.equity()
        gross_room = max(0.0, L.max_gross_frac - risk.gross() / eq) if eq > 0 else 0.0
        size_frac = min(risk_frac / loss_per_notional, cap, gross_room)
        if size_frac <= 1e-4:
            R.append("size rounds to zero after caps")
            return d

        mid = snap.fields["mid"]
        sgn = 1 if d.direction == "long" else -1
        d.size_frac = size_frac
        d.notional = size_frac * eq
        d.stop_px = mid * (1 - sgn * stop_bps / 1e4)
        d.take_px = mid * (1 + sgn * take_bps / 1e4)
        d.verdict = Verdict.FIRE
        return d
