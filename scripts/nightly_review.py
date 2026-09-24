#!/usr/bin/env python3
"""Nightly review: score the ledger, write report + PENDING_REVIEW proposal. Never edits config/."""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hive_trader.app import current_bundle  # noqa: E402
from hive_trader.ledger import Ledger  # noqa: E402
from hive_trader.review.nightly import run_review  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default="runtime/paper/ledger.jsonl")
ap.add_argument("--out", default="runtime/reviews")
ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"))
a = ap.parse_args()

limits, pcfg, cal, _ = current_bundle()
prop = run_review(Ledger(a.ledger).read(), pcfg.candle_ms * pcfg.horizon_candles, pcfg.candle_ms,
                  pcfg.round_trip_cost_bps, cal, a.date, a.out, limits.max_jev_latency_ms)
print((Path(a.out) / a.date / "report.md").read_text())
