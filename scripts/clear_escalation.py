#!/usr/bin/env python3
"""Brain/operator clears an escalation ticket after a full re-read.

    python scripts/clear_escalation.py SOL-1790000300000 --by "brain:nightly" --minutes 30 --note "..."
The clearance must be picked up by the loop before it expires.
"""
import argparse
import json
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("ticket")
ap.add_argument("--by", required=True)
ap.add_argument("--minutes", type=int, default=30)
ap.add_argument("--note", required=True)
ap.add_argument("--runtime", default="runtime/paper")
a = ap.parse_args()
p = Path(a.runtime) / "escalations" / "cleared" / f"{a.ticket}.json"
p.write_text(json.dumps({"by": a.by, "note": a.note, "until_ms": int(time.time() * 1000) + a.minutes * 60_000}))
print(f"cleared {a.ticket} -> {p}")
