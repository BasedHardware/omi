"""Doc parity for the worker-flight salvage contract.

The docs page is the contract of record
(``docs/batch-flight-escape-salvage.md``); these pins fail when code and
contract drift apart in either direction. Every pin reads the real page -
nothing is hard-coded twice.

Failure-Class: FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine
"""

from pathlib import Path

FC = 'FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine'
DOCS = Path(__file__).resolve().parents[2] / 'docs' / 'batch-flight-escape-salvage.md'


def docs_text():
    """The docs page, whitespace-normalized so pins never hinge on line wraps."""
    return ' '.join(DOCS.read_text().split())


# ------------------------------------------------------------------ the void


def test_parity_doc_opens_with_the_anonymous_quarantine_line():
    assert 'event=batch_quarantined reason=worker_failed attempt=5 recovery=held stage=unknown' in docs_text()


def test_parity_doc_names_worker_reason_unclassified():
    assert 'worker_reason=unclassified' in docs_text()


def test_parity_doc_calls_it_the_ladders_anonymous_terminal_quarantine():
    assert "the ladder's anonymous terminal quarantine" in docs_text()


def test_parity_doc_names_the_typed_fail_closure():
    assert 'typed `fail()`' in docs_text()


def test_parity_doc_names_left_context_bookkeeping():
    assert 'left-context bookkeeping' in docs_text()


def test_parity_doc_names_window_packing():
    assert 'window packing pass' in docs_text()


def test_parity_doc_names_route_recording():
    assert "the decode generator's route recording" in docs_text()


def test_parity_doc_names_observability_hooks_inside_fail():
    assert 'observability hooks inside the typed `fail()` closure itself' in docs_text()


def test_parity_doc_propagation_target():
    assert 'propagate out of `process_batch`' in docs_text()


def test_parity_doc_pump_received_no_results():
    assert 'The pump received no results for any unit in the flight' in docs_text()


def test_parity_doc_settled_outcomes_were_re_leased():
    assert 're-leased for duplicate GPU work' in docs_text()


def test_parity_doc_holds_re_leased_into_ordinary_failures():
    assert 're-leased into ordinary worker-failure attempts' in docs_text()


def test_parity_doc_evidence_less_ladder():
    assert 'walked the whole bounded retry ladder evidence-less' in docs_text()


def test_parity_doc_no_diagnosis_preserved():
    assert 'no diagnosis ever preserved on the job' in docs_text()


def test_parity_doc_ceiling_attempt_collapsed():
    assert 'ceiling attempt collapsed to the historical anonymous shape' in docs_text()


def test_parity_doc_escapes_are_deterministic():
    assert 'an escape inside a flight is deterministic for the units it touches' in docs_text()


def test_parity_doc_quarantined_blind():
    assert 're-crashed on every attempt until the attempt ceiling quarantined them blind' in docs_text()


# ------------------------------------------------------------- failure class


def test_parity_doc_fc_trailer_present():
    assert FC in docs_text()


def test_parity_doc_fc_name_is_the_escape_class():
    assert 'FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine' in docs_text()


# ------------------------------------------------------------- stage cursor


def test_parity_doc_cursor_section_exists():
    assert '## The stage cursor' in docs_text()


def test_parity_doc_cursor_names_deepest_completed_boundary():
    assert 'the deepest typed stage boundary whose evidence the unit has completed' in docs_text()


def test_parity_doc_cursor_advances_only_at_four_boundaries():
    assert 'advances only at the four typed boundaries' in docs_text()


def test_parity_doc_cursor_never_inside_exception_handler():
    assert 'never inside an exception handler' in docs_text()


def test_parity_doc_fetch_decode_after_extent_check():
    assert 'written after a unit decodes and passes the decoded-extent check' in docs_text()


def test_parity_doc_vad_windows_after_verdict_and_cut():
    assert "the unit's VAD verdict, window cut and language" in docs_text()


def test_parity_doc_silent_units_keep_vad_windows():
    assert 'silent units (no windows) keep this token' in docs_text()


