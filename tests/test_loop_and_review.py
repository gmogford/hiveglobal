import heapq
import json
import shutil
from pathlib import Path

import pytest

from hive_trader.app import build_loop, current_bundle
from hive_trader.finalists import FINALISTS
from hive_trader.jev.client import MockJev
from hive_trader.review import gate
from hive_trader.review.nightly import brier, brier_skill, fit_isotonic, run_review
from hive_trader.sim import synthetic_events
from hive_trader.types import Verdict

ROOT = Path(__file__).resolve().parent.parent


def run(loop, minutes=300, start=1_790_000_000_000):
    streams = [synthetic_events(f.symbol, start, minutes, 100.0, seed=i, vol_1m_bps=15) for i, f in enumerate(FINALISTS)]
    candle = loop.pcfg.candle_ms
    nxt = start - start % candle + candle
    out = []
    for ev in heapq.merge(*streams, key=lambda e: e.recv_ts):
        while ev.recv_ts > nxt:
            out += loop.on_candle_close(nxt)
            nxt += candle
        loop.on_event(ev)
    return out


def test_end_to_end_paper_loop_logs_every_decision(tmp_path):
    loop = build_loop("paper", tmp_path, 10_000, skip_gate=True)
    loop.jev = MockJev(overrides={s.symbol: {"p_long": 0.92, "direction": "long", "quality": "q3"} for s in FINALISTS})
    ds = run(loop)
    recs = loop.ledger.read()
    kinds = {r["kind"] for r in recs}
    assert {"decision", "jev_call", "mark"} <= kinds
    assert sum(1 for r in recs if r["kind"] == "decision") == len(ds)
    assert any(d.verdict == Verdict.FIRE for d in ds)                 # SOL/HYPE/AAVE longs allowed
    assert all(d.verdict != Verdict.FIRE for d in ds if d.symbol == "ENA")  # ENA long forbidden in code
    rej = [r for r in recs if r["kind"] == "decision" and r["decision"]["verdict"] == "reject"]
    assert rej and all(r["decision"]["reasons"] for r in rej)          # every rejection has a reason
    # risk never exceeded: gross <= 30% after every fill
    assert loop.risk.gross() / loop.risk.equity() <= 0.30 + 1e-6


def test_escalation_freezes_symbol_until_cleared(tmp_path):
    loop = build_loop("paper", tmp_path, 10_000, skip_gate=True)
    loop.jev = MockJev(overrides={"SOL": {"confidence": 0.4}})
    ds = run(loop, minutes=30)
    assert any(d.symbol == "SOL" and d.verdict == Verdict.ESCALATE for d in ds)
    assert "SOL" in loop.desk.open_tickets()
    assert loop.desk.is_frozen("SOL", 0)


def test_nightly_review_proposes_but_never_applies(tmp_path):
    loop = build_loop("paper", tmp_path, 10_000, skip_gate=True)
    run(loop, minutes=12 * 60)
    before = (ROOT / "config" / "calibration.json").read_text()
    limits, pcfg, cal, _ = current_bundle()
    prop = run_review(loop.ledger.read(), pcfg.candle_ms * pcfg.horizon_candles, pcfg.candle_ms,
                      pcfg.round_trip_cost_bps, cal, "2026-09-24", tmp_path / "rev", limits.max_jev_latency_ms)
    assert prop["status"] == "PENDING_REVIEW"
    assert (tmp_path / "rev" / "2026-09-24" / "report.md").exists()
    ev = prop["evidence"]
    assert ev["n_scored"] > 0 and ev["brier_raw"] is not None
    # 1h horizon on 5m candles: independent sample is ~1/12 of scored decisions
    assert 0 < ev["n_independent"] <= ev["n_scored"] / 10
    assert (ROOT / "config" / "calibration.json").read_text() == before


def test_brier_and_isotonic():
    assert brier([1.0, 0.0], [1, 0]) == 0
    assert brier([0.5, 0.5], [1, 0]) == 0.25
    assert brier_skill([0.9, 0.1, 0.9, 0.1], [1, 0, 1, 0]) > 0
    cal = fit_isotonic([0.1, 0.2, 0.9, 0.95] * 50, [0, 0, 1, 0] * 50)
    assert cal.fitted and list(cal.ys) == sorted(cal.ys)
    assert cal(0.95) <= 0.6            # overconfident 0.95s that hit 50% get shrunk


def test_gate_blocks_unapproved_changes_and_bot_approvers(tmp_path):
    cfg = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg)
    limits, pcfg, cal, b = current_bundle(cfg)
    lock = cfg / "approved.lock.json"
    with pytest.raises(gate.GateError):
        gate.verify(b, "paper", lock)                                  # no lock yet
    with pytest.raises(gate.GateError):
        gate.approve(b, "paper", "claude", {"tests_passed": True}, limits, lock)
    gate.approve(b, "paper", "Operator Name", {"tests_passed": True}, limits, lock)
    gate.verify(b, "paper", lock)
    with pytest.raises(gate.GateError):
        gate.verify(b, "live", lock)                                   # paper approval != live
    raw = json.loads((cfg / "limits.json").read_text())
    raw["policy"]["min_direction_p"] = 0.70                             # "overnight" relaxation
    (cfg / "limits.json").write_text(json.dumps(raw))
    _, _, _, b2 = current_bundle(cfg)
    with pytest.raises(gate.GateError):
        gate.verify(b2, "paper", lock)
    with pytest.raises(gate.GateError):
        build_loop("paper", tmp_path / "rt", 10_000, config_dir=cfg)


def test_live_gate_requires_evidence(tmp_path):
    limits, pcfg, cal, b = current_bundle()
    b["calibration"]["fitted"] = True
    weak = {"tests_passed": True, "paper_days": 3, "scored_decisions": 100, "brier_skill_oos": 0.0,
            "latency_p95_ms": 2000, "net_pnl_after_costs": -5, "max_drawdown_paper": 0.08}
    with pytest.raises(gate.GateError) as e:
        gate.approve(b, "live", "Operator Name", weak, limits, tmp_path / "l.json")
    msg = str(e.value)
    for k in ("paper_days", "scored_decisions", "brier_skill_oos", "latency_p95_ms", "net_pnl", "max_drawdown_paper"):
        assert k in msg


def test_live_venue_refuses():
    from hive_trader.execution.base import LiveVenue, LiveVenueNotApproved
    with pytest.raises(LiveVenueNotApproved):
        LiveVenue().submit(None, None)
