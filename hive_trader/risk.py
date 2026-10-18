"""Hard risk layer. Deterministic, outside the model's reach.

Nothing in this module reads a model output. The policy may *ask* for an order; this
module decides whether it may exist. `pre_trade_check` runs before EVERY order,
entries and exits alike, and the kill switch is consulted first, every time.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import RiskLimits
from .types import Fill, Order

UTC_DAY_MS = 86_400_000


class KillSwitch:
    """File-backed, fail-closed kill switch.

    State file: {"armed": true, "tripped": false, "reason": ""}.
      armed=True  -> the switch is live and will be checked (must be True to trade at all)
      tripped     -> no new risk; only reduce-only orders pass
    Unreadable / missing / malformed file => treated as TRIPPED. Re-arming after a trip
    is a manual operator action (edit the file or scripts/killswitch.py rearm).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._mem_tripped = False
        self._mem_reason = ""

    def state(self) -> tuple[bool, str]:
        """Returns (ok_to_add_risk, reason)."""
        if self._mem_tripped:
            return False, f"kill switch tripped: {self._mem_reason}"
        try:
            st = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            return False, f"kill switch unreadable ({type(e).__name__}) -> fail closed"
        if st.get("armed") is not True:
            return False, "kill switch not armed -> trading disabled"
        if st.get("tripped", True) is not False:
            return False, f"kill switch tripped: {st.get('reason', '')}"
        return True, "ok"

    def trip(self, reason: str) -> None:
        self._mem_tripped = True
        self._mem_reason = reason
        try:
            self.path.write_text(json.dumps({"armed": True, "tripped": True, "reason": reason,
                                             "ts": int(time.time() * 1000)}))
        except OSError:
            pass  # in-memory trip already holds; file write failure cannot un-trip


@dataclass
class Position:
    qty: float = 0.0       # signed
    avg_px: float = 0.0
    stop_px: float | None = None
    take_px: float | None = None


class RiskStateError(RuntimeError):
    """Saved risk state exists but cannot be trusted. The loop must not start on a reset state."""


STATE_VERSION = 1


