"""Soniox language hints must stay inside the provider's documented vocabulary.

Production evidence (backend-listen, GCP 2026-09-02/03, Loop S sensor):
``ERROR:utils.stt.soniox:Soniox streaming error: 400 invalid_request Invalid
language hint.`` fired in essentially every 30-minute window for 6+ hours
(~16/24h) at a steady one-to-two-per-window cadence — a small set of sessions
dying on **every reconnect**, not a fleet-wide outage.

Root cause: selection is honest that "Soniox identifies the language itself, so
every requested language is serviceable", but the client then sent
``language_hints: [<base code>]`` for every non-``multi`` language,
unvalidated. The provider validates that one field against its documented
vocabulary and answers 400 **after the WebSocket upgrade already succeeded**,
so the death surfaces as an in-stream error frame. A live example: ``mt``
(Maltese) is an accepted app language (the batch Parakeet model lists it) but
is outside both Modulate's auto-detect table and Soniox's hint vocabulary, so
for that user Modulate is skipped, Soniox is selected, the hint kills the
socket at the config frame, and the soniox branch's own fallbacks are both
None — no provider left, on every reconnect. Compounding the invisibility:

- the raw-string ``language != 'multi'`` guard compared the INPUT while sending
  the NORMALIZED code, so ``'Multi'`` was sent as a literal ``multi`` hint;
- ``soniox_death_reason`` mapped every 400 to ``soniox_idle_timeout`` — a
  config-shaped death wearing a usage-shaped costume, logged at WARNING and
  counted as VAD starvation in terminal-failure metrics.

Failure-Class: FC-provider-vocabulary-assumed-unbounded — the client assumed a
provider accepts any ISO code in a request field the provider validates against
a closed set. The fix keeps selection's any-language promise (identification
serves every supported language with no hint), drops the hint for
out-of-vocabulary codes with a ``record_fallback`` mode-change event, and types
the provider's own rejection frame so it can never masquerade as an idle
timeout again.

These tests drive the REAL ``process_audio_soniox`` config builder (patching
only the ``websockets.connect`` transport), the REAL ``SafeSonioxSocket``
receive loop over synthetic provider frames, and the REAL terminal-vocabulary
seams from ``utils.stt.live_failure``.
"""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    SONIOX_SUPPORTED_LANGUAGE_HINTS,
    normalized_stt_language,
    soniox_accepts_language_hint,
)

# Imported at module scope on purpose: the fast-unit duration guard measures
# per-test CPU in the call phase only (see tests/conftest.py), and this module's
# first import costs ~3s CPU. Lazy, per-test imports would land that charge on
# whichever test touches ``streaming`` first and fail the 1.0s budget.
from utils.stt import live_failure, streaming as stt_streaming
from utils.stt.live_failure import live_stt_terminal_reason, note_typed_provider_death
from utils.stt.streaming import STTService, get_stt_service_for_language
from utils.stt.soniox import (
    SONIOX_DEATH_IDLE_TIMEOUT,
    SONIOX_DEATH_INVALID_HINT,
    SafeSonioxSocket,
    process_audio_soniox,
    soniox_death_reason,
)

API_KEY_ENV = {'SONIOX_API_KEY': 'test-key'}


def _connect_transport():
    """Patch the streaming transport, returning the captured provider socket."""
    ws = AsyncMock()
    connect = patch.object(stt_streaming.websockets, 'connect', new=AsyncMock(return_value=ws))
    socket_ctor = patch.object(stt_streaming, 'SafeSonioxSocket', MagicMock())
    return ws, connect, socket_ctor


async def _sent_config(language: str) -> dict:
    """Run the real config builder for a language; return the frame sent to the provider."""
    ws, connect, socket_ctor = _connect_transport()
    with connect, socket_ctor, patch.dict('os.environ', API_KEY_ENV):
        await process_audio_soniox(lambda _s: None, 16000, language)
    return json.loads(ws.send.await_args.args[0])


# ---------------------------------------------------------------------------
# The provider's rejection frame must type as config-shaped, not usage-shaped.
# ---------------------------------------------------------------------------


