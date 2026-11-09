"""The closed proof vocabulary grid: every fixed retained fault message maps to
its seal reason, arbitrary text never becomes state even when it embeds a
known phrase, and the tail-gap buckets hold their documented boundaries.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

from datetime import datetime, timezone

import pytest

from utils.batch_pipeline.record_seal_reasons import PROOF_REASONS, proof_reason, tail_gap_bucket


class SealError(ValueError):
    pass


def seal(message):
    return SealError(message)


def test_tail_lagging_message_maps_to_its_token():
    assert proof_reason(seal('retained capture tail not durable yet')) == 'tail_lagging'


def test_tail_lost_message_maps_to_its_token():
    assert proof_reason(seal('retained capture not durable yet')) == 'tail_lost_or_unproven'


def test_overlap_conflict_message_maps_to_its_token():
    assert proof_reason(seal('conflicting retained audio overlap')) == 'overlap_conflict'


def test_unit_budget_message_maps_to_budget_limit():
    assert proof_reason(seal('retained capture unit budget exceeded')) == 'budget_limit'


def test_reference_budget_message_maps_to_budget_limit():
    assert proof_reason(seal('retained capture reference budget exceeded')) == 'budget_limit'


def test_source_budget_message_maps_to_budget_limit():
    assert proof_reason(seal('retained audio source exceeds size budget')) == 'budget_limit'


def test_invalid_size_message_maps_to_budget_limit():
    assert proof_reason(seal('invalid retained audio size')) == 'budget_limit'


def test_finish_missing_message_maps_to_its_token():
    assert proof_reason(seal('retained capture finish missing')) == 'finish_missing'


def test_registration_refused_message_maps_to_its_token():
    assert proof_reason(seal('registration refused')) == 'registration_refused'


def test_decode_family_retained_source_has_no_aligned_audio_maps_to_decode_or_checksum():
    assert proof_reason(seal('retained source has no aligned audio')) == 'decode_or_checksum'


def test_decode_family_truncated_encrypted_audio_length_maps_to_decode_or_checksum():
    assert proof_reason(seal('truncated encrypted audio length')) == 'decode_or_checksum'


def test_decode_family_invalid_encrypted_audio_frame_maps_to_decode_or_checksum():
    assert proof_reason(seal('invalid encrypted audio frame')) == 'decode_or_checksum'


def test_decode_family_retained_audio_authentication_failed_maps_to_decode_or_checksum():
    assert proof_reason(seal('retained audio authentication failed')) == 'decode_or_checksum'


def test_decode_family_retained_capture_checksum_mismatch_maps_to_decode_or_checksum():
    assert proof_reason(seal('retained capture checksum mismatch')) == 'decode_or_checksum'


def test_decode_family_invalid_retained_PCM_maps_to_decode_or_checksum():
    assert proof_reason(seal('invalid retained PCM')) == 'decode_or_checksum'


def test_decode_family_retained_PCM_digest_changed_maps_to_decode_or_checksum():
    assert proof_reason(seal('retained PCM digest changed')) == 'decode_or_checksum'


def test_decode_family_invalid_WAL_packet_maps_to_decode_or_checksum():
    assert proof_reason(seal('invalid WAL packet')) == 'decode_or_checksum'


def test_decode_family_capture_decoder_produced_no_PCM_maps_to_decode_or_checksum():
    assert proof_reason(seal('capture decoder produced no PCM')) == 'decode_or_checksum'


def test_unknown_message_maps_to_other():
    assert proof_reason(seal('some provider said something')) == 'other'


def test_embedded_phrase_never_maps_to_a_token():
    assert proof_reason(seal('prefix invalid retained PCM suffix')) == 'other'


def test_empty_message_maps_to_other():
    assert proof_reason(seal('')) == 'other'


def test_every_known_token_is_in_the_closed_set():
    for token in ('tail_lagging', 'decode_or_checksum', 'budget_limit', 'other'):
        assert token in PROOF_REASONS


def test_every_mapping_lands_in_the_closed_set():
    tokens = {proof_reason(seal(message)) for message in ('registration refused', 'invalid retained PCM')}
    assert tokens <= PROOF_REASONS


def seal_at(gap_seconds):
    finished = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return finished, finished.timestamp() - gap_seconds


def test_tail_gap_zero_is_under_1s():
    finished, end = seal_at(0.0)
    assert tail_gap_bucket(finished, end) == 'under_1s'


def test_tail_gap_half_second_is_under_1s():
    finished, end = seal_at(0.5)
    assert tail_gap_bucket(finished, end) == 'under_1s'


def test_tail_gap_one_second_is_1_to_5s():
    finished, end = seal_at(1.0)
    assert tail_gap_bucket(finished, end) == '1_to_5s'


def test_tail_gap_five_seconds_is_5_to_30s():
    finished, end = seal_at(5.0)
    assert tail_gap_bucket(finished, end) == '5_to_30s'


def test_tail_gap_thirty_seconds_is_30_to_120s():
    finished, end = seal_at(30.0)
    assert tail_gap_bucket(finished, end) == '30_to_120s'


def test_tail_gap_exactly_120_is_30_to_120s():
    finished, end = seal_at(120.0)
    assert tail_gap_bucket(finished, end) == '30_to_120s'


def test_tail_gap_past_120_is_over_120s():
    finished, end = seal_at(121.0)
    assert tail_gap_bucket(finished, end) == 'over_120s'


def test_tail_gap_negative_is_negative_or_unknown():
    finished, end = seal_at(-3.0)
    assert tail_gap_bucket(finished, end) == 'negative_or_unknown'


def test_tail_gap_non_datetime_finisher_is_negative_or_unknown():
    assert tail_gap_bucket(object(), 0.0) == 'negative_or_unknown'


def test_tail_gap_string_end_is_negative_or_unknown():
    finished = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert tail_gap_bucket(finished, 'soon') == 'negative_or_unknown'


def test_proof_reasons_is_frozen():
    assert isinstance(PROOF_REASONS, frozenset)


def test_proof_reasons_holds_exactly_the_documented_members():
    assert PROOF_REASONS == frozenset(
        {
            "tail_lagging",
            "tail_lost_or_unproven",
            "overlap_conflict",
            "decode_or_checksum",
            "budget_limit",
            "finish_missing",
            "registration_refused",
            "other",
        }
    )


def test_tail_gap_bucket_boundaries_bucket_name_only():
    finished, end = seal_at(2.0)
    assert tail_gap_bucket(finished, end) in {"under_1s", "1_to_5s", "5_to_30s", "30_to_120s", "over_120s"}
