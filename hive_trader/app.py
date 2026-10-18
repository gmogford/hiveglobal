"""Wiring: load approved bundle, verify gate, build the loop."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .config import load_limits
from .escalation import EscalationDesk
from .execution.base import LiveVenue
from .execution.paper import PaperVenue
from .finalists import FINALISTS
from .jev.client import MockJev, TypeSafeJev
from .ledger import Ledger
from .loop import TradingLoop
from .policy import CalibrationMap, Policy
from .review import gate
from .risk import KillSwitch, RiskManager

ROOT = Path(__file__).resolve().parent.parent


def load_calibration(path: Path) -> CalibrationMap:
    raw = json.loads(path.read_text())
    return CalibrationMap(xs=tuple(raw["xs"]), ys=tuple(raw["ys"]), fitted=raw["fitted"],
                          n_samples=raw.get("n_samples", 0))


def current_bundle(config_dir: Path = ROOT / "config"):
    limits, pcfg = load_limits(config_dir / "limits.json")
    cal = load_calibration(config_dir / "calibration.json")
    return limits, pcfg, cal, gate.bundle(limits, pcfg, FINALISTS, cal)


def build_loop(mode: str, runtime: Path, equity: float, jev: str = "mock",
               config_dir: Path = ROOT / "config", skip_gate: bool = False) -> TradingLoop:
    limits, pcfg, cal, b = current_bundle(config_dir)
    if not skip_gate:
        gate.verify(b, mode, config_dir / "approved.lock.json")
    if mode == "live" and jev == "mock":
        raise gate.GateError("live mode cannot run on MockJev")
    runtime.mkdir(parents=True, exist_ok=True)
    ks_path = runtime / "killswitch.json"
    if not ks_path.exists():
        ks_path.write_text(json.dumps({"armed": True, "tripped": False, "reason": ""}))
    risk = RiskManager(limits, KillSwitch(ks_path), equity,
                       per_symbol_cap={f.symbol: f.max_position_frac for f in FINALISTS if f.max_position_frac},
                       state_path=runtime / "risk_state.json")
    model = MockJev() if jev == "mock" else TypeSafeJev(timeout_s=limits.max_jev_latency_ms / 1000)
    venue = PaperVenue(taker_fee_bps=pcfg.taker_fee_bps) if mode == "paper" else LiveVenue()
    ledger = Ledger(runtime / "ledger.jsonl")
    if risk.restored:   # the saved book wins over --equity; a restart is never a fresh start
        ledger.write("risk_state_restored", int(time.time() * 1000), equity=risk.equity(), hwm=risk.hwm,
                     drawdown=risk.drawdown(), day_halted=risk.day_halted, requested_equity=equity,
                     positions={s: p.qty for s, p in risk.positions.items() if p.qty})
    return TradingLoop(FINALISTS, model, Policy(pcfg, limits, cal), risk, venue,
                       ledger, EscalationDesk(runtime / "escalations"), pcfg, limits)