def test_the_invalid_hint_frame_types_as_its_own_death_reason():
    assert soniox_death_reason(400, 'invalid_request', 'Invalid language hint.') == SONIOX_DEATH_INVALID_HINT


def test_the_invalid_hint_match_is_case_insensitive_on_the_provider_text():
    assert soniox_death_reason(400, 'invalid_request', 'INVALID LANGUAGE HINT.') == SONIOX_DEATH_INVALID_HINT


def test_a_no_audio_400_still_types_as_the_idle_timeout():
    """The VAD-starvation shape keeps its existing type and WARNING severity."""
    assert soniox_death_reason(400, 'invalid_request', 'No audio received') == SONIOX_DEATH_IDLE_TIMEOUT


def test_a_400_without_a_message_degrades_to_the_idle_timeout():
    """A bare 400 frame carries no hint evidence; the pre-existing mapping stands."""
    assert soniox_death_reason(400, 'invalid_request', None) == SONIOX_DEATH_IDLE_TIMEOUT


def test_the_invalid_hint_typed_reason_is_bounded_by_the_terminal_vocabulary():
    assert live_stt_terminal_reason(SimpleNamespace(typed_death_reason=SONIOX_DEATH_INVALID_HINT), 'send_failed') == (
        SONIOX_DEATH_INVALID_HINT
    )


def test_the_invalid_hint_death_does_not_bench_the_healthy_provider():
    """The provider is fine; our config was wrong. The circuit must stay closed."""
    calls = []

    def fake_opener(provider, *, reason):
        calls.append((provider, reason))
        return True

    with patch.object(stt_streaming, 'open_provider_selection_circuit', side_effect=fake_opener):
        assert note_typed_provider_death(SimpleNamespace(typed_death_reason=SONIOX_DEATH_INVALID_HINT), 'soniox') is (
            False
        )
    assert calls == []


# ---------------------------------------------------------------------------
# Severity: a config rejection is our side's fault and must stay an ERROR.
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    def __init__(self, frames):
        self._frames = frames

    async def send(self, _data):
        pass

    async def close(self):
        pass

    def __aiter__(self):
        async def gen():
            for frame in self._frames:
                yield json.dumps(frame)

        return gen()


def _drive_socket(frames):
    def run():
        async def main():
            sock = SafeSonioxSocket(_FakeWebSocket(frames), lambda _s: None, asyncio.get_running_loop())
            await asyncio.sleep(0.05)
            return sock

        return asyncio.run(main())

    return run()


def test_an_invalid_hint_frame_logs_at_error_not_warning(caplog):
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = _drive_socket(
            [{'error_code': 400, 'error_type': 'invalid_request', 'error_message': 'Invalid language hint.'}]
        )
    assert sock.typed_death_reason == SONIOX_DEATH_INVALID_HINT
    assert [r.levelname for r in caplog.records if 'Soniox' in r.message] == ['ERROR']


def test_the_raw_invalid_hint_frame_stays_on_the_death_latch():
    sock = _drive_socket(
        [{'error_code': 400, 'error_type': 'invalid_request', 'error_message': 'Invalid language hint.'}]
    )
    assert 'Invalid language hint' in (sock.death_reason or '')
    assert sock.typed_death_reason == SONIOX_DEATH_INVALID_HINT


# ---------------------------------------------------------------------------
# The config frame: no rejected entry may ever be sent.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_out_of_vocabulary_language_sends_no_hint():
    """The exact prod shape: a language the app accepts but the provider does not."""
    config = await _sent_config('mt')
    assert 'language_hints' not in config
    assert config['enable_language_identification'] is True


@pytest.mark.asyncio
async def test_a_supported_language_still_sends_its_hint():
    config = await _sent_config('ja')
    assert config['language_hints'] == ['ja']


@pytest.mark.asyncio
async def test_a_region_tagged_locale_sends_its_normalized_base_code():
    config = await _sent_config('pt-BR')
    assert config['language_hints'] == ['pt']


