"""Nightly BRAIN review: score the session, measure calibration, PROPOSE changes.

Outputs (never touches config/):
    runtime/reviews/<YYYY-MM-DD>/report.md
    runtime/reviews/<YYYY-MM-DD>/proposal.json   status = "PENDING_REVIEW"

A proposal becomes live only through review/gate.approve() with a named human approver
and passing evidence — the same gate new code goes through.
"""
from __future__ import annotations

import bisect
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from ..policy import CalibrationMap

MIN_CAL_SAMPLES = 500


@dataclass
class Outcome:
    symbol: str
    as_of: int
    p_long: float
    y_up: int
    move_bps: float
    verdict: str
    direction: str
    reasons: list


def brier(ps: list[float], ys: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps) if ps else float("nan")


def brier_skill(ps: list[float], ys: list[int]) -> float:
    """1 - Brier/Brier(climatology). > 0 means better than always predicting the base rate."""
    if not ps:
        return float("nan")
    base = sum(ys) / len(ys)
    ref = brier([base] * len(ys), ys)
    return float("nan") if ref == 0 else 1 - brier(ps, ys) / ref


def reliability(ps: list[float], ys: list[int], bins: int = 10) -> list[dict]:
    b = defaultdict(list)
    for p, y in zip(ps, ys):
        b[min(int(p * bins), bins - 1)].append((p, y))
    return [{"bin": f"{k/bins:.1f}-{(k+1)/bins:.1f}", "n": len(v),
             "mean_p": round(sum(p for p, _ in v) / len(v), 3),
             "freq": round(sum(y for _, y in v) / len(v), 3)} for k, v in sorted(b.items())]


def fit_isotonic(ps: list[float], ys: list[int]) -> CalibrationMap:
    """Pool-adjacent-violators on the symmetric dataset -> monotone knots."""
    pts = sorted(zip(ps, ys))
    blocks: list[list[float]] = []  # [sum_x, sum_y, n]
    for x, y in pts:
        blocks.append([x, float(y), 1])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            sx, sy, n = blocks.pop()
            blocks[-1][0] += sx
            blocks[-1][1] += sy
            blocks[-1][2] += n
    xs, ys_ = [0.0], [0.0]
    for sx, sy, n in blocks:
        x, y = sx / n, sy / n
        if x <= xs[-1]:
            ys_[-1] = max(ys_[-1], y)
            continue
        xs.append(x)
        ys_.append(max(y, ys_[-1]))
    if xs[-1] < 1.0:
        xs.append(1.0)
        ys_.append(ys_[-1])
    return CalibrationMap(xs=tuple(round(x, 4) for x in xs), ys=tuple(round(y, 4) for y in ys_),
                          fitted=True, n_samples=len(ps))


def build_outcomes(records: list[dict], horizon_ms: int, tolerance_ms: int) -> list[Outcome]:
    marks: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for r in records:
        if r["kind"] == "mark":
            marks[r["symbol"]].append((r["ts"], r["mid"]))
    for v in marks.values():
        v.sort()
    out = []
    for r in records:
        if r["kind"] != "decision" or not r.get("answer"):
            continue
        d, a = r["decision"], r["answer"]
        s, t0 = d["symbol"], d["as_of"]
        series = marks.get(s, [])
        ts_list = [t for t, _ in series]
        i0 = bisect.bisect_right(ts_list, t0) - 1
        i1 = bisect.bisect_left(ts_list, t0 + horizon_ms)
        if i0 < 0 or i1 >= len(series) or series[i1][0] - (t0 + horizon_ms) > tolerance_ms:
            continue  # outcome not yet observable -> excluded, never guessed
        m0, m1 = series[i0][1], series[i1][1]
        pl, ps_ = a["direction_probs"].get("long", 0.0), a["direction_probs"].get("short", 0.0)
        if pl + ps_ <= 0:
            continue
        out.append(Outcome(s, t0, pl / (pl + ps_), int(m1 > m0), math.log(m1 / m0) * 1e4,
                           d["verdict"], d["direction"], d["reasons"]))
    return out


def non_overlapping(outs: list[Outcome], horizon_ms: int) -> list[Outcome]:
    """Per symbol, keep outcomes spaced >= one horizon apart so forward windows don't overlap.

    Consecutive 5m decisions on a 1h horizon share 11/12 of their outcome window; scoring all of
    them overstates the evidence ~12x. Gate evidence uses this subsample.
    """
    keep, last = [], {}
    for o in sorted(outs, key=lambda o: (o.symbol, o.as_of)):
        if o.as_of - last.get(o.symbol, -10**18) >= horizon_ms:
            keep.append(o)
            last[o.symbol] = o.as_of
    return keep


def trade_pnl(records: list[dict]) -> dict:
    fills = [r["fill"] for r in records if r["kind"] == "fill"]
    fees = sum(f["fee"] for f in fills)
    slips = [f["slippage_bps"] for f in fills]
    eq = [r["equity"] for r in records if r["kind"] == "fill"]
    return {"n_fills": len(fills), "fees": round(fees, 2),
            "slippage_bps_mean": round(statistics.fmean(slips), 2) if slips else None,
            "slippage_bps_p95": round(sorted(slips)[int(0.95 * (len(slips) - 1))], 2) if slips else None,
            "last_equity": eq[-1] if eq else None}


