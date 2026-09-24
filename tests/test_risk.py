from hive_trader.config import RiskLimits
from hive_trader.risk import KillSwitch
from hive_trader.types import Fill, Order

from helpers import risk


def order(side="buy", qty=5.0, px=100.0, reduce_only=False, sym="SOL"):
    return Order("c1", sym, side, qty, px, reduce_only, 0, "t")


def test_killswitch_fail_closed(tmp_path):
    ks = KillSwitch(tmp_path / "missing.json")
    assert ks.state()[0] is False
    (tmp_path / "bad.json").write_text("{not json")
    assert KillSwitch(tmp_path / "bad.json").state()[0] is False
    (tmp_path / "unarmed.json").write_text('{"armed": false, "tripped": false}')
    assert KillSwitch(tmp_path / "unarmed.json").state()[0] is False


def test_killswitch_checked_before_every_entry(tmp_path):
    r = risk(tmp_path)
    r.marks["SOL"] = 100.0
    assert r.pre_trade_check(order(), 0)[0]
    r.kill.trip("test")
    ok, why = r.pre_trade_check(order(), 1)
    assert not ok and "kill switch" in why[0]


def test_exits_allowed_when_tripped(tmp_path):
    r = risk(tmp_path)
    r.marks["SOL"] = 100.0
    r.on_fill(Fill("c", "SOL", "buy", 5, 100.0, 0.0, 0, 0.0))
    r.kill.trip("x")
    assert r.pre_trade_check(order(side="sell", qty=5, reduce_only=True), 0)[0]
    assert not r.pre_trade_check(order(side="sell", qty=6, reduce_only=True), 0)[0]


def test_position_and_gross_caps(tmp_path):
    r = risk(tmp_path, SOL=0.05)
    r.marks["SOL"] = 100.0
    ok, why = r.pre_trade_check(order(qty=6), 0)       # 600/10000 = 6% > 5% finalist cap
    assert not ok and "cap" in why[0]
    assert r.pre_trade_check(order(qty=4), 0)[0]


def test_drawdown_trips_killswitch_and_flattens(tmp_path):
    r = risk(tmp_path)
    r.marks["SOL"] = 100.0
    r.on_fill(Fill("c", "SOL", "buy", 10, 100.0, 0.0, 0, 0.0))  # 1000 notional
    exits = r.on_mark("SOL", 100.0, 0)
    assert exits == []
    r.cash -= 1_000                                      # simulate other losses -> ~10% dd
    exits = r.on_mark("SOL", 99.0, 1)
    assert exits and exits[0].reduce_only and exits[0].side == "sell"
    assert r.kill.state()[0] is False


def test_daily_loss_halts_entries_until_next_day(tmp_path):
    r = risk(tmp_path)
    r.on_mark("SOL", 100.0, 0)
    r.cash -= 250                                        # -2.5% on the day
    r.on_mark("SOL", 100.0, 1_000)
    ok, why = r.pre_trade_check(order(qty=1), 2_000)
    assert not ok and any("daily loss" in w for w in why)
    r.on_mark("SOL", 100.0, 86_400_000 + 5)              # next UTC day
    assert r.pre_trade_check(order(qty=1), 86_400_000 + 10)[0]


def test_stop_triggers_exit(tmp_path):
    r = risk(tmp_path)
    r.marks["SOL"] = 100.0
    r.on_fill(Fill("c", "SOL", "sell", 5, 100.0, 0.0, 0, 0.0), stop_px=101.0, take_px=98.0)
    assert r.on_mark("SOL", 100.5, 1) == []
    ex = r.on_mark("SOL", 101.2, 2)
    assert ex and ex[0].side == "buy" and ex[0].reason == "stop"


def test_rate_limit_and_fat_finger(tmp_path):
    r = risk(tmp_path, limits=RiskLimits(max_orders_per_minute=2))
    r.marks["SOL"] = 100.0
    assert r.pre_trade_check(order(qty=1), 0)[0]
    assert r.pre_trade_check(order(qty=1), 1)[0]
    assert not r.pre_trade_check(order(qty=1), 2)[0]
    assert not r.pre_trade_check(order(qty=1, px=105), 70_000)[0]
