"""Legacy unknown absorption and diagnostic bytes through the live receiver."""

import json
import os
from pathlib import Path

import pytest

from models.transcript_segment import TranscriptSegment
from routers.listen.parity_capture import ListenParityCapture
from testing.parity_pack_v0.capture import CaptureInvocation
from testing.parity_pack_v0.schema import CassetteIdentity, RequestFingerprint
from tests.unit.test_capture_window_merge_union_r5 import accept, harness, known, raw, tick


@pytest.mark.parametrize('provider', ['modulate', 'soniox', 'deepgram'])
@pytest.mark.parametrize('language', ['en', 'vi'])
async def test_simulated_mixed_boundaries_rows_and_coverage(monkeypatch, provider, language):
    texts = (
        ['We met Dr.', 'Smith arrived today.', 'We have clear audio.', 'This audio was lost.']
        if language == 'en'
        else ['Chúng tôi gặp TS.', 'Smith đã đến đây.', 'Chúng tôi nghe rõ.', 'Câu này bị mất.']
    )
    report = {}
    for enabled in (False, True):
        receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled, provider)
        receiver.host.request.language = language
        callback([raw('a', texts[0], 0.1, 1.5)])
        await tick(receiver, processor, store)
        accept(receiver, sender, 0, 6)
        for sid, text, start in zip(['b', 'c', 'd'], texts[1:], [2, 4, 6]):
            callback([raw(sid, text, start, start + 1.5)])
            rows = await tick(receiver, processor, store)
        report['on' if enabled else 'off'] = dict(
            rows=len(rows),
            known_window=known(rows),
            known_words=sum(len(s['text'].split()) for s in rows if 'audio_capture_start' in s),
            words=sum(len(s['text'].split()) for s in rows),
            texts=[s['text'] for s in rows],
            durations=[s['end'] - s['start'] for s in rows],
        )
    # Emit before assertions so an exact starting-HEAD replay records the unsafe
    # extra window/row too, without weakening the candidate's acceptance checks.
    if os.getenv('CAPTURE_R6_SIMULATION_OUTPUT'):
        Path(os.environ['CAPTURE_R6_SIMULATION_OUTPUT'] + '.' + provider + '.' + language + '.json').write_text(
            json.dumps(report, indent=2) + '\n'
        )
    assert report['off']['rows'] == 1 and report['off']['known_window'] == 0
    assert report['on'] == report['off']
    assert report['on']['words'] == report['off']['words']
    assert all(d >= 1 for d in report['on']['durations'])
    assert all(len(t.split()) >= 2 for t in report['on']['texts'])


