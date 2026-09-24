"""Append-only JSONL ledger. Every decision is written: fires, rejections (with every reason),
escalations, orders, risk vetoes, fills, and per-candle marks used to score outcomes later."""
from __future__ import annotations

import dataclasses
import json
from enum import Enum
from pathlib import Path


def _default(o):
    if dataclasses.is_dataclass(o):
        return dataclasses.asdict(o)
    if isinstance(o, Enum):
        return o.value
    raise TypeError(type(o))


class Ledger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, ts: int, **payload) -> None:
        rec = {"kind": kind, "ts": ts, **payload}
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec, default=_default, sort_keys=True, separators=(",", ":")) + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
