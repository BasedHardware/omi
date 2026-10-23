"""Synthetic admission fixtures, shared across dictionary live and typed sync segments."""

import ast
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.refactor_modes import uid_digest
from models.transcript_segment import TranscriptSegment
from utils.conversations.relevance_content import FLAG
from utils.stt.transcript_admission import AdmissionState, admit_segments, filter_admission, hallucination_rule


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for suffix in ('', '_SERVE_PERCENT', '_SERVE_UID_SHA256S'):
        monkeypatch.delenv(FLAG + suffix, raising=False)


def raw(text):
    return dict(id='synthetic-segment', text=text, start=0, end=5, is_user=False)


@pytest.mark.parametrize(
    'text,rule',
    [
        ('Caption Credit for Synthetic Person', 'subtitle_credit'),
        ('Subtitles by Synthetic Team.', 'subtitle_credit'),
        ('Captions provided by Synthetic Team', 'subtitle_credit'),
        ('Subtitles and translation by Synthetic Team', 'subtitle_credit'),
        ('[silence]', 'silence_marker'),
        ('[BLANK_AUDIO]', 'silence_marker'),
        ('가상의 문장입니다. 가상의 문장입니다. 가상의 문장입니다.', 'repeated_sentence'),
        ('这是合成的句子。这是合成的句子。这是合成的句子。', 'repeated_sentence'),
    ],
)
def test_known_patterns_match_dictionaries_and_typed_sync(text, rule):
    assert hallucination_rule(raw(text)) == rule
    assert hallucination_rule(TranscriptSegment(**raw(text))) == rule


@pytest.mark.parametrize(
    'text',
    [
        'We discussed subtitle credits for the synthetic film.',
        'The tutorial was on YouTube.',
        'Call mom before five.',
        '가상의 문장입니다.',
        '这是合成的句子。然后这是另一句。',
        'Synthetic repetition. Synthetic repetition. Synthetic repetition.',
    ],
)
def test_language_media_mentions_and_discussions_are_not_silence(text):
    assert hallucination_rule(raw(text)) is None


def test_owner_repetition_is_protected():
    segment = raw('가상의 문장입니다. 가상의 문장입니다. 가상의 문장입니다.')
    segment['is_user'] = True
    assert hallucination_rule(segment) is None


@pytest.mark.parametrize('origin', ['live', 'sync'])
def test_shadow_counts_but_preserves_identical_input(monkeypatch, origin):
    segments = [raw('Subtitles by Synthetic Team'), raw('Ordinary synthetic speech.')]
    admitted, receipts = filter_admission('', segments, origin=origin)
    assert admitted == segments and all(a is b for a, b in zip(admitted, segments))
    assert len(receipts) == 1 and not receipts[0].dropped
    monkeypatch.setenv(FLAG, 'srve')
    assert admit_segments('', segments, origin=origin) == segments


@pytest.mark.parametrize('origin', ['live', 'sync'])
def test_serve_drops_and_audits_without_text_or_account(monkeypatch, caplog, origin):
    monkeypatch.setenv(FLAG, 'serve')
    caplog.set_level(logging.INFO)
    hallucination = raw('Caption Credit for Synthetic Person')
    speech = raw('Ordinary synthetic speech.')
    admitted, receipts = filter_admission('', [hallucination, speech], origin=origin)
    assert admitted == [speech] and receipts[0].dropped and receipts[0].version == 1
    assert 'event=transcript_admission' in caplog.text and 'dropped=true' in caplog.text
    assert receipts[0].fingerprint in caplog.text
    assert 'Synthetic Person' not in caplog.text and 'synthetic-segment' not in caplog.text
    assert receipts == filter_admission('', [hallucination], origin=origin)[1]


def test_off_does_not_filter_or_audit(monkeypatch):
    monkeypatch.setenv(FLAG, 'off')
    segments = [raw('[silence]')]
    assert filter_admission('', segments, origin='live') == (segments, [])


def test_cohort_and_rollback_share_policy(monkeypatch):
    account = 'synthetic-account'
    segments = [raw('[silence]')]
    monkeypatch.setenv(FLAG + '_SERVE_UID_SHA256S', uid_digest(account))
    assert admit_segments(account, segments, origin='sync') == []
    monkeypatch.setenv(FLAG, 'off')
    assert admit_segments(account, segments, origin='sync') == segments


@pytest.mark.parametrize('v2', [False, True])
def test_real_listen_enqueue_filters_before_either_queue(monkeypatch, v2):
    # Execute the actual small enqueue method, with its queue collaborators.
    # No live socket, Firebase, or provider import is needed for this boundary.
    from collections import deque

    path = Path(__file__).resolve().parents[2] / 'routers/listen/transcripts.py'
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'TranscriptProcessor')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'enqueue')
    code = ast.Module(body=[method], type_ignores=[])
    namespace = dict(List=list, Dict=dict, Any=object, admit_segments=admit_segments)
    exec(compile(code, str(path), 'exec'), namespace)
    host = SimpleNamespace(state=SimpleNamespace(capture_timeline_v2=v2), request=SimpleNamespace(uid=''))
    processor = SimpleNamespace(
        host=host, media_admission=AdmissionState(), segment_buffer=deque(maxlen=4), _v2_legacy_fallback=deque(maxlen=4)
    )
    monkeypatch.setenv(FLAG, 'serve')
    namespace['enqueue'](processor, [raw('[silence]'), raw('Ordinary synthetic speech.')])
    assert len(processor.segment_buffer) == 1
    assert processor.segment_buffer[0]['text'] == 'Ordinary synthetic speech.'


def test_live_and_sync_hooks_import_one_authority():
    root = Path(__file__).resolve().parents[2]
    for path in (root / 'routers/listen/transcripts.py', root / 'utils/sync/pipeline.py'):
        tree = ast.parse(path.read_text())
        assert any(isinstance(n, ast.ImportFrom) and n.module == 'utils.stt.transcript_admission' for n in tree.body)
    # Both sources invoke the same admission policy, with no second model call.
    assert admit_segments('', [], origin='live') == admit_segments('', [], origin='sync') == []


def test_repeated_foreign_sentence_across_live_batches_has_bounded_state(monkeypatch):
    monkeypatch.setenv(FLAG, 'serve')
    state = AdmissionState()
    for n in range(3):
        segment = dict(raw('这是合成的句子。'), id=f'synthetic-{n}', start=n * 5, end=(n + 1) * 5)
        admitted, receipts = filter_admission('', [segment], origin='live', state=state)
        assert bool(admitted) == (n < 2)
    assert state.count == 3 and state.signature is not None
    assert '合成' not in state.signature
    assert receipts[0].rule == 'repeated_sentence_run'
    later = dict(raw('这是合成的句子。'), id='synthetic-later', start=300, end=305)
    assert admit_segments('', [later], origin='live', state=state) == [later]
    assert state.count == 1


def test_repetition_does_not_cross_distinct_speech_or_time_reset(monkeypatch):
    monkeypatch.setenv(FLAG, 'serve')
    state = AdmissionState()
    for n in range(2):
        segment = dict(raw('这是合成的句子。'), id=f'synthetic-{n}', start=n * 5, end=(n + 1) * 5)
        assert admit_segments('', [segment], origin='live', state=state)
    ordinary = raw('Different synthetic speech.')
    assert admit_segments('', [ordinary], origin='live', state=state)
    assert state.count == 0
    assert admit_segments('', [dict(raw('这是合成的句子。'), start=0, end=5)], origin='live', state=state)
    assert state.count == 1
