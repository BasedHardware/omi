"""The retained outside-admitted-source fault is typed, retryable, and named.

A retained manifest reference naming a bucket this deployment does not admit
used to raise a bare ``ValueError`` from ``validate_reference`` — the only
untyped raise site left on the GPU fetch_decode boundary. The worker logged
``error_class=ValueError reason=unclassified`` (x386/30m in the loop sensor's
window on 2026-11-07, all of it bare ``ValueError`` class names), the
bounded retry ladder walked blind, and the terminal quarantine could not
name the fault. The fault is now ``RetainedAudioOutsideAdmittedSource``: a
plain ``ValueError`` subclass (retry semantics untouched — the admitted set
is deploy config, not bytes), carrying the closed
``outside_admitted_source`` evidence token end to end.

The same validator admitted unicode-digit generations (``'²'.isdigit()`` is
``True``) whose ``int()`` then crashed with a second anonymous bare
``ValueError`` past the guard; that shape is now ``InvalidRetainedManifest``,
terminal like its sibling manifest faults. JSON-number generations stay
admitted, as before.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import pytest

from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
    read_reference,
    validate_reference,
)
from utils.observability.reasons import WorkerValidationReason

BUCKETS = {'admitted'}


# --- Typed identity -------------------------------------------------------------


def test_outside_admitted_source_is_a_value_error():
    assert issubclass(RetainedAudioOutsideAdmittedSource, ValueError)


def test_outside_admitted_source_is_not_retained_audio_invalid():
    # The bytes may be sound: the deploy's admitted set is what rejects the
    # reference, so the fault must not inherit the terminal bytes family.
    assert not issubclass(RetainedAudioOutsideAdmittedSource, RetainedAudioInvalid)


def test_outside_admitted_source_is_not_invalid_retained_manifest():
    assert not issubclass(RetainedAudioOutsideAdmittedSource, InvalidRetainedManifest)


def test_outside_admitted_source_is_distinct_from_the_manifest_family():
    assert not issubclass(InvalidRetainedManifest, RetainedAudioOutsideAdmittedSource)


def test_outside_admitted_source_message_is_stable():
    with pytest.raises(
        RetainedAudioOutsideAdmittedSource, match='^retained audio reference is outside admitted source$'
    ):
        validate_reference(_ref(), 'o', 'c', BUCKETS)


def _ref(**changes):
    return {'bucket': 'elsewhere', 'path': 'chunks/o/c/x.bin', 'generation': 1, **changes}


def _good_ref(**changes):
    return {'bucket': 'admitted', 'path': 'chunks/o/c/x.bin', 'generation': 1, 'pcm_sha256': 'd' * 64, **changes}


# --- The closed evidence token ----------------------------------------------------


def test_outside_admitted_source_token_is_in_the_closed_reason_vocabulary():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.value == 'outside_admitted_source'


def test_outside_admitted_source_token_name_matches_its_reason():
    assert WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.name == 'OUTSIDE_ADMITTED_SOURCE'


def test_outside_admitted_source_token_is_unique_across_the_vocabulary():
    values = [reason.value for reason in WorkerValidationReason]
    assert len(values) == len(set(values))


def test_outside_admitted_source_token_is_a_terminal_vocabulary_member():
    from utils.batch_pipeline.errors import WORKER_VALIDATION_REASONS

    assert 'outside_admitted_source' in WORKER_VALIDATION_REASONS


def test_outside_admitted_source_token_is_an_evidence_vocabulary_member():
    from utils.batch_pipeline.errors import WORKER_VALIDATION_REASON_TOKENS

    assert 'outside_admitted_source' in WORKER_VALIDATION_REASON_TOKENS


def test_terminal_gate_accepts_the_new_token_on_the_fetch_stage():
    from utils.batch_pipeline.errors import validate_worker_failure

    assert validate_worker_failure({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}) is None


def test_evidence_gate_accepts_the_new_token_on_the_fetch_stage():
    from utils.batch_pipeline.errors import validate_worker_failure_evidence

    assert validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}) is None


def test_terminal_gate_accepts_the_new_token_on_every_worker_stage():
    from utils.batch_pipeline.errors import WORKER_VALIDATION_STAGES, validate_worker_failure

    for stage in WORKER_VALIDATION_STAGES:
        assert validate_worker_failure({'stage': stage, 'reason': 'outside_admitted_source'}) is None


def test_evidence_gate_accepts_the_new_token_on_every_worker_stage():
    from utils.batch_pipeline.errors import WORKER_VALIDATION_STAGES, validate_worker_failure_evidence

    for stage in WORKER_VALIDATION_STAGES:
        assert validate_worker_failure_evidence({'stage': stage, 'reason': 'outside_admitted_source'}) is None


def test_worker_validation_reason_roundtrips_through_str_value():
    assert str(WorkerValidationReason.OUTSIDE_ADMITTED_SOURCE.value) == 'outside_admitted_source'


# --- The bucket arm: every rejected reference shape -------------------------------


def test_bucket_fault_when_bucket_is_absent():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference({'path': 'chunks/o/c/x.bin', 'generation': 1}, 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_is_none():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket=None), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_is_an_int():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket=7), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_is_empty_string():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket=''), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_differs_only_by_case():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='Admitted'), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_differs_only_by_whitespace():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='admitted '), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_has_a_unicode_lookalike():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='аdmitted'), 'o', 'c', BUCKETS)


def test_bucket_fault_carries_a_closed_message_even_for_a_unicode_lookalike():
    with pytest.raises(
        RetainedAudioOutsideAdmittedSource, match='^retained audio reference is outside admitted source$'
    ):
        validate_reference(_ref(bucket='аdmitted'), 'o', 'c', BUCKETS)


def test_bucket_fault_when_allowed_set_is_empty():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='admitted'), 'o', 'c', set())


def test_bucket_fault_when_bucket_matches_a_superset_string():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='admitted-bucket'), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_matches_a_prefix_string():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='admit'), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_is_a_bytes_object():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket=b'admitted'), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_is_a_dict():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket={'name': 'admitted'}), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_is_a_list():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket=['admitted']), 'o', 'c', BUCKETS)


def test_bucket_fault_when_bucket_is_a_bool():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket=True), 'o', 'c', BUCKETS)


def test_bucket_fault_precedes_the_path_arm():
    # The bucket arm fires first: a garbage path must not mask which arm
    # rejected the reference.
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='elsewhere', path='../../etc/passwd', generation='x'), 'o', 'c', BUCKETS)


def test_bucket_fault_precedes_the_generation_arm():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='elsewhere', generation='²'), 'o', 'c', BUCKETS)


def test_bucket_fault_does_not_depend_on_owner_or_conversation():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='elsewhere'), 'someone-else', 'other', BUCKETS)


# --- The admitted arm: exact-match buckets pass validation -----------------------


def test_exact_bucket_is_admitted():
    assert validate_reference(_good_ref(), 'o', 'c', BUCKETS) is None


def test_admitted_bucket_set_of_one_other_name_still_rejects():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(_ref(bucket='admitted'), 'o', 'c', {'other-name'})


def test_admitted_bucket_set_with_two_names_accepts_either():
    assert validate_reference(_good_ref(), 'o', 'c', {'admitted', 'second'}) is None
    assert validate_reference(_good_ref(bucket='second'), 'o', 'c', {'admitted', 'second'}) is None


def test_admitted_set_accepts_the_default_private_cloud_bucket_name():
    assert validate_reference(_good_ref(bucket='omi-private-cloud-sync'), 'o', 'c', {'omi-private-cloud-sync'}) is None


# --- The generation arm: the unicode-digit hole is closed ------------------------


def test_unicode_superscript_digit_generation_is_typed_manifest_invalid():
    # '²'.isdigit() is True; int('²') raised a bare ValueError past the
    # validator. The manifest shape is now the typed terminal family.
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='²'), 'o', 'c', BUCKETS)


def test_unicode_fullwidth_digit_generation_is_typed_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='１２３'), 'o', 'c', BUCKETS)


def test_unicode_letter_lookup_alike_generation_is_typed_manifest_invalid():
    # '³' and friends were the crash shape; a plain letter was always rejected.
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='1x3'), 'o', 'c', BUCKETS)


def test_mixed_ascii_and_unicode_digit_generation_is_typed_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='12³'), 'o', 'c', BUCKETS)


def test_ascii_digit_string_generation_is_admitted():
    assert validate_reference(_good_ref(generation='1234567890'), 'o', 'c', BUCKETS) is None


def test_zero_padded_string_generation_is_admitted():
    assert validate_reference(_good_ref(generation='0000001'), 'o', 'c', BUCKETS) is None


def test_json_number_generation_is_admitted():
    assert validate_reference(_good_ref(generation=7), 'o', 'c', BUCKETS) is None


def test_large_json_number_generation_is_admitted():
    assert validate_reference(_good_ref(generation=2**62), 'o', 'c', BUCKETS) is None


def test_generation_zero_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation=0), 'o', 'c', BUCKETS)


def test_generation_zero_string_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='0'), 'o', 'c', BUCKETS)


def test_negative_generation_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation=-3), 'o', 'c', BUCKETS)


def test_negative_string_generation_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='-3'), 'o', 'c', BUCKETS)


def test_bool_true_generation_is_rejected_as_manifest_invalid():
    # isinstance(True, int) is True; the guard must not admit booleans.
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation=True), 'o', 'c', BUCKETS)


def test_bool_false_generation_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation=False), 'o', 'c', BUCKETS)


def test_float_generation_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation=1.0), 'o', 'c', BUCKETS)


def test_generation_absent_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference({'bucket': 'admitted', 'path': 'chunks/o/c/x.bin'}, 'o', 'c', BUCKETS)


def test_generation_none_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation=None), 'o', 'c', BUCKETS)


def test_generation_empty_string_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation=''), 'o', 'c', BUCKETS)


def test_generation_with_leading_plus_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='+7'), 'o', 'c', BUCKETS)


def test_generation_with_internal_space_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='12 3'), 'o', 'c', BUCKETS)


def test_generation_with_ascii_letters_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='12a3'), 'o', 'c', BUCKETS)


def test_generation_with_underscore_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='1_2'), 'o', 'c', BUCKETS)


def test_generation_with_decimal_point_is_rejected_as_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation='1.2'), 'o', 'c', BUCKETS)


def test_generation_manifest_invalid_still_requires_the_path_arm_to_pass_first():
    # The generation arm is reached only with a well-formed path: a bad path
    # rejects for the path reason within the same typed family.
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path='chunks/other/c/x.bin', generation='²'), 'o', 'c', BUCKETS)


def test_generation_with_ascii_digits_only_from_a_bytes_value_is_rejected():
    # bytes are not str: the guard never admits a bytes generation.
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(generation=b'123'), 'o', 'c', BUCKETS)


# --- The path arm -----------------------------------------------------------------


def test_path_for_the_wrong_owner_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path='chunks/other/c/x.bin'), 'o', 'c', BUCKETS)


def test_path_for_the_wrong_conversation_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path='chunks/o/other/x.bin'), 'o', 'c', BUCKETS)


def test_path_outside_both_lane_prefixes_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path='playback/o/c/x.bin'), 'o', 'c', BUCKETS)


def test_raw_live_lane_prefix_is_admitted():
    assert validate_reference(_good_ref(path='raw-live/o/c/x.bin'), 'o', 'c', BUCKETS) is None


def test_chunks_lane_prefix_is_admitted():
    assert validate_reference(_good_ref(path='chunks/o/c/x.bin'), 'o', 'c', BUCKETS) is None


def test_path_with_dot_part_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path='chunks/o/c/./x.bin'), 'o', 'c', BUCKETS)


def test_path_with_dotdot_part_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path='chunks/o/c/../x.bin'), 'o', 'c', BUCKETS)


def test_path_with_dotdot_at_the_root_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path='../chunks/o/c/x.bin'), 'o', 'c', BUCKETS)


def test_path_with_empty_part_stays_admitted_unchanged():
    # An empty part is a legal object name, not traversal; the guard blocks
    # only the '.'/'..' escape shapes, exactly as before this change.
    assert validate_reference(_good_ref(path='chunks/o/c//x.bin'), 'o', 'c', BUCKETS) is None


def test_non_string_path_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path=42), 'o', 'c', BUCKETS)


def test_path_absent_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference({'bucket': 'admitted', 'generation': 1}, 'o', 'c', BUCKETS)


def test_path_none_is_manifest_invalid():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path=None), 'o', 'c', BUCKETS)


def test_path_absent_with_bad_bucket_reports_the_bucket_arm():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference({'generation': 1}, 'o', 'c', BUCKETS)


def test_nested_traversal_is_rejected_even_deep_in_the_path():
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(_good_ref(path='chunks/o/c/sub/../../x.bin'), 'o', 'c', BUCKETS)


def test_reference_absent_hits_the_bucket_arm():
    # The bucket arm is the first keyed check: a reference with no fields at
    # all is an outside-admitted-source fault, not a manifest-shape fault.
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference({}, 'o', 'c', BUCKETS)


def test_reference_is_not_a_dict_shape_surfaces_as_an_attribute_failure_not_bucket():
    # validate_reference contracts a mapping; a list reference explodes on
    # .get — that contract is the caller's (materialize validates the list
    # before it fetches). The guard here documents the boundary honestly:
    # the bucket arm is the first keyed access.
    with pytest.raises(AttributeError):
        validate_reference(['admitted'], 'o', 'c', BUCKETS)


# --- read_reference surfaces the typed faults before any GCS call ----------------


def test_read_reference_raises_the_typed_bucket_fault_without_touching_the_client():
    class ExplodingClient:
        def bucket(self, *args, **kwargs):
            raise AssertionError('storage must not be touched for a rejected reference')

    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        read_reference(ExplodingClient(), _ref(), 'o', 'c', BUCKETS, b'\\1' * 32)


def test_read_reference_raises_the_typed_manifest_fault_without_touching_the_client():
    class ExplodingClient:
        def bucket(self, *args, **kwargs):
            raise AssertionError('storage must not be touched for a rejected reference')

    with pytest.raises(InvalidRetainedManifest):
        read_reference(ExplodingClient(), _good_ref(generation='²'), 'o', 'c', BUCKETS, b'\\1' * 32)


def test_read_reference_typed_bucket_fault_is_not_confused_with_bytes_faults():
    with pytest.raises(RetainedAudioOutsideAdmittedSource) as error:
        validate_reference(_ref(), 'o', 'c', BUCKETS)
    assert not isinstance(error.value, RetainedAudioInvalid)


# --- The typed exception's own surface --------------------------------------------


def test_outside_admitted_source_str_is_the_stable_message():
    fault = RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')
    assert str(fault) == 'retained audio reference is outside admitted source'


def test_outside_admitted_source_repr_carries_the_class_name():
    fault = RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')
    assert 'RetainedAudioOutsideAdmittedSource' in repr(fault)


def test_outside_admitted_source_is_raisable_and_catchable_as_value_error():
    with pytest.raises(ValueError):

        def raise_it():
            raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

        raise_it()


def test_outside_admitted_source_survives_a_raise_from_with_style():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source') from None


def test_module_exports_the_new_class():
    import utils.batch_pipeline.source_audio as module

    assert hasattr(module, 'RetainedAudioOutsideAdmittedSource')


def test_module_still_exports_the_untouched_families():
    import utils.batch_pipeline.source_audio as module

    for name in ('RetainedAudioInvalid', 'InvalidRetainedManifest'):
        assert hasattr(module, name)


def test_new_class_module_of_origin_is_source_audio():
    import utils.batch_pipeline.source_audio as module

    assert RetainedAudioOutsideAdmittedSource.__module__ == module.__name__


def test_new_class_docstring_documents_its_retryable_contract():
    doc = RetainedAudioOutsideAdmittedSource.__doc__ or ''
    assert 'retry' in doc.lower()
    assert 'RetainedAudioInvalid' in doc


def test_new_class_docstring_carries_the_failure_class_trailer():
    assert 'Failure-Class:' in (RetainedAudioOutsideAdmittedSource.__doc__ or '')
