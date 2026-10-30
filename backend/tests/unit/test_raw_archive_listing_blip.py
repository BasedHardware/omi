"""The raw archive pack listing rides the GCS SDK's own availability retry.

Failure-Class: FC-listing-blip-drops-coverage-and-logs-degrade-as-error — a
momentary provider fault on a listing read must ride the provider's own
availability retry, and a listing whose retry budget drains must degrade by
its documented fallback classification, never as an unexpected traceback.

The merge and STOP_PCM read paths prefer complete raw-archive packs over the
legacy PCM chunks, and that preference starts with one GCS prefix listing
(``list_packs``). The listing was issued single-shot (``retry=None``), so one
503 ``ServiceUnavailable`` blip — the storage SDK's own retryable class —
killed the whole pack listing for the conversation. Two failures followed
from the same root: the merge silently lost every raw-archive pack it was
about to prefer (audio coverage dropped on a transient fault), and the
handler re-logged the handled degrade with its full traceback, which the
prod sensor classifies as a true error (pusher ``raw archive listing
failed`` family, ×36/30m at the 2026-10-30 sensor window).

The classification boundary was the bug's root, again: the listing boundary
had no transient classifier at all. Every listing fault — a blip the SDK
itself replays, a drained retry envelope, or a permanent refusal — landed in
one arm that logged ``exc_info=True``. This change gives the listing the
same two-layer shape every other storage boundary in this tree already has
(``_is_storage_blip`` in ``utils/conversations/lifecycle.py``, the
Firestore writers' availability trio): the listing requests the SDK's
availability retry (``google.cloud.storage.retry.DEFAULT_RETRY``, bounded),
and the caller sheds exactly the replayed set to a quiet degrade — warning,
shared ``omi_fallback_total`` event, legacy chunks retained — while
permanent refusals keep the loud traceback.

Guards:
- the listing requests a real, bounded, non-conditional SDK retry, and that
  retry object demonstrably heals a single blip and drains to a
  ``RetryError`` whose cause is the last fault;
- the boundary classifier mirrors the SDK's retryable types exactly — every
  member the SDK replays is a quiet degrade, nothing quieter is, and the
  drained envelope follows its cause;
- a degraded listing keeps the merge's legacy chunks and records one
  fallback event without any traceback; permanent refusals keep the loud
  classification;
- the listing's own preserved semantics (prefix, metadata filters, sort,
  TTL cache, eviction, 10000-budget cap, index invalidation) survive the
  retry change, and the pack-union merge behavior is unchanged.

RED on the parent commit: the retry-request tests fail on ``retry=None``,
the classifier tests fail on the missing classifier, and the degrade tests
fail on the traceback-bearing catch-all arm.
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import (
    BadGateway,
    BadRequest,
    Forbidden,
    GatewayTimeout,
    InternalServerError,
    NotFound,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)
from google.cloud.storage.retry import DEFAULT_RETRY as _SDK_DEFAULT_RETRY
from google.cloud.storage.retry import _RETRYABLE_TYPES as _SDK_RETRYABLE_TYPES
from requests.exceptions import ChunkedEncodingError as RequestsChunkedEncodingError
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from utils.other import raw_audio_read, storage

_CONV = ('owner', 'conversation')


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _pack_blob(name, start, end, *, codec='opus', gap=0, channels=1, layout='mono', size=100, generation=1, **extra):
    metadata = {
        'capture_start': start,
        'capture_end': end,
        'gap_count': gap,
        'channels': channels,
        'codec': codec,
        'source_layout': layout,
    }
    metadata.update(extra)
    return SimpleNamespace(name=name, size=size, generation=generation, metadata=metadata)


class _SplitBucket:
    """Serves the legacy ``chunks/`` listing and the ``raw-live/`` pack listing."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.chunk_blobs: list = []
        self.raw_blobs: list = []
        self.raw_error: Exception | None = None

    def list_blobs(self, prefix, **kwargs):
        self.calls.append((prefix, kwargs))
        if prefix.startswith('raw-live/'):
            if self.raw_error is not None:
                raise self.raw_error
            return list(self.raw_blobs)
        return list(self.chunk_blobs)


