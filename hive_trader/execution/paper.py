"""Paper venue with pessimistic, not optimistic, fills.

  * walks the visible book level by level (no fills beyond visible depth)
  * only fills against the book as it was when the order is submitted, then
    applies an extra adverse latency penalty (default 1 bp) for queue/latency drift
  * charges taker fee on every fill; never assumes maker rebates
  * respects the order's limit price (IOC: unfilled remainder is cancelled)
"""
from __future__ import annotations

from ..types import BookUpdate, Fill, Order


class PaperVenue:
    name = "paper"

    def __init__(self, taker_fee_bps: float = 4.5, latency_penalty_bps: float = 1.0,
                 visible_depth_fraction: float = 0.5) -> None:
        self.fee = taker_fee_bps / 1e4
        self.penalty = latency_penalty_bps / 1e4
        self.depth_frac = visible_depth_fraction  # assume we only get half of displayed size

    def submit(self, order: Order, book: BookUpdate) -> list[Fill]:
        levels = book.asks if order.side == "buy" else book.bids
        mid = (book.bids[0].price + book.asks[0].price) / 2
        remaining, notional, filled = order.qty, 0.0, 0.0
        for lvl in levels:
            px = lvl.price * (1 + self.penalty if order.side == "buy" else 1 - self.penalty)
            if (order.side == "buy" and px > order.limit_px) or (order.side == "sell" and px < order.limit_px):
                break
            take = min(remaining, lvl.size * self.depth_frac)
            notional += take * px
            filled += take
            remaining -= take
            if remaining <= 1e-12:
                break
        if filled <= 0:
            return []
        vwap = notional / filled
        slip_bps = (vwap / mid - 1) * 1e4 * (1 if order.side == "buy" else -1)
        return [Fill(client_id=order.client_id, symbol=order.symbol, side=order.side, qty=filled,
                     px=vwap, fee=notional * self.fee, ts=book.recv_ts, slippage_bps=slip_bps)]
