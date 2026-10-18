#!/usr/bin/env python3
"""Paper run over a synthetic feed (default) — exercises the full loop end to end.

    python scripts/run_paper.py --hours 6 [--jev typesafe] [--skip-gate]
Live market data adapters are the next build phase; see docs/00_AGENKIT_PHASES.md.
"""
import argparse
import heapq
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hive_trader.app import build_loop  # noqa: E402
from hive_trader.finalists import FINALISTS  # noqa: E402
from hive_trader.sim import synthetic_events  # noqa: E402

START_MIDS = {"HYPE": 94.0, "AAVE": 250.0, "SOL": 114.5, "ENA": 0.17}  # illustrative only

ap = argparse.ArgumentParser()
ap.add_argument("--hours", type=float, default=6)
ap.add_argument("--equity", type=float, default=10_000)
ap.add_argument("--jev", default="mock", choices=["mock", "typesafe"])
ap.add_argument("--runtime", default="runtime/paper")
ap.add_argument("--skip-gate", action="store_true", help="dev only; never for live")
a = ap.parse_args()

loop = build_loop("paper", Path(a.runtime), a.equity, a.jev, skip_gate=a.skip_gate)
if loop.risk.restored:
    print(f"resumed saved book: equity {loop.risk.equity():.2f}, drawdown {loop.risk.drawdown():.2%} "
          f"(--equity ignored; delete {Path(a.runtime) / 'risk_state.json'} to start fresh)")
start = 1_790_000_000_000
minutes = int(a.hours * 60)
streams = [synthetic_events(f.symbol, start, minutes, START_MIDS.get(f.symbol, 100.0), seed=i)
           for i, f in enumerate(FINALISTS)]
events = heapq.merge(*streams, key=lambda e: e.recv_ts)
candle = loop.pcfg.candle_ms
next_close = start - start % candle + candle
counts = {}
for ev in events:
    while ev.recv_ts > next_close:
        for d in loop.on_candle_close(next_close):
            counts[d.verdict.value] = counts.get(d.verdict.value, 0) + 1
        next_close += candle
    loop.on_event(ev)
print(f"decisions: {counts}  equity: {loop.risk.equity():.2f}  fees: {loop.risk.fees_paid:.2f}")
print(f"ledger: {Path(a.runtime) / 'ledger.jsonl'}")
