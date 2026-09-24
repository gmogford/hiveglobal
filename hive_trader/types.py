"""Core value types. All timestamps are integer milliseconds since epoch (UTC).

Two clocks exist and are never mixed up:
  * exchange_ts - when the venue says the event happened (informational only)
  * recv_ts     - when *we* received it. Causality is enforced on recv_ts, because
                  that is the moment the information became available to a decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

Side = Literal["buy", "sell"]
Direction = Literal["long", "short", "neutral"]
Regime = Literal["trending", "mean_reverting", "high_vol", "crisis"]
RiskState = Literal["safe", "near_limit", "reduce"]

RISK_SEVERITY: dict[str, int] = {"safe": 0, "near_limit": 1, "reduce": 2}


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class BookUpdate:
    """Full L2 snapshot of the top of book (venue adapters convert deltas to snapshots)."""
    symbol: str
    exchange_ts: int
    recv_ts: int
    bids: tuple[BookLevel, ...]  # best first
    asks: tuple[BookLevel, ...]  # best first


@dataclass(frozen=True)
class TradePrint:
    symbol: str
    exchange_ts: int
    recv_ts: int
    price: float
    size: float
    taker_side: Side


@dataclass(frozen=True)
class FundingUpdate:
    symbol: str
    exchange_ts: int
    recv_ts: int
    rate_8h: float  # fraction per 8h, e.g. 0.0001 = 0.01%


@dataclass(frozen=True)
class Snapshot:
    """The ONLY thing Jev sees. Compact, numeric, causally stamped."""
    symbol: str
    as_of: int            # decision time (ms)
    max_input_ts: int     # newest recv_ts that contributed; must be <= as_of
    fields: dict          # flat-ish dict of rounded numbers, see state_engine.FIELDS

    def __post_init__(self) -> None:
        if self.max_input_ts > self.as_of:
            raise CausalityError(
                f"{self.symbol}: snapshot uses data from {self.max_input_ts} > as_of {self.as_of}"
            )


class CausalityError(RuntimeError):
    """Raised when any input from after the decision point would leak into a snapshot."""


@dataclass(frozen=True)
class JevAnswer:
    """Parsed per-finalist answer from one Jev call. Pure data; carries no authority."""
    symbol: str
    regime: str
    regime_probs: dict[str, float]
    direction: str
    direction_probs: dict[str, float]
    direction_confidence: float | None  # TypeSafe 'confidence' statistic (separate from probability)
    toxic_flow_p: float                 # P(toxic_flow = true)
    setup_quality: int                  # 0..3
    setup_quality_probs: dict[str, float]
    risk_state: str
    risk_state_probs: dict[str, float]
    latency_ms: float
    model_id: str


class Verdict(str, Enum):
    FIRE = "fire"
    REJECT = "reject"
    ESCALATE = "escalate"


@dataclass
class Decision:
    symbol: str
    as_of: int
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    direction: str = "neutral"
    p_raw: float | None = None          # Jev probability for chosen direction
    p_calibrated: float | None = None   # after the approved calibration map
    kelly_full: float | None = None
    size_frac: float = 0.0              # fraction of equity, after every cap
    notional: float = 0.0
    stop_px: float | None = None
    take_px: float | None = None


@dataclass(frozen=True)
class Order:
    client_id: str
    symbol: str
    side: Side
    qty: float
    limit_px: float          # marketable limit; never a naked market order
    reduce_only: bool
    created_ts: int
    reason: str


@dataclass(frozen=True)
class Fill:
    client_id: str
    symbol: str
    side: Side
    qty: float
    px: float
    fee: float
    ts: int
    slippage_bps: float
