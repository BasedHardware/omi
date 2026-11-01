"""Japanese on the live Parakeet window: owner ramp, endpoint, anchors and sentence segments. No network."""

import os
import sys
from unittest.mock import Mock

import pytest

from config import parakeet_ja
from config.live_stt_registry import Target, window_ja_admits
from config.policy.batch import cohort_bucket
from utils.stt import live_router
from utils.stt import parakeet_window as window
from utils.stt import streaming as st
from utils.stt.live_rollout import window_language_supported
from utils.stt.window_anchor import RawSegment, is_terminal_sentence

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../parakeet"))

from transcribe import _transcribe_from_gpu_result  # noqa: E402

JA_URL = 'http://parakeet-ja.invalid'
V3_URL = 'http://parakeet.invalid'


def _uid_in(percent: float) -> str:
    return next(
        f'owner-{i}' for i in range(10000) if cohort_bucket(f'owner-{i}', parakeet_ja.JA_COHORT_SALT, bits=64) < percent
    )


def _uid_out(percent: float) -> str:
    return next(
        f'owner-{i}'
        for i in range(10000)
        if cohort_bucket(f'owner-{i}', parakeet_ja.JA_COHORT_SALT, bits=64) >= percent
    )


@pytest.fixture
def ja_env(monkeypatch):
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', V3_URL)
    monkeypatch.setenv(parakeet_ja.JA_URL_ENV, JA_URL)
    monkeypatch.setenv(parakeet_ja.JA_PERCENT_ENV, '25')
    return monkeypatch


@pytest.mark.parametrize('raw,expected', [('25', 25.0), ('150', 100.0), ('-3', 0.0), ('nan', 0.0), ('x', 0.0)])
def test_percent_parses_closed(monkeypatch, raw, expected):
    monkeypatch.setenv(parakeet_ja.JA_PERCENT_ENV, raw)
    assert parakeet_ja.ja_window_percent() == expected


def test_dark_by_default(monkeypatch):
    monkeypatch.delenv(parakeet_ja.JA_URL_ENV, raising=False)
    monkeypatch.delenv(parakeet_ja.JA_PERCENT_ENV, raising=False)
    assert not parakeet_ja.ja_window_configured()
    assert not window_language_supported('ja', 'ja', _uid_in(100))
    assert not Target('parakeet-window', 'parakeet', 0.02).capable('ja')


def test_url_is_the_kill_switch(ja_env):
    ja_env.setenv(parakeet_ja.JA_URL_ENV, '')
    assert not parakeet_ja.ja_window_allocated(_uid_in(25))
    assert parakeet_ja.window_endpoint('ja') == ''


def test_owner_ramp_gates_japanese_only(ja_env):
    inside, outside = _uid_in(25), _uid_out(25)
    assert window_language_supported('ja', 'ja', inside)
    assert not window_language_supported('ja', 'ja', outside)
    assert not window_language_supported('ja', 'ja', None)
    # A multi session that requested ja resolves to ja.
    assert window_language_supported('ja', 'multi', inside)
    # Other languages are unchanged by the ja ramp.
    assert window_language_supported('en', 'en', outside)
    assert not window_language_supported('ko', 'ko', inside)


def test_endpoint_by_language(ja_env):
    assert parakeet_ja.window_endpoint('ja') == JA_URL
    assert parakeet_ja.window_endpoint('en') == V3_URL
    assert parakeet_ja.window_endpoint('') == V3_URL


def test_router_capability_and_ramp(ja_env):
    target = Target('parakeet-window', 'parakeet', 0.02)
    assert target.capable('ja')
    assert window_ja_admits(target, _uid_in(25), 'ja')
    assert not window_ja_admits(target, _uid_out(25), 'ja')
    assert window_ja_admits(target, _uid_out(25), 'en')
    assert window_ja_admits(Target('soniox', 'soniox', 0.0754), _uid_out(25), 'ja')
    window_engine = {'parakeet': 'parakeet-window'}
    assert live_router._family_supports(target, 'ja', window_engine)
    assert not live_router._family_supports(target, 'ja', {'parakeet': 'parakeet'})
    ja_env.setenv(parakeet_ja.JA_PERCENT_ENV, '0')
    assert not target.capable('ja')
    assert not live_router._family_supports(target, 'ja', window_engine)


