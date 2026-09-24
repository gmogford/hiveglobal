# hive-trader

An autonomous crypto trading agent, built in two layers that never blur:

- **BRAIN** (Claude sessions, offline): research, strategy, code, nightly review, and escalation re-reads.
- **REFLEX** ([Jev](https://api.typesafe.ai), TypeSafe System One): one typed call per candle scores all
  finalists. It never sizes, executes, or sets limits.

Deterministic code owns every number, threshold, size, and side effect.

> **Status: paper-only.** Live execution is not implemented (`LiveVenue` raises). Live requires gates G5 and G6
> in [`docs/00_AGENKIT_PHASES.md`](docs/00_AGENKIT_PHASES.md). Nothing here is financial advice.

## Read in this order
1. [`docs/research/MARKET_REGIME_2026-09-24.md`](docs/research/MARKET_REGIME_2026-09-24.md): sourced, dated regime read
2. [`docs/research/FINALISTS_2026-09-24.md`](docs/research/FINALISTS_2026-09-24.md): HYPE, AAVE, SOL, ENA (bull / bear / invalidation / Jev schema)
3. [`docs/00_AGENKIT_PHASES.md`](docs/00_AGENKIT_PHASES.md): phases and pass/fail gates
4. [`docs/02_ARCHITECTURE.md`](docs/02_ARCHITECTURE.md): layers, risk limits, and why each number was chosen
5. [`docs/FINAL_CHECK.md`](docs/FINAL_CHECK.md): honest answers, plus **WHAT COULD I BE WRONG ABOUT?**

## Layout
```
hive_trader/
  state_engine.py   order book + trades -> causal, deterministic snapshot (<400 tokens)
  jev/schema.py     5 questions x N finalists, one request; hashed for the approval gate
  jev/client.py     POST /systemone (wire format from @ai-sdk/typesafe-ai 3.0.6), MockJev
  policy.py         all gates in code, calibration map, 1/4-Kelly sizing, cost/edge check
  risk.py           kill switch (fail-closed), drawdown/daily-loss/position/gross/rate limits, stops
  escalation.py     freeze + ticket to brain; clearance protocol
  loop.py           event loop: book -> risk marks; candle close -> snapshot -> Jev -> policy -> risk -> venue
  execution/        PaperVenue (pessimistic fills), LiveVenue (refuses)
  review/nightly.py Brier, reliability, misses/saves, cost attribution -> PENDING_REVIEW proposal
  review/gate.py    bundle hash + human-signed lock; live evidence criteria
config/limits.json  hard limits + thresholds (ceilings enforced in code)
scripts/            run_paper, nightly_review, approve, clear_escalation, killswitch
```

## Run
```bash
python -m pytest -q                                   # 44 tests, offline
python scripts/run_paper.py --hours 24 --skip-gate    # synthetic feed, MockJev (no edge by construction)
python scripts/nightly_review.py --date 2026-09-24    # report + proposal under runtime/reviews/
python scripts/approve.py --mode paper --approver "<your name>" --evidence evidence.json   # G4
TYPESAFE_AI_API_KEY=... python scripts/run_paper.py --jev typesafe                       # real Jev, paper fills
```