def test_parity_doc_word_clocks_once_every_window_validated():
    assert 'once every window cut for the unit has validated its word' in docs_text()


def test_parity_doc_windows_pack_across_microbatches():
    assert 'windows pack across microbatches' in docs_text()


def test_parity_doc_own_clip_count_threshold():
    assert "the unit's own clip count from the shapes record" in docs_text()


def test_parity_doc_prefix_window_is_predecessor_audio():
    assert 'The left-context prefix window is the predecessor\'s audio' in docs_text()


def test_parity_doc_assemble_words_on_joining_the_list():
    assert 'written when the unit joins the assembly list' in docs_text()


def test_parity_doc_entry_boundary_attribution():
    assert 'the salvage attributes it to `fetch_decode`, the boundary it was entering' in docs_text()


def test_parity_doc_no_unit_stays_anonymous():
    assert 'No unit of a salvaged flight is left without a closed stage token' in docs_text()


# ------------------------------------------------------------- salvage rules


def test_parity_doc_salvage_rules_section():
    assert '## The salvage rules' in docs_text()


def test_parity_doc_fatal_arm_precedes_generic():
    assert 'one `except Exception` arm below a `except FatalGpuError:' in docs_text()


def test_parity_doc_base_exception_propagates():
    assert 'Cancellation and other `BaseException` subclasses still propagate' in docs_text()


def test_parity_doc_rule_1_cuda_fatal_conversion():
    assert 'A CUDA-fatal escape converts to `FatalGpuError` above the salvage' in docs_text()


def test_parity_doc_rule_1_sets_unavailable_flag():
    assert 'sets the unavailable flag, and restarts the GPU chain exactly as before' in docs_text()


def test_parity_doc_rule_1_never_decides_transitions():
    assert 'never a transition a typed boundary did not make' in docs_text()


def test_parity_doc_rule_2_settled_stand():
    assert 'Settled outcomes stand: every emitted result in the results list' in docs_text()


def test_parity_doc_rule_2_pending_persist():
    assert 'every unit with a pending persist future is never re-emitted' in docs_text()


def test_parity_doc_rule_2_mid_fail_rescue():
    assert 'whose typed `fail()` handler itself died mid-way' in docs_text()


def test_parity_doc_rule_2_re_emits_exactly_once():
    assert 're-emits it exactly once' in docs_text()


def test_parity_doc_rule_2_no_double_count():
    assert "without a second `counts['failed']`" in docs_text()


def test_parity_doc_rule_2_no_double_callback():
    assert 'without a second `on_failure` callback' in docs_text()


def test_parity_doc_rule_3_holds_keep_their_holds():
    assert 'Held units keep their admission holds' in docs_text()


def test_parity_doc_rule_3_heldwork_with_recorded_reason():
    assert 're-emerges as `HeldWork` carrying its recorded hold reason' in docs_text()


def test_parity_doc_rule_3_never_re_walks_a_policy_hold():
    assert 'never re-walks a policy hold as an ordinary failure' in docs_text()


def test_parity_doc_rule_4_failed_work_with_cursor_evidence():
    assert "ordinary retryable `FailedWork` whose" in docs_text()


def test_parity_doc_rule_4_evidence_shape():
    assert "evidence is `{'stage': <cursor>, 'reason': 'unknown'}`" in docs_text()


def test_parity_doc_rule_4_closed_unknown_token():
    assert 'the closed `unknown`' in docs_text()


def test_parity_doc_rule_4_never_exception_text():
    assert 'never the escape\'s exception text' in docs_text()


def test_parity_doc_rule_5_counts_parity():
    assert "`counts['failed']` increments once per salvaged unit" in docs_text()


def test_parity_doc_rule_5_on_failure_with_escape_class():
    assert 'fires with the escape\'s class name' in docs_text()


def test_parity_doc_rule_5_raising_callback_warns():
    assert 'a raising callback warns and never breaks the salvage' in docs_text()


def test_parity_doc_rule_5_fault_channel_per_unit():
    assert 'one `event=batch_worker_failed` record per salvaged unit' in docs_text()


