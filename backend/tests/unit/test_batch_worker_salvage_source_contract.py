"""Source contract for the worker-flight salvage implementation.

These pins read the real ``diarizer/batch_pipeline.py`` source and fail when
the structural commitments the salvage makes drift: the cursor writes sit at
the four typed boundaries, the salvage arm orders CUDA-fatality ahead of the
generic catch and never catches ``BaseException``, the settled set is the
emitted-outcome scan plus pending persists, the mid-fail rescue skips the
second counter increment, the evidence is the closed ``unknown`` token and
never exception text, and the fault-channel record carries the static site
field. Literal extraction, one commitment per pin.

Failure-Class: FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine
"""

import inspect
from pathlib import Path

from diarizer import batch_pipeline
from diarizer.batch_pipeline import PipelineWorker

FC = 'FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine'
DOCS = Path(__file__).resolve().parents[2] / 'docs' / 'batch-flight-escape-salvage.md'

SOURCE = inspect.getsource(batch_pipeline)
PROCESS = inspect.getsource(PipelineWorker._process)


def _process_source():
    return PROCESS


def docs_text():
    return ' '.join(DOCS.read_text().split())


# ------------------------------------------------------------ cursor plumbing


def test_source_declares_the_stage_cursor_dict():
    assert 'stage_cursor: dict[str, str] = {}' in _process_source()


def test_source_declares_the_window_validation_counter():
    assert 'validated_windows: dict[str, int] = {}' in _process_source()


def test_source_cursor_fetch_decode_write():
    assert 'stage_cursor[item.segment_id] = WorkerValidationStage.FETCH_DECODE.value' in _process_source()


def test_source_cursor_vad_windows_write():
    assert 'stage_cursor[item.segment_id] = WorkerValidationStage.VAD_WINDOWS.value' in _process_source()


def test_source_cursor_word_clocks_write():
    assert 'stage_cursor[window.segment_id] = WorkerValidationStage.WORD_CLOCKS.value' in _process_source()


def test_source_cursor_assemble_words_write():
    assert 'stage_cursor[item.segment_id] = WorkerValidationStage.ASSEMBLE_WORDS.value' in _process_source()


def test_source_cursor_advances_on_the_own_clip_threshold():
    assert 'if validated >= shapes[window.segment_id][\'windows\']:' in _process_source()


def test_source_fetch_decode_cursor_follows_the_decode_boundary():
    source = _process_source()
    decode_fail = source.index("fail(item, exc, 'fetch_decode')")
    cursor = source.index('stage_cursor[item.segment_id] = WorkerValidationStage.FETCH_DECODE.value')
    frozen = source.index('frozen_languages[item.segment_id] = frozen_language')
    assert decode_fail < cursor < frozen


def test_source_vad_cursor_precedes_the_silence_branch():
    source = _process_source()
    cursor = source.index('stage_cursor[item.segment_id] = WorkerValidationStage.VAD_WINDOWS.value')
    silence = source.index("if not clips:\n")
    assert cursor < silence


def test_source_assemble_cursor_follows_the_prepare_append():
    source = _process_source()
    append = source.rindex('prepared.append((item, state, words, silence, duration, single, evidence, short))')
    cursor = source.rindex('stage_cursor[item.segment_id] = WorkerValidationStage.ASSEMBLE_WORDS.value')
    except_arm = source.rindex('except Exception as exc:\n                    fail(item, exc, stage)')
    assert append < cursor < except_arm


def test_source_word_clocks_cursor_sits_inside_the_window_try():
    source = _process_source()
    counter = source.index('validated_windows[window.segment_id] = validated')
    advance = source.index('stage_cursor[window.segment_id] = WorkerValidationStage.WORD_CLOCKS.value')
    handler = source.index("fail(states[window.segment_id]['item'], exc, 'word_clocks')")
    assert counter < advance < handler


# --------------------------------------------------------------- salvage arm


def test_source_salvage_has_a_dedicated_fatal_arm():
    assert 'except FatalGpuError:\n            raise' in _process_source()


def test_source_salvage_generic_arm_is_exception_only():
    assert 'except Exception as error:' in _process_source()


def test_source_salvage_never_catches_base_exception():
    assert 'except BaseException' not in _process_source()


def test_source_fatal_arm_precedes_the_generic_arm():
    source = _process_source()
    assert source.index('except FatalGpuError:') < source.index('except Exception as error:')


def test_source_cuda_fatal_conversion_inside_the_salvage():
    source = _process_source()
    salvage = source.index('except Exception as error:')
    conversion = source.index("raise FatalGpuError('fatal CUDA error; restart GPU chain') from error")
    assert salvage < conversion


def test_source_cuda_fatal_conversion_sets_unavailable():
    source = _process_source()
    salvage = source.index('except Exception as error:')
    flag = source.index('self._unavailable = True', salvage)
    conversion = source.index("raise FatalGpuError('fatal CUDA error; restart GPU chain') from error", salvage)
    assert flag < conversion


def test_source_handed_off_precedes_the_salvage_arm():
    source = _process_source()
    salvage = source.index('except Exception as error:')
    handed = source.index('handed_off = True')
    assert handed < salvage


def test_source_settled_scans_the_results_list():
    assert 'result.segment_id for result in results if result is not None' in _process_source()


def test_source_settled_scans_pending_persists():
    assert 'entry[1].segment_id for entry in pending_persist' in _process_source()


def test_source_settled_excludes_bare_failed_membership():
    settled = _process_source()[_process_source().index('settled =') : _process_source().index('salvaged = []')]
    assert 'failed\n' not in settled and 'failed |' not in settled


def test_source_salvage_reads_the_flight_cursor():
    assert 'cursor_stage = stage_cursor.get(flight_item.segment_id)' in _process_source()


