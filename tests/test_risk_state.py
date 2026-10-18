import json

import pytest

from hive_trader.app import build_loop
from hive_trader.config import RiskLimits
from hive_trader.risk import KillSwitch, RiskManager, RiskStateError, UTC_DAY_MS
from hive_trader.types import Fill


def manager(tmp_path, equity=10_000.0):
    ks = tmp_path / "ks.json"
    if not ks.exists():
        ks.write_text('{"armed": true, "tripped": false, "reason": ""}')
    return RiskManager(RiskLimits(), KillSwitch(ks), equity, state_path=tmp_path / "risk_state.json")


def test_restart_keeps_drawdown_hwm_and_positions(tmp_path):
    r = manager(tmp_path)
    r.on_fill(Fill("c", "SOL", "buy", 10, 100.0, 0.5, 0, 0.0), stop_px=95.0, take_px=110.0)
    r.on_mark("SOL", 140.0, 1)                     # HWM rises to ~10_399.5
    r.on_mark("SOL", 100.0, 2)                     # back down: drawdown ~3.8%
    dd, hwm = r.drawdown(), r.hwm
    assert dd > 0.03

    r2 = manager(tmp_path, equity=50_000.0)        # a restart with a different --equity
    assert r2.restored
    assert r2.hwm == pytest.approx(hwm)
    assert r2.drawdown() == pytest.approx(dd)       # drawdown is NOT reset to zero
    assert r2.positions["SOL"].qty == 10 and r2.positions["SOL"].stop_px == 95.0
    assert r2.equity() == pytest.approx(r.equity())
    assert r2.fees_paid == pytest.approx(0.5)


def test_restart_keeps_daily_halt_until_next_utc_day(tmp_path):
    day0 = 20_000 * UTC_DAY_MS
    r = manager(tmp_path)
    r.on_fill(Fill("c", "SOL", "buy", 10, 100.0, 0.0, day0, 0.0))
    r.on_mark("SOL", 100.0, day0 + 1)
    r.on_mark("SOL", 79.0, day0 + 2)               # -2.1% on the day -> halt
    assert r.day_halted

    r2 = manager(tmp_path)
    r2.on_mark("SOL", 79.0, day0 + 3)              # same UTC day after the restart
    assert r2.day_halted
    r2.on_mark("SOL", 79.0, day0 + UTC_DAY_MS)     # next UTC day clears it, as before
    assert not r2.day_halted


def test_restart_keeps_order_rate_window(tmp_path):
    from hive_trader.types import Order
    r = manager(tmp_path)
    r.marks["SOL"] = 100.0
    for i in range(RiskLimits().max_orders_per_minute):
        assert r.pre_trade_check(Order(f"c{i}", "SOL", "buy", 0.1, 100.0, False, i, "t"), i)[0]
    r2 = manager(tmp_path)
    ok, why = r2.pre_trade_check(Order("c9", "SOL", "buy", 0.1, 100.0, False, 10, "t"), 10)
    assert not ok and "order rate limit" in why


@pytest.mark.parametrize("content", ["{not json", '{"version": 99}', '{"version": 1, "cash": 1}', ""])
def test_unreadable_state_fails_closed(tmp_path, content):
    (tmp_path / "risk_state.json").write_text(content)
    with pytest.raises(RiskStateError):
        manager(tmp_path)


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    r = manager(tmp_path)
    r.on_fill(Fill("c", "SOL", "buy", 1, 100.0, 0.0, 0, 0.0))
    assert json.loads((tmp_path / "risk_state.json").read_text())["positions"]["SOL"]["qty"] == 1
    assert not (tmp_path / "risk_state.tmp").exists()


def test_no_state_path_means_in_memory_only(tmp_path):
    ks = tmp_path / "ks.json"
    ks.write_text('{"armed": true, "tripped": false, "reason": ""}')
    r = RiskManager(RiskLimits(), KillSwitch(ks), 10_000.0)
    r.on_fill(Fill("c", "SOL", "buy", 1, 100.0, 0.0, 0, 0.0))
    assert not r.restored and list(tmp_path.iterdir()) == [ks]


def test_build_loop_restores_and_logs_it(tmp_path):
    loop = build_loop("paper", tmp_path, 10_000, skip_gate=True)
    loop.risk.on_fill(Fill("c", "SOL", "buy", 5, 100.0, 0.0, 0, 0.0))
    loop2 = build_loop("paper", tmp_path, 99_999, skip_gate=True)
    assert loop2.risk.restored and loop2.risk.positions["SOL"].qty == 5
    rec = [r for r in loop2.ledger.read() if r["kind"] == "risk_state_restored"]
    assert rec and rec[0]["requested_equity"] == 99_999 and rec[0]["positions"] == {"SOL": 5}
