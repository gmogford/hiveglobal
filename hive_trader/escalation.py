"""Escalation to the BRAIN layer.

When Jev's confidence < 0.60 or a crisis regime is detected (by Jev OR by code), the
symbol is frozen for new entries and a ticket is written. Protective exits (stops,
drawdown flatten) keep working — the freeze blocks new risk, never risk reduction.

A frozen symbol unfreezes only when a clearance file exists for its open ticket:
    runtime/escalations/cleared/<ticket_id>.json  {"by": "...", "until_ms": ..., "note": "..."}
Clearance is written by the brain (a Claude session doing the full re-read) or the operator
via scripts/clear_escalation.py. Clearances expire; nothing unfreezes by timeout alone.
"""
from __future__ import annotations

import json
from pathlib import Path

from .ledger import _default


class EscalationDesk:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        (self.root / "open").mkdir(parents=True, exist_ok=True)
        (self.root / "cleared").mkdir(parents=True, exist_ok=True)
        self._open: dict[str, str] = {}  # symbol -> ticket id
        for p in sorted((self.root / "open").glob("*.json")):
            t = json.loads(p.read_text())
            self._open[t["symbol"]] = t["id"]

    def escalate(self, symbol: str, ts: int, reasons: list[str], context: dict) -> str:
        if symbol in self._open:
            return self._open[symbol]          # one open ticket per symbol; don't spam
        tid = f"{symbol}-{ts}"
        (self.root / "open" / f"{tid}.json").write_text(json.dumps(
            {"id": tid, "symbol": symbol, "ts": ts, "reasons": reasons, "context": context},
            indent=2, default=_default))
        self._open[symbol] = tid
        return tid

    def is_frozen(self, symbol: str, now_ms: int) -> bool:
        tid = self._open.get(symbol)
        if tid is None:
            return False
        c = self.root / "cleared" / f"{tid}.json"
        if not c.exists():
            return True
        try:
            clr = json.loads(c.read_text())
        except json.JSONDecodeError:
            return True
        if int(clr.get("until_ms", 0)) <= now_ms:
            return True                        # expired clearance: still frozen
        (self.root / "open" / f"{tid}.json").unlink(missing_ok=True)
        del self._open[symbol]
        return False

    def open_tickets(self) -> dict[str, str]:
        return dict(self._open)
