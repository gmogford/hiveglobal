import dataclasses

import pytest

from hive_trader.config import PolicyConfig, RiskLimits
from hive_trader.finalists import BY_SYMBOL
from hive_trader.policy import CalibrationMap, Policy, kelly_fraction
from hive_trader.types import Verdict

from helpers import answer, risk, snap

SOL, ENA = BY_SYMBOL["SOL"], BY_SYMBOL["ENA"]


def mk(**cal):
    return Policy(PolicyConfig(), RiskLimits(), CalibrationMap(**cal) if cal else CalibrationMap())


def test_fires_and_sizes_within_quarter_kelly_and_caps(tmp_path):
    r = risk(tmp_path)
    r.marks["SOL"] = 100.0
    d = mk().decide(snap(rv=60), answer(p=0.9), SOL, r, 10_000)
    assert d.verdict == Verdict.FIRE, d.reasons
    cfg, L = PolicyConfig(), RiskLimits()
    assert d.kelly_full > 0
    sigma_h = 60.0
    loss_per_notional = (cfg.stop_sigma * sigma_h + cfg.round_trip_cost_bps) / 1e4
    risk_taken = d.size_frac * loss_per_notional
    assert risk_taken <= cfg.kelly_fraction * d.kelly_full + 1e-9
    assert risk_taken <= L.max_risk_per_trade + 1e-9
    assert d.size_frac <= L.max_position_frac
    assert d.stop_px < 100 < d.take_px


@pytest.mark.parametrize("kw,reason", [
    (dict(quality=1), "setup_quality"),
    (dict(p=0.80), "p_cal"),            # strictly greater than 0.80 required
    (dict(toxic=0.7), "toxic_flow"),
    (dict(risk_state="near_limit"), "risk_state"),
    (dict(direction="neutral"), "direction=neutral"),
])
def test_each_gate_rejects_with_logged_reason(tmp_path, kw, reason):
    r = risk(tmp_path)
    d = mk().decide(snap(), answer(**kw), SOL, r, 10_000)
    assert d.verdict == Verdict.REJECT
    assert any(reason in x for x in d.reasons), d.reasons


def test_all_failing_reasons_collected(tmp_path):
    d = mk().decide(snap(), answer(quality=0, toxic=0.9, p=0.6), SOL, risk(tmp_path), 10_000)
    joined = " ".join(d.reasons)
    assert "setup_quality" in joined and "toxic_flow" in joined and "p_cal" in joined


def test_low_confidence_escalates_not_trades(tmp_path):
    d = mk().decide(snap(), answer(conf=0.55), SOL, risk(tmp_path), 10_000)
    assert d.verdict == Verdict.ESCALATE


def test_missing_confidence_escalates(tmp_path):
    d = mk().decide(snap(), answer(conf=None), SOL, risk(tmp_path), 10_000)
    assert d.verdict == Verdict.ESCALATE


def test_crisis_from_model_or_code_escalates(tmp_path):
    assert mk().decide(snap(), answer(regime="crisis"), SOL, risk(tmp_path), 10_000).verdict == Verdict.ESCALATE
    assert mk().decide(snap(spread=40), answer(), SOL, risk(tmp_path), 10_000).verdict == Verdict.ESCALATE
    assert mk().decide(snap(vol_ratio=5), answer(), SOL, risk(tmp_path), 10_000).verdict == Verdict.ESCALATE


def test_model_cannot_relax_code_risk_state(tmp_path):
    L = RiskLimits()
    r = risk(tmp_path)
    r.marks["SOL"] = 100.0
    r.hwm = 10_000 / (1 - 0.07)             # 7% drawdown -> 0.7 of 10% limit -> near_limit
    d = Policy(PolicyConfig(), L, CalibrationMap()).decide(snap(), answer(risk_state="safe"), SOL, r, 10_000)
    assert d.verdict == Verdict.REJECT
    assert any("code=near_limit" in x for x in d.reasons)


def test_direction_permission_is_code_enforced(tmp_path):
    d = mk().decide(snap(symbol="ENA", mid=0.17), answer(symbol="ENA", direction="long"), ENA, risk(tmp_path), 10_000)
    assert any("not allowed" in x for x in d.reasons)


def test_blackout_window(tmp_path):
    start, _ = ENA.blackouts[0]
    d = mk().decide(snap(symbol="ENA", as_of=start + 1, mid=0.17), answer(symbol="ENA", direction="short"), ENA,
                    risk(tmp_path), start + 1)
    assert "catalyst_blackout" in d.reasons


def test_stale_and_late(tmp_path):
    assert "stale" in mk().decide(snap(age=5_000), answer(), SOL, risk(tmp_path), 10_000).reasons[0]
    assert "jev_late" in mk().decide(snap(), answer(latency=5_000), SOL, risk(tmp_path), 10_000).reasons[0]
    assert mk().decide(snap(), None, SOL, risk(tmp_path), 10_000).reasons == ["no_jev_answer"]


def test_costs_can_kill_a_high_probability_trade(tmp_path):
    # tiny volatility: bracket smaller than round-trip cost -> no edge regardless of p
    d = mk().decide(snap(rv=5), answer(p=0.95), SOL, risk(tmp_path), 10_000)
    assert d.verdict == Verdict.REJECT and any("edge" in x or "kelly" in x for x in d.reasons)


def test_calibration_map_shrinks_overconfident_model(tmp_path):
    shrunk = mk(xs=(0.0, 1.0), ys=(0.25, 0.75), fitted=True, n_samples=1000)
    d = shrunk.decide(snap(), answer(p=0.95), SOL, risk(tmp_path), 10_000)
    assert d.p_calibrated == pytest.approx(0.725)
    assert d.verdict == Verdict.REJECT


def test_kelly_math():
    assert kelly_fraction(0.5, 1.0) == 0
    assert kelly_fraction(0.6, 1.0) == pytest.approx(0.2)
    assert kelly_fraction(0.9, 0.0) == 0


def test_config_ceilings_block_dangerous_values():
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown=0.5)
    with pytest.raises(ValueError):
        PolicyConfig(kelly_fraction=0.5)
    with pytest.raises(ValueError):
        RiskLimits(max_leverage=3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        RiskLimits().max_drawdown = 0.9  # type: ignore[misc]