@pytest.mark.parametrize('enabled', [False, True])
async def test_dr_smith_callback_before_send_acceptance(monkeypatch, enabled):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled)
    callback([raw('u', 'Lost sentence.', 0, 0)])
    await tick(receiver, processor, store)
    accept(receiver, sender, 0, 0.5)
    callback([raw('d', 'Dr.', 0.1, 0.4)])
    await tick(receiver, processor, store)
    callback([raw('s', 'Smith', 0.6, 0.9)])
    await tick(receiver, processor, store)
    accept(receiver, sender, 0.5, 1.5)
    callback([raw('a', 'arrived.', 1.1, 1.4)])
    rows = await tick(receiver, processor, store)
    if os.getenv('CAPTURE_R6_TITLE_OUTPUT'):
        Path(os.environ['CAPTURE_R6_TITLE_OUTPUT'] + '.' + str(enabled).lower() + '.json').write_text(
            json.dumps(
                dict(
                    rows=len(rows),
                    known_window=known(rows),
                    known_words=sum(len(s['text'].split()) for s in rows if 'audio_capture_start' in s),
                    words=sum(len(s['text'].split()) for s in rows),
                    texts=[s['text'] for s in rows],
                    durations=[s['end'] - s['start'] for s in rows],
                ),
                indent=2,
            )
            + '\n'
        )
    assert [s['text'] for s in rows] == ['Lost sentence. Dr. Smith arrived.']
    assert known(rows) == 0


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('known_first', [False, True])
@pytest.mark.parametrize(
    'language,prefix,continuation', [('en', 'We met', 'Smith arrived.'), ('vi', 'Chúng tôi gặp', 'Smith đã đến.')]
)
@pytest.mark.parametrize(
    'ending',
    [
        'Dr.',
        'Mr.',
        'e.g.',
        'U.S.',
        'J. R. R.',
        'R.',
        'AB.',
        '3.5',
        '3.5.',
        '...',
        'wait...',
        'omi.me',
        'omi.me.',
        'TS.',
        'ThS.',
        'PGS.',
    ],
)
async def test_ambiguous_provider_endings_keep_legacy_absorption(
    monkeypatch, enabled, known_first, language, prefix, continuation, ending
):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled, 'soniox')
    receiver.host.request.language = language
    if known_first:
        accept(receiver, sender, 0, 1.8)
    callback([raw('a', prefix + ' ' + ending, 0.1, 1.5)])
    await tick(receiver, processor, store)
    if not known_first:
        accept(receiver, sender, 0, 4)
    callback([raw('b', continuation, 2, 3.5)])
    rows = await tick(receiver, processor, store)
    # Existing transcript formatting attaches standalone punctuation to its word.
    expected = (prefix + ' ' + ending).replace(' .', '.') + ' ' + continuation
    assert [s['text'] for s in rows] == [expected]
    assert known(rows) == 0


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('known_first', [False, True])
@pytest.mark.parametrize(
    'left,right,left_end,right_end',
    [
        ('Lost sentence.', 'Next sentence.', 0.8, 3.5),
        ('Lost.', 'Next sentence.', 1.5, 3.5),
        ('Lost sentence.', 'Next sentence.', 1.5, 2.8),
        ('Lost sentence.', 'Next.', 1.5, 3.5),
        ('Lost sentence.', 'Next .', 1.5, 3.5),
        ('Lost sentence.', 'Next ?', 1.5, 3.5),
        ('Lost sentence.', 'Next ...', 1.5, 3.5),
        ('Lost sentence.', 'Next ！', 1.5, 3.5),
        ('Lost sentence.', 'next sentence.', 1.5, 3.5),
        ('Lost sentence.', '下一句话。', 1.5, 3.5),
    ],
)
async def test_uncertain_or_short_sides_never_split(
    monkeypatch, enabled, known_first, left, right, left_end, right_end
):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled)
    if known_first:
        accept(receiver, sender, 0, 1.8)
    callback([raw('a', left, 0.1, left_end)])
    await tick(receiver, processor, store)
    if not known_first:
        accept(receiver, sender, 0, 4)
    callback([raw('b', right, 2, right_end)])
    rows = await tick(receiver, processor, store)
    expected = (left + ' ' + right).replace(' .', '.').replace(' ?', '?')
    assert [s['text'] for s in rows] == [expected]
    assert known(rows) == 0


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('known_first', [False, True])
@pytest.mark.parametrize(
    'language,left,right', [('en', 'Lost sentence.', 'Next sentence.'), ('vi', 'Mất câu trước.', 'Câu tiếp theo.')]
)
async def test_full_sentence_punctuation_keeps_legacy_absorption(
    monkeypatch, enabled, known_first, language, left, right
):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled)
    receiver.host.request.language = language
    if known_first:
        accept(receiver, sender, 0, 1.8)
    callback([raw('a', left, 0.1, 1.5)])
    await tick(receiver, processor, store)
    if not known_first:
        accept(receiver, sender, 0, 4)
    callback([raw('b', right, 2, 3.5)])
    rows = await tick(receiver, processor, store)
    assert [s['text'] for s in rows] == [left + ' ' + right]
    assert known(rows) == 0


async def test_inbound_cassette_and_public_storage_bytes_exclude_private_proof(monkeypatch, tmp_path):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, True)
    invocation = CaptureInvocation(
        tmp_path,
        CassetteIdentity('r6', 'stt', 'modulate', 0, 0, 'parent'),
        RequestFingerprint.from_request({'sample_rate': 16000}),
        lambda: 0,
    )
    capture = ListenParityCapture(invocation, environ={'OMI_ENV_STAGE': 'dev'})
    captured = []

    def observe(segments):
        captured.extend(segments)
        capture.observe_inbound_stt(segments)

    receiver.host.capture_inbound_stt = observe
    accept(receiver, sender, 0, 4)
    callback([raw('a', 'First sentence.', 0.1, 1.5)])
    proof = receiver.collected[0]['_capture_merge_proof']
    assert '_capture_merge_proof' not in captured[0]
    cassette_bytes = invocation.persist().read_bytes()
    segment = TranscriptSegment(
        **receiver.collected[0], audio_capture_start=proof.window[0], audio_capture_end=proof.window[1]
    )
    segment.capture_merge_proof = proof
    assert segment.capture_merge_proof is proof
    for payload in (cassette_bytes, segment.model_dump_json().encode(), json.dumps(segment.model_dump()).encode()):
        assert b'_capture_merge_proof' not in payload
        assert proof.epoch.encode() not in payload
        assert b'accepted_run' not in payload
    assert json.loads(cassette_bytes)['events'][0]['payload']['segments'][0]['text'] == 'First sentence.'
    assert receiver.collected[0]['_capture_merge_proof'] is proof
    assert known(await tick(receiver, processor, store)) == 1
    # The live proof must still authorize the next observed positive-gap union.
    callback([raw('b', 'Another sentence.', 2, 3.5)])
    rows = await tick(receiver, processor, store)
    assert [s['text'] for s in rows] == ['First sentence. Another sentence.']
    assert known(rows) == 1
