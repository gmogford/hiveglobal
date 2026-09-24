"""Deterministic state engine: live order book + trades -> one compact numeric snapshot.

Guarantees (tested in tests/test_state_engine.py):
  1. Causality: a snapshot at `as_of` is built only from events with recv_ts <= as_of.
     If the engine has already ingested anything newer, snapshot() raises CausalityError
     instead of silently mixing the future in.
  2. Determinism: identical event sequence + as_of -> byte-identical snapshot JSON.
  3. Compactness: serialized snapshot stays under TOKEN_BUDGET (~4 chars/token estimate).
  4. Every number is computed here. Jev receives results, never raw arithmetic tasks.
"""
from __future__ import annotations

import bisect
import json
import math
from collections import deque
from dataclasses import dataclass

from .types import BookUpdate, CausalityError, FundingUpdate, Snapshot, TradePrint

TOKEN_BUDGET = 400
SAMPLE_MS = 1_000          # mid sampled into 1s bins
HISTORY_MS = 4 * 3_600_000 # keep 4h of mids
TRADE_WINDOW_MS = 3_600_000


def estimate_tokens(obj: object) -> int:
    """Conservative token estimate for compact JSON (~3.5 chars/token for numeric JSON)."""
    return math.ceil(len(json.dumps(obj, separators=(",", ":"))) / 3.5)


@dataclass(frozen=True)
class PortfolioView:
    """Inventory/drawdown are computed by the risk layer (code) and injected here."""
    position_frac: float = 0.0     # signed notional / equity
    unrealized_bps: float = 0.0
    drawdown_frac: float = 0.0     # from high-water mark
    daily_pnl_frac: float = 0.0


