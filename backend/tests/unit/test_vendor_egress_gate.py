"""OMI_VENDOR_EGRESS gates the three surfaces that have no local alternative (ADR-0057).

The perimeter was narrowed from twelve to three by measurement: where configuration already selects the
local provider (the gateway pins 37/37 features at our endpoint, STT selects parakeet, TTS is already 503
without a key) a gate adds nothing, and the real problem there is fallbacks — separate defects (L40/L41).
What is left are the surfaces that either send data to a vendor or do not exist:

  prosodia Hume     — sends a URL to the conversation audio, and stores predictions on the conversation
  tracing LangSmith — sends the prompts themselves plus uid/app_id
  release check     — tells api.github.com this deployment exists

All three DEGRADE at deny, with a recorded fallback: they are enrichments, and Hume already has a clean
skip path, so raising would fail a whole conversation's postprocessing for an enrichment.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import vendor_egress


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv('OMI_VENDOR_EGRESS', raising=False)


# --- the policy ---------------------------------------------------------------------------------


def test_unset_allows_so_upstream_behaviour_is_unchanged():
    assert vendor_egress.vendor_egress_allowed() is True


@pytest.mark.parametrize('value', ['deny', 'DENY', ' deny '])
def test_deny_in_any_casing(monkeypatch, value):
    monkeypatch.setenv('OMI_VENDOR_EGRESS', value)
    assert vendor_egress.vendor_egress_allowed() is False


def test_an_unknown_value_fails_closed_and_says_so(monkeypatch):
    """A typo in a sovereignty gate must not open it. Fails closed AND records, so the misconfiguration
    is visible rather than mistaken for a deliberate deny."""
    events: list[dict] = []
    monkeypatch.setattr(vendor_egress, 'record_fallback', lambda **kw: events.append(kw))
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'yes-please')

    assert vendor_egress.vendor_egress_allowed() is False
    assert len(events) == 1 and events[0]['reason'] == 'config_incomplete'
    # The bad value must not become a metric label: from_mode is a Prometheus label, so a free-form env var
    # would give every operator's typo its own time series. It belongs in the log.
    assert events[0]['from_mode'] == 'invalid_value'


def test_denied_records_the_surface(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(vendor_egress, 'record_fallback', lambda **kw: events.append(kw))
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')

    assert vendor_egress.vendor_egress_denied('hume_prosody') is True
    assert events[0]['component'] == 'vendor_egress'
    assert events[0]['from_mode'] == 'hume_prosody'
    assert events[0]['reason'] == 'policy'
    assert events[0]['outcome'] == 'degraded'


def test_allowed_records_nothing(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(vendor_egress, 'record_fallback', lambda **kw: events.append(kw))
    assert vendor_egress.vendor_egress_denied('hume_prosody') is False
    assert events == []


# --- surface 1: Hume ----------------------------------------------------------------------------


def test_hume_makes_no_request_when_denied(monkeypatch):
    """Today the POST goes out even with no key at all:
    `'X-Hume-Api-Key': self.api_key if self.api_key is not None else ''`."""
    import httpx

    from utils.other import hume as hume_mod

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    calls: list[str] = []
    monkeypatch.setattr(httpx, 'post', lambda url, **kw: calls.append(url))

    client = hume_mod.HumeClient(api_key='k', callback_url='http://backend/cb')
    ok = client.request_user_expression_mersurement(['http://store/audio.wav'])

    assert calls == [], 'the conversation audio URL left the process'
    assert 'error' in ok, "the caller's existing skip path keys off `\"error\" in ok`"


def test_hume_still_requests_when_allowed(monkeypatch):
    import httpx

    from utils.other import hume as hume_mod

    calls: list[str] = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {'job_id': 'j1'}

    monkeypatch.setattr(httpx, 'post', lambda url, **kw: calls.append(url) or _Resp())
    hume_mod.HumeClient(api_key='k', callback_url='http://backend/cb').request_user_expression_mersurement(
        ['http://store/audio.wav']
    )
    assert calls == ['https://api.hume.ai/v0/batch/jobs']


# --- surface 2: LangSmith -----------------------------------------------------------------------


def test_langsmith_tracer_is_off_when_denied(monkeypatch):
    """One assertion per surface here; the detail (prompt hub, key present/absent, and the regression
    that the STAGE no longer decides) lives in tests/unit/test_langsmith_vendor_egress.py."""
    from utils.observability import langsmith as ls

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    monkeypatch.setenv('LANGSMITH_API_KEY', 'lsv2_pt_real_looking_key')
    assert ls.get_chat_tracer_callbacks() == []


# --- surface 3: GitHub release check ------------------------------------------------------------


async def _noop_cache_miss(*_a, **_kw):
    return None


def test_github_releases_returns_empty_when_denied(monkeypatch):
    import asyncio

    from utils import github_releases as gr

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')

    def _boom(*_a, **_kw):
        raise AssertionError('a request went to api.github.com')

    monkeypatch.setattr(gr, 'get_web_fetch_client', _boom)
    monkeypatch.setattr(gr, 'run_blocking', _noop_cache_miss)
    assert asyncio.run(gr.get_omi_github_releases('github_releases_omi')) == []


def test_github_releases_still_reaches_out_when_allowed(monkeypatch):
    """Proves the tripwire above measures the gate and not the absence of a network."""
    import asyncio

    import httpx

    from utils import github_releases as gr

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')
    monkeypatch.setattr(gr, 'run_blocking', _noop_cache_miss)
    reached: list[str] = []

    def _tripwire(*_a, **_kw):
        reached.append('client')
        raise httpx.RequestError('no network in the test sandbox')

    monkeypatch.setattr(gr, 'get_web_fetch_client', _tripwire)

    assert asyncio.run(gr.get_omi_github_releases('github_releases_omi')) == []
    assert reached == ['client']


def test_github_docs_content_returns_none_when_denied(monkeypatch):
    from utils import app_integrations as ai

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    monkeypatch.setattr(ai, 'get_generic_cache', lambda _k: None)
    assert ai.get_github_docs_content() is None


def test_hume_denied_leaves_no_orphan_task_row(monkeypatch):
    """The caller writes a PROCESSING task row BEFORE calling, and its error path returns without ever
    moving it on. Gating only the client would leave one stuck row per conversation, forever."""
    from utils.conversations import process_conversation as pc

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    created: list[dict] = []
    monkeypatch.setattr(pc.tasks_db, 'create', lambda doc: created.append(doc))
    monkeypatch.setattr(pc, 'get_hume', lambda: (_ for _ in ()).throw(AssertionError('reached the client')))

    conversation = SimpleNamespace(id='c1')
    pc.process_user_emotion('u1', 'en', conversation, ['http://store/audio.wav'])

    assert created == []


def test_github_docs_still_reaches_out_when_allowed(monkeypatch):
    """Same tripwire discipline: a `None` return proves nothing on its own in a sandbox with no network."""
    import httpx

    from utils import app_integrations as ai

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')
    monkeypatch.setattr(ai, 'get_generic_cache', lambda _k: None)
    monkeypatch.setattr(ai, 'set_generic_cache', lambda *_a, **_kw: None)
    reached: list[str] = []

    def _tripwire(url, **_kw):
        reached.append(url)
        raise httpx.RequestError('no network in the test sandbox')

    monkeypatch.setattr(httpx, 'get', _tripwire)

    with pytest.raises(httpx.RequestError):
        ai.get_github_docs_content()
    assert reached == ['https://api.github.com/repos/BasedHardware/omi/contents/docs/doc']
