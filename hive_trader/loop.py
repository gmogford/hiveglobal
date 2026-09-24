"""The live REFLEX loop. Event-driven; one Jev call per candle close covers all finalists.

Per book update:   engine.on_book -> risk.on_mark -> protective exits (stops / drawdown flatten)
Per candle close:  snapshots (code) -> ONE Jev call -> policy per symbol (code) ->
                   escalation freeze check -> risk.pre_trade_check -> venue.submit -> ledger
"""
from __future__ import annotations

import time

from .config import PolicyConfig, RiskLimits
from .escalation import EscalationDesk
from .execution.base import Venue
from .finalists import Finalist
from .jev.client import JevModel
from .ledger import Ledger
from .policy import Policy
from .risk import RiskManager
from .state_engine import PortfolioView, StateEngine
from .types import BookUpdate, FundingUpdate, Order, TradePrint, Verdict


class TradingLoop:
    def __init__(self, finalists: tuple[Finalist, ...], jev: JevModel, policy: Policy,
                 risk: RiskManager, venue: Venue, ledger: Ledger, desk: EscalationDesk,
                 pcfg: PolicyConfig, limits: RiskLimits) -> None:
        self.finalists = {f.symbol: f for f in finalists}
        self.engines = {f.symbol: StateEngine(f.symbol) for f in finalists}
        self.books: dict[str, BookUpdate] = {}
        self.jev, self.policy, self.risk = jev, policy, risk
        self.venue, self.ledger, self.desk = venue, ledger, desk
        self.pcfg, self.limits = pcfg, limits
        self._seq = 0

    # ------------------------------------------------------------------ events
    def on_event(self, ev) -> None:
        if isinstance(ev, BookUpdate):
            self.engines[ev.symbol].on_book(ev)
            if ev.bids and ev.asks and ev.bids[0].price < ev.asks[0].price:
                self.books[ev.symbol] = ev
                mid = (ev.bids[0].price + ev.asks[0].price) / 2
                for o in self.risk.on_mark(ev.symbol, mid, ev.recv_ts):
                    self._execute(o, ev.recv_ts)
        elif isinstance(ev, TradePrint):
            self.engines[ev.symbol].on_trade(ev)
        elif isinstance(ev, FundingUpdate):
            self.engines[ev.symbol].on_funding(ev)

    # ------------------------------------------------------------------ decisions
    def on_candle_close(self, as_of: int, now_ms: int | None = None) -> list:
        now_ms = as_of if now_ms is None else now_ms
        snaps = {}
        for s, eng in self.engines.items():
            pf = PortfolioView(position_frac=self.risk.position_frac(s),
                               unrealized_bps=self._upnl_bps(s),
                               drawdown_frac=self.risk.drawdown(),
                               daily_pnl_frac=self.risk.daily_pnl_frac())
            snap = eng.snapshot(as_of, pf)
            if snap is not None:
                snaps[s] = snap
                self.ledger.write("mark", as_of, symbol=s, mid=snap.fields["mid"])
        if not snaps:
            return []

        horizon_min = int(self.pcfg.candle_ms * self.pcfg.horizon_candles / 60_000)
        t0 = time.perf_counter()
        answers, meta = self.jev.evaluate({s: sn.fields for s, sn in snaps.items()},
                                          tuple(self.finalists[s] for s in snaps),
                                          horizon_min, self.pcfg.round_trip_cost_bps)
        self.ledger.write("jev_call", as_of, meta=meta, n_answers=len(answers),
                          wall_ms=(time.perf_counter() - t0) * 1e3)

        decisions = []
        for s, snap in snaps.items():
            fin = self.finalists[s]
            ans = answers.get(s)
            d = self.policy.decide(snap, ans, fin, self.risk, now_ms)
            if d.verdict == Verdict.ESCALATE:
                tid = self.desk.escalate(s, as_of, d.reasons, {"snapshot": snap.fields, "answer": ans})
                d.reasons.append(f"ticket={tid}")
            elif d.verdict == Verdict.FIRE and self.desk.is_frozen(s, now_ms):
                d.verdict = Verdict.REJECT
                d.reasons.append("symbol frozen pending brain review")
            self.ledger.write("decision", as_of, decision=d, answer=ans, snapshot=snap.fields)
            if d.verdict == Verdict.FIRE:
                self._enter(d, now_ms)
            decisions.append(d)
        return decisions

    # ------------------------------------------------------------------ execution
    def _enter(self, d, now_ms: int) -> None:
        book = self.books.get(d.symbol)
        if book is None:
            return
        mid = (book.bids[0].price + book.asks[0].price) / 2
        side = "buy" if d.direction == "long" else "sell"
        # marketable limit capped at the expected-slippage budget: we accept a miss over a bad fill
        cap = (self.pcfg.expected_slippage_bps * 2) / 1e4
        lim = mid * (1 + cap) if side == "buy" else mid * (1 - cap)
        self._seq += 1
        o = Order(client_id=f"e-{d.symbol}-{d.as_of}-{self._seq}", symbol=d.symbol, side=side,
                  qty=d.notional / mid, limit_px=lim, reduce_only=False, created_ts=now_ms,
                  reason="entry")
        self._execute(o, now_ms, stop_px=d.stop_px, take_px=d.take_px)

    def _execute(self, o: Order, now_ms: int, stop_px=None, take_px=None) -> None:
        ok, why = self.risk.pre_trade_check(o, now_ms)      # kill switch checked inside, first
        if not ok:
            self.ledger.write("risk_veto", now_ms, order=o, reasons=why)
            return
        book = self.books.get(o.symbol)
        if book is None:
            self.ledger.write("risk_veto", now_ms, order=o, reasons=["no book"])
            return
        self.ledger.write("order", now_ms, order=o)
        fills = self.venue.submit(o, book)
        if not fills:
            self.ledger.write("miss", now_ms, order=o, reason="no fill within limit")
        for f in fills:
            self.risk.on_fill(f, stop_px, take_px)
            self.ledger.write("fill", now_ms, fill=f, equity=self.risk.equity())

    def _upnl_bps(self, s: str) -> float:
        p = self.risk.positions.get(s)
        if not p or p.qty == 0 or p.avg_px <= 0:
            return 0.0
        m = self.risk.marks.get(s, p.avg_px)
        return (m / p.avg_px - 1) * 1e4 * (1 if p.qty > 0 else -1)