def test_parity_doc_rule_5_static_site_field():
    assert 'the static `site=` file:line field' in docs_text()


def test_parity_doc_rule_5_shadow_channel_unchanged():
    assert 'Shadow units stay on the shadow channel' in docs_text()


def test_parity_doc_rule_6_batch_chain_salvaged():
    assert '`event=batch_chain` channel as `outcome=salvaged`' in docs_text()


def test_parity_doc_rule_6_closed_exception_type():
    assert 'with the closed exception type' in docs_text()


def test_parity_doc_rule_6_salvaged_settled_counts():
    assert 'the salvaged/settled counts' in docs_text()


def test_parity_doc_rule_6_pump_void_line_unreachable():
    assert 'never fires for a contained group' in docs_text()


def test_parity_doc_salvage_evidence_rides_the_evidence_slot():
    assert 'evidence rides the ordinary evidence slot, which never decides a transition' in docs_text()


# ------------------------------------------------------- terminal record gains


def test_parity_doc_terminal_section():
    assert '## What the terminal record gains' in docs_text()


def test_parity_doc_before_empty_result_map():
    assert 'an escaping flight gave the pump an empty result map' in docs_text()


def test_parity_doc_after_names_the_real_stage():
    assert 'the eventual terminal record names the real stage' in docs_text()


def test_parity_doc_terminal_example_vad_windows():
    assert '`stage=vad_windows worker_reason=unknown`' in docs_text()


def test_parity_doc_terminal_example_word_clocks():
    assert '`stage=word_clocks worker_reason=unknown`' in docs_text()


def test_parity_doc_anonymous_bucket_drains():
    assert 'The anonymous bucket drains into attributed per-stage records' in docs_text()


def test_parity_doc_salvaged_evidence_never_demotes():
    assert 'Salvaged evidence never demotes' in docs_text()


def test_parity_doc_guard_predicate_requires_typed_reason():
    assert 'the language-guard redrive predicate' in docs_text()


def test_parity_doc_empty_ladder_predicate_requires_typed_reason():
    assert 'the empty-ladder recovery predicate' in docs_text()


def test_parity_doc_disposition_predicate_requires_typed_reason():
    assert 'the terminal validation-disposition predicate' in docs_text()


def test_parity_doc_unknown_is_not_a_typed_reason():
    assert '`unknown` is not one' in docs_text()


def test_parity_doc_escape_stays_booked_on_the_error_channel():
    assert 'An escape stays booked as the fault it is, on the ERROR channel, at every logging site' in docs_text()


# ----------------------------------------------------------- what did not change


def test_parity_doc_unchanged_section():
    assert '## What did not change' in docs_text()


def test_parity_doc_ladder_untouched():
    assert 'The bounded retry ladder, lease fencing, the attempt ceiling, quarantine custody and' in docs_text()


def test_parity_doc_ordinary_failure_still_defers():
    assert 'an ordinary failure still defers' in docs_text()


def test_parity_doc_fatal_gpu_still_refunds():
    assert 'Fatal GPU state still restarts the whole chain without an attempt charge' in docs_text()


def test_parity_doc_escape_sites_remain_bugs():
    assert 'Escape sites remain bugs worth fixing' in docs_text()


def test_parity_doc_salvage_bounds_blast_radius():
    assert 'The salvage bounds the blast radius and names' in docs_text()


def test_parity_doc_no_retry_of_poisoned_flight():
    assert 'it does not retry a poisoned flight inside the same GPU chain' in docs_text()


def test_parity_doc_pump_settle_line_remains():
    assert '`event=batch_chain outcome=retry` line remains the report for faults that' in docs_text()


def test_parity_doc_no_longer_reachable_from_process():
    assert 'no longer reachable for an orchestration escape from `_process`' in docs_text()


# ------------------------------------------------------------- never does


def test_parity_doc_never_section():
    assert '## What salvage never does' in docs_text()