@pytest.mark.asyncio
async def test_a_capitalized_sentinel_is_not_sent_as_a_hint():
    """The old raw-string guard compared the input; 'Multi' leaked a literal hint."""
    config = await _sent_config('Multi')
    assert 'language_hints' not in config


@pytest.mark.asyncio
async def test_the_auto_detect_sentinel_still_sends_no_hint():
    config = await _sent_config('multi')
    assert 'language_hints' not in config


@pytest.mark.asyncio
async def test_an_unknown_language_sends_no_hint():
    config = await _sent_config('xx')
    assert 'language_hints' not in config


@pytest.mark.asyncio
async def test_dropping_a_hint_emits_the_fallback_mode_change_event(monkeypatch):
    """Silent UX healing is allowed; silent ops is not (fallback-telemetry contract)."""
    events = []
    monkeypatch.setattr('utils.stt.soniox.record_fallback', lambda **kw: events.append(kw))
    await _sent_config('mt')
    assert events == [
        {
            'component': 'stt_selection',
            'from_mode': 'soniox_language_hint',
            'to_mode': 'soniox_language_identification',
            'reason': 'capability_mismatch',
            'outcome': 'degraded',
        }
    ]


@pytest.mark.asyncio
async def test_a_supported_language_emits_no_fallback_event(monkeypatch):
    events = []
    monkeypatch.setattr('utils.stt.soniox.record_fallback', lambda **kw: events.append(kw))
    await _sent_config('ja')
    assert events == []


# ---------------------------------------------------------------------------
# The vocabulary itself: policy-owned, normalized, and honest about coverage.
# ---------------------------------------------------------------------------


def test_the_hint_vocabulary_is_within_the_policy_module():
    """The table lives in the one module that owns provider capability."""
    from config import stt_provider_policy

    assert stt_provider_policy.SONIOX_SUPPORTED_LANGUAGE_HINTS is SONIOX_SUPPORTED_LANGUAGE_HINTS


def test_the_hint_gate_normalizes_before_deciding():
    assert soniox_accepts_language_hint('ja-JP') is True
    assert soniox_accepts_language_hint('EN_us') is True
    assert soniox_accepts_language_hint('mt') is False
    assert soniox_accepts_language_hint(None) is False
    assert soniox_accepts_language_hint('') is False
    assert soniox_accepts_language_hint('multi') is False


def test_every_documented_hint_code_is_a_real_base_code():
    for code in SONIOX_SUPPORTED_LANGUAGE_HINTS:
        assert normalized_stt_language(code) == code
        assert len(code) == 2


def test_the_documented_vocabulary_covers_the_prod_evidence():
    """The 2026-09-02/03 incident shape: a language the APP accepts (so selection
    stays honest about serving it) but the provider's hint vocabulary does not."""
    from utils.user_language import ACCEPTED_BASE_LANGUAGES

    assert 'mt' in ACCEPTED_BASE_LANGUAGES
    assert soniox_accepts_language_hint('en') is True
    assert soniox_accepts_language_hint('mt') is False


@pytest.mark.asyncio
async def test_a_terminal_funnel_reports_the_config_rejection_with_its_phase(monkeypatch):
    """Drive the real terminate path: the typed reason survives and the phase
    says the session died at setup, not mid-stream."""
    websocket = AsyncMock()
    session = SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1001, live_transcription_attempt=None)
    recorded = []
    monkeypatch.setattr(live_failure, 'record_live_stt_failure', lambda **labels: recorded.append(labels))
    from utils.stt.live_failure import terminate_live_stt_session

    sent = await terminate_live_stt_session(
        websocket,
        session,
        failure=live_failure.live_stt_upstream_failure('soniox'),
        reason=SONIOX_DEATH_INVALID_HINT,
        platform='ios',
    )
    assert sent is True
    assert session.stt_terminal_failure is True
    event = websocket.send_json.await_args.args[0]
    assert event['reason'] == 'soniox_invalid_hint'
    assert recorded[0]['phase'] == 'initialization'


# ---------------------------------------------------------------------------
# The product promise survives: selection still serves every language.
# ---------------------------------------------------------------------------


