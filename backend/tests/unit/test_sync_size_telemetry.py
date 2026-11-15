"""Size telemetry retains only closed buckets and hashed, bounded job references."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from google.api_core.exceptions import InvalidArgument

from config.sync_telemetry import bounded_correlation_ref
from utils.sync.assignment import run_with_size_limit_backstop
from utils.sync.size_telemetry import remember_size_payload, shape_fields, size_fields, with_size_attribution


@pytest.mark.parametrize(
    'count,seconds,expected_segments,expected_speech',
    [(1, 0, '1', '5'), (5, 120, '5', '120'), (6, 121, '10', '300'), (5001, 90000, '+Inf', '+Inf')],
)
def test_shape_buckets(count, seconds, expected_segments, expected_speech):
    payload = {'transcript_segments': [{'start': 0, 'end': seconds}] + [{}] * (count - 1)}
    assert shape_fields(payload) == (f'segments_bucket={expected_segments} speech_seconds_bucket={expected_speech}')


def test_refs_are_hashed_scoped_and_thread_isolated():
    job, attempt = str(uuid.uuid4()), str(uuid.uuid4())

    @with_size_attribution
    def observe(job_id=None, attempt_ref=None):
        return size_fields({'transcript_segments': []})

    with ThreadPoolExecutor(max_workers=2) as pool:
        lines = list(pool.map(lambda value: observe(job_id=value, attempt_ref=attempt), [job, 'private-uid']))
    assert f'job_ref={bounded_correlation_ref(job)}' in lines[0]
    assert 'job_ref=none' in lines[1]
    assert all(f'attempt_ref={bounded_correlation_ref(attempt)}' in line for line in lines)
    assert job not in str(lines) and uuid.UUID(job).hex not in str(lines) and attempt not in str(lines)
    assert 'private' not in str(lines)
    assert observe(job, attempt) == lines[0]
    assert 'job_ref=none attempt_ref=none' in size_fields()


def test_rejections_stamp_the_actual_attempted_payload_and_never_log_ids(caplog):
    job, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    calls = []

    def run(full_ids):
        cid = 'private-second' if full_ids else 'private-first'
        calls.append(cid)
        remember_size_payload(cid, {'transcript_segments': [{'start': 0, 'end': 120}] * len(calls)})
        raise InvalidArgument('Document exceeds the maximum allowed size private-uid')

    @with_size_attribution
    def invoke(*, job_id, attempt_ref):
        return run_with_size_limit_backstop(run, lambda: calls[-1])

    with pytest.raises(InvalidArgument) as caught:
        invoke(job_id=job, attempt_ref=attempt)
    event = next(r.message for r in caplog.records if 'event=sync_assignment_target' in r.message)
    assert 'reason=size_limit_retry outcome=rejected' in event
    assert 'segments_bucket=1 speech_seconds_bucket=120' in event
    fields = caught.value.sync_size_fields
    assert 'segments_bucket=2 speech_seconds_bucket=300' in fields
    for line in (event, fields):
        assert f'job_ref={bounded_correlation_ref(job)} attempt_ref={bounded_correlation_ref(attempt)}' in line
        assert 'rollover_target_kind=none' in line
        assert 'private' not in line and job not in line and attempt not in line
    assert 'segments_bucket=unknown' in size_fields(cid='private-first')
