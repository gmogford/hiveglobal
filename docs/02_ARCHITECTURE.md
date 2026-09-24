# Architecture (G1)

```
 venue WS/REST ──► adapters (G5, not built) ──► BookUpdate / TradePrint / FundingUpdate  (recv_ts stamped)
                                                     │
                                  ┌──────────────────┴──────────────────┐
                                  ▼                                     ▼
                     state_engine.StateEngine (per symbol)     risk.RiskManager.on_mark
                     causal, deterministic, <400 tokens         stops / take / drawdown flatten
                                  │  candle close                        │ exits (reduce-only)
                                  ▼                                     │
               jev.client  ── ONE POST /systemone, all finalists ──┐     │
               (scores only: typed answers + probabilities)        │     │
                                  │                                │     │
                                  ▼                                │     │
                        policy.Policy.decide  (all gates in code)  │     │
                FIRE / REJECT(reasons) / ESCALATE ──► escalation desk (freeze + ticket → BRAIN)
                                  │ FIRE                                 │
                                  ▼                                      ▼
                  risk.pre_trade_check  (kill switch first, every order) ─► venue.submit ─► ledger.jsonl
                                                                                    │
                           nightly: review.nightly ─► report.md + proposal.json (PENDING_REVIEW)
                                                     └─► review.gate.approve (named human + evidence) ─► approved.lock.json
```

## Layer rules
| Rule | Where enforced |
|---|---|
| Jev never sizes, executes, or sets thresholds | `jev/` imports nothing from `risk`, `policy`, `execution`, `loop` (test `test_layering`) |
| A model output can only make the system more cautious | `policy.py`: effective risk_state = max(code, model); toxic_flow is veto-only; Jev's `crisis` → escalate |
| Every number comes from code | `state_engine.py` computes mid, spread, imbalance, microprice, depth, returns, realized vol, flow, inventory, drawdown |
| No future data | `Snapshot.__post_init__` + `StateEngine.snapshot` raise `CausalityError` |
| Kill switch before every order | `RiskManager.pre_trade_check` step 1. It fails closed if the file is missing or malformed |
| No unreviewed live change | `review/gate.verify` at startup: bundle hash must equal the human-signed lock |

## Jev integration (verified, not assumed)
Wire format comes from the official provider package `@ai-sdk/typesafe-ai` v3.0.6 (unpacked and read):
`POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer $TYPESAFE_AI_API_KEY`, body
`{model, state, questions}`. Choice answers carry `choice`, `probabilities` and a separate `confidence`.
Noul (boolean) answers carry `noul` = P(true). Values are rounded to 2 dp.

- **Latency:** TypeSafe advertises 70–500 ms. One public integration (jarrodwatts/jev-trader) reports
  ~80 ms inference / ~100 ms loop p50, but on a *mock* dry run. **We have no measured number.** No API key
  was available and the sandbox blocked egress. The loop logs every call's wall time. G6 requires p95 ≤ 1500 ms,
  measured over ≥14 days.
- **"Confidence > 0.80"** is implemented as *calibrated probability* of the chosen direction > 0.80.
  TypeSafe's separate `confidence` statistic drives escalation (< 0.60). The provider docs say the two
  are different quantities, and a raw probability is not a probability of profit.
- **setup_quality** is a 4-way ordered choice (`q0..q3`), not a `score`. The score type's level indexing
  is undocumented [CONFIRM with TypeSafe].

## Risk: limits decided, not inherited
| Limit | Value | Why this number |
|---|---|---|
| Max drawdown (HWM) | **10%** → kill + flatten + manual re-arm | ¼-Kelly with 0.5% risk/trade needs a long losing streak to lose 10%. If that happens on a model with claimed calibration, it is evidence the edge is absent. 15% gives a broken model more time to lose money |
| Daily loss | 2% → no entries until next UTC day | Caps one bad regime day at ~4 max-risk losses |
| Risk per trade | 0.5% of equity at the stop, costs included | Keeps ¼-Kelly from ever betting large on an overconfident probability |
| Per-symbol notional | 10% (HYPE/AAVE 8%, ENA 5%) | Alt perps gap through stops. Size assumes a 2× stop overshoot |
| Gross | 30%, leverage ≤ 1× | The book can survive a correlated −30% crypto day with a < 10% loss |
| Stale data | book age > 2 s → no trade | |
| Jev late | > 1.5 s → treated as no answer | A late answer describes a book that has already moved |
| Rate | ≤ 6 entry orders/min | Bounds damage from a loop bug |
Absolute ceilings live in code (`config.py`: drawdown ≤ 20%, Kelly ≤ ¼, leverage ≤ 1). A config edit cannot exceed them.

## Sizing
Bracket: stop = 1.0 σ_h, take = 1.5 σ_h, where σ_h is the 1 h realized vol scaled to the horizon.
Net payoff b = (take − cost)/(stop + cost). Full Kelly f* = p − (1−p)/b is the fraction of equity *at risk*.
Risk taken = min(¼ f*, 0.5%). Notional = risk / (stop + cost), then capped by the per-symbol and gross limits.
The trade is also rejected if gross edge p·take − (1−p)·stop < 1.5 × round-trip cost.

## Escalation (cheap by default, heavy only on exception)
The normal path is one Jev call per candle; there is no LLM in the hot path. On Jev confidence < 0.60, a Jev
`crisis` call, or a code crisis (spread > 25 bps, |1 h ret| > 10%, or vol ratio > 3), the symbol is frozen for
new entries and a ticket goes to `runtime/escalations/open/`. A Claude session (the brain) re-reads the context and
writes a clearance, or doesn't. Stops and drawdown exits keep working while a symbol is frozen.

## Known gaps (to close before G6)
- Live data and venue adapters (G5). The venue is not yet chosen.
- The funding feed is plumbed into the snapshot, but no adapter populates it yet.
- The brain escalation handler is a file protocol. A Claude API call is not yet wired in.