def test_parity_doc_never_exception_text_in_evidence():
    assert 'never captures an exception message, traceback text or any payload into durable' in docs_text()


def test_parity_doc_closed_vocabularies_are_the_whole_record():
    assert 'the closed vocabularies and the static `site=` field are the whole record' in docs_text()


def test_parity_doc_never_fabricates_persist_outcomes():
    assert 'It never fabricates a persist outcome' in docs_text()


def test_parity_doc_unsettled_upload_reruns():
    assert 're-runs on the ladder rather than inventing a stored artifact' in docs_text()


def test_parity_doc_never_marks_unavailable():
    assert 'It never marks the worker unavailable' in docs_text()


def test_parity_doc_cursor_never_in_handlers():
    assert 'It never advances a cursor inside an exception handler' in docs_text()


def test_parity_doc_cursor_records_only_completed_boundaries():
    assert 'the cursor records only what a typed boundary actually completed' in docs_text()


# ------------------------------------------------------- vocabulary surface


def test_parity_doc_names_the_five_closed_stages():
    text = docs_text()
    for stage in ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words'):
        assert stage in text


def test_parity_doc_names_failed_work_class():
    assert '`FailedWork`' in docs_text()


def test_parity_doc_names_held_work_class():
    assert '`HeldWork`' in docs_text()


def test_parity_doc_names_the_worker_fault_event():
    assert '`event=batch_worker_failed`' in docs_text()


def test_parity_doc_names_the_batch_chain_event():
    assert '`event=batch_chain`' in docs_text()


def test_parity_doc_names_the_salvaged_outcome():
    assert '`outcome=salvaged`' in docs_text()


def test_parity_doc_names_the_retry_outcome():
    assert '`event=batch_chain outcome=retry`' in docs_text()


def test_parity_doc_names_the_evidence_slot():
    assert '`worker_failure_evidence`' in docs_text()


def test_parity_doc_names_worker_failure_field():
    assert '`worker_failure`' in docs_text()


# --------------------------------------------------- deeper sentence pins


def test_parity_doc_orchestration_runs_unwrapped():
    assert 'runs unwrapped' in docs_text()


def test_parity_doc_names_the_salvage_rules_order():
    assert 'The rules, in order:' in docs_text()


def test_parity_doc_cursor_section_intro_names_per_flight():
    assert '_process` keeps a per-flight `stage_cursor`' in docs_text()


def test_parity_doc_word_clocks_boundary_completes_only_when_all_validated():
    assert 'the boundary completes only when the' in docs_text()


def test_parity_doc_unit_own_clip_count_from_shapes():
    assert "unit's own clip count from the shapes record has validated" in docs_text()


def test_parity_doc_salvage_rechannels_only_reports():
    assert 'The salvage rechannels only what the flight reports' in docs_text()


def test_parity_doc_settled_scan_names_both_sources():
    assert 'every emitted result in the results list and every unit' in docs_text()


def test_parity_doc_handler_death_has_no_completed_diagnosis():
    assert 'has neither a result nor a completed diagnosis' in docs_text()


def test_parity_doc_salvage_treats_it_as_unsettled():
    assert 'the salvage treats it as unsettled' in docs_text()


def test_parity_doc_holds_re_emerge_as_heldwork():
    assert 'each re-emerges as `HeldWork`' in docs_text()


def test_parity_doc_contained_escape_never_re_walks_policy_hold():
    assert 'a contained escape never re-walks a policy hold' in docs_text()


def test_parity_doc_unsettled_units_leave_as_ordinary_failures():
    assert 'Each unsettled unit leaves as an ordinary retryable `FailedWork` whose' in docs_text()


def test_parity_doc_evidence_closes_at_real_position():
    assert "The evidence closes at the unit's real position" in docs_text()


def test_parity_doc_fault_channel_record_per_salvaged_unit_names_cursor():
    assert 'with the cursor stage, the `unknown` reason and the static' in docs_text()


def test_parity_doc_escape_logged_once_per_contained_flight():
    assert 'The escape itself is logged once per contained flight' in docs_text()
