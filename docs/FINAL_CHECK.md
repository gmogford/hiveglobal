# Final check (answered honestly, as of 2026-09-24)

## Is the edge organic, or incentive-driven?
Two different "edges" are involved here.
- **Fundamental value accrual** for the finalists is organic where it exists. HYPE burns come from real trading
  fees. AAVE buybacks come from real borrow interest. TAO was rejected because its revenue is emission-subsidized.
  ENA's buyback is dormant. No finalist depends on points or farming programs.
- **The trading edge** is a Jev direction call on 1 h crypto perp moves. It is **unproven, and my prior is
  that it does not exist after costs.** Jev is a general-purpose typed classifier, not a model trained on
  our markets. Nothing in this repo shows skill yet. The mock run showed *negative* Brier skill, by
  construction. The system is built so that, with no edge, it rarely trades, loses little, and the nightly
  review flags it.

## Is the catalyst already priced in?
- **ENA Oct-5 unlock:** probably partly priced. It was announced Aug 27 and ENA rallied ~24% after the
  announcement. That is why ENA is short-only with a blackout around the event, a 5% cap, and no forced trade.
- **SOL Alpenglow:** not a confirmed date. An on-time ship is likely priced; a slip is the surprise.
- **HYPE/AAVE buybacks:** public, mechanical, and known. There is no information edge in the mechanism itself.

## Does value actually accrue to the token?
| Token | Accrual | Verdict |
|---|---|---|
| HYPE | ~97% fees → open-market buy + burn | Yes, strongest |
| AAVE | Protocol + GHO revenue → automated buybacks (since 2026-06-27; paused once in April) | Yes, if revenue holds |
| SOL | Partial fee burn vs ~6% inflation | Weak for non-stakers |
| ENA | 95% of revenue → buybacks **only once USDe ≥ $7.5B** (currently ~$4–4.9B) | Not today |

## Will it survive real costs and slippage?
The design assumes costs are real. There is a 15 bps round-trip cost [ESTIMATE] in every gate. The edge must be
≥ 1.5× cost. Brackets are sized from realized vol, so low-vol periods auto-reject. Paper fills walk only 50% of
displayed depth, add a 1 bp penalty, and always pay the taker fee. Nightly review replaces estimated slippage
with the measured p95. **Whether it survives is unknown.** G6 requires positive paper PnL net of these costs
over ≥14 days before any live capital. Two known optimism gaps remain: stops are software-monitored at mid,
while real stops gap through levels; and the paper venue has no queue or impact memory.

## Is any hard limit delegated to the model?
**No.** Where each limit is enforced:
- Max drawdown, daily loss, per-trade risk, position/gross caps, leverage, rate limit, stale data, late answer,
  kill switch: all in `risk.py` / `policy.py`, with ceilings in `config.py`. A config edit cannot exceed them.
- Model `risk_state` is advisory: effective = max(code, model). `toxic_flow` is veto-only. Model `crisis`
  only escalates.
- What the model *does* influence: whether a trade fires (via direction + probability) and, through the
  calibrated probability, how big the Kelly fraction is. Both are bounded by code caps. Sizing is capped at
  0.5% risk regardless of what the model says.
- Nothing the nightly review produces can go live without `scripts/approve.py`, a named human, and evidence that passes the gate.

---

# WHAT COULD I BE WRONG ABOUT?

Ordered by how likely each is to cost money.

1. **Jev may have zero skill at this task.** This is the most likely failure. A fast, calibrated classifier is
   not the same as a predictive one. If Brier skill stays ≤ 0 after 14 paper days, the right move is to stop,
   not to tune thresholds until it fires.
2. **Sample size could still overstate evidence.** Outcomes are 1 h forward on 5 m candles, so consecutive
   decisions overlap. *Mitigated:* the review now reports Brier skill on a non-overlapping subsample
   (`n_independent`, ~1/12 of decisions), and the G6 gate counts only those. 500 independent 1 h outcomes
   across 4 names takes about 5+ days of continuous data. Cross-asset correlation still shrinks the effective N further. That part is not corrected.
3. **A calibrated P > 0.80 at a 1 h horizon may simply never occur in liquid markets.** Then the system is a
   very expensive monitor. That is a safe failure, but it means the strategy has no edge to find, not that the gate is broken.
4. **Software stops are not real stops.** If the process dies or the venue gaps, positions have no protection.
   G5 must add venue-native reduce-only stop orders and position reconciliation. Until then, live is blocked.
5. **The market data is secondhand.** Egress was blocked, so every figure came from dated news and search summaries,
   and several conflicted (AAVE TVL $12B vs $30B, USDe $4.0B vs $4.9B, PUMP price off by 3×). Any of them could be
   stale. Nothing numeric from the research docs is used in live code except the ENA unlock date.
6. **The AAVE thesis could be stale.** It rests on a mid-2026 revenue run-rate. The token fell 9% on the day of
   writing, and I found no reason why.
7. **I may be anchoring on macro.** I read a Fed hike plus a failed Clarity Act as headwinds. BTC then rallied about 13%
   in a week. The market may be right and my regime read wrong. The system trades both directions partly
   for this reason.
8. **Correlation.** Kelly assumes independent bets, but four alt perps in a liquidation cascade are one bet.
   The 30% gross cap and the 10% drawdown kill switch are the real protection, not Kelly.
9. **Crowding on ENA.** A widely known unlock short is a classic squeeze setup. The code allows the short but never
   forces it. If funding goes deeply negative into Oct 5, the thesis is invalidated.
10. **Latency is unmeasured.** 70–500 ms is the vendor's figure. If p95 is worse than 1.5 s, most answers are
    discarded as late, and the system will (correctly) do nothing.
11. **Process risk.** An escalation freezes a symbol until the brain clears it, with no timeout. That is
    deliberately fail-safe, but if nobody is watching it can freeze indefinitely. Likewise, an in-memory
    kill-switch trip needs a process restart after re-arming. Risk state (equity, HWM, positions, daily halt)
    is saved to disk, so a restart resumes the same book instead of resetting the drawdown and daily-loss limits.
    It is a paper book: on live, the venue is the source of truth and G5 reconciliation must override it.
12. **AgenKit was not actually run.** The phase gates follow its structure by hand. If the real tool's
    workflow differs, re-drive the build through `/agenkit` and reconcile.

**Prioritization:** survive first. Every default in this repo errs toward not trading. A version that
backtests beautifully but can breach its limits was never the goal.
