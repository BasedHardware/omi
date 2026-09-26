"""Offline pre-recorded STT stub: gating, determinism, and word-shape contract.

The stub exists so PROVIDER_MODE=offline harness sessions can complete
transcript -> conversation end-to-end (observed on hardware: uploaded phone
captures dead-ended at PrerecordedSTTConfigurationError because offline
stages strip HOSTED_PARAKEET_API_URL). These tests pin the double gate — it
must never activate in a production-family process — and the word shape the
sync pipeline's postprocessing consumes.
"""

from utils.stt.pre_recorded import _words_cleaning, get_prerecorded_provider
from utils.stt.prerecorded_stub import PrerecordedStubProvider, prerecorded_stub_enabled


def test_stub_inert_without_flag(monkeypatch):
    monkeypatch.setenv('PROVIDER_MODE', 'offline')
    monkeypatch.delenv('OMI_STT_STUB', raising=False)
    assert not prerecorded_stub_enabled()
    assert not isinstance(get_prerecorded_provider('en'), PrerecordedStubProvider)


def test_stub_requires_offline_stage(monkeypatch):
    monkeypatch.setenv('OMI_STT_STUB', '1')
    monkeypatch.setenv('PROVIDER_MODE', 'real')
    assert not prerecorded_stub_enabled()
    monkeypatch.delenv('PROVIDER_MODE', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'production')
    assert not prerecorded_stub_enabled()


def test_stub_active_only_with_both_gates(monkeypatch):
    monkeypatch.setenv('OMI_STT_STUB', '1')
    monkeypatch.setenv('PROVIDER_MODE', 'offline')
    assert prerecorded_stub_enabled()
    assert isinstance(get_prerecorded_provider('en'), PrerecordedStubProvider)


def test_stub_words_shape_matches_pipeline_contract():
    words = PrerecordedStubProvider().transcribe_bytes(b'anything')
    assert words, 'stub must return a non-empty transcript'
    for w in words:
        assert set(w) == {'timestamp', 'speaker', 'text'}
        start, end = w['timestamp']
        assert isinstance(start, float) and isinstance(end, float)
        assert end >= start
    cleaned = _words_cleaning([dict(w) for w in words])
    assert cleaned and all(c['text'] for c in cleaned)


def test_stub_transcript_is_self_declaring_and_deterministic():
    first = PrerecordedStubProvider().transcribe_bytes(b'')
    second = PrerecordedStubProvider().transcribe_url('http://127.0.0.1/x.wav')
    assert first == second
    assert '[offline' in ' '.join(w['text'] for w in first)


def test_stub_return_language_variant():
    result = PrerecordedStubProvider().transcribe_bytes(b'', return_language=True)
    words, language = result
    assert language == 'en'
    assert words
