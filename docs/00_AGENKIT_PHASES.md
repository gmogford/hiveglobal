# Build phases and approval gates

## Mapping to AgenKit (checked 2026-09-24)

AgenKit ([agenkit.xyz](https://agenkit.xyz/)) is a paid kit installed into Claude Code / Cursor / Codex.
Its single `/agenkit` command runs **brainstorm → architecture → plan → test-first build → review → ship**,
pausing for approval at each step (per the vendor site and search summaries; the site itself was
blocked by this sandbox's egress policy, so the phase names below come from secondary sources).
Not to be confused with `scttfrdmn/agenkit` (agenkit.dev, a Go/Python agent SDK) or OpenAI AgentKit.

| Requested phase | AgenKit phase | Deliverable in this repo | Gate |
|---|---|---|---|
| Spec | brainstorm | `docs/01_SPEC.md`, `docs/research/*` | G0 |
| Architecture | architecture | `docs/02_ARCHITECTURE.md` | G1 |
| Test plan | plan (+ test-first) | `docs/03_TEST_PLAN.md`, `tests/` written against interfaces | G2 |
| Implementation | test-first build | `hive_trader/**` | G3 |
| Review | review | nightly loop + `scripts/approve.py` paper lock | G4 |
| Ship | ship | live venue adapter + live lock | G5, G6 |

**This build was not driven by the `/agenkit` command.** AgenKit is not installed in this cloud
session, and its site was unreachable. The phase structure and gates were followed by hand. To
re-drive with AgenKit, run `/agenkit` in this repo and point it at this file. The gates below are
tool-agnostic.

## Gates: each one is pass/fail with no judgment call

| Gate | Pass criterion | Status |
|---|---|---|
| **G0 Spec** | Every market claim in `docs/research/` has a date and a source link, and every estimate/speculation is labelled | ✅ delivered, operator to sign |
| **G1 Architecture** | No code path lets a model output set a size, a limit, or place an order. Verified by `grep`: `hive_trader/jev/` imports nothing from `risk`, `execution`, `loop` | ✅ |
| **G2 Test plan** | Each hard limit, gate, causality rule, and the approval lock has at least one named test in `docs/03_TEST_PLAN.md` | ✅ |
| **G3 Implementation** | `python -m pytest` reports 0 failures (44 passed at commit time) | ✅ |
| **G4 Paper approval** | `scripts/approve.py --mode paper` succeeds: named human approver, `tests_passed=true`. The loop refuses to start without this lock | ⏳ operator |
| **G5 Live data + venue** | Live data adapter + live venue adapter, testnet orders round-trip, reconciliation of positions vs venue = 0 diffs over 24h | ⏳ not built |
| **G6 Live approval** | `scripts/approve.py --mode live` accepts the evidence: ≥14 paper days, ≥500 non-overlapping scored outcomes, out-of-sample Brier skill ≥ 0.02 (on that subsample), Jev p95 latency ≤ 1500 ms, net paper PnL after pessimistic costs > 0, paper max drawdown ≤ 5%, fitted + reviewed calibration map | ⏳ blocked on G5 + data |

Every later change to limits, policy, finalists, the Jev schema, or calibration changes the bundle hash
and re-enters at G4 (paper) or G6 (live). That covers changes proposed by the nightly review.