def test_full_width_sentence_ends_anchor():
    assert is_terminal_sentence(RawSegment('今日は晴れです。', 0.0, 1.0))
    assert is_terminal_sentence(RawSegment('本当ですか？', 0.0, 1.0))
    assert not is_terminal_sentence(RawSegment('今日は', 0.0, 1.0))
    assert is_terminal_sentence(RawSegment('It is.', 0.0, 1.0))


def _ja_result(chars):
    text = ''.join(c for c, _, _ in chars)
    return {
        'text': text,
        'timestamp': {
            'segment': [{'segment': text, 'start': chars[0][1], 'end': chars[-1][2]}],
            'char': [{'char': c, 'start': s, 'end': e} for c, s, e in chars],
        },
    }


def test_server_splits_japanese_window_into_sentences():
    chars = [
        ('今日', 0.0, 0.4),
        ('は', 0.4, 0.5),
        ('晴れ', 0.5, 0.9),
        ('。', 0.9, 0.9),
        ('明日', 1.6, 2.0),
        ('も', 2.0, 2.1),
    ]
    out = _transcribe_from_gpu_result(_ja_result(chars))
    assert out['text'] == '今日は晴れ。明日も'
    assert out['segments'] == [
        {'text': '今日は晴れ。', 'start': 0.0, 'end': 0.9},
        {'text': '明日も', 'start': 1.6, 'end': 2.1},
    ]


def test_server_keeps_segments_when_tokens_disagree():
    result = _ja_result([('今日', 0.0, 0.4), ('。', 0.4, 0.4), ('明日', 1.0, 1.4)])
    result['timestamp']['char'][2]['char'] = '昨日'
    out = _transcribe_from_gpu_result(result)
    assert [seg['text'] for seg in out['segments']] == ['今日。明日']


def test_server_leaves_spaced_languages_alone():
    result = {
        'text': 'Hello there. How are you?',
        'timestamp': {
            'segment': [
                {'segment': 'Hello there.', 'start': 0.0, 'end': 1.0},
                {'segment': 'How are you?', 'start': 1.2, 'end': 2.0},
            ],
            'char': [{'char': 'Hello', 'start': 0.0, 'end': 0.5}],
        },
    }
    out = _transcribe_from_gpu_result(result)
    assert [seg['text'] for seg in out['segments']] == ['Hello there.', 'How are you?']


@pytest.mark.asyncio
async def test_japanese_window_posts_to_its_own_pool(ja_env):
    # Default-pool batch pressure must not refuse the ja deployment.
    ja_env.setattr(window.batch_pressure, 'allows', lambda *_args: False)
    sock = window.connect_window(lambda _: None, 16000, language='ja')
    try:
        assert sock._url == JA_URL + '/v1/transcribe'
        assert not sock.replica_scoped
        circuit = Mock()
        ja_env.setattr(st, '_parakeet_circuit', circuit)
        sock._record_family_failure('provider_5xx')
        circuit.record_serve_failure.assert_not_called()
    finally:
        await sock.drain_and_close()


@pytest.mark.asyncio
async def test_japanese_window_without_endpoint_is_config_incomplete(ja_env):
    ja_env.setenv(parakeet_ja.JA_URL_ENV, '')
    with pytest.raises(st.ParakeetConnectionError) as error:
        window.connect_window(lambda _: None, 16000, language='ja')
    assert error.value.reason == 'config_incomplete'


@pytest.mark.asyncio
async def test_default_window_still_reports_family_failures(ja_env):
    ja_env.setattr(window.batch_pressure, 'allows', lambda *_args: True)
    sock = window.connect_window(lambda _: None, 16000, language='en')
    try:
        circuit = Mock()
        ja_env.setattr(st, '_parakeet_circuit', circuit)
        sock._record_family_failure('timeout')
        circuit.record_serve_failure.assert_called_once_with(error_class='timeout')
    finally:
        await sock.drain_and_close()
