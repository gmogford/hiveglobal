# Spec (G0)

**Goal.** A 24/7 agent trades a small set of researched crypto perps. It fires only when a calibrated
model score, a deterministic cost model, and hard risk limits all agree. The goal is survival first.
A strategy that backtests well but can blow up does not count as success.

**In scope**
- BRAIN (Claude sessions, offline): research, finalist selection, code, nightly review, escalation re-reads.
- REFLEX (Jev, online): one call per candle close. It returns typed regime / direction / toxic_flow /
  setup_quality / risk_state for all finalists.
- Deterministic code: state engine, policy gates, sizing, risk limits, kill switch, execution, ledger.

**Out of scope (explicitly)**
- Leverage > 1x, market making, cross-venue arbitrage, anything that requires sub-100 ms reaction.
- Self-modifying live config. Every change goes through the approval gate.

**Operating parameters (decided, with rationale in 02_ARCHITECTURE.md)**
- Candle 5 m, decision horizon 1 h. Universe: HYPE, AAVE, SOL, ENA (ENA short-only).
- Fire iff: setup_quality ≥ 2 AND calibrated P(direction) > 0.80 AND effective risk_state == safe AND
  toxic_flow P < 0.5 AND expected edge ≥ 1.5× round-trip cost AND no escalation open.
- Size: ¼-Kelly on the calibrated probability and the cost-adjusted bracket payoff, then capped by
  per-trade risk 0.5%, per-symbol cap (5–10%), and gross cap 30%.
- Max drawdown 10% (kill + flatten), daily loss 2% (entries halt until next UTC day).

**Success metric.** Out-of-sample Brier skill > 0 and positive net PnL after pessimistic costs over
≥14 paper days, with no limit breach. Backtest PnL is not a success metric.
