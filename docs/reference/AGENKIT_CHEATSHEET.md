# Cheatsheet: Build a 24/7 AI Trading Bot (AgenKit)

> Transcribed from a third-party cheatsheet image (agenkit.xyz marketing), 2026-10-18. Part 1 is the
> original text, verbatim apart from formatting. Part 2 checks it against this repo. The vendor's own
> footer reads: *Educational only. Not financial advice. No strategy guarantees profit. Trade only what
> you can afford to lose.*

---

# Part 1: Transcription

*End-to-end production setup with any frontier AI model + AgenKit. No coding experience needed.*

## What you need before starting
- A laptop (Mac or Windows)
- An AI subscription (ChatGPT Pro or Claude)
- An AgenKit license from agenkit.xyz
- An exchange account with a testnet or paper mode
- 1 weekend and zero coding experience

## Pick your AI model
- **GPT-6 Astra**: deep reasoning, math, and production code
- **Claude Opus 5.5**: long agentic coding sessions
- **Grok 4.7**: real-time market and news context
- **Jev**: fast decisions in milliseconds

The model is the pilot. Your system is the jet. New model next month? Plug it in. Keep the jet.

## Plain-English glossary
- **Terminal**: the app where you type commands
- **Harness**: the tool that lets AI work in your files
- **API key**: a password that lets your bot trade
- **Backtest**: testing a strategy on past data
- **Paper trading**: trading with fake money first
- **Drawdown**: the biggest drop from a peak
- **Kill switch**: one button that stops everything
- **VPS**: a rented computer that never sleeps

## Step 0: Open the terminal
- **Mac:** press Cmd + Space, type Terminal, hit Enter
- **Windows:** press Start, type PowerShell, hit Enter
- Install Node.js (LTS) from nodejs.org first
- Check it worked: `node -v`

## Setup in 5 commands
Copy and paste one line at a time.

1. **Install your harness**
   ```bash
   npm install -g @openai/codex
   # or
   npm install -g @anthropic-ai/claude-code
   ```
2. **Sign in to unlock your model**: `codex login` or `claude`
3. **Create the project folder**: `mkdir trading-bot && cd trading-bot`
4. **Activate AgenKit**: `npx agenkit activate <license-key>`
5. **Install the 10-agent team**: `npx agenkit install engineering-kit`

## Fire the build
Start the harness inside the folder, then type:

- In Claude Code: `/agenkit build a 24/7 mean reversion bot for Hyperliquid perps`
- In Codex CLI: `@agenkit build a 24/7 mean reversion bot for Hyperliquid perps`

One line. The specialist team takes it from there.

## The 10 specialists
- **Conductor**: turns your idea into a plan
- **Backend Architect**: designs the system
- **Test Engineer**: tests before code
- **Code Reviewer**: checks every change
- **Data Engineer**: builds the price feeds
- **Debugger**: fixes what breaks
- **Frontend Engineer**: builds your dashboard
- **Infra/DevOps**: deploys with rollback
- **Perf/Observability**: speed and monitoring
- **Security Engineer**: keys and kill switch

## How to answer the Conductor
It asks one question at a time. Answer simply:
- **Market:** "Hyperliquid perps, ETH and SOL"
- **Mode:** "Paper trading first"
- **Risk:** "Max 1 percent per trade"
- **Stop:** "Kill switch at 5 percent daily loss"
- **Alerts:** "Telegram for fills and errors"

Not sure? Say "use the safest default."

## The 6-phase workflow
1. **Brainstorm**: your idea becomes a written spec
2. **Architecture**: modules, data, failure handling
3. **Plan**: small tasks with exact file paths
4. **Build**: test first, then code, then cleanup
5. **Review**: checked for spec and quality
6. **Ship**: deploy with verification and rollback

You approve spec, architecture, and plan. Nothing ships without you.

## The 6-layer architecture
1. **Data**: live feeds, auto-reconnect, gap detection
2. **Signal**: the math: z-scores, spreads, indicators
3. **Decision**: entry and exit rules, each tested
4. **Risk**: limits checked before every order
5. **Execution**: orders, retries, reconciliation
6. **Monitoring**: dashboard, logs, alerts

## Data rules
- Use at least 3 to 5 years of history
- Include delisted assets, avoid survivorship bias
- Use data as known at the time, never later
- Store raw data first, clean it second
- Log every gap, never fill it silently

## Backtest rules
- Build on early years, test on later ones
- Include fees and slippage on every trade
- At least 30 trades before trusting a result
- Test nearby settings, a real edge is a plateau
- Run Monte Carlo to see the worst drawdowns
- Target Sharpe above 1.5 out-of-sample

## Risk rules
- Risk 0.5 to 1 percent of capital per trade
- Size with fractional Kelly, 0.25x at most
- Daily loss limit stops all trading
- Max drawdown triggers the kill switch
- Cap exposure per asset and per direction

## Security rules
- API keys: trading ON, withdrawals OFF
- Keys in environment variables, never in code
- Never paste keys into a chat window
- Use IP whitelisting on the exchange if available

## Deploy 24/7
1. **Package** the bot with Docker
2. **Run** it on a VPS, not your laptop
3. **Auto-restart** with Docker or systemd
4. **Send** fills, errors, and breaches to Telegram
5. **Paper trade** 2 to 4 weeks first
6. **Go live** small, scale only if results match

## Common errors and fixes
- **/agenkit not recognized in Codex**: type `@agenkit` instead
- **Agents not found**: run the harness inside your project folder
- **Command not found**: reinstall Node.js, reopen the terminal
- **Bot stopped overnight**: move it to a VPS with auto-restart
- **Paper and backtest differ**: check fees and slippage