@dataclass
class RiskManager:
    limits: RiskLimits
    kill: KillSwitch
    start_equity: float
    per_symbol_cap: dict[str, float] = field(default_factory=dict)  # tighter finalist caps
    state_path: Path | None = None   # set => state survives restarts; None => in-memory only (tests, sims)

    def __post_init__(self) -> None:
        self.cash = self.start_equity
        self.positions: dict[str, Position] = {}
        self.marks: dict[str, float] = {}
        self.hwm = self.start_equity
        self.day = None
        self.day_start_equity = self.start_equity
        self.day_halted = False
        self._order_ts: deque[int] = deque()
        self.fees_paid = 0.0
        self.restored = False
        if self.state_path is not None:
            self.state_path = Path(self.state_path)
            if self.state_path.exists():
                self._load()
                self.restored = True
            else:
                self.save()

    # ------------------------------------------------------------ persistence
    # A restart must never reset drawdown, the daily loss, or open positions. Every change to
    # cash, positions, HWM, the day boundary or the halt flag is written before the next event
    # is processed. A state file that exists but cannot be read is fatal (fail closed), never
    # silently replaced with a fresh one: that would hand a losing book a clean slate.
    def save(self) -> None:
        if self.state_path is None:
            return
        st = {"version": STATE_VERSION, "start_equity": self.start_equity, "cash": self.cash,
              "positions": {s: asdict(p) for s, p in self.positions.items()}, "marks": self.marks,
              "hwm": self.hwm, "day": self.day, "day_start_equity": self.day_start_equity,
              "day_halted": self.day_halted, "order_ts": list(self._order_ts), "fees_paid": self.fees_paid,
              "saved_at": int(time.time() * 1000)}
        tmp = self.state_path.with_suffix(".tmp")
        with tmp.open("w") as fh:
            json.dump(st, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.state_path)          # atomic: a crash mid-write leaves the old file

    def _load(self) -> None:
        try:
            st = json.loads(self.state_path.read_text())
            if st.get("version") != STATE_VERSION:
                raise ValueError(f"unsupported state version {st.get('version')!r}")
            self.start_equity = float(st["start_equity"])
            self.cash = float(st["cash"])
            self.positions = {s: Position(**p) for s, p in st["positions"].items()}
            self.marks = {s: float(v) for s, v in st["marks"].items()}
            self.hwm = float(st["hwm"])
            self.day = st["day"]
            self.day_start_equity = float(st["day_start_equity"])
            self.day_halted = bool(st["day_halted"])
            self._order_ts = deque(int(t) for t in st["order_ts"])
            self.fees_paid = float(st["fees_paid"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise RiskStateError(f"risk state {self.state_path} unreadable ({type(e).__name__}: {e}); "
                                 "refusing to start on a reset state. Inspect it; delete it only to "
                                 "deliberately start a fresh book.") from e

    # ------------------------------------------------------------ accounting
    def equity(self) -> float:
        return self.cash + sum(p.qty * self.marks.get(s, p.avg_px) for s, p in self.positions.items())

    def gross(self) -> float:
        return sum(abs(p.qty) * self.marks.get(s, p.avg_px) for s, p in self.positions.items())

    def drawdown(self) -> float:
        eq = self.equity()
        return 0.0 if self.hwm <= 0 else max(0.0, 1 - eq / self.hwm)

    def daily_pnl_frac(self) -> float:
        return self.equity() / self.day_start_equity - 1 if self.day_start_equity > 0 else 0.0

    def position_frac(self, symbol: str) -> float:
        p = self.positions.get(symbol)
        eq = self.equity()
        if not p or eq <= 0:
            return 0.0
        return p.qty * self.marks.get(symbol, p.avg_px) / eq

    def roll_day(self, ts: int) -> None:
        d = ts // UTC_DAY_MS
        if d != self.day:
            self.day = d
            self.day_start_equity = self.equity()
            self.day_halted = False
            self.save()

    def on_mark(self, symbol: str, px: float, ts: int) -> list[Order]:
        """Update mark; enforce drawdown/daily-loss; return protective exit orders."""
        self.marks[symbol] = px
        self.roll_day(ts)
        eq = self.equity()
        if eq > self.hwm:
            self.hwm = eq
            self.save()
        exits: list[Order] = []
        if self.drawdown() >= self.limits.max_drawdown:
            self.kill.trip(f"max drawdown {self.drawdown():.2%} >= {self.limits.max_drawdown:.0%}")
            self.save()
            return self.flatten_all(ts, "max_drawdown")
        if self.daily_pnl_frac() <= -self.limits.max_daily_loss and not self.day_halted:
            self.day_halted = True
            self.save()
        p = self.positions.get(symbol)
        if p and p.qty != 0:
            hit_stop = p.stop_px is not None and ((p.qty > 0 and px <= p.stop_px) or (p.qty < 0 and px >= p.stop_px))
            hit_take = p.take_px is not None and ((p.qty > 0 and px >= p.take_px) or (p.qty < 0 and px <= p.take_px))
            if hit_stop or hit_take:
                exits.append(self._close_order(symbol, p, px, ts, "stop" if hit_stop else "take"))
        return exits

    def _close_order(self, symbol: str, p: Position, px: float, ts: int, why: str) -> Order:
        side = "sell" if p.qty > 0 else "buy"
        # marketable limit with a 1% collar: exits must fill, but never at any price
        lim = px * (0.99 if side == "sell" else 1.01)
        return Order(client_id=f"x-{symbol}-{ts}-{why}", symbol=symbol, side=side, qty=abs(p.qty),
                     limit_px=lim, reduce_only=True, created_ts=ts, reason=why)

    def flatten_all(self, ts: int, why: str) -> list[Order]:
        return [self._close_order(s, p, self.marks.get(s, p.avg_px), ts, why)
                for s, p in self.positions.items() if p.qty != 0]

    def on_fill(self, f: Fill, stop_px: float | None = None, take_px: float | None = None) -> None:
        p = self.positions.setdefault(f.symbol, Position())
        signed = f.qty if f.side == "buy" else -f.qty
        self.cash -= signed * f.px + f.fee
        self.fees_paid += f.fee
        new_qty = p.qty + signed
        if p.qty == 0 or (p.qty > 0) == (signed > 0):          # open / add
            p.avg_px = (p.avg_px * abs(p.qty) + f.px * abs(signed)) / abs(new_qty)
            if stop_px is not None:
                p.stop_px, p.take_px = stop_px, take_px
        elif abs(signed) > abs(p.qty):                           # flip (policy never requests this)
            p.avg_px = f.px
            p.stop_px = p.take_px = None
        p.qty = 0.0 if abs(new_qty) < 1e-12 else new_qty
        if p.qty == 0:
            p.avg_px, p.stop_px, p.take_px = 0.0, None, None
        self.marks.setdefault(f.symbol, f.px)
        self.save()

    # ------------------------------------------------------------ gatekeeping
    def code_risk_state(self, symbol: str) -> str:
        L = self.limits
        cap = min(L.max_position_frac, self.per_symbol_cap.get(symbol, L.max_position_frac))
        eq = max(self.equity(), 1e-9)
        ratio = max(self.drawdown() / L.max_drawdown,
                    max(0.0, -self.daily_pnl_frac()) / L.max_daily_loss,
                    self.gross() / eq / L.max_gross_frac,
                    abs(self.position_frac(symbol)) / cap)
        if self.day_halted or ratio >= L.reduce_ratio:
            return "reduce"
        if ratio >= L.near_limit_ratio:
            return "near_limit"
        return "safe"

    def pre_trade_check(self, o: Order, now_ms: int) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        ok_kill, why = self.kill.state()                  # 1. kill switch, always first
        p = self.positions.get(o.symbol, Position())
        signed = o.qty if o.side == "buy" else -o.qty
        reduces = p.qty != 0 and (p.qty > 0) != (signed > 0) and abs(signed) <= abs(p.qty) + 1e-12
        if o.reduce_only and not reduces:
            return False, ["reduce_only order would not reduce position"]
        if o.qty <= 0 or o.limit_px <= 0:
            return False, ["non-positive qty/price"]
        mark = self.marks.get(o.symbol)
        if mark is None:
            return False, ["no mark price"]
        if abs(o.limit_px / mark - 1) > 0.02:
            return False, [f"limit {o.limit_px} >2% from mark {mark} (fat-finger guard)"]
        if o.reduce_only:
            return True, []                                   # exits always allowed once sane
        if not ok_kill:
            reasons.append(why)
        if self.day_halted:
            reasons.append("daily loss limit hit: entries halted until next UTC day")
        if self.drawdown() >= self.limits.max_drawdown:
            reasons.append("max drawdown breached")
        eq = self.equity()
        if eq <= 0:
            return False, reasons + ["non-positive equity"]
        cap = min(self.limits.max_position_frac, self.per_symbol_cap.get(o.symbol, self.limits.max_position_frac))
        post_pos = abs((p.qty + signed) * mark) / eq
        if post_pos > cap + 1e-9:
            reasons.append(f"position {post_pos:.3f} > cap {cap:.3f}")
        post_gross = (self.gross() - abs(p.qty) * mark + abs(p.qty + signed) * mark) / eq
        if post_gross > min(self.limits.max_gross_frac, self.limits.max_leverage) + 1e-9:
            reasons.append(f"gross {post_gross:.3f} > {self.limits.max_gross_frac:.3f}")
        while self._order_ts and self._order_ts[0] < now_ms - 60_000:
            self._order_ts.popleft()
        if len(self._order_ts) >= self.limits.max_orders_per_minute:
            reasons.append("order rate limit")
        if not reasons:
            self._order_ts.append(now_ms)
            self.save()
        return (not reasons), reasons
