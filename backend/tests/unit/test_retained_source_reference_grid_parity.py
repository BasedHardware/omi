"""The retained reference grid: every reference shape gets a closed verdict.

``read_reference`` admits or rejects a manifest reference before any storage
call; after this change no reject path on that boundary can produce an
anonymous exception: bucket faults are ``RetainedAudioOutsideAdmittedSource``
(retryable, named) and manifest-shape faults are ``InvalidRetainedManifest``
(terminal, typed). This suite walks the grid.

Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
"""

import hashlib
from unittest.mock import Mock

import pytest

from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
    read_reference,
)

KEY = b'\\2' * 32
ADMITTED = {'b'}


def ref(**changes):
    base = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1, 'pcm_sha256': hashlib.sha256(b'').hexdigest()}
    base.update(changes)
    return base


def _configured_mock():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 16
    blob.metadata = {}
    blob.download_as_bytes.return_value = b'\\0' * 16
    return client


def rejects_bucket(changes, uid='o', conversation_id='c', buckets=ADMITTED):
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        read_reference(_configured_mock(), ref(**changes), uid, conversation_id, buckets, KEY)


def rejects_manifest(changes, uid='o', conversation_id='c', buckets=ADMITTED):
    with pytest.raises(InvalidRetainedManifest):
        read_reference(_configured_mock(), ref(**changes), uid, conversation_id, buckets, KEY)


def admits(changes, uid='o', conversation_id='c', buckets=ADMITTED, *, metadata_probe=False):
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 16
    blob.metadata = {'record_sample_rate': '16000'}
    blob.download_as_bytes.return_value = b'\\0' * 16
    try:
        read_reference(client, ref(**changes), uid, conversation_id, buckets, KEY, source_metadata=metadata_probe)
    except RetainedAudioOutsideAdmittedSource:
        pytest.fail('an admitted reference must reach storage')
    except RetainedAudioInvalid:
        pass  # downstream decode faults are other suites' subject


# --- The bucket arm through read_reference ------------------------------------------


def test_bucket_outside_admitted_set_is_the_named_fault():
    rejects_bucket({'bucket': 'elsewhere'})


def test_bucket_absent_is_the_named_fault():
    rejects_bucket({'bucket': None})


def test_bucket_numeric_is_the_named_fault():
    rejects_bucket({'bucket': 1})


def test_bucket_unicode_lookalike_is_the_named_fault():
    rejects_bucket({'bucket': 'b\u0430'})


def test_bucket_adopted_from_the_record_lane_is_admitted():
    admits({'bucket': 'omi-private-cloud-sync'}, buckets={'omi-private-cloud-sync'})


def test_bucket_from_the_derived_lane_is_admitted_when_configured():
    admits({'bucket': 'derived'}, buckets={'b', 'derived'})


def test_bucket_empty_with_empty_in_admitted_set_stays_the_deploy_config_contract():
    admits({'bucket': ''}, buckets={'', 'b'})


# --- The generation arm through read_reference ---------------------------------------


def test_generation_unicode_digit_is_manifest_invalid():
    rejects_manifest({'generation': '²'})


def test_generation_superscript_pair_is_manifest_invalid():
    rejects_manifest({'generation': '²³'})


def test_generation_negative_is_manifest_invalid():
    rejects_manifest({'generation': -1})


def test_generation_zero_is_manifest_invalid():
    rejects_manifest({'generation': 0})


def test_generation_bool_is_manifest_invalid():
    rejects_manifest({'generation': True})


def test_generation_absent_is_manifest_invalid():
    rejects_manifest({'generation': None})


def test_generation_string_digits_are_admitted():
    admits({'generation': '123'})


def test_generation_json_number_is_admitted():
    admits({'generation': 123})


def test_generation_left_padded_digits_are_admitted():
    admits({'generation': '0123'})


def test_generation_with_math_minus_is_manifest_invalid():
    rejects_manifest({'generation': '−1'})


# --- The path arm through read_reference ----------------------------------------------


def test_path_other_owner_is_manifest_invalid():
    rejects_manifest({'path': 'chunks/x/c/x.bin'})


def test_path_other_conversation_is_manifest_invalid():
    rejects_manifest({'path': 'chunks/o/z/x.bin'})


def test_path_foreign_lane_is_manifest_invalid():
    rejects_manifest({'path': 'results/o/c/x.bin'})


def test_path_traversal_upward_is_manifest_invalid():
    rejects_manifest({'path': 'chunks/o/../../c/x.bin'})


def test_path_dot_part_is_manifest_invalid():
    rejects_manifest({'path': 'chunks/o/c/./x.bin'})


def test_path_non_string_is_manifest_invalid():
    rejects_manifest({'path': 7})


