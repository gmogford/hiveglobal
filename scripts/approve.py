#!/usr/bin/env python3
"""Human approval gate. Writes config/approved.lock.json for the CURRENT bundle.

    python scripts/approve.py --mode paper --approver "Jane Doe" --evidence evidence.json
Evidence JSON keys: tests_passed, paper_days, scored_decisions, brier_skill_oos,
latency_p95_ms, net_pnl_after_costs, max_drawdown_paper. Criteria: hive_trader/review/gate.py.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hive_trader.app import ROOT, current_bundle  # noqa: E402
from hive_trader.review import gate  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--mode", required=True, choices=["paper", "live"])
ap.add_argument("--approver", required=True)
ap.add_argument("--evidence", required=True)
a = ap.parse_args()
limits, _, _, b = current_bundle()
try:
    lock = gate.approve(b, a.mode, a.approver, json.loads(Path(a.evidence).read_text()), limits,
                        ROOT / "config" / "approved.lock.json")
except gate.GateError as e:
    sys.exit(f"REJECTED: {e}")
print(f"APPROVED {a.mode} bundle {lock['hash'][:12]} by {lock['approved_by']}")
