"""A denied vendor egress must not be able to route conversation AUDIO to a vendor (BACKLOG L40).

ADR-0057 deliberately left STT out of its three-surface perimeter, and the reason still holds: our
configuration already selects the local provider (`STT_PRERECORDED_MODEL=parakeet`,
`STT_SERVICE_MODELS=parakeet`). But configuration picks the **happy path**. The selectors are ordered
preference lists with fallbacks underneath, and those fallbacks end at a vendor:

  * pre-recorded — a language outside Parakeet's set selects Modulate Velma-2 (a hardcoded vendor URL,
    `utils/stt/pre_recorded.py:583`), and a language no capability map claims at all reaches the
    unconditional `return MODULATE, 'multi'` tail;
  * streaming — the policy-owned default order is `dg-nova-3, modulate-velma-2, parakeet`, i.e. cloud
    first, so a deployment that does not declare `STT_SERVICE_MODELS` gets Deepgram cloud.

What leaves on those paths is not metadata: it is the conversation audio (a public URL to it, or the
bytes). That makes this the case ADR-0057 wrote its criterion for — **raise, do not degrade**: a missing
transcript is an empty artefact the user sees, so failing closed must be loud.

The guard goes in `provider_is_enabled`, which the policy module already calls "the single source of truth
for provider enablement" and where it says "future availability changes start here". Every selector and
every fallback predicate — pre-recorded, streaming, PTT — asks that one question, so gating it there is one
guard surface instead of an exception at each call site.

The distinction that matters: `deepgram_self_hosted` is NOT a vendor. It is the operator's own endpoint
(ADR-0035) and the code already refuses to let it point at api.deepgram.com
(`_require_self_hosted_deepgram_endpoint`). Denying vendor egress must leave it alone.
"""

from __future__ import annotations

import pytest

from config.stt_provider_policy import (
    DEEPGRAM_CLOUD_PROVIDER,
    DEEPGRAM_SELF_HOSTED_PROVIDER,
    MODULATE_PROVIDER,
    PARAKEET_PROVIDER,
    STTServingSurface,
    model_is_enabled,
    provider_is_enabled,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv('OMI_VENDOR_EGRESS', raising=False)


# --- the policy seam ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    'provider,surface',
    [
        (MODULATE_PROVIDER, STTServingSurface.PRERECORDED),
        (MODULATE_PROVIDER, STTServingSurface.STREAMING),
        (MODULATE_PROVIDER, STTServingSurface.PTT),
        (DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.STREAMING),
    ],
)
def test_a_vendor_provider_is_not_enabled_when_egress_is_denied(monkeypatch, provider, surface):
    assert provider_is_enabled(provider, surface) is True, 'precondition: enabled by the serving table'
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    assert provider_is_enabled(provider, surface) is False


@pytest.mark.parametrize(
    'provider,surface',
    [
        (PARAKEET_PROVIDER, STTServingSurface.PRERECORDED),
        (PARAKEET_PROVIDER, STTServingSurface.STREAMING),
        (PARAKEET_PROVIDER, STTServingSurface.PTT),
        (DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.STREAMING),
    ],
)
def test_the_operators_own_providers_are_untouched(monkeypatch, provider, surface):
    """Parakeet is ours, and self-hosted Deepgram is the operator's endpoint, not a vendor (ADR-0035)."""
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    assert provider_is_enabled(provider, surface) is True


def test_allow_leaves_the_serving_table_exactly_as_upstream_ships_it(monkeypatch):
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')
    for surface in STTServingSurface:
        assert provider_is_enabled(MODULATE_PROVIDER, surface) is True
    assert provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.STREAMING) is True


def test_a_deepgram_token_stays_admissible_because_selection_rechecks_the_runtime(monkeypatch):
    """`model_is_enabled` ORs over both Deepgram deployments on purpose: a `dg-*` token names the model,
    not who serves it. It must stay True under deny — a self-hosted runtime is entitled to it — and it is
    `deepgram_provider_for_runtime` at selection time that keeps the cloud one out."""
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    assert model_is_enabled('dg-nova-3', STTServingSurface.STREAMING) is True
    assert model_is_enabled('modulate-velma-2', STTServingSurface.STREAMING) is False


# --- pre-recorded: the product path -------------------------------------------------------------


