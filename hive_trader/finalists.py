"""Finalist universe. Research + rationale: docs/research/FINALISTS_2026-09-24.md.

`allowed_directions` is enforced in CODE (policy.py). The `context` line is the only
thesis text Jev sees; it is short on purpose (Jev is documented to be distracted by
large irrelevant state). Catalyst dates are enforced as code-side blackout windows.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DAY = 86_400_000


@dataclass(frozen=True)
class Finalist:
    symbol: str                                  # internal id, also the Jev question prefix
    venue_symbol: str                            # perp symbol on execution venue [CONFIRM per venue]
    allowed_directions: tuple[str, ...]
    context: str                                 # <= ~40 words, shown to Jev
    blackouts: tuple[tuple[int, int], ...] = field(default_factory=tuple)  # (start_ms, end_ms): no NEW entries
    max_position_frac: float | None = None       # tighter per-name cap than the global one (never looser)


def _ts(y: int, m: int, d: int) -> int:
    import datetime as _dt
    return int(_dt.datetime(y, m, d, tzinfo=_dt.timezone.utc).timestamp() * 1000)


FINALISTS: tuple[Finalist, ...] = (
    Finalist(
        symbol="HYPE",
        venue_symbol="HYPE-PERP",
        allowed_directions=("long", "short"),
        context=("Perp DEX token; ~97% of protocol fees buy back HYPE. Large locked supply "
                 "(~77% not circulating). Tends to lead on risk-on days and gap down on "
                 "liquidation cascades."),
        max_position_frac=0.08,
    ),
    Finalist(
        symbol="AAVE",
        venue_symbol="AAVE-PERP",
        allowed_directions=("long", "short"),
        context=("Lending protocol; since 2026-06-27 protocol revenue auto-buys AAVE. "
                 "Revenue tracks borrow demand, which falls when funding and leverage fall."),
        max_position_frac=0.08,
    ),
    Finalist(
        symbol="SOL",
        venue_symbol="SOL-PERP",
        allowed_directions=("long", "short"),
        context=("L1; spot ETFs live; Alpenglow consensus upgrade targeted around Oct 2026 "
                 "(date not confirmed). High beta to BTC."),
    ),
    Finalist(
        symbol="ENA",
        venue_symbol="ENA-PERP",
        # Event-driven: ~14% of circulating supply becomes transferable 2026-10-05 and the
        # fee-switch buyback is dormant until USDe >= $7.5B (was ~$4B). Long side disabled.
        allowed_directions=("short",),
        context=("Synthetic-dollar protocol token. Large investor unlock 2026-10-05; buybacks "
                 "inactive until USDe supply roughly doubles. Squeeze-prone when funding flips negative."),
        # no new entries 12h either side of 2026-10-05 00:00Z (exact unlock time unconfirmed): gap risk, not edge
        blackouts=((_ts(2026, 10, 4) + DAY // 2, _ts(2026, 10, 5) + DAY // 2),),
        max_position_frac=0.05,
    ),
)

BY_SYMBOL = {f.symbol: f for f in FINALISTS}