class StateEngine:
    def __init__(self, symbol: str, depth_levels: int = 5) -> None:
        self.symbol = symbol
        self.depth_levels = depth_levels
        self._book: BookUpdate | None = None
        self._mid_ts: list[int] = []      # bin timestamps, ascending, one per SAMPLE_MS bin
        self._mid_px: list[float] = []
        self._trades: deque[TradePrint] = deque()
        self._funding: FundingUpdate | None = None
        self._last_recv_ts: int = -1
        self.dropped_out_of_order = 0

    # ---------------------------------------------------------------- ingest
    def _accept(self, recv_ts: int, symbol: str) -> bool:
        if symbol != self.symbol:
            raise ValueError(f"event for {symbol} sent to engine {self.symbol}")
        if recv_ts < self._last_recv_ts:
            # our own receive clock went backwards -> adapter bug; never reorder silently
            self.dropped_out_of_order += 1
            return False
        self._last_recv_ts = recv_ts
        return True

    def on_book(self, u: BookUpdate) -> None:
        if not self._accept(u.recv_ts, u.symbol):
            return
        if not u.bids or not u.asks:
            return
        if u.bids[0].price >= u.asks[0].price:
            return  # crossed/locked book: ignore the update, keep last good one
        self._book = u
        mid = (u.bids[0].price + u.asks[0].price) / 2
        b = u.recv_ts - (u.recv_ts % SAMPLE_MS)
        if self._mid_ts and self._mid_ts[-1] == b:
            self._mid_px[-1] = mid
        else:
            self._mid_ts.append(b)
            self._mid_px.append(mid)
        cut = bisect.bisect_left(self._mid_ts, u.recv_ts - HISTORY_MS)
        if cut > 4096:  # amortized trim
            del self._mid_ts[:cut], self._mid_px[:cut]

    def on_trade(self, t: TradePrint) -> None:
        if not self._accept(t.recv_ts, t.symbol):
            return
        self._trades.append(t)
        while self._trades and self._trades[0].recv_ts < t.recv_ts - TRADE_WINDOW_MS:
            self._trades.popleft()

    def on_funding(self, f: FundingUpdate) -> None:
        if self._accept(f.recv_ts, f.symbol):
            self._funding = f

    # ---------------------------------------------------------------- helpers
    def _mid_at(self, ts: int) -> float | None:
        """Last sampled mid with bin_ts <= ts (causal lookup)."""
        i = bisect.bisect_right(self._mid_ts, ts) - 1
        if i < 0 or self._mid_ts[i] < ts - HISTORY_MS:
            return None
        return self._mid_px[i]

    def _minute_returns(self, as_of: int, minutes: int) -> list[float]:
        rets = []
        prev = self._mid_at(as_of - minutes * 60_000)
        for k in range(minutes - 1, -1, -1):
            cur = self._mid_at(as_of - k * 60_000)
            if prev is not None and cur is not None and prev > 0:
                rets.append(math.log(cur / prev))
            prev = cur
        return rets

    @staticmethod
    def _std(xs: list[float]) -> float:
        if len(xs) < 2:
            return 0.0
        mu = sum(xs) / len(xs)
        return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))

    # ---------------------------------------------------------------- snapshot
    def snapshot(self, as_of: int, pf: PortfolioView | None = None) -> Snapshot | None:
        if self._last_recv_ts > as_of:
            raise CausalityError(
                f"{self.symbol}: engine already holds data at {self._last_recv_ts} > as_of {as_of}"
            )
        if self._book is None:
            return None
        pf = pf or PortfolioView()
        bk = self._book
        bid, ask = bk.bids[0].price, bk.asks[0].price
        mid = (bid + ask) / 2
        spread_bps = (ask - bid) / mid * 1e4

        bids = bk.bids[: self.depth_levels]
        asks = bk.asks[: self.depth_levels]
        bsz, asz = sum(l.size for l in bids), sum(l.size for l in asks)
        imbalance = (bsz - asz) / (bsz + asz) if bsz + asz > 0 else 0.0
        micro = (bid * bk.asks[0].size + ask * bk.bids[0].size) / (bk.bids[0].size + bk.asks[0].size)
        micro_bps = (micro - mid) / mid * 1e4

        def depth_usd(levels, band_bps):  # resting notional within band of mid, in $k
            lim = mid * band_bps / 1e4
            return sum(l.price * l.size for l in levels if abs(l.price - mid) <= lim) / 1e3

        def ret_bps(ms: int) -> float | None:
            past = self._mid_at(as_of - ms)
            return None if past is None else math.log(mid / past) * 1e4

        r1m = self._minute_returns(as_of, 60)
        r4h = self._minute_returns(as_of, 240)
        rv_1h_bps = self._std(r1m) * math.sqrt(60) * 1e4 if len(r1m) >= 10 else None
        rv_4h_ref = self._std(r4h) * math.sqrt(60) * 1e4 if len(r4h) >= 60 else None
        vol_ratio = rv_1h_bps / rv_4h_ref if rv_1h_bps and rv_4h_ref else None

        def flow(ms: int) -> tuple[float, float, int]:
            lo = as_of - ms
            buy = sell = 0.0
            n = 0
            for t in self._trades:
                if lo < t.recv_ts <= as_of:
                    n += 1
                    if t.taker_side == "buy":
                        buy += t.size * t.price
                    else:
                        sell += t.size * t.price
            tot = buy + sell
            return ((buy - sell) / tot if tot else 0.0), tot / 1e3, n

        cvd5, vol5k, n5 = flow(300_000)
        cvd60, vol60k, _ = flow(3_600_000)

        age_ms = as_of - bk.recv_ts
        max_ts = max(
            bk.recv_ts,
            max((t.recv_ts for t in self._trades if t.recv_ts <= as_of), default=bk.recv_ts),
            self._funding.recv_ts if self._funding else bk.recv_ts,
        )

        r = lambda x, d=1: None if x is None else round(x, d)  # noqa: E731
        fields = {
            "mid": float(f"{mid:.6g}"),
            "spread_bps": r(spread_bps, 2),
            "micro_bps": r(micro_bps, 2),
            "imb5": r(imbalance, 3),
            "depth25_k": [r(depth_usd(bids, 25)), r(depth_usd(asks, 25))],
            "ret_bps": {"1m": r(ret_bps(60_000)), "5m": r(ret_bps(300_000)),
                        "1h": r(ret_bps(3_600_000)), "4h": r(ret_bps(14_400_000))},
            "rv1h_bps": r(rv_1h_bps),
            "vol_ratio": r(vol_ratio, 2),
            "cvd": {"5m": r(cvd5, 3), "1h": r(cvd60, 3)},
            "tvol_k": {"5m": r(vol5k), "1h": r(vol60k)},
            "trades5m": n5,
            "funding_bps_8h": r(self._funding.rate_8h * 1e4, 2) if self._funding else None,
            "pos_frac": r(pf.position_frac, 3),
            "upnl_bps": r(pf.unrealized_bps),
            "dd_frac": r(pf.drawdown_frac, 4),
            "day_pnl_frac": r(pf.daily_pnl_frac, 4),
            "age_ms": age_ms,
        }
        snap = Snapshot(symbol=self.symbol, as_of=as_of, max_input_ts=max_ts, fields=fields)
        if estimate_tokens(fields) > TOKEN_BUDGET:
            raise ValueError(f"{self.symbol}: snapshot exceeds {TOKEN_BUDGET}-token budget")
        return snap


def snapshot_json(s: Snapshot) -> str:
    return json.dumps({"symbol": s.symbol, "as_of": s.as_of, **s.fields}, sort_keys=True,
                      separators=(",", ":"))
