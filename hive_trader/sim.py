"""Synthetic market feed for tests and dry runs (the sandbox had no exchange egress).

Random-walk mids with a 10-level book and random taker prints. There is NO signal in
this data by construction; any paper profit on it is noise or a bug.
"""
from __future__ import annotations

import math
import random

from .types import BookLevel, BookUpdate, TradePrint


def synthetic_events(symbol: str, start_ms: int, minutes: int, mid0: float, vol_1m_bps: float = 8.0,
                     spread_bps: float = 2.0, seed: int = 7, updates_per_min: int = 60,
                     latency_ms: int = 40):
    rng = random.Random(seed)
    mid = mid0
    step_ms = 60_000 // updates_per_min
    sd = vol_1m_bps / 1e4 / math.sqrt(updates_per_min)
    for k in range(minutes * updates_per_min):
        ts = start_ms + k * step_ms
        mid *= math.exp(rng.gauss(0, sd))
        half = mid * spread_bps / 2e4
        tick = mid * 1e-4
        bids = tuple(BookLevel(round(mid - half - i * tick, 6), round(rng.uniform(5, 50) * 1000 / mid, 6)) for i in range(10))
        asks = tuple(BookLevel(round(mid + half + i * tick, 6), round(rng.uniform(5, 50) * 1000 / mid, 6)) for i in range(10))
        yield BookUpdate(symbol, ts, ts + latency_ms, bids, asks)
        if rng.random() < 0.6:
            side = "buy" if rng.random() < 0.5 else "sell"
            px = asks[0].price if side == "buy" else bids[0].price
            yield TradePrint(symbol, ts + 1, ts + latency_ms + 1, px, round(rng.uniform(1, 20) * 1000 / mid, 6), side)