## Prompts to fire next
- `@agenkit add Telegram alerts for every fill and error`
- `@agenkit build a dashboard for PnL, positions, drawdown`
- `@agenkit add a kill switch on 5 percent daily drawdown`
- `@agenkit write a walk-forward backtest with fees`
- `@agenkit add hourly position reconciliation`

## Your daily routine (5 minutes)
- Check the dashboard: PnL, open positions, drawdown
- Read Telegram alerts from overnight
- Confirm positions match the exchange
- Change nothing on emotion, only on data

## Production checklist
- [ ] Spec approved
- [ ] Tests passing
- [ ] Backtest validated out-of-sample
- [ ] Kill switch tested
- [ ] Paper results match backtest
- [ ] Alerts working
- [ ] Then go live

---

# Part 2: Is it relevant to hive-trader's 24/7 workflow?

**Short answer: yes, as a checklist. No, as a build recipe.** hive-trader already follows the cheatsheet's
phase model (see [`00_AGENKIT_PHASES.md`](../00_AGENKIT_PHASES.md)) and meets or exceeds most of its risk
and security rules. Its real value here is the **Deploy 24/7** and **Monitoring** sections, which name
exactly what this repo has not built yet.

## Where hive-trader already matches or is stricter

| Cheatsheet rule | hive-trader | Verdict |
|---|---|---|
| 6-phase workflow, human approves | G0–G6 gates; `scripts/approve.py` needs a named human; bundle hash lock | ✅ Stricter |
| Risk 0.5–1% per trade | `max_risk_per_trade: 0.005` | ✅ Low end |
| Fractional Kelly ≤ 0.25× | `kelly_fraction: 0.25`, ceiling enforced in `config.py` | ✅ |
| Daily loss limit stops trading | 2% → no entries until next UTC day | ✅ Tighter than the sheet's 5% example |
| Max drawdown → kill switch | 10% HWM → kill + flatten + manual re-arm | ✅ |
| Cap per asset / direction | 10% per symbol (5–8% for alts), 30% gross, 1× leverage | ✅ Per asset and gross. No explicit long/short net cap |
| Limits checked before every order | `RiskManager.pre_trade_check`, kill switch first, fails closed | ✅ |
| Data as known at the time | `CausalityError` on any future data | ✅ |
| Fees and slippage on every trade | 4.5 bps taker + 3 bps slippage; edge must be ≥ 1.5× cost; pessimistic paper fills | ✅ |
| Keys in env vars | `TYPESAFE_AI_API_KEY` from env | ✅ |
| Paper 2–4 weeks first | G6 needs ≥ 14 paper days and ≥ 500 independent outcomes | ✅ |
| Jev for fast decisions | Jev is the REFLEX layer, one call per candle, scores only | ✅ Same idea, with a harder rule: the model never sizes or executes |

## Where the cheatsheet is a weaker fit

- **Backtest rules (3–5 years of history, Sharpe > 1.5).** hive-trader deliberately does not use backtest
  PnL as a success metric (`01_SPEC.md`). It is a Jev-scored, order-book strategy, and Jev's answers
  cannot be replayed honestly over years of history. Its out-of-sample test is forward paper trading
  scored by Brier skill. The sheet's "30 trades" bar is also far below this repo's 500 independent outcomes.
  Keep these rules for any purely rule-based strategy you add later.
- **"Paper results match backtest".** No backtest exists, so this checklist line maps to G6 instead.
- **"Kill switch at 5% daily loss".** Looser than the current 2%. Don't loosen to match.
- **Model list.** "GPT-6 Astra" and "Grok 4.7" are as the vendor states them and are not verified here.
  The point stands either way: the model is swappable and the deterministic system is the asset.
- **"No coding experience, one weekend".** This is marketing. A 24/7 money-handling system needs someone
  who can read the risk code and the ledger.

## Gaps the cheatsheet exposes (the 24/7 work still to do)

| Cheatsheet item | Status in repo | Suggested next step |
|---|---|---|
| Live feeds, auto-reconnect, gap detection | ❌ No adapters (G5) | Build the venue WS adapter with reconnect and gap logging. Stale-book guard (2 s) already exists |
| Execution: retries, reconciliation | ❌ `LiveVenue` refuses | G5: testnet round-trip, venue-native reduce-only stops, hourly reconciliation (0 diffs over 24 h) |
| Docker packaging | ❌ None | Add a `Dockerfile` that runs `scripts/run_paper.py` |
| VPS + auto-restart (Docker / systemd) | ❌ None | Needed for the 14-day paper run. Note that a restart must re-verify the approval lock and keep the kill-switch state |
| Telegram (or Slack) alerts for fills, errors, breaches | ❌ None | Alert on: fills, limit breaches, kill-switch trips, **new escalation tickets** (FINAL_CHECK risk 11: an unwatched escalation freezes a symbol indefinitely) |
| Dashboard: PnL, positions, drawdown | ❌ Only the nightly `report.md` | A small read-only view over `ledger.jsonl` is enough |
| Exchange key: withdrawals OFF, IP whitelist | ⏳ Not applicable until live | Add to the G6 checklist |
| Daily 5-minute routine | ⏳ Partly covered by the nightly review | Add "positions match the venue" once reconciliation exists |

## Recommendation

Use the cheatsheet's **Deploy 24/7**, **Monitoring** and **Security** sections as the G5 checklist. Ignore
its backtest targets and its looser risk examples. In priority order:

1. Docker + systemd/VPS auto-restart, so the ≥ 14-day paper run can actually run unattended.
2. Alerts, with escalation tickets first, because the current design fails safe by freezing and needs a human to notice.
3. Live data adapter with reconnect and gap logging, then testnet execution and reconciliation (G5).
4. Exchange key hygiene (withdrawals off, IP whitelist) as a G6 precondition.