def test_selection_still_promises_soniox_for_an_out_of_vocabulary_language():
    """The fix must not narrow selection: identification serves 'mt' fine —
    only the hint is dropped. Selection runs through its real seam here."""
    with patch.dict(
        'os.environ', {'STT_SERVICE_MODELS': 'modulate-velma-2,soniox', 'SONIOX_API_KEY': 'k'}
    ), patch.object(stt_streaming, 'stt_service_models', ['modulate-velma-2', 'soniox']):
        service, language, _model = get_stt_service_for_language('mt')
    assert service == STTService.soniox
    assert language == 'mt'


@pytest.mark.parametrize('code', sorted(MODULATE_SUPPORTED_LANGUAGES - {'multi'}))
def test_every_modulate_language_is_also_hintable_at_soniox(code):
    """Cross-provider coherence: a language Modulate's auto-detect serves must
    fail over to Soniox WITHOUT a mode change — its hint must be accepted too,
    or every failover from the primary would take the degraded no-hint path."""
    assert soniox_accepts_language_hint(code) is True


def test_the_mt_session_has_no_configured_fallback_provider():
    """Why the incident sessions died with no rescue: at the receiver's own
    gates, 'mt' configures neither the Modulate nor the Deepgram fallback."""
    assert stt_streaming.modulate_is_configured_fallback('mt') is False
    assert stt_streaming.deepgram_fallback_model('mt') is None


# ---------------------------------------------------------------------------
# The config frame itself: nothing else about it may drift.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_config_frame_shape_is_unchanged_for_supported_languages():
    config = await _sent_config('en')
    assert config['api_key'] == 'test-key'
    assert config['model']
    assert config['audio_format'] == 'pcm_s16le'
    assert config['sample_rate'] == 16000
    assert config['num_channels'] == 1
    assert config['enable_speaker_diarization'] is True
    assert config['enable_language_identification'] is True
    assert config['language_hints'] == ['en']


@pytest.mark.asyncio
async def test_the_config_frame_shape_is_unchanged_when_the_hint_is_dropped():
    """Dropping the hint must not disturb any other setting: identification is
    precisely what keeps the session alive for the unsupported language."""
    config = await _sent_config('mt')
    assert config['enable_language_identification'] is True
    assert config['enable_speaker_diarization'] is True
    assert config['sample_rate'] == 16000
    assert 'language_hints' not in config


@pytest.mark.asyncio
async def test_uppercase_input_sends_the_normalized_hint():
    config = await _sent_config('JA')
    assert config['language_hints'] == ['ja']


@pytest.mark.asyncio
async def test_dropping_a_hint_logs_the_ops_warning(caplog):
    """The metric is the contract, but the log line is what an on-call greps."""
    import logging as _logging

    with caplog.at_level(_logging.WARNING, logger='utils.stt.soniox'):
        await _sent_config('mt')
    drops = [r for r in caplog.records if 'Soniox language hint dropped' in r.message]
    assert drops and drops[0].levelname == 'WARNING'


def test_the_fallback_event_labels_are_all_inside_the_telemetry_contract():
    """A label outside the closed enums would be silently bucketed to 'other';
    pin each label against the contract's own allowlists."""
    from utils.observability.fallback import (
        ALLOWED_COMPONENTS,
        ALLOWED_OUTCOMES,
        ALLOWED_REASONS,
    )

    assert 'stt_selection' in ALLOWED_COMPONENTS
    assert 'capability_mismatch' in ALLOWED_REASONS
    assert 'degraded' in ALLOWED_OUTCOMES


def test_the_vocabulary_size_pins_the_documented_table():
    """Ratchet against accidental truncation: the documented table has 60 codes
    ('en' in, our sentinel and the incident language out)."""
    assert len(SONIOX_SUPPORTED_LANGUAGE_HINTS) == 60
    assert 'en' in SONIOX_SUPPORTED_LANGUAGE_HINTS
    assert 'multi' not in SONIOX_SUPPORTED_LANGUAGE_HINTS
    assert 'mt' not in SONIOX_SUPPORTED_LANGUAGE_HINTS