def run_review(records: list[dict], horizon_ms: int, candle_ms: int, cost_bps: float,
               current_cal: CalibrationMap, date: str, out_root: str | Path,
               max_latency_ms: float) -> dict:
    outs = build_outcomes(records, horizon_ms, candle_ms)
    p_long = [o.p_long for o in outs]
    y = [o.y_up for o in outs]
    sym_p = p_long + [1 - p for p in p_long]
    sym_y = y + [1 - v for v in y]
    cal_p = [current_cal(p) for p in sym_p]

    indep = non_overlapping(outs, horizon_ms)
    ip, iy = [o.p_long for o in indep], [o.y_up for o in indep]

    lat = sorted(r["meta"].get("latency_ms", 0) for r in records if r["kind"] == "jev_call" and "meta" in r)
    errors = sum(1 for r in records if r["kind"] == "jev_call" and r["meta"].get("error"))
    decisions = [r["decision"] for r in records if r["kind"] == "decision"]
    reason_hist = Counter(reason.split(" ")[0] for d in decisions if d["verdict"] != "fire" for reason in d["reasons"])

    # misses: rejected long/short calls that would have beaten cost; saves: rejected calls that lost
    misses = saves = 0
    for o in outs:
        if o.verdict == "reject" and o.direction in ("long", "short"):
            signed = o.move_bps if o.direction == "long" else -o.move_bps
            if signed > cost_bps:
                misses += 1
            elif signed < 0:
                saves += 1

    report = {
        "date": date,
        "n_decisions": len(decisions),
        "n_scored": len(outs),
        "verdicts": dict(Counter(d["verdict"] for d in decisions)),
        "brier_raw": round(brier(sym_p, sym_y), 4) if outs else None,
        "brier_calibrated": round(brier(cal_p, sym_y), 4) if outs else None,
        "brier_skill_raw": round(brier_skill(p_long, y), 4) if outs else None,
        "n_independent": len(indep),
        "brier_skill_independent": round(brier_skill(ip, iy), 4) if indep else None,
        "reliability_raw": reliability(sym_p, sym_y) if outs else [],
        "latency_ms_p50": round(lat[len(lat) // 2], 1) if lat else None,
        "latency_ms_p95": round(lat[int(0.95 * (len(lat) - 1))], 1) if lat else None,
        "jev_errors": errors,
        "reject_reasons": dict(reason_hist.most_common()),
        "rejected_misses": misses,
        "rejected_saves": saves,
        "trades": trade_pnl(records),
        "escalations": sum(1 for d in decisions if d["verdict"] == "escalate"),
    }

    proposal: dict = {"status": "PENDING_REVIEW", "date": date, "changes": [], "evidence": report}
    if len(sym_p) >= MIN_CAL_SAMPLES:
        cand = fit_isotonic(sym_p, sym_y)
        new_b = brier([cand(p) for p in sym_p], sym_y)
        proposal["changes"].append({
            "type": "calibration_map", "candidate": asdict(cand),
            "in_sample_brier": round(new_b, 4),
            "note": "in-sample fit; approval requires out-of-sample replay on the next session"})
    else:
        proposal["changes"].append({"type": "none", "note": f"only {len(sym_p)} scored samples (< {MIN_CAL_SAMPLES}); no calibration change proposed"})
    if report["brier_skill_independent"] is not None and report["brier_skill_independent"] <= 0:
        proposal["changes"].append({"type": "flag", "severity": "high",
                                    "note": "Jev direction has no skill vs base rate this session; do not relax any gate; consider disabling finalists"})
    if report["latency_ms_p95"] is not None and report["latency_ms_p95"] > max_latency_ms:
        proposal["changes"].append({"type": "flag", "severity": "high",
                                    "note": f"latency p95 {report['latency_ms_p95']}ms > {max_latency_ms}ms budget"})
    tr = report["trades"]
    if tr["slippage_bps_mean"] is not None:
        proposal["changes"].append({"type": "cost_model", "field": "expected_slippage_bps",
                                    "measured_mean": tr["slippage_bps_mean"], "measured_p95": tr["slippage_bps_p95"],
                                    "note": "set expected_slippage_bps to the measured p95, never lower than measured mean"})

    out = Path(out_root) / date
    out.mkdir(parents=True, exist_ok=True)
    (out / "proposal.json").write_text(json.dumps(proposal, indent=2, default=str))
    (out / "report.md").write_text(render_md(report, proposal))
    return proposal


def render_md(r: dict, prop: dict) -> str:
    lines = [f"# Nightly review {r['date']}", "",
             f"- decisions: {r['n_decisions']} (scored: {r['n_scored']}) verdicts: {r['verdicts']}",
             f"- Brier raw / calibrated: {r['brier_raw']} / {r['brier_calibrated']} (0.25 = coin flip)",
             f"- Brier skill vs base rate: {r['brier_skill_raw']} (all) / {r['brier_skill_independent']} "
             f"(non-overlapping, n={r['n_independent']} — use this one for gate evidence)",
             f"- Jev latency p50/p95: {r['latency_ms_p50']} / {r['latency_ms_p95']} ms, errors: {r['jev_errors']}",
             f"- escalations: {r['escalations']}",
             f"- rejected misses (would have beaten cost): {r['rejected_misses']}; saves (would have lost): {r['rejected_saves']}",
             f"- trades: {r['trades']}", "", "## Reject reasons", ""]
    lines += [f"- {k}: {v}" for k, v in r["reject_reasons"].items()]
    lines += ["", "## Reliability (raw)", "", "| bin | n | mean p | freq |", "|---|---|---|---|"]
    lines += [f"| {b['bin']} | {b['n']} | {b['mean_p']} | {b['freq']} |" for b in r["reliability_raw"]]
    lines += ["", "## Proposed changes (PENDING_REVIEW — not applied)", ""]
    lines += [f"- `{c['type']}`: {c.get('note', '')}" for c in prop["changes"]]
    return "\n".join(lines) + "\n"
