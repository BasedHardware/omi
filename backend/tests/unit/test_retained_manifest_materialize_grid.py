"""The retained manifest contract grid: every stored-manifest shape materializes
to exact bytes or carries a typed fault (InvalidRetainedManifest for manifest
shape and binding cells, RetainedAudioInvalid for byte-level cells), and every
stored-reference validation cell routes to the closed vocabulary. These cells
fence the admission-to-worker custody handoff so malformed stored state can
never rejoin the anonymous retry ladder.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import hashlib
import json
import struct

from unittest.mock import Mock

import pytest

from utils.batch_pipeline.source_audio import (
    MAX_REFERENCES,
    MAGIC,
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
    materialize,
    read_reference,
    validate_reference,
)

KEY = b"\3" * 32
SOURCE = b"\x01\x00" * 160
PCM16 = b"\x00\x02" * 320


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest(*references, **changes):
    body = {
        'owner_id': 'o',
        'conversation_id': 'c',
        'capture_at': 1,
        'references': list(references),
        'context': {},
    }
    return MAGIC + json.dumps({**body, **changes}).encode()


def slice_ref(source, start=0, frames=160, offset=0, **extra):
    return {
        'bucket': 'b',
        'path': 'chunks/o/c/x.bin',
        'generation': 1,
        'pcm_sha256': digest(source),
        'start_frame': start,
        'offset_frame': offset,
        'frames': frames,
        **extra,
    }


def manifest_item():
    from types import SimpleNamespace

    return SimpleNamespace(owner_id='o', conversation_id='c', capture_at=1, duration_seconds=1.0)


def fetch_ok(_ref):
    return SOURCE


def read_only_blob(size):
    blob = Mock()
    blob.reload = Mock(return_value=None)
    blob.size = size
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    return client


def test_manifest_not_json_is_typed():
    with pytest.raises(InvalidRetainedManifest, match='^retained audio manifest is not JSON$'):
        materialize(MAGIC + b'not-json', manifest_item(), fetch_ok)


def test_manifest_body_only_magic_is_typed():
    with pytest.raises(InvalidRetainedManifest, match='^retained audio manifest is not JSON$'):
        materialize(MAGIC, manifest_item(), fetch_ok)


def test_manifest_json_array_is_typed_malformed():
    body = MAGIC + json.dumps([1, 2]).encode()
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_references_missing_is_typed_malformed():
    body = MAGIC + json.dumps({'owner_id': 'o', 'conversation_id': 'c', 'capture_at': 1, 'context': {}}).encode()
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_references_not_a_list_is_typed_malformed():
    body = MAGIC + json.dumps({'references': {'a': 1}, 'context': {}}).encode()
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_context_missing_is_typed_malformed():
    body = MAGIC + json.dumps({'references': []}).encode()
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_context_not_a_dict_is_typed_malformed():
    body = MAGIC + json.dumps({'references': [], 'context': [1]}).encode()
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_reference_wellformed_missing_sha_is_typed_malformed():
    body = manifest(
        {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1, 'start_frame': 0, 'offset_frame': 0, 'frames': 160}
    )
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_reference_wellformed_integer_sha_is_typed_malformed():
    body = manifest(
        {
            'bucket': 'b',
            'path': 'chunks/o/c/x.bin',
            'generation': 1,
            'start_frame': 0,
            'offset_frame': 0,
            'frames': 160,
            'pcm_sha256': 12345,
        }
    )
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_reference_wellformed_list_sha_is_typed_malformed():
    body = manifest(
        {
            'bucket': 'b',
            'path': 'chunks/o/c/x.bin',
            'generation': 1,
            'start_frame': 0,
            'offset_frame': 0,
            'frames': 160,
            'pcm_sha256': ['ab'],
        }
    )
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_reference_wellformed_float_sha_is_typed_malformed():
    body = manifest(
        {
            'bucket': 'b',
            'path': 'chunks/o/c/x.bin',
            'generation': 1,
            'start_frame': 0,
            'offset_frame': 0,
            'frames': 160,
            'pcm_sha256': 1.5,
        }
    )
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_reference_wellformed_dict_sha_is_typed_malformed():
    body = manifest(
        {
            'bucket': 'b',
            'path': 'chunks/o/c/x.bin',
            'generation': 1,
            'start_frame': 0,
            'offset_frame': 0,
            'frames': 160,
            'pcm_sha256': {'a': 1},
        }
    )
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_reference_wellformed_boolean_sha_is_typed_malformed():
    body = manifest(
        {
            'bucket': 'b',
            'path': 'chunks/o/c/x.bin',
            'generation': 1,
            'start_frame': 0,
            'offset_frame': 0,
            'frames': 160,
            'pcm_sha256': True,
        }
    )
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_binding_owner_mismatch_is_typed():
    body = manifest(slice_ref(SOURCE), **{'owner_id': 'other'})
    with pytest.raises(InvalidRetainedManifest, match='^retained audio manifest binding mismatch$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_binding_conversation_mismatch_is_typed():
    body = manifest(slice_ref(SOURCE), **{'conversation_id': 'other'})
    with pytest.raises(InvalidRetainedManifest, match='^retained audio manifest binding mismatch$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_binding_capture_at_mismatch_is_typed():
    body = manifest(slice_ref(SOURCE), **{'capture_at': 2})
    with pytest.raises(InvalidRetainedManifest, match='^retained audio manifest binding mismatch$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_with_zero_references_is_typed():
    body = manifest()
    with pytest.raises(InvalidRetainedManifest, match='^retained audio manifest binding mismatch$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_at_the_reference_ceiling_materializes():
    refs = [slice_ref(SOURCE, start=i, frames=1, offset=0) for i in range(MAX_REFERENCES)]
    body = manifest(*refs)
    item = manifest_item()
    item.duration_seconds = float(MAX_REFERENCES) / 16000
    out = materialize(body, item, fetch_ok)
    assert isinstance(out, bytes) and out


def test_manifest_past_the_reference_ceiling_is_typed():
    refs = [slice_ref(SOURCE, start=i, frames=1, offset=0) for i in range(MAX_REFERENCES + 1)]
    body = manifest(*refs)
    with pytest.raises(InvalidRetainedManifest, match='^retained audio manifest binding mismatch$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_reference_not_a_dict_is_typed_malformed():
    body = manifest([1, 2, 3])
    with pytest.raises(InvalidRetainedManifest, match='^malformed retained audio manifest$'):
        materialize(body, manifest_item(), fetch_ok)


def test_manifest_bytes_shape_with_valid_cells_materializes():
    body = manifest(slice_ref(SOURCE))
    out = materialize(body, manifest_item(), fetch_ok)
    assert isinstance(out, bytes) and out


def test_manifest_materializes_owner_bound_bytes():
    body = manifest(slice_ref(SOURCE, frames=80))
    out = materialize(body, manifest_item(), fetch_ok)
    assert len(out) > 0


def test_slice_bool_start_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'start_frame': True})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_float_start_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'start_frame': 0.0})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_string_start_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'start_frame': '0'})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_negative_start_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'start_frame': -1})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_bool_offset_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'offset_frame': False})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_float_offset_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'offset_frame': 0.5})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_string_offset_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'offset_frame': '0'})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_negative_offset_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'offset_frame': -1})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_bool_frames_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'frames': True})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_float_frames_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'frames': 160.0})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_string_frames_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'frames': '160'})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_zero_frames_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'frames': 0})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_negative_frames_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'frames': -160})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_missing_start_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'start_frame': None})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_missing_offset_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'offset_frame': None})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_missing_frames_is_typed_invalid_slice():
    ref = slice_ref(SOURCE, **{'frames': None})
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_offset_past_source_is_typed():
    ref = slice_ref(SOURCE, offset=81, frames=160)
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^retained audio slice exceeds capture$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_offset_at_the_source_edge_fits():
    ref = slice_ref(SOURCE, offset=0, frames=160)
    body = manifest(ref)
    out = materialize(body, manifest_item(), fetch_ok)
    assert isinstance(out, bytes) and out


def test_slice_frames_past_capture_is_typed():
    ref = slice_ref(SOURCE, start=15999, frames=2)
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^retained audio slice exceeds capture$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_start_regression_is_typed():
    first = slice_ref(SOURCE, start=10, frames=5)
    second = slice_ref(SOURCE, start=5, frames=5)
    body = manifest(first, second)
    with pytest.raises(InvalidRetainedManifest, match='^invalid retained audio slice$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_monotonic_starts_materialize():
    first = slice_ref(SOURCE, start=0, frames=5)
    second = slice_ref(SOURCE, start=5, frames=5)
    body = manifest(first, second)
    out = materialize(body, manifest_item(), fetch_ok)
    assert isinstance(out, bytes) and out


def test_slice_contiguous_ranges_reconstruct_in_order():
    first = slice_ref(SOURCE, start=0, frames=80)
    second = slice_ref(SOURCE, start=80, frames=80)
    body = manifest(first, second)
    out = materialize(body, manifest_item(), fetch_ok)
    assert isinstance(out, bytes) and out


def test_slice_gap_after_previous_zero_fills_and_materializes():
    first = slice_ref(SOURCE, start=0, frames=5)
    second = slice_ref(SOURCE, start=10, frames=5)
    body = manifest(first, second)
    out = materialize(body, manifest_item(), fetch_ok)
    assert isinstance(out, bytes) and out


def test_slice_offset_equal_to_source_length_is_typed():
    ref = slice_ref(SOURCE, offset=160, frames=1)
    body = manifest(ref)
    with pytest.raises(InvalidRetainedManifest, match='^retained audio slice exceeds capture$'):
        materialize(body, manifest_item(), fetch_ok)


def test_slice_full_source_coverage_materializes_exact_frames():
    ref = slice_ref(SOURCE, start=0, frames=160)
    body = manifest(ref)
    out = materialize(body, manifest_item(), fetch_ok)
    assert isinstance(out, bytes) and out


def test_digest_mismatch_is_typed_and_not_manifest_class():
    ref = slice_ref(SOURCE, pcm_sha256=digest(b'\x02\x00' * 160))
    body = manifest(ref)
    with pytest.raises(RetainedAudioInvalid, match='^retained PCM digest changed$') as error:
        materialize(body, manifest_item(), fetch_ok)
    assert not isinstance(error.value, InvalidRetainedManifest)


def test_digest_of_the_exact_source_passes():
    ref = slice_ref(SOURCE)
    body = manifest(ref)
    out = materialize(body, manifest_item(), fetch_ok)
    assert isinstance(out, bytes) and out


def test_empty_source_digest_never_matches_a_nonempty_slice():
    ref = slice_ref(SOURCE, pcm_sha256=digest(b''))
    body = manifest(ref)
    with pytest.raises(RetainedAudioInvalid, match='^retained PCM digest changed$'):
        materialize(body, manifest_item(), fetch_ok)


def test_digest_covers_every_sourced_byte():
    first = slice_ref(SOURCE[:160], offset=0, frames=80)
    second = slice_ref(SOURCE[160:], offset=80, frames=80, pcm_sha256=digest(SOURCE))
    body = manifest(first, second)
    with pytest.raises(RetainedAudioInvalid, match='^retained PCM digest changed$'):
        materialize(body, manifest_item(), fetch_ok)


def test_identical_consecutive_slices_fetch_once():
    seen = []

    def counting_fetch(ref):
        seen.append(ref['path'])
        return SOURCE

    first = slice_ref(SOURCE, start=0, frames=80)
    second = slice_ref(SOURCE, start=80, frames=80)
    body = manifest(first, second)
    out = materialize(body, manifest_item(), counting_fetch)
    assert isinstance(out, bytes) and out
    assert seen == ['chunks/o/c/x.bin']


def test_unpinned_slices_refetch_every_time():
    seen = []

    def counting_fetch(ref):
        seen.append(ref.get('generation'))
        return SOURCE

    one = slice_ref(SOURCE, start=0, frames=80)
    two = slice_ref(SOURCE, start=80, frames=80)
    del two['bucket']
    del two['path']
    del two['generation']
    del two['pcm_sha256']
    two['pcm_sha256'] = digest(SOURCE)
    two['start_frame'] = 80
    two['frames'] = 80
    del two['offset_frame']
    two['offset_frame'] = 80
    body = manifest(one, two)
    out = materialize(body, manifest_item(), counting_fetch)
    assert isinstance(out, bytes) and out


def test_validate_reference_missing_bucket_is_outside_admitted():
    ref = {'path': 'chunks/o/c/x.bin', 'generation': 1, **{}}
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_non_string_bucket_is_outside_admitted():
    ref = {'path': 'chunks/o/c/x.bin', 'generation': 1, **{'bucket': 7}}
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_dict_bucket_is_outside_admitted():
    ref = {'path': 'chunks/o/c/x.bin', 'generation': 1, **{'bucket': {'name': 'b'}}}
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_foreign_bucket_is_outside_admitted():
    ref = {'path': 'chunks/o/c/x.bin', 'generation': 1, **{'bucket': 'other'}}
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_zero_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 0}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_negative_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': -1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_boolean_true_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': True}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_boolean_false_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': False}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_float_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1.5}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_empty_string_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': ''}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_non_digit_string_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 'abc'}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_unicode_digits_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '12\u00b2'}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_none_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': None}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_list_generation_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': [1]}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_foreign_prefix_path_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/other/c/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_no_prefix_path_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_dot_dot_path_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/../c/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_dot_path_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': 'chunks/o/./c/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_non_string_path_is_invalid_manifest():
    ref = {'bucket': 'b', 'path': ['chunks/o/c/x.bin'], 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_missing_path_is_invalid_manifest():
    ref = {'bucket': 'b', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_integer_generation_passes_the_guard():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_string_generation_passes_the_guard():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '1'}
    validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_zero_padded_string_generation_passes_the_guard():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': '012'}
    validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_big_generation_passes_the_guard():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 98765432101234567890}
    validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_raw_live_path_passes():
    ref = {'bucket': 'b', 'path': 'raw-live/o/c/x.bin', 'generation': 1}
    validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_deep_foreign_owner_is_invalid():
    ref = {'bucket': 'b', 'path': 'chunks/o/other/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_validate_reference_traversal_in_later_segment_is_invalid():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/../x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        validate_reference(ref, 'o', 'c', {'b'})


def test_read_reference_empty_source_is_typed():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(RetainedAudioInvalid, match='^retained audio source exceeds size budget$'):
        read_reference(read_only_blob(0), ref, 'o', 'c', {'b'}, KEY)


def test_read_reference_none_size_is_typed():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(RetainedAudioInvalid, match='^retained audio source exceeds size budget$'):
        read_reference(read_only_blob(None), ref, 'o', 'c', {'b'}, KEY)


def test_read_reference_negative_size_is_typed():
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(RetainedAudioInvalid, match='^retained audio source exceeds size budget$'):
        read_reference(read_only_blob(-5), ref, 'o', 'c', {'b'}, KEY)


def test_read_reference_valid_size_downloads_generation_pinned(monkeypatch):
    downloaded = []
    blob = Mock()
    blob.reload = Mock(return_value=None)
    blob.size = 32
    blob.download_as_bytes = Mock(side_effect=lambda **kw: downloaded.append(kw) or PCM16[:32])
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    monkeypatch.setattr(
        'utils.batch_pipeline.source_audio.decode_source',
        lambda raw, ref, key: raw,
    )
    out = read_reference(client, ref, 'o', 'c', {'b'}, KEY)
    assert out == PCM16[:32]
    assert client.bucket.return_value.blob.call_args.kwargs.get('generation') == 1


def test_read_reference_size_guard_precedes_download(monkeypatch):
    blob = Mock()
    blob.reload = Mock(return_value=None)
    blob.size = None
    blob.download_as_bytes = Mock(side_effect=AssertionError('must not download'))
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(RetainedAudioInvalid):
        read_reference(client, ref, 'o', 'c', {'b'}, KEY)
    blob.download_as_bytes.assert_not_called()


def test_read_reference_invalid_generation_fails_closed_before_io(monkeypatch):
    client = Mock()
    ref = {'bucket': 'b', 'path': 'chunks/o/c/x.bin', 'generation': 0}
    with pytest.raises(InvalidRetainedManifest):
        read_reference(client, ref, 'o', 'c', {'b'}, KEY)
    client.bucket.assert_not_called()


def test_read_reference_outside_bucket_fails_closed_before_io(monkeypatch):
    client = Mock()
    ref = {'bucket': 'other', 'path': 'chunks/o/c/x.bin', 'generation': 1}
    with pytest.raises(RetainedAudioOutsideAdmittedSource):
        read_reference(client, ref, 'o', 'c', {'b'}, KEY)
    client.bucket.assert_not_called()


def test_read_reference_wrong_owner_path_fails_closed_before_io(monkeypatch):
    client = Mock()
    ref = {'bucket': 'b', 'path': 'chunks/other/c/x.bin', 'generation': 1}
    with pytest.raises(InvalidRetainedManifest):
        read_reference(client, ref, 'o', 'c', {'b'}, KEY)
    client.bucket.assert_not_called()