def test_source_salvage_defaults_to_the_entry_boundary():
    assert 'cursor_stage = WorkerValidationStage.FETCH_DECODE.value' in _process_source()


def test_source_mid_fail_rescue_skips_the_double_count():
    source = _process_source()
    assert "if flight_item.segment_id not in failed:\n                    self.counts['failed'] += 1" in source


def test_source_salvage_emits_heldwork_with_the_recorded_reason():
    assert (
        'HeldWork(flight_item.segment_id, reason=held_reasons.get(flight_item.segment_id, \'\'))' in _process_source()
    )


def test_source_salvage_emits_failed_work():
    assert 'salvaged.append(\n                    FailedWork(' in _process_source()


def test_source_salvage_evidence_is_the_closed_mapping():
    assert 'transient_failure_evidence(cursor_stage, WorkerValidationReason.UNKNOWN.value)' in _process_source()


def test_source_salvage_never_interpolates_the_exception():
    source = _process_source()
    salvage = source[source.index('except Exception as error:') :]
    assert "str(error)" not in salvage and "{error}" not in salvage and 'error.args' not in salvage


def test_source_salvage_keeps_the_on_failure_parity_hook():
    assert 'self.on_failure(flight_item, type(error).__name__)' in _process_source()


def test_source_salvage_guards_the_on_failure_callback():
    source = _process_source()
    callback = source.index('self.on_failure(flight_item, type(error).__name__)')
    guard = source.index(
        "logger.warning('batch_failure_callback_failed exception_type=%s', type(callback_error).__name__)",
        callback,
    )
    assert callback < guard


def test_source_salvage_appends_the_ten_field_record():
    assert 'error_site_field(error),' in _process_source()


def test_source_salvage_record_carries_the_cursor_stage():
    source = _process_source()
    record = source[
        source.index(
            'failure_records.append(\n                    (\n                        type(error).__name__',
        ) : source.index('results.extend(salvaged)')
    ]
    assert 'cursor_stage,' in record
    assert 'WorkerValidationReason.UNKNOWN.value,' in record


def test_source_salvage_extends_the_results_list():
    assert 'results.extend(salvaged)' in _process_source()


def test_source_salvage_logs_one_batch_chain_line():
    assert "'event=batch_chain outcome=salvaged exception_type=%s salvaged=%d settled=%d'" in _process_source()


def test_source_salvage_line_logs_the_exception_type():
    source = _process_source()
    log = source[source.index("'event=batch_chain outcome=salvaged") :]
    assert 'type(error).__name__' in log


# ------------------------------------------------------------- channel parity


def test_source_fault_channel_keeps_the_ten_field_unpack():
    assert (
        'error_class,\n                failure_stage,\n                segment_id,\n                reason,'
        in inspect.getsource(batch_pipeline)
    )


def test_source_fault_channel_names_the_worker_failed_event():
    assert "'event=batch_worker_failed error_class=%s stage=%s segment_id=%s reason=%s '" in SOURCE


def test_source_shadow_channel_keeps_its_own_line():
    assert "'event=batch_shadow_worker_failure stage=%s reason=%s'" in SOURCE


def test_source_stage_vocabulary_is_the_shared_closed_enum():
    assert 'from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage' in SOURCE


def test_source_transient_evidence_maps_only_closed_stages():
    helper = inspect.getsource(batch_pipeline.transient_failure_evidence)
    assert 'WORKER_VALIDATION_STAGES' in helper
    assert 'WorkerValidationReason.UNKNOWN.value' in helper


def test_source_transient_evidence_folds_foreign_reasons():
    helper = inspect.getsource(batch_pipeline.transient_failure_evidence)
    assert "reason if reason in WORKER_VALIDATION_REASONS else WorkerValidationReason.UNKNOWN.value" in helper


# --------------------------------------------------------------- docs parity


def test_source_docs_page_exists():
    assert DOCS.exists()


def test_source_docs_page_carries_the_failure_class():
    assert FC in docs_text()


def test_source_cursor_comment_names_the_anonymous_shape():
    assert 'worker_reason=unclassified' in _process_source()


def test_source_salvage_comment_names_the_pump_void():
    source = _process_source()
    salvage = source[source.index('except Exception as error:') :]
    assert 'event_batch_chain' in salvage or 'batch_chain' in salvage


# ------------------------------------------------- comment + literal surface


def test_source_cursor_comment_names_the_void_consequence():
    source = _process_source()
    assert 're-leased for duplicate GPU work' in source


def test_source_salvage_comment_names_settled_and_held():
    source = _process_source()
    salvage = source[source.index('except Exception as error:') :]
    assert 'settled outcomes stand' in salvage
    assert 'held units keep their admission' in salvage


def test_source_salvage_comment_names_the_evidence_slot():
    source = _process_source()
    salvage = source[source.index('except Exception as error:') :]
    assert 'the evidence slot is diagnostics' in salvage


def test_source_salvage_comment_names_the_entry_boundary_default():
    source = _process_source()
    salvage = source[source.index('except Exception as error:') :]
    assert 'the boundary it was entering' in salvage


def test_source_salvage_comment_names_the_mid_fail_rescue():
    source = _process_source()
    salvage = source[source.index('except Exception as error:') :]
    assert 'died mid-way' in salvage


def test_source_word_clocks_comment_names_the_left_context_exclusion():
    assert "the predecessor's audio" in _process_source()


def test_source_cursor_comment_names_the_four_boundaries_attribution():
    assert 'fetch_decode` — written after a unit decodes' not in _process_source()
    assert 'so no unit of a salvaged flight stays' in _process_source()


def test_source_docs_and_code_name_the_same_salvaged_outcome():
    assert 'outcome=salvaged' in docs_text()
    assert 'outcome=salvaged' in _process_source()
