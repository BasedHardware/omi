"""Stored-reference validation grid: every admitted path prefix, owner binding,
traversal shape and generation encoding the validator accepts or rejects, plus
the read rows that fail closed before any storage IO.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

from unittest.mock import Mock

import pytest

from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
    read_reference,
    validate_reference,
)

KEY = b"\5" * 32


def test_chunks_prefix_for_the_owner_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b'})


def test_raw_live_prefix_for_the_owner_passes():
    ref = {'bucket': 'b', 'path': 'raw-live/o/c/x.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b'})


def test_nested_segment_names_pass():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/deep/nested/x.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b'})


def test_unicode_segment_names_pass():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/caf\u00e9.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b'})


def test_owner_prefix_mismatch_is_invalid():
    ref = {'bucket': 'b', 'path': 'chunks/attacker/c/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_conversation_prefix_mismatch_is_invalid():
    ref = {'bucket': 'b', 'path': 'chunks/o/other/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_dot_segment_is_invalid():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/./x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_dot_dot_segment_is_invalid():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/../x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_dot_dot_owner_escape_is_invalid():
    ref = {'bucket': 'b', 'path': 'chunks/../c/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_empty_path_is_invalid():
    ref = {'bucket': 'b', 'path': '', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_both_prefixes_are_admitted_and_no_others():
    for path in ('chunks/o/c/a.bin', 'raw-live/o/c/a.bin'):
        validate_reference({'bucket': 'b', 'path': path, 'generation': 1}, 'o', 'c', {'b'})
    for path in ('other/o/c/a.bin', 'chunks-x/o/c/a.bin', 'CHUNKS/o/c/a.bin'):
        with pytest.raises(InvalidRetainedManifest):
            validate_reference({'bucket': 'b', 'path': path, 'generation': 1}, 'o', 'c', {'b'})


def test_generation_1_integer_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_2_integer_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 2}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_7_integer_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 7}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_12345_integer_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 12345}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_98765432109876543210_integer_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 98765432109876543210}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_1_padded_string_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '1'}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_01_padded_string_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '01'}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_001_padded_string_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '001'}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_000123_padded_string_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '000123'}
    validate_reference(ref, 'o', 'c', {'b'})


def test_generation_int_zero_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 0}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_int_negative_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': -1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_float_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1.0}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_bool_true_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': True}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_bool_false_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': False}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_string_with_space_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': ' 1'}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_string_with_plus_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '+1'}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_string_with_sign_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '-1'}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_string_float_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '1.0'}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_string_hex_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '0x1'}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_empty_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': ''}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_bytes_shape_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': b'1'}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_list_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': [1]}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_dict_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': {1: 1}}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_generation_none_is_rejected():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': None}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_bucket_set_membership_is_exact():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b', 'other'})
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(ref, 'o', 'c', {'other'})


def test_bucket_case_is_exact():
    ref = {'bucket': 'B', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(ref, 'o', 'c', {'b'})


def test_traversal_segment_between_owner_and_conversation_is_invalid():
    ref = {'bucket': 'b', 'path': 'chunks/o/../../evil/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_path_segment_containing_dot_dot_midname_passes():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/a..b.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b'})


def test_read_reference_valid_row_downloads_and_decodes(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    blob = Mock()
    blob.reload = Mock(return_value=None)
    blob.size = 16
    blob.download_as_bytes = Mock(return_value=b'\x00\x02' * 8)
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    monkeypatch.setattr(source_audio, 'decode_source', lambda raw, ref, key: raw)
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    out = read_reference(client, ref, 'o', 'c', {'b'}, KEY)
    assert out == b'\x00\x02' * 8


def test_read_reference_pins_the_bucket_name(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    blob = Mock()
    blob.reload = Mock(return_value=None)
    blob.size = 16
    blob.download_as_bytes = Mock(return_value=b'\x00\x02' * 8)
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    monkeypatch.setattr(source_audio, 'decode_source', lambda raw, ref, key: raw)
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    read_reference(client, ref, 'o', 'c', {'b'}, KEY)
    client.bucket.assert_called_once_with('b')


def test_read_reference_blob_is_generation_pinned(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    blob = Mock()
    blob.reload = Mock(return_value=None)
    blob.size = 16
    blob.download_as_bytes = Mock(return_value=b'\x00\x02' * 8)
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    monkeypatch.setattr(source_audio, 'decode_source', lambda raw, ref, key: raw)
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '000123'}
    read_reference(client, ref, 'o', 'c', {'b'}, KEY)
    call = client.bucket.return_value.blob.call_args
    assert call.kwargs.get('generation') == 123


def test_path_with_an_empty_segment_is_rejected_by_the_owner_prefix():
    ref = {"bucket": "b", "path": "chunks//o/c/x.bin", "generation": 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, "o", "c", {"b"})


def test_path_with_a_trailing_slash_passes_the_guard():
    ref = {"bucket": "b", "path": "chunks/o/c/x.bin/", "generation": 1}
    validate_reference(ref, "o", "c", {"b"})


def test_path_with_a_tab_passes_the_guard():
    ref = {"bucket": "b", "path": "chunks/o/c/x\t.bin", "generation": 1}
    validate_reference(ref, "o", "c", {"b"})


def test_double_dot_as_a_name_substring_passes_the_guard():
    ref = {"bucket": "b", "path": "chunks/o/c/..name.bin", "generation": 1}
    validate_reference(ref, "o", "c", {"b"})


def test_generation_exactly_one_string_passes():
    ref = {"bucket": "b", "path": "chunks/o/c/x.bin", "generation": "1"}
    validate_reference(ref, "o", "c", {"b"})


def test_generation_19_digit_string_passes_the_guard():
    ref = {"bucket": "b", "path": "chunks/o/c/x.bin", "generation": "1234567890123456789"}
    validate_reference(ref, "o", "c", {"b"})


def test_generation_20_digit_string_passes_the_guard():
    ref = {"bucket": "b", "path": "chunks/o/c/x.bin", "generation": "12345678901234567890"}
    validate_reference(ref, "o", "c", {"b"})


def test_generation_huge_string_beyond_firestore_range_passes_the_guard():
    ref = {"bucket": "b", "path": "chunks/o/c/x.bin", "generation": "9" * 19}
    validate_reference(ref, "o", "c", {"b"})


def test_path_deep_nesting_passes_the_guard():
    ref = {"bucket": "b", "path": "chunks/o/c/a/b/c/d/e/f.bin", "generation": 1}
    validate_reference(ref, "o", "c", {"b"})
