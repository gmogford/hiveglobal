from hive_trader.finalists import FINALISTS
from hive_trader.jev.client import MockJev, parse_answers
from hive_trader.jev.schema import SEP, build_questions, schema_hash


def test_questions_one_request_all_finalists_wire_types():
    q = build_questions(FINALISTS)
    assert len(q) == 5 * len(FINALISTS)
    types = {k.split(SEP)[1]: v["type"] for k, v in q.items()}
    assert types == {"regime": "choice", "direction": "choice", "toxic_flow": "noul",
                     "setup_quality": "choice", "risk_state": "choice"}
    for k, v in q.items():
        if v["type"] == "choice":
            assert 1 <= len(v["criteria"]) <= 255


def test_parse_wire_response_roundtrip():
    snaps = {"SOL": {"ret_bps": {"1h": 80}, "cvd": {"1h": 0.3}}, "HYPE": {"ret_bps": {"1h": -80}, "cvd": {"1h": -0.3}}}
    raw = MockJev().raw_response(snaps)
    out = parse_answers(raw, FINALISTS, 123.0)
    assert set(out) == {"SOL", "HYPE"}
    assert out["SOL"].direction == "long" and out["HYPE"].direction == "short"
    assert out["SOL"].setup_quality == 2 and out["SOL"].latency_ms == 123.0
    assert 0 <= out["SOL"].toxic_flow_p <= 1


def test_malformed_answer_dropped_not_guessed():
    raw = MockJev().raw_response({"SOL": {}})
    raw["answers"][f"SOL{SEP}setup_quality"]["choice"] = "q9"
    assert parse_answers(raw, FINALISTS, 1.0) == {}
    raw = MockJev().raw_response({"SOL": {}})
    del raw["answers"][f"SOL{SEP}toxic_flow"]
    assert parse_answers(raw, FINALISTS, 1.0) == {}


def test_schema_hash_changes_with_schema():
    import dataclasses
    h1 = schema_hash(FINALISTS)
    changed = (dataclasses.replace(FINALISTS[0], context="different"),) + FINALISTS[1:]
    assert schema_hash(changed) != h1
