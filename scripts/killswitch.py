#!/usr/bin/env python3
"""Operator kill switch.  python scripts/killswitch.py {status|trip|rearm} [--reason ...]"""
import argparse
import json
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["status", "trip", "rearm"])
ap.add_argument("--reason", default="operator")
ap.add_argument("--runtime", default="runtime/paper")
a = ap.parse_args()
p = Path(a.runtime) / "killswitch.json"
if a.cmd == "trip":
    p.write_text(json.dumps({"armed": True, "tripped": True, "reason": a.reason, "ts": int(time.time() * 1000)}))
elif a.cmd == "rearm":
    p.write_text(json.dumps({"armed": True, "tripped": False, "reason": f"rearmed: {a.reason}", "ts": int(time.time() * 1000)}))
print(p.read_text() if p.exists() else "missing (=> fail closed)")
