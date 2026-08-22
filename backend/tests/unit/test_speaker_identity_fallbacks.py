"""Losing WHO spoke must be counted, not just logged (BACKLOG L20).

Three paths give up on speaker identity and carry on. Each is a defensible fail-open — a conversation
without attribution beats a conversation that fails to save — but each was invisible: an `info` or a
`warning`, nothing on `omi_fallback_total`. An operator whose matcher had been down for a week saw a
product that "worked" and transcripts that quietly belonged to nobody, indistinguishable from a week of
conversations that genuinely had no known speaker in them.

  utils/stt/speech_profile.py     six return-default paths across the sync and async twins (non-200, JSON
                                  error, malformed shape, transport error) -> every segment gets
                                  `is_user: False, person_id: None`
  utils/stt/pre_recorded.py       batch diarization fails -> every segment collapses to SPEAKER_00
  routers/speech_profile.py       embedding extraction fails -> the audio is stored, the endpoint answers
                                  200, and speaker matching can never fire for that user again

The fail-open behaviour is unchanged on purpose; only its visibility is. Each test asserts BOTH — the
return value the caller still gets, and the event an operator now gets.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest


def _segments(count: int = 2):
    return [{'text': f's{i}', 'start': i, 'end': i + 1} for i in range(count)]


@pytest.fixture
def events(monkeypatch):
    recorded: list[dict] = []
    from utils.stt import speech_profile

    monkeypatch.setattr(speech_profile, 'record_fallback', lambda **kw: recorded.append(kw))
    monkeypatch.setattr(speech_profile, '_get_speech_profile_api_url', lambda: 'http://matcher.invalid/match')
    return recorded


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / 'a.wav'
    path.write_bytes(b'RIFF....WAVE')
    return str(path)


# --- speech-profile matching ------------------------------------------------------------------------


@pytest.mark.parametrize(
    'status,reason',
    [(503, 'provider_5xx'), (429, 'provider_429'), (404, 'other')],
)
def test_a_non_200_from_the_matcher_is_recorded(monkeypatch, events, audio, status, reason):
    from utils.stt import speech_profile

    monkeypatch.setattr(httpx, 'post', lambda *a, **k: httpx.Response(status, text='nope'))

    matches = speech_profile.get_speech_profile_matching_predictions('u1', audio, _segments())

    assert matches == [{'is_user': False, 'person_id': None}] * 2, 'the fail-open itself must not change'
    assert len(events) == 1
    assert events[0]['component'] == 'speaker'
    assert events[0]['to_mode'] == 'unattributed'
    assert events[0]['reason'] == reason
    assert events[0]['outcome'] == 'degraded'


def test_a_malformed_shape_is_told_apart_from_a_dead_matcher(monkeypatch, events, audio):
    """A 200 whose body does not match the contract is not a transport problem, and the distinction is
    'the matcher is down' vs 'the matcher changed its response' — different people fix those."""
    from utils.stt import speech_profile

    monkeypatch.setattr(httpx, 'post', lambda *a, **k: httpx.Response(200, json={'unexpected': True}))

    matches = speech_profile.get_speech_profile_matching_predictions('u1', audio, _segments())

    assert matches == [{'is_user': False, 'person_id': None}] * 2
    assert [e['reason'] for e in events] == ['malformed_doc']


def test_a_body_that_is_not_json_at_all_is_recorded(monkeypatch, events, audio):
    from utils.stt import speech_profile

    monkeypatch.setattr(httpx, 'post', lambda *a, **k: httpx.Response(200, text='<html>gateway</html>'))

    speech_profile.get_speech_profile_matching_predictions('u1', audio, _segments())

    assert [e['reason'] for e in events] == ['malformed_doc']


def test_a_good_response_records_nothing(monkeypatch, events, audio):
    from utils.stt import speech_profile

    monkeypatch.setattr(
        httpx,
        'post',
        lambda *a, **k: httpx.Response(200, json=[{'is_user': True, 'person_id': None}, {'is_user': False}]),
    )

    matches = speech_profile.get_speech_profile_matching_predictions('u1', audio, _segments())

    assert matches[0]['is_user'] is True
    assert events == [], 'a working matcher must not look like a degraded one'


@pytest.mark.parametrize(
    'error,reason',
    [(httpx.ConnectTimeout('slow'), 'timeout'), (httpx.ConnectError('refused'), 'other')],
)
def test_the_async_twin_records_transport_failures(monkeypatch, events, audio, error, reason):
    """The twin exists because two call sites need sync and async; instrumenting one and not the other
    would make the counter depend on which path the caller happened to take."""
    from utils.stt import speech_profile

    class _Client:
        async def post(self, *_a, **_k):
            raise error

    monkeypatch.setattr(speech_profile, 'get_stt_client', lambda: _Client())

    matches = asyncio.run(speech_profile.async_get_speech_profile_matching_predictions('u1', audio, _segments()))

    assert matches == [{'is_user': False, 'person_id': None}] * 2
    assert [(e['to_mode'], e['reason']) for e in events] == [('unattributed', reason)]


def test_the_async_twin_records_a_non_200_the_same_way_as_the_sync_one(monkeypatch, events, audio):
    from utils.stt import speech_profile

    class _Client:
        async def post(self, *_a, **_k):
            return httpx.Response(500, text='boom')

    monkeypatch.setattr(speech_profile, 'get_stt_client', lambda: _Client())

    asyncio.run(speech_profile.async_get_speech_profile_matching_predictions('u1', audio, _segments()))

    assert [(e['from_mode'], e['to_mode'], e['reason']) for e in events] == [
        ('speech_profile_match', 'unattributed', 'provider_5xx')
    ]


# --- batch diarization ------------------------------------------------------------------------------


def test_diarization_collapsing_onto_one_speaker_is_recorded(monkeypatch):
    """Every segment becomes SPEAKER_00 — a two-person conversation reads as a monologue."""
    from utils.stt import pre_recorded

    recorded: list[dict] = []
    monkeypatch.setattr(pre_recorded, 'record_fallback', lambda **kw: recorded.append(kw))

    def _no_model(*_a, **_k):
        raise RuntimeError('embedding model not loaded')

    monkeypatch.setattr(pre_recorded, 'extract_embedding_from_bytes', _no_model)

    label = pre_recorded._parakeet_assign_speaker_sync(_wav(16000, 2.0), 16000, 0.0, 2.0, [], [])

    assert label == 'SPEAKER_00', 'the fail-open itself must not change'
    assert len(recorded) == 1
    assert recorded[0]['component'] == 'speaker'
    assert recorded[0]['from_mode'] == 'diarization'
    assert recorded[0]['to_mode'] == 'single_speaker'
    assert recorded[0]['outcome'] == 'degraded'


def test_a_segment_too_short_to_diarize_is_not_a_fallback(monkeypatch):
    """SPEAKER_00 for a 0.2s segment is the design, not a degradation. Counting it would drown the signal
    the counter exists for."""
    from utils.stt import pre_recorded

    recorded: list[dict] = []
    monkeypatch.setattr(pre_recorded, 'record_fallback', lambda **kw: recorded.append(kw))

    assert pre_recorded._parakeet_assign_speaker_sync(_wav(16000, 2.0), 16000, 0.0, 0.2, [], []) == 'SPEAKER_00'
    assert recorded == []


def _wav(sample_rate: int, seconds: float) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b'\x00\x00' * int(sample_rate * seconds))
    return buf.getvalue()


# --- enrolment --------------------------------------------------------------------------------------


def test_enrolment_that_stored_no_embedding_is_recorded(monkeypatch):
    """The one that reaches a person. The route catches the failure and still answers 200 with the URL, so
    the user believes their voice profile is set up while matching can never fire for them."""
    from routers import speech_profile as route

    recorded: list[dict] = []
    monkeypatch.setattr(route, 'record_fallback', lambda **kw: recorded.append(kw))

    def _down(*_a, **_k):
        raise RuntimeError('embedding service down')

    monkeypatch.setattr(route, 'extract_embedding', _down)

    assert route._store_speaker_embedding('u1', '/tmp/x.wav') is False
    assert len(recorded) == 1
    assert recorded[0]['component'] == 'speaker'
    assert recorded[0]['from_mode'] == 'enrolled'
    assert recorded[0]['to_mode'] == 'no_embedding'


def test_a_successful_enrolment_records_nothing(monkeypatch):
    from routers import speech_profile as route

    recorded: list[dict] = []
    stored: list[tuple] = []
    monkeypatch.setattr(route, 'record_fallback', lambda **kw: recorded.append(kw))

    class _Embedding:
        def flatten(self):
            return _Embedding.Flat()

        class Flat:
            def tolist(self):
                return [0.1, 0.2]

    monkeypatch.setattr(route, 'extract_embedding', lambda *_a, **_k: _Embedding())
    monkeypatch.setattr(route, 'set_user_speaker_embedding', lambda uid, e: stored.append((uid, e)))

    assert route._store_speaker_embedding('u1', '/tmp/x.wav') is True
    assert stored == [('u1', [0.1, 0.2])]
    assert recorded == []


def test_the_upload_route_still_stores_the_embedding():
    """The extraction moved into a helper; a route that stopped calling it would pass every test above."""
    import inspect

    from routers import speech_profile as route

    assert '_store_speaker_embedding(uid, file_path)' in inspect.getsource(route.upload_profile)


# --- the person twin of enrolment -------------------------------------------------------------------


def test_a_person_sample_stored_without_its_embedding_is_recorded(monkeypatch):
    """Same defect, different principal: the speech sample lands, the embedding does not, and that person
    can never be matched in a future conversation."""
    from utils import speaker_identification as si

    recorded: list[dict] = []
    monkeypatch.setattr(si, 'record_fallback', lambda **kw: recorded.append(kw))

    def _down(*_a, **_k):
        raise RuntimeError('embedding model not loaded')

    monkeypatch.setattr(si, 'extract_embedding_from_bytes', _down)

    stored = asyncio.run(si._store_person_speaker_embedding('u1', 'p1', b'wav', 'c1'))

    assert stored is False
    assert [(e['component'], e['to_mode']) for e in recorded] == [('speaker', 'no_embedding')]


def test_a_person_embedding_that_lands_records_nothing(monkeypatch):
    from utils import speaker_identification as si

    recorded: list[dict] = []
    written: list[tuple] = []
    monkeypatch.setattr(si, 'record_fallback', lambda **kw: recorded.append(kw))

    class _Flat:
        def tolist(self):
            return [0.3]

    class _Embedding:
        def flatten(self):
            return _Flat()

    monkeypatch.setattr(si, 'extract_embedding_from_bytes', lambda *_a, **_k: _Embedding())
    monkeypatch.setattr(si.users_db, 'set_person_speaker_embedding', lambda *a: written.append(a), raising=False)

    assert asyncio.run(si._store_person_speaker_embedding('u1', 'p1', b'wav', 'c1')) is True
    assert written == [('u1', 'p1', [0.3])]
    assert recorded == []


def test_the_sample_collector_still_stores_the_person_embedding():
    """Static tripwire: the extraction moved into a helper, and a collector that stopped calling it would
    pass both tests above."""
    import inspect

    from utils import speaker_identification as si

    assert '_store_person_speaker_embedding(uid, person_id, wav_bytes, conversation_id)' in inspect.getsource(
        si.extract_speaker_samples
    )
