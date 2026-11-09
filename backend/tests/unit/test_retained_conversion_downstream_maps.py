"""Generated grid: the downstream maps a retained decode fault feeds.

proof_reason's exact-message table, the tail-gap buckets, the site= attribution
field and the closed vocabulary round-trips — pinned so the conversion cohort's
downstream bookings cannot drift.

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder
"""

import logging
import re
from datetime import datetime, timezone

import pytest

from utils.batch_pipeline.record_seal_reasons import (
    PROOF_REASONS,
    proof_diagnostics,
    proof_reason,
    tail_gap_bucket,
)
from utils.batch_pipeline.errors import error_site_field
from utils.batch_pipeline.source_audio import RetainedAudioInvalid


def test_proof_reason_tail_not_durable():
    fault = RetainedAudioInvalid('retained capture tail not durable yet')
    assert proof_reason(fault) == 'tail_lagging'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_not_durable():
    fault = RetainedAudioInvalid('retained capture not durable yet')
    assert proof_reason(fault) == 'tail_lost_or_unproven'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_overlap_conflict():
    fault = RetainedAudioInvalid('conflicting retained audio overlap')
    assert proof_reason(fault) == 'overlap_conflict'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_unit_budget():
    fault = RetainedAudioInvalid('retained capture unit budget exceeded')
    assert proof_reason(fault) == 'budget_limit'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_reference_budget():
    fault = RetainedAudioInvalid('retained capture reference budget exceeded')
    assert proof_reason(fault) == 'budget_limit'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_source_size_budget():
    fault = RetainedAudioInvalid('retained audio source exceeds size budget')
    assert proof_reason(fault) == 'budget_limit'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_invalid_audio_size():
    fault = RetainedAudioInvalid('invalid retained audio size')
    assert proof_reason(fault) == 'budget_limit'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_finish_missing():
    fault = RetainedAudioInvalid('retained capture finish missing')
    assert proof_reason(fault) == 'finish_missing'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_registration_refused():
    fault = RetainedAudioInvalid('registration refused')
    assert proof_reason(fault) == 'registration_refused'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_no_aligned_audio():
    fault = RetainedAudioInvalid('retained source has no aligned audio')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_truncated_encrypted():
    fault = RetainedAudioInvalid('truncated encrypted audio length')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_invalid_enc_frame():
    fault = RetainedAudioInvalid('invalid encrypted audio frame')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_auth_failed():
    fault = RetainedAudioInvalid('retained audio authentication failed')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_checksum_mismatch():
    fault = RetainedAudioInvalid('retained capture checksum mismatch')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_invalid_pcm():
    fault = RetainedAudioInvalid('invalid retained PCM')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_digest_changed():
    fault = RetainedAudioInvalid('retained PCM digest changed')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_invalid_wal():
    fault = RetainedAudioInvalid('invalid WAL packet')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_no_pcm():
    fault = RetainedAudioInvalid('capture decoder produced no PCM')
    assert proof_reason(fault) == 'decode_or_checksum'
    assert proof_reason(fault) in PROOF_REASONS


def test_proof_reason_defaults_to_other_for_unknown_text():
    assert proof_reason(RetainedAudioInvalid('never-seen provider text')) == 'other'


def test_proof_reason_is_exact_match_not_substring():
    assert proof_reason(RetainedAudioInvalid('prefix invalid retained PCM suffix')) == 'other'


def test_proof_diagnostics_carries_only_the_reason():
    fault = RetainedAudioInvalid('invalid retained PCM')
    assert proof_diagnostics(fault) == {'proof_reason': 'decode_or_checksum'}


def test_proof_diagnostics_tail_bucket_from_the_refusal_attribute():
    from utils.batch_pipeline.record_seal_reasons import TailGapRefusal

    fault = TailGapRefusal('1_to_5s')
    assert proof_diagnostics(fault) == {'proof_reason': 'tail_lagging', 'tail_gap_bucket': '1_to_5s'}


def test_proof_diagnostics_unknown_tail_bucket_is_bounded():
    from utils.batch_pipeline.record_seal_reasons import TailGapRefusal

    fault = TailGapRefusal('made_up_bucket')
    assert proof_diagnostics(fault)['tail_gap_bucket'] == 'negative_or_unknown'


def test_tail_gap_bucket_negative():
    end = 1000.0
    finished = datetime.fromtimestamp(end + -1.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == 'negative_or_unknown'


def test_tail_gap_bucket_zero():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 0.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == 'under_1s'


def test_tail_gap_bucket_half_second():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 0.5, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == 'under_1s'


def test_tail_gap_bucket_exactly_1s():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 1.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == '1_to_5s'


def test_tail_gap_bucket_four_seconds():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 4.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == '1_to_5s'


def test_tail_gap_bucket_exactly_5s():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 5.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == '5_to_30s'


def test_tail_gap_bucket_twenty_nine():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 29.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == '5_to_30s'


def test_tail_gap_bucket_exactly_30s():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 30.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == '30_to_120s'


def test_tail_gap_bucket_exactly_120s():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 120.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == '30_to_120s'


def test_tail_gap_bucket_over_120s():
    end = 1000.0
    finished = datetime.fromtimestamp(end + 121.0, tz=timezone.utc)
    assert tail_gap_bucket(finished, end) == 'over_120s'


def test_tail_gap_bucket_nonfinite_is_negative_or_unknown():
    class NanStamp:

        def timestamp(self):
            return float('nan')

    assert tail_gap_bucket(NanStamp(), 1000.0) == 'negative_or_unknown'


def test_site_field_names_the_raise_site_for_the_conversion_fault():
    import utils.batch_pipeline.source_audio as source_audio

    try:
        source_audio.decode_source(b'\\0' * 4, {'path': 'chunks/o/c/x.bin', 'sample_rate': 'nope'}, b'\\1' * 32)
    except RetainedAudioInvalid as fault:
        site = error_site_field(fault)
    assert site.startswith(' site=source_audio.py:')
    assert re.fullmatch(r' site=source_audio\.py:\d+', site)


def test_site_field_empty_without_a_traceback():
    assert error_site_field(ValueError("just the value")) == ""


def test_site_field_prefers_the_application_frame_over_site_packages():
    code = compile("raise ValueError('boom')", '/opt/venv/lib/python3.11/site-packages/fakepkg/mod.py', 'exec')
    fault = None
    try:
        exec(code, {})
    except ValueError as error:
        fault = error
    assert fault.__traceback__.tb_next is not None
    fault.__traceback__ = fault.__traceback__.tb_next
    assert error_site_field(fault) == ""


def test_site_field_skips_site_packages_frames_for_the_app_frame():
    inner = compile(
        "def raise_it():" + chr(10) + "    raise ValueError('boom')",
        '/opt/venv/lib/python3.11/site-packages/fakepkg/mod.py',
        'exec',
    )
    namespace = {}
    exec(inner, namespace)
    try:
        namespace["raise_it"]()
    except ValueError as error:
        site = error_site_field(error)
    assert "site-packages" not in site
    assert re.fullmatch(r" site=test_retained_conversion_downstream_maps\.py:\d+", site)
