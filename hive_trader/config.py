"""Configuration: hard risk limits + policy thresholds.

Limits are loaded from config/limits.json, validated against absolute ceilings that
live in *code* (so a config typo cannot set max drawdown to 90%), and frozen.
The whole live config (limits + schema + calibration) is content-hashed; the loop
refuses to start unless that hash matches the operator-approved lock file
(see review/gate.py). No component can mutate these objects at runtime.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

# Absolute ceilings. Changing these requires a code change + review, not a config edit.
CEILING_MAX_DRAWDOWN = 0.20
CEILING_DAILY_LOSS = 0.05
CEILING_POSITION_FRAC = 0.25
CEILING_GROSS_FRAC = 1.0
CEILING_KELLY_FRACTION = 0.25     # "capped at quarter-Kelly"
CEILING_RISK_PER_TRADE = 0.01


@dataclass(frozen=True)
class RiskLimits:
    # Decided, not inherited — rationale in docs/02_ARCHITECTURE.md §Risk.
    max_drawdown: float = 0.10          # from equity high-water mark -> kill switch trips, flatten, manual re-arm
    max_daily_loss: float = 0.02        # of start-of-UTC-day equity -> no new entries until next UTC day
    max_position_frac: float = 0.10     # per-symbol notional / equity
    max_gross_frac: float = 0.30        # sum |notional| / equity
    max_risk_per_trade: float = 0.005   # loss-at-stop / equity
    max_leverage: float = 1.0
    max_orders_per_minute: int = 6
    max_snapshot_age_ms: int = 2_000    # stale book -> no trade
    max_jev_latency_ms: int = 1_500     # late answer -> treated as no answer
    near_limit_ratio: float = 0.6       # fraction of any limit at which code-side risk_state becomes near_limit
    reduce_ratio: float = 0.85          # ... becomes reduce

    def __post_init__(self) -> None:
        _check("max_drawdown", self.max_drawdown, CEILING_MAX_DRAWDOWN)
        _check("max_daily_loss", self.max_daily_loss, CEILING_DAILY_LOSS)
        _check("max_position_frac", self.max_position_frac, CEILING_POSITION_FRAC)
        _check("max_gross_frac", self.max_gross_frac, CEILING_GROSS_FRAC)
        _check("max_risk_per_trade", self.max_risk_per_trade, CEILING_RISK_PER_TRADE)
        if not (0 < self.max_leverage <= 1.0):
            raise ValueError("max_leverage must be in (0, 1]: this system does not run leverage")
        if not (0 < self.near_limit_ratio < self.reduce_ratio < 1):
            raise ValueError("need 0 < near_limit_ratio < reduce_ratio < 1")


@dataclass(frozen=True)
class PolicyConfig:
    min_setup_quality: int = 2
    min_direction_p: float = 0.80       # calibrated P(direction) must EXCEED this
    escalate_confidence_below: float = 0.60
    max_toxic_flow_p: float = 0.50      # model may veto via toxic_flow; it may never un-veto
    kelly_fraction: float = 0.25
    # bracket geometry in units of sigma_h (realized vol scaled to the decision horizon)
    stop_sigma: float = 1.0
    take_sigma: float = 1.5
    min_edge_over_cost: float = 1.5     # expected edge must be >= 1.5x round-trip cost
    taker_fee_bps: float = 4.5          # [ESTIMATE] typical VIP0 perp taker fee; set per venue
    expected_slippage_bps: float = 3.0  # [ESTIMATE] replaced by measured value from nightly review
    # code-side crisis detector (independent of Jev's regime call)
    crisis_spread_bps: float = 25.0
    crisis_abs_ret1h_bps: float = 1000.0
    crisis_vol_ratio: float = 3.0
    candle_ms: int = 300_000            # 5m candles
    horizon_candles: int = 12           # decision horizon = 1h

    def __post_init__(self) -> None:
        if self.kelly_fraction > CEILING_KELLY_FRACTION:
            raise ValueError(f"kelly_fraction {self.kelly_fraction} > quarter-Kelly ceiling")
        if not (0.5 < self.min_direction_p < 1):
            raise ValueError("min_direction_p must be in (0.5, 1)")
        if self.min_setup_quality not in (0, 1, 2, 3):
            raise ValueError("min_setup_quality must be 0..3")

    @property
    def round_trip_cost_bps(self) -> float:
        return 2 * (self.taker_fee_bps + self.expected_slippage_bps)


def _check(name: str, value: float, ceiling: float) -> None:
    if not (0 < value <= ceiling):
        raise ValueError(f"{name}={value} outside (0, {ceiling}] hard ceiling")


def load_limits(path: str | Path) -> tuple[RiskLimits, PolicyConfig]:
    raw = json.loads(Path(path).read_text())
    return RiskLimits(**raw.get("risk", {})), PolicyConfig(**raw.get("policy", {}))


def content_hash(*objs: object) -> str:
    """Stable sha256 over dataclasses / dicts, used for the approval lock."""
    h = hashlib.sha256()
    for o in objs:
        d = asdict(o) if hasattr(o, "__dataclass_fields__") else o
        h.update(json.dumps(d, sort_keys=True, separators=(",", ":")).encode())
    return h.hexdigest()
