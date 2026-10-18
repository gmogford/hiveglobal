# Test plan (G2)

Run: `python -m pytest -q`. Everything runs offline; the network is not needed.

| Requirement | Test |
|---|---|
| Snapshot uses no data newer than as_of | `test_state_engine::test_snapshot_refuses_when_future_data_already_ingested`, `test_future_events_never_change_a_past_snapshot` |
| Out-of-order receive not silently reordered | `test_out_of_order_receive_is_dropped_not_reordered` |
| Deterministic, < 400 tokens | `test_deterministic_and_under_token_budget` |
| Crossed book ignored | `test_crossed_book_ignored` |
| Jev wire format: one request, all finalists | `test_jev::test_questions_one_request_all_finalists_wire_types`, `test_parse_wire_response_roundtrip` |
| Malformed model output → no answer (reject), never guessed | `test_malformed_answer_dropped_not_guessed` |
| Schema edits change the hash | `test_schema_hash_changes_with_schema` |
| Each gate rejects with a logged reason; all reasons collected | `test_policy::test_each_gate_rejects_with_logged_reason`, `test_all_failing_reasons_collected` |
| ¼-Kelly cap, per-trade risk cap, position cap | `test_fires_and_sizes_within_quarter_kelly_and_caps` |
| Confidence < 0.60 / crisis (model or code) → escalate | `test_low_confidence_escalates_not_trades`, `test_missing_confidence_escalates`, `test_crisis_from_model_or_code_escalates` |
| Model cannot relax code risk_state | `test_model_cannot_relax_code_risk_state` |
| Direction permission + catalyst blackout in code | `test_direction_permission_is_code_enforced`, `test_blackout_window` |
| Costs can veto a high-probability trade | `test_costs_can_kill_a_high_probability_trade` |
| Calibration shrinks overconfidence | `test_calibration_map_shrinks_overconfident_model` |
| Config ceilings cannot be exceeded, limits immutable | `test_config_ceilings_block_dangerous_values` |
| Kill switch fails closed; checked before every entry; exits still allowed | `test_risk::test_killswitch_fail_closed`, `test_killswitch_checked_before_every_entry`, `test_exits_allowed_when_tripped` |
| Drawdown → trip + flatten; daily loss → halt until next day | `test_drawdown_trips_killswitch_and_flattens`, `test_daily_loss_halts_entries_until_next_day` |
| Restart never resets the book: drawdown/HWM, positions + stops, daily halt, order-rate window survive; unreadable state fails closed; `build_loop` restores and logs it | `test_risk_state::test_restart_keeps_drawdown_hwm_and_positions`, `test_restart_keeps_daily_halt_until_next_utc_day`, `test_restart_keeps_order_rate_window`, `test_unreadable_state_fails_closed`, `test_build_loop_restores_and_logs_it` |
| Stops, rate limit, fat-finger | `test_stop_triggers_exit`, `test_rate_limit_and_fat_finger` |
| End-to-end loop logs every decision; gross cap holds; forbidden direction never fires | `test_loop_and_review::test_end_to_end_paper_loop_logs_every_decision` |
| Escalation freezes symbol | `test_escalation_freezes_symbol_until_cleared` |
| Nightly review proposes, never applies | `test_nightly_review_proposes_but_never_applies` |
| Brier / isotonic correctness | `test_brier_and_isotonic` |
| Unapproved change blocks startup; bot approvers refused; paper ≠ live | `test_gate_blocks_unapproved_changes_and_bot_approvers` |
| Live gate enforces every evidence criterion | `test_live_gate_requires_evidence` |
| Live venue refuses until built | `test_live_venue_refuses` |
| Jev layer imports no execution/risk code | `test_layering` |

**Needed for G5/G6 but not yet possible here:** a replay test on recorded real L2 data (no egress in
this sandbox), testnet order round-trip, and position reconciliation against the venue.
