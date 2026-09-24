from hive_trader.config import PolicyConfig, RiskLimits
from hive_trader.risk import KillSwitch, RiskManager
from hive_trader.types import BookLevel, BookUpdate, JevAnswer, Snapshot


def book(symbol="SOL", ts=1_000, mid=100.0, spread=0.02, size=10.0, levels=5):
    h = spread / 2
    bids = tuple(BookLevel(mid - h - i * 0.01, size) for i in range(levels))
    asks = tuple(BookLevel(mid + h + i * 0.01, size) for i in range(levels))
    return BookUpdate(symbol, ts - 5, ts, bids, asks)


def risk(tmp_path, equity=10_000.0, limits=None, **caps):
    ks = tmp_path / "ks.json"
    ks.write_text('{"armed": true, "tripped": false, "reason": ""}')
    return RiskManager(limits or RiskLimits(), KillSwitch(ks), equity, per_symbol_cap=caps)


def answer(symbol="SOL", direction="long", p=0.9, conf=0.8, quality=3, toxic=0.1,
           regime="trending", risk_state="safe", latency=100.0):
    return JevAnswer(symbol=symbol, regime=regime, regime_probs={regime: 1.0},
                     direction=direction,
                     direction_probs={"long": p, "short": round(1 - p, 4), "neutral": 0.0} if direction != "short"
                     else {"long": round(1 - p, 4), "short": p, "neutral": 0.0},
                     direction_confidence=conf, toxic_flow_p=toxic, setup_quality=quality,
                     setup_quality_probs={}, risk_state=risk_state, risk_state_probs={},
                     latency_ms=latency, model_id="test")


def snap(symbol="SOL", as_of=10_000, mid=100.0, rv=60.0, spread=2.0, ret1h=50.0, vol_ratio=1.0, age=100):
    return Snapshot(symbol=symbol, as_of=as_of, max_input_ts=as_of - age, fields={
        "mid": mid, "spread_bps": spread, "rv1h_bps": rv, "vol_ratio": vol_ratio,
        "ret_bps": {"1h": ret1h}, "age_ms": age})