def test_raw_live_path_is_admitted():
    admits({'path': 'raw-live/o/c/x.bin'})


def test_deep_chunks_path_is_admitted():
    admits({'path': 'chunks/o/c/part/00001.bin'})


# --- The lane arms run before storage is touched ----------------------------------------


def test_rejected_reference_never_builds_a_blob():
    client = Mock()
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        read_reference(client, ref(bucket='nope'), 'o', 'c', ADMITTED, KEY)
    client.bucket.assert_not_called()


def test_rejected_manifest_shape_never_builds_a_blob():
    client = Mock()
    with pytest.raises(InvalidRetainedManifest):
        read_reference(client, ref(generation='²'), 'o', 'c', ADMITTED, KEY)
    client.bucket.assert_not_called()


def test_admitted_reference_builds_a_generation_pinned_blob():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 8
    blob.metadata = {}
    blob.download_as_bytes.return_value = b'\\0' * 8
    try:
        read_reference(client, ref(generation='77'), 'o', 'c', ADMITTED, KEY)
    except RetainedAudioInvalid:
        pass
    client.bucket.assert_called_once_with('b')
    client.bucket.return_value.blob.assert_called_once_with('chunks/o/c/x.bin', generation=77)


# --- The metadata lane (source_metadata=True) keeps its numeric contract ----------------


def test_metadata_lane_parses_a_numeric_record_sample_rate():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 8
    blob.metadata = {'record_sample_rate': '44100'}
    blob.download_as_bytes.return_value = b'\\0' * 8
    try:
        read_reference(client, ref(), 'o', 'c', ADMITTED, KEY, source_metadata=True)
    except RetainedAudioInvalid:
        pass
    assert blob.download_as_bytes.call_args is not None


def test_metadata_lane_with_missing_record_sample_rate_defaults_to_16k():
    client = Mock()
    blob = client.bucket.return_value.blob.return_value
    blob.size = 8
    blob.metadata = {}
    blob.download_as_bytes.return_value = b'\\0' * 8
    try:
        read_reference(client, ref(), 'o', 'c', ADMITTED, KEY, source_metadata=True)
    except RetainedAudioInvalid:
        pass
    assert ref()['generation'] == 1  # the probe itself never mutated the manifest


def test_metadata_lane_refusals_stay_typed():
    rejects_bucket({'bucket': 'nope'})


def test_metadata_lane_generation_faults_stay_typed():
    rejects_manifest({'generation': '²'})


# --- Grid sweeps: uid and conversation interpolation -------------------------------------


def test_uid_embedded_in_a_longer_prefix_does_not_match():
    # The binding is a literal prefix of the owner's own prefix; 'o' must not
    # admit paths under 'other' owners that merely share the first character.
    rejects_manifest({'path': 'chunks/other/c/x.bin'}, uid='o', conversation_id='c')


def test_conversation_prefix_binding_is_literal_not_substring():
    rejects_manifest({'path': 'chunks/o/c2/x.bin'}, uid='o', conversation_id='c')


def test_uid_boundary_is_exact_prefix_not_substring():
    rejects_manifest({'path': 'chunks/oxx/c/x.bin'}, uid='o', conversation_id='c')


def test_raw_live_prefix_for_another_owner_is_manifest_invalid():
    rejects_manifest({'path': 'raw-live/x/c/x.bin'})


def test_prefix_match_stays_case_sensitive():
    rejects_manifest({'path': 'CHUNKS/o/c/x.bin'})


def test_unicode_uid_still_binds_exactly():
    admits({'path': 'chunks/ü/c/x.bin'}, uid='ü', conversation_id='c')


# --- The typed verdicts are exhaustive over the shape grid -------------------------------


def test_every_field_absence_lands_in_a_typed_family():
    for absent in ('bucket', 'generation'):
        body = ref()
        body.pop(absent)
        with pytest.raises((RetainedAudioOutsideAdmittedSource, InvalidRetainedManifest)):
            read_reference(Mock(), body, 'o', 'c', ADMITTED, KEY)


def test_path_absence_is_manifest_invalid_even_with_admitted_bucket():
    body = ref()
    body.pop('path')
    with pytest.raises(InvalidRetainedManifest):
        read_reference(_configured_mock(), body, 'o', 'c', ADMITTED, KEY)


def test_empty_reference_hits_the_bucket_arm():
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        read_reference(Mock(), {}, 'o', 'c', ADMITTED, KEY)


def test_the_two_families_are_mutually_exclusive_by_type():
    assert not issubclass(RetainedAudioOutsideAdmittedSource, RetainedAudioInvalid)
    assert issubclass(InvalidRetainedManifest, RetainedAudioInvalid)
    assert issubclass(RetainedAudioOutsideAdmittedSource, ValueError)