def test_prerecorded_language_outside_parakeet_no_longer_selects_the_vendor(monkeypatch):
    """`ja` is outside Parakeet's set and inside Velma-2's, so today it selects Modulate."""
    from utils.stt import pre_recorded
    from utils.stt.outcomes import TranscriptionFailure

    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet')

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')
    service, language, model = pre_recorded.get_prerecorded_service('ja')
    assert model == 'velma-2', 'precondition: the cloud fallback is what happens today'

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    with pytest.raises(TranscriptionFailure) as raised:
        pre_recorded.get_prerecorded_service('ja')
    assert raised.value.retryable is False, 'no retry resolves a policy decision'


def test_prerecorded_unknown_language_no_longer_reaches_the_multi_tail(monkeypatch):
    """A language no capability map claims fell through to `return MODULATE, 'multi'` unconditionally —
    the widest of the two cloud paths, because it does not even need the language to be supported."""
    from utils.stt import pre_recorded
    from utils.stt.outcomes import TranscriptionFailure

    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet')

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')
    assert pre_recorded.get_prerecorded_service('sw') == (
        pre_recorded.PrerecordedSTTService.MODULATE,
        'multi',
        'velma-2',
    )

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    with pytest.raises(TranscriptionFailure):
        pre_recorded.get_prerecorded_service('sw')


def test_prerecorded_english_still_works_on_the_local_provider(monkeypatch):
    """The posture must not break the language we actually serve — otherwise it is not a gate, it is an
    outage. This is the legacy-principal case AGENTS.md asks every fail-closed gate to carry."""
    from utils.stt import pre_recorded

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet')

    assert pre_recorded.get_prerecorded_service('en') == (
        pre_recorded.PrerecordedSTTService.PARAKEET,
        'en',
        'parakeet',
    )


# --- streaming: the product path ----------------------------------------------------------------


def test_streaming_default_order_no_longer_starts_at_deepgram_cloud(monkeypatch):
    """With `STT_SERVICE_MODELS` undeclared the policy default is `dg-nova-3, modulate-velma-2, parakeet`.
    Under deny nothing serves `ja` (Parakeet streaming is English-only), and that must be reported as
    exhausted rather than served by a vendor."""
    from utils.stt import streaming

    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3', 'modulate-velma-2', 'parakeet'])
    monkeypatch.setattr(streaming, '_deepgram_is_available', lambda: True)
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', False)

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')
    service, _language, _model = streaming.get_stt_service_for_language('ja', multi_lang_enabled=False)
    assert service is not None, 'precondition: a vendor serves this today'

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    events: list[dict] = []
    monkeypatch.setattr(streaming, 'record_fallback', lambda **kw: events.append(kw))

    assert streaming.get_stt_service_for_language('ja', multi_lang_enabled=False) == (None, None, None)

    # The reason must name the real cause. `capability_mismatch` was the only value this branch could
    # report, and it sends whoever reads the counter looking for a language-coverage bug.
    assert events[-1]['to_mode'] == 'unavailable'
    assert events[-1]['reason'] == 'policy'
    assert events[-1]['outcome'] == 'exhausted'


def test_streaming_self_hosted_deepgram_still_serves_under_deny(monkeypatch):
    """The runtime that configured its OWN Deepgram endpoint keeps it: that is ADR-0035, not egress."""
    from utils.stt import streaming

    monkeypatch.setattr(streaming, 'stt_service_models', ['dg-nova-3'])
    monkeypatch.setattr(streaming, '_deepgram_is_available', lambda: True)
    monkeypatch.setattr(streaming, 'is_dg_self_hosted', True)
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')

    service, _language, model = streaming.get_stt_service_for_language('ja', multi_lang_enabled=False)
    assert service is not None and model == 'nova-3'


def test_streaming_fallback_predicates_close_too(monkeypatch):
    """`modulate_is_configured_fallback` takes over a session whose primary failed — a second door to the
    same vendor, and one reached mid-session rather than at selection."""
    from utils.stt import streaming

    monkeypatch.setattr(streaming, 'stt_service_models', ['parakeet', 'modulate-velma-2'])

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')
    assert streaming.modulate_is_configured_fallback('ja') is True

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    assert streaming.modulate_is_configured_fallback('ja') is False


def test_prerecorded_refusal_says_why(monkeypatch, caplog):
    """An operator sees "no transcript". The log is the only place that can tell them it was a decision."""
    import logging

    from utils.stt import pre_recorded
    from utils.stt.outcomes import TranscriptionFailure

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet')

    with caplog.at_level(logging.ERROR, logger='utils.stt.pre_recorded'):
        with pytest.raises(TranscriptionFailure):
            pre_recorded.get_prerecorded_service('ja')

    assert 'OMI_VENDOR_EGRESS=deny' in caplog.text
    assert 'language=ja' in caplog.text
