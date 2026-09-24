import pytest

from hive_trader.state_engine import TOKEN_BUDGET, PortfolioView, StateEngine, estimate_tokens, snapshot_json
from hive_trader.sim import synthetic_events
from hive_trader.types import CausalityError, TradePrint

from helpers import book


def feed(engine, minutes=240, seed=1):
    last = 0
    for ev in synthetic_events(engine.symbol, 0, minutes, 100.0, seed=seed):
        (engine.on_book if hasattr(ev, "bids") else engine.on_trade)(ev)
        last = ev.recv_ts
    return last


def test_basic_fields_computed_in_code():
    e = StateEngine("SOL")
    e.on_book(book(mid=100.0, spread=0.02, ts=1_000))
    s = e.snapshot(1_500)
    assert s.fields["mid"] == 100.0
    assert s.fields["spread_bps"] == pytest.approx(2.0, abs=0.01)
    assert s.fields["imb5"] == 0.0
    assert s.fields["age_ms"] == 500


def test_snapshot_refuses_when_future_data_already_ingested():
    e = StateEngine("SOL")
    e.on_book(book(ts=1_000))
    e.on_book(book(ts=5_000, mid=101))
    with pytest.raises(CausalityError):
        e.snapshot(4_000)


def test_future_events_never_change_a_past_snapshot():
    a, b = StateEngine("SOL"), StateEngine("SOL")
    evs = list(synthetic_events("SOL", 0, 120, 100.0, seed=3))
    as_of = 60 * 60_000
    for ev in evs:
        if ev.recv_ts <= as_of:
            for eng in (a, b):
                (eng.on_book if hasattr(ev, "bids") else eng.on_trade)(ev)
    s1 = snapshot_json(a.snapshot(as_of))
    s2 = snapshot_json(b.snapshot(as_of))
    assert s1 == s2
    assert a.snapshot(as_of).max_input_ts <= as_of


def test_out_of_order_receive_is_dropped_not_reordered():
    e = StateEngine("SOL")
    e.on_book(book(ts=2_000))
    e.on_trade(TradePrint("SOL", 0, 1_000, 100.0, 1.0, "buy"))
    assert e.dropped_out_of_order == 1
    assert e.snapshot(2_000).fields["trades5m"] == 0


def test_deterministic_and_under_token_budget():
    e1, e2 = StateEngine("SOL"), StateEngine("SOL")
    t = feed(e1)
    feed(e2)
    pf = PortfolioView(position_frac=-0.05, unrealized_bps=-12.3, drawdown_frac=0.021, daily_pnl_frac=-0.004)
    s1, s2 = e1.snapshot(t, pf), e2.snapshot(t, pf)
    assert snapshot_json(s1) == snapshot_json(s2)
    assert s1.fields["rv1h_bps"] is not None and s1.fields["vol_ratio"] is not None
    assert estimate_tokens(s1.fields) < TOKEN_BUDGET


def test_crossed_book_ignored():
    e = StateEngine("SOL")
    e.on_book(book(ts=1_000, mid=100))
    bad = book(ts=2_000, mid=100)
    crossed = type(bad)(bad.symbol, bad.exchange_ts, bad.recv_ts, bad.asks, bad.bids)
    e.on_book(crossed)
    assert e.snapshot(2_000).fields["mid"] == 100.0