@pytest.fixture
def listing_bucket(monkeypatch):
    bucket = _SplitBucket()
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'canonical')
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(storage.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.setattr(raw_audio_read, '_indexes', {})
    return bucket


def enable(monkeypatch):
    monkeypatch.setenv('AUDIO_ARCHIVE_READ_ENABLED', 'true')
    monkeypatch.setenv('AUDIO_ARCHIVE_UID_ALLOWLIST', 'owner')


@pytest.fixture
def fallback_events(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(storage, 'record_fallback', lambda **kwargs: events.append(kwargs))
    return events


# ── A. The listing requests the SDK's availability retry ────────────────────


def test_list_packs_requests_an_availability_retry(listing_bucket):
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    (pack_call,) = [kwargs for prefix, kwargs in listing_bucket.calls if prefix.startswith('raw-live/')]
    assert pack_call.get('retry') is not None


def test_requested_retry_replays_the_sdk_availability_set(listing_bucket):
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    (pack_call,) = [kwargs for prefix, kwargs in listing_bucket.calls if prefix.startswith('raw-live/')]
    retry = pack_call.get('retry')
    assert retry is not None
    predicate = getattr(retry, '_predicate', None)
    assert predicate is not None
    for member in _SDK_RETRYABLE_TYPES:
        assert predicate(member('blip')), member


def test_requested_retry_timeout_is_bounded(listing_bucket):
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    (pack_call,) = [kwargs for prefix, kwargs in listing_bucket.calls if prefix.startswith('raw-live/')]
    retry = pack_call.get('retry')
    assert retry is not None
    timeout = getattr(retry, '_timeout', None)
    assert timeout is not None and 0 < timeout <= 60


def test_requested_retry_is_unconditional(listing_bucket):
    """A ``ConditionalRetryPolicy`` would silently disable itself on a plain
    listing call (no ``if_generation_match`` kwargs to satisfy it); the listing
    needs an always-on retry."""
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    (pack_call,) = [kwargs for prefix, kwargs in listing_bucket.calls if prefix.startswith('raw-live/')]
    from google.api_core.retry import Retry

    assert isinstance(pack_call.get('retry'), Retry)


def test_retry_object_heals_a_single_blip(listing_bucket, monkeypatch):
    """The exact retry object the listing requests replays a 503 and succeeds."""
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    (pack_call,) = [kwargs for prefix, kwargs in listing_bucket.calls if prefix.startswith('raw-live/')]
    retry = pack_call.get('retry')
    assert retry is not None

    monkeypatch.setattr(time, 'sleep', lambda seconds: None)
    attempts = {'n': 0}

    def flaky():
        attempts['n'] += 1
        if attempts['n'] == 1:
            raise ServiceUnavailable('503 blip')
        return ['pack']

    assert retry(flaky)() == ['pack']
    assert attempts['n'] == 2


def test_retry_object_drains_to_retry_error_with_cause(listing_bucket, monkeypatch):
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    (pack_call,) = [kwargs for prefix, kwargs in listing_bucket.calls if prefix.startswith('raw-live/')]
    retry = pack_call.get('retry')
    assert retry is not None

    monkeypatch.setattr(time, 'sleep', lambda seconds: None)

    def always_down():
        raise ServiceUnavailable('503 still down')

    decorated = retry(always_down)
    with pytest.raises(RetryError) as excinfo:
        decorated()
    assert isinstance(excinfo.value.cause, ServiceUnavailable)


# ── B. The boundary classifier mirrors the SDK's replayed set ────────────────


def test_rate_limit_is_a_listing_blip():
    assert storage._is_pack_listing_blip(TooManyRequests('429: rate limited'))


def test_internal_server_error_is_a_listing_blip():
    assert storage._is_pack_listing_blip(InternalServerError('500: internal'))


def test_bad_gateway_is_a_listing_blip():
    assert storage._is_pack_listing_blip(BadGateway('502: bad gateway'))


def test_service_unavailable_is_a_listing_blip():
    assert storage._is_pack_listing_blip(ServiceUnavailable('503: unavailable'))


def test_gateway_timeout_is_a_listing_blip():
    assert storage._is_pack_listing_blip(GatewayTimeout('504: gateway timeout'))


def test_builtin_connection_error_is_a_listing_blip():
    assert storage._is_pack_listing_blip(ConnectionError('reset by peer'))


def test_requests_connection_error_is_a_listing_blip():
    assert storage._is_pack_listing_blip(RequestsConnectionError('reset by peer'))


def test_requests_chunked_encoding_error_is_a_listing_blip():
    assert storage._is_pack_listing_blip(RequestsChunkedEncodingError('chunk break'))


def test_requests_timeout_is_a_listing_blip():
    assert storage._is_pack_listing_blip(RequestsTimeout('read timed out'))


def test_drained_envelope_over_service_unavailable_is_a_listing_blip():
    error = RetryError('budget drained', ServiceUnavailable('503'))
    assert storage._is_pack_listing_blip(error)


def test_drained_envelope_over_transport_reset_is_a_listing_blip():
    error = RetryError('budget drained', RequestsConnectionError('reset'))
    assert storage._is_pack_listing_blip(error)


def test_drained_envelope_over_permission_refusal_stays_loud():
    error = RetryError('budget drained', Forbidden('403'))
    assert not storage._is_pack_listing_blip(error)


def test_causeless_envelope_stays_loud():
    assert not storage._is_pack_listing_blip(RetryError('budget drained', None))


def test_permission_refusal_stays_loud():
    assert not storage._is_pack_listing_blip(Forbidden('403: forbidden'))


def test_bad_request_stays_loud():
    assert not storage._is_pack_listing_blip(BadRequest('400: bad request'))


def test_not_found_stays_loud():
    assert not storage._is_pack_listing_blip(NotFound('404: missing'))


def test_unknown_fault_stays_loud():
    assert not storage._is_pack_listing_blip(ValueError('unexpected'))


def test_classifier_matches_the_storage_sdk_retryable_types():
    for member in _SDK_RETRYABLE_TYPES:
        assert storage._is_pack_listing_blip(member('blip')), member


def test_classifier_matches_the_requested_retry_predicate():
    """No gap between what the listing asks the SDK to replay and what the
    boundary sheds: the two sets must stay identical."""
    assert raw_audio_read._PACK_LIST_RETRY is not None
    predicate = raw_audio_read._PACK_LIST_RETRY._predicate
    boundary = storage._is_pack_listing_blip
    probe = [member('blip') for member in _SDK_RETRYABLE_TYPES]
    for error in probe:
        assert bool(predicate(error)) == boundary(error), error


# ── C. The caller boundary: blips degrade quietly, refusals stay loud ────────


_DEGRADE_SHAPES = [
    ServiceUnavailable('503: unavailable'),
    InternalServerError('500: internal'),
    BadGateway('502: bad gateway'),
    GatewayTimeout('504: gateway timeout'),
    TooManyRequests('429: rate limited'),
    ConnectionError('reset by peer'),
    RequestsConnectionError('reset by peer'),
    RequestsChunkedEncodingError('chunk break'),
    RequestsTimeout('read timed out'),
]


@pytest.mark.parametrize('error', _DEGRADE_SHAPES, ids=lambda e: type(e).__name__)
def test_pack_listing_blip_degrades_quietly_and_keeps_legacy_chunks(
    listing_bucket, monkeypatch, caplog, fallback_events, error
):
    enable(monkeypatch)
    listing_bucket.chunk_blobs = [SimpleNamespace(name='chunks/owner/conversation/1000.000.opus', size=3, generation=1)]
    listing_bucket.raw_error = error
    with caplog.at_level(logging.DEBUG, logger='utils.other.storage'):
        chunks = storage.list_audio_chunks(*_CONV)
    assert [item['path'] for item in chunks] == ['chunks/owner/conversation/1000.000.opus']
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert not any(record.exc_info for record in caplog.records)
    assert len(fallback_events) == 1


@pytest.mark.parametrize(
    'cause', [ServiceUnavailable('503'), RequestsConnectionError('reset')], ids=lambda c: type(c).__name__
)
def test_drained_listing_envelope_degrades_quietly(listing_bucket, monkeypatch, caplog, fallback_events, cause):
    enable(monkeypatch)
    listing_bucket.chunk_blobs = [SimpleNamespace(name='chunks/owner/conversation/1000.000.opus', size=3, generation=1)]
    listing_bucket.raw_error = RetryError('budget drained', cause)
    with caplog.at_level(logging.DEBUG, logger='utils.other.storage'):
        chunks = storage.list_audio_chunks(*_CONV)
    assert [item['path'] for item in chunks] == ['chunks/owner/conversation/1000.000.opus']
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert not any(record.exc_info for record in caplog.records)
    assert len(fallback_events) == 1


def test_permanent_listing_refusal_keeps_the_loud_traceback(listing_bucket, monkeypatch, caplog, fallback_events):
    enable(monkeypatch)
    listing_bucket.chunk_blobs = [SimpleNamespace(name='chunks/owner/conversation/1000.000.opus', size=3, generation=1)]
    listing_bucket.raw_error = Forbidden('403: forbidden')
    with caplog.at_level(logging.DEBUG, logger='utils.other.storage'):
        chunks = storage.list_audio_chunks(*_CONV)
    assert [item['path'] for item in chunks] == ['chunks/owner/conversation/1000.000.opus']
    loud = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert loud and any(record.exc_info for record in loud)


def test_permanent_listing_refusal_records_the_exhausted_event(listing_bucket, monkeypatch, caplog, fallback_events):
    enable(monkeypatch)
    listing_bucket.raw_error = BadRequest('400: bad request')
    with caplog.at_level(logging.DEBUG, logger='utils.other.storage'):
        storage.list_audio_chunks(*_CONV)
    assert fallback_events and fallback_events[0]['outcome'] == 'exhausted'


def test_degraded_listing_records_the_shared_fallback_labels(listing_bucket, monkeypatch, fallback_events):
    enable(monkeypatch)
    listing_bucket.raw_error = ServiceUnavailable('503: unavailable')
    storage.list_audio_chunks(*_CONV)
    (event,) = fallback_events
    assert event['component'] == 'other'
    assert event['from_mode'] == 'raw_archive'
    assert event['to_mode'] == 'legacy_chunks'
    assert event['outcome'] == 'degraded'
    assert event['reason'] in ('provider_5xx', 'provider_429')


def test_rate_limit_blip_reports_the_quota_reason(listing_bucket, monkeypatch, fallback_events):
    enable(monkeypatch)
    listing_bucket.raw_error = TooManyRequests('429: rate limited')
    storage.list_audio_chunks(*_CONV)
    (event,) = fallback_events
    assert event['reason'] == 'provider_429'


def test_blip_reason_envelope_follows_the_cause_to_quota():
    assert storage._listing_blip_reason(RetryError('drained', TooManyRequests('429'))) == 'provider_429'


def test_blip_reason_envelope_follows_the_cause_to_transport():
    assert storage._listing_blip_reason(RetryError('drained', RequestsConnectionError('reset'))) == 'transport_error'


def test_blip_reason_envelope_follows_the_cause_to_5xx():
    assert storage._listing_blip_reason(RetryError('drained', ServiceUnavailable('503'))) == 'provider_5xx'


def test_blip_reason_transport_reset_buckets_as_transport_error():
    assert storage._listing_blip_reason(ConnectionError('reset by peer')) == 'transport_error'


def test_blip_reason_gateway_timeout_buckets_as_5xx():
    assert storage._listing_blip_reason(GatewayTimeout('504')) == 'provider_5xx'


def test_requests_transport_helper_matches_the_exact_module():
    class Reset(Exception):
        pass

    Reset.__module__ = 'requests.exceptions'
    assert raw_audio_read is not None
    from utils.storage_retry_types import is_requests_transport_error

    assert is_requests_transport_error(Reset('x'))


def test_requests_transport_helper_matches_submodules():
    class Retries(Exception):
        pass

    Retries.__module__ = 'requests.exceptions.retries'
    from utils.storage_retry_types import is_requests_transport_error

    assert is_requests_transport_error(Retries('x'))


def test_requests_transport_helper_rejects_same_named_other_modules():
    """A lookalike from another module (or the builtin) is not the transport
    family — the boundary tuple carries those explicitly instead."""

    class ConnectionError(Exception):
        pass

    from utils.storage_retry_types import is_requests_transport_error

    assert not is_requests_transport_error(ConnectionError('x'))


def test_refusal_records_exhausted_and_never_degraded(listing_bucket, monkeypatch, fallback_events):
    enable(monkeypatch)
    listing_bucket.raw_error = Forbidden('403: forbidden')
    storage.list_audio_chunks(*_CONV)
    assert [event['outcome'] for event in fallback_events] == ['exhausted']


def test_blip_records_degraded_and_never_exhausted(listing_bucket, monkeypatch, fallback_events):
    enable(monkeypatch)
    listing_bucket.raw_error = ServiceUnavailable('503: unavailable')
    storage.list_audio_chunks(*_CONV)
    assert [event['outcome'] for event in fallback_events] == ['degraded']


def test_deadline_bounded_caller_skips_the_pack_arm_by_deadline(listing_bucket, monkeypatch):
    """The speaker-listing budget path owns its own deadline; the raw-archive
    preference stays out of it for the deadline variant too."""
    enable(monkeypatch)
    listing_bucket.raw_error = ServiceUnavailable('503: unavailable')
    listing_bucket.chunk_blobs = [SimpleNamespace(name='chunks/owner/conversation/1000.000.opus', size=3, generation=1)]
    chunks = storage.list_audio_chunks(*_CONV, deadline=time.monotonic() + 5)
    assert [item['path'] for item in chunks] == ['chunks/owner/conversation/1000.000.opus']
    assert not any(prefix.startswith('raw-live/') for prefix, _ in listing_bucket.calls)


def test_blip_warning_carries_the_owner_and_conversation(listing_bucket, monkeypatch, caplog, fallback_events):
    enable(monkeypatch)
    listing_bucket.raw_error = ServiceUnavailable('503: unavailable')
    with caplog.at_level(logging.DEBUG, logger='utils.other.storage'):
        storage.list_audio_chunks(*_CONV)
    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING and 'owner' in record.getMessage()
    ]
    assert warnings


def test_read_phase_gate_still_prevents_the_pack_listing(listing_bucket, monkeypatch):
    monkeypatch.setenv('AUDIO_ARCHIVE_READ_ENABLED', 'false')

    def forbidden(*args, **kwargs):
        raise AssertionError('flags-off must not list raw')

    monkeypatch.setattr(storage, 'list_packs', forbidden)
    listing_bucket.chunk_blobs = [SimpleNamespace(name='chunks/owner/conversation/1000.000.opus', size=3, generation=1)]
    assert storage.list_audio_chunks(*_CONV)


def test_deadline_bounded_caller_skips_the_pack_arm(listing_bucket, monkeypatch):
    """The speaker-listing budget path owns its own deadline; the raw-archive
    preference stays out of it."""
    enable(monkeypatch)
    listing_bucket.raw_error = ServiceUnavailable('503: unavailable')
    listing_bucket.chunk_blobs = [SimpleNamespace(name='chunks/owner/conversation/1000.000.opus', size=3, generation=1)]
    chunks = storage.list_audio_chunks(*_CONV, timeout=5)
    assert [item['path'] for item in chunks] == ['chunks/owner/conversation/1000.000.opus']
    assert not any(prefix.startswith('raw-live/') for prefix, _ in listing_bucket.calls)


def test_blip_does_not_poison_the_pack_index(listing_bucket, monkeypatch):
    enable(monkeypatch)
    listing_bucket.raw_error = ServiceUnavailable('503: unavailable')
    storage.list_audio_chunks(*_CONV)
    listing_bucket.raw_error = None
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    chunks = storage.list_audio_chunks(*_CONV)
    assert any(item['path'].startswith('raw-live/') for item in chunks)


def test_successful_listing_records_no_fallback_event(listing_bucket, monkeypatch, fallback_events):
    enable(monkeypatch)
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    storage.list_audio_chunks(*_CONV)
    assert fallback_events == []


# ── D. Preserved listing semantics ──────────────────────────────────────────


def test_pack_budget_cap_still_raises_timeouterror(listing_bucket):
    listing_bucket.raw_blobs = [
        _pack_blob(f'raw-live/owner/conversation/{index}.opus', float(index), float(index) + 1)
        for index in range(10001)
    ]
    with pytest.raises(TimeoutError):
        raw_audio_read.list_packs(listing_bucket, *_CONV)


def test_pack_listing_still_cached_within_ttl(listing_bucket):
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    assert len([call for call in listing_bucket.calls if call[0].startswith('raw-live/')]) == 1


def test_pack_cache_expires_and_relists(listing_bucket, monkeypatch):
    monkeypatch.setattr(raw_audio_read, '_INDEX_TTL', -1.0)
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus', 1.0, 2.0)]
    raw_audio_read.invalidate_pack_index(listing_bucket, *_CONV)
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    assert len([call for call in listing_bucket.calls if call[0].startswith('raw-live/')]) == 2


def test_pack_index_eviction_bounds_the_cache(listing_bucket, monkeypatch):
    monkeypatch.setattr(raw_audio_read, '_MAX_INDEXES', 2)
    for uid in ('a', 'b', 'c'):
        raw_audio_read.list_packs(listing_bucket, uid, 'conversation')
    assert len(raw_audio_read._indexes) == 2


def test_uncovered_packs_still_extend_the_merge_listing(listing_bucket, monkeypatch):
    enable(monkeypatch)
    listing_bucket.chunk_blobs = [SimpleNamespace(name='chunks/owner/conversation/1000.000.opus', size=3, generation=1)]
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/2000-2100.opus.raw', 2000.0, 2100.0)]
    chunks = storage.list_audio_chunks(*_CONV)
    paths = sorted(item['path'] for item in chunks)
    assert paths == ['chunks/owner/conversation/1000.000.opus', 'raw-live/owner/conversation/2000-2100.opus.raw']


def test_covered_packs_do_not_duplicate_the_merge_listing(listing_bucket, monkeypatch):
    enable(monkeypatch)
    listing_bucket.chunk_blobs = [SimpleNamespace(name='chunks/owner/conversation/1000.000.opus', size=3, generation=1)]
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1000-1100.opus.raw', 1000.0, 1100.0)]
    chunks = storage.list_audio_chunks(*_CONV)
    assert [item['path'] for item in chunks] == ['chunks/owner/conversation/1000.000.opus']


@pytest.mark.parametrize(
    'kwargs',
    [
        {'gap': 1},
        {'channels': 2},
        {'layout': 'stereo'},
        {'codec': 'mp3'},
    ],
    ids=['gapped', 'multichannel', 'nonmono', 'unknown-codec'],
)
def test_pack_metadata_filters_still_skip_disqualified_packs(listing_bucket, kwargs):
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus.raw', 1.0, 2.0, **kwargs)]
    assert raw_audio_read.list_packs(listing_bucket, *_CONV) == []


def test_opus_and_flac_packs_still_qualify(listing_bucket):
    listing_bucket.raw_blobs = [
        _pack_blob('raw-live/owner/conversation/1.opus.raw', 1.0, 2.0, codec='opus'),
        _pack_blob('raw-live/owner/conversation/2.flac.raw', 3.0, 4.0, codec='flac'),
    ]
    assert len(raw_audio_read.list_packs(listing_bucket, *_CONV)) == 2


@pytest.mark.parametrize(
    'metadata_extra',
    [{'capture_start': 'soon'}, {'gap_count': 'many'}, {'channels': None}, {'capture_end': None}],
    ids=['bad-start', 'bad-gap', 'bad-channels', 'missing-end'],
)
def test_malformed_pack_metadata_still_skips_the_pack(listing_bucket, metadata_extra):
    base = {'capture_start': 1.0, 'capture_end': 2.0, 'gap_count': 0, 'channels': 1, 'codec': 'opus'}
    base.update(metadata_extra)
    listing_bucket.raw_blobs = [
        SimpleNamespace(name='raw-live/owner/conversation/1.opus.raw', size=1, generation=1, metadata=base)
    ]
    assert raw_audio_read.list_packs(listing_bucket, *_CONV) == []


def test_packs_still_sort_by_timestamp(listing_bucket):
    listing_bucket.raw_blobs = [
        _pack_blob('raw-live/owner/conversation/5.opus.raw', 5.0, 6.0),
        _pack_blob('raw-live/owner/conversation/1.opus.raw', 1.0, 2.0),
    ]
    assert [pack['timestamp'] for pack in raw_audio_read.list_packs(listing_bucket, *_CONV)] == [1.0, 5.0]


def test_invalidate_pack_index_still_forces_a_relist(listing_bucket):
    listing_bucket.raw_blobs = [_pack_blob('raw-live/owner/conversation/1.opus.raw', 1.0, 2.0)]
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    raw_audio_read.invalidate_pack_index(listing_bucket, *_CONV)
    raw_audio_read.list_packs(listing_bucket, *_CONV)
    assert len([call for call in listing_bucket.calls if call[0].startswith('raw-live/')]) == 2


# ── E. The read proofs keep owning their own classification ─────────────────


def test_verified_pcm_paths_lets_the_listing_fault_propagate(listing_bucket, monkeypatch):
    monkeypatch.setattr(raw_audio_read, 'list_packs', lambda *args: (_ for _ in ()).throw(ServiceUnavailable('503')))
    chunk = {'timestamp': 1.0, 'data': b'\x00\x00', 'span': {'sample_rate': 16000}}
    with pytest.raises(ServiceUnavailable):
        raw_audio_read.verified_pcm_paths(listing_bucket, *_CONV, [chunk], 16000)


def test_pcm_for_span_lets_the_listing_fault_propagate(listing_bucket, monkeypatch):
    monkeypatch.setattr(raw_audio_read, 'list_packs', lambda *args: (_ for _ in ()).throw(ServiceUnavailable('503')))
    span = {'start': 1.0, 'samples': 16000, 'sample_rate': 16000}
    with pytest.raises(ServiceUnavailable):
        raw_audio_read.pcm_for_span(listing_bucket, *_CONV, span)


def test_sdk_default_retry_still_replays_the_availability_set():
    """Pin the SDK behavior the boundary mirrors, so a pinned-SDK bump that
    narrows the replay set cannot silently re-open the loud family."""
    predicate = _SDK_DEFAULT_RETRY._predicate
    for member in (ServiceUnavailable, InternalServerError, RequestsConnectionError):
        assert predicate(member('blip')), member
    for member in (Forbidden, BadRequest, NotFound):
        assert not predicate(member('blip')), member
