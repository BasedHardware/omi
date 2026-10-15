"""Committed coverage proves only recognized word/token intervals.

Pure mapping tests for utils/stt/committed_words.py plus the real Deepgram
and Soniox adapter callbacks: segment spans are never evidence, gaps are
never filled, and malformed word metadata abstains the whole segment.
"""

import copy
from types import SimpleNamespace

import pytest

from tests.unit.test_soniox_token_boundaries import drive, token
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator, SendMap
from utils.stt import streaming
from utils.stt.committed_words import (
    CAPTURE_WORD_RANGES_KEY,
    PROVIDER_WORD_RANGES_KEY,
    PROVIDER_WORDS_ABSTAIN_KEY,
    project_provider_words,
    remember_provider_word,
)

RATE = 16000


def _flags_on(monkeypatch):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'true')


def _flags_off(monkeypatch):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'false')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'false')


def _flags_partial(monkeypatch, dark_write, committed):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', dark_write)
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', committed)


def _map(*spans):
    send_map = SendMap(RATE)
    for provider_first, capture_first, length in spans:
        send_map.add_accepted(provider_first, capture_first, length)
    return send_map


@pytest.mark.parametrize(
    'dark_write,committed',
    [
        ('false', 'false'),
        ('false', 'true'),
        ('true', 'false'),
    ],
)
def test_remember_provider_word_flag_off_leaves_segment_byte_identical(monkeypatch, dark_write, committed):
    _flags_partial(monkeypatch, dark_write, committed)
    segment = {'text': 'hi', 'start': 0.0, 'end': 0.5}
    before = copy.deepcopy(segment)
    remember_provider_word(segment, 0.0, 0.5, 'hi')
    assert segment == before


def test_remember_provider_word_collects_valid_intervals_only(monkeypatch):
    _flags_on(monkeypatch)
    segment = {'text': 'hi there', 'start': 0.0, 'end': 1.0}
    remember_provider_word(segment, 0.0, 0.5, 'hi')
    remember_provider_word(segment, 0.6, 1.0, 'there')
    assert segment[PROVIDER_WORD_RANGES_KEY] == [(0.0, 0.5), (0.6, 1.0)]
    remember_provider_word(segment, 1.0, 1.5, '   ')
    remember_provider_word(segment, 1.0, 1.5, '')
    assert segment[PROVIDER_WORD_RANGES_KEY] == [(0.0, 0.5), (0.6, 1.0)]
    assert PROVIDER_WORDS_ABSTAIN_KEY not in segment


@pytest.mark.parametrize(
    'start,end',
    [
        (True, 1.0),
        (0.0, True),
        (float('nan'), 1.0),
        (0.0, float('inf')),
        (-0.1, 0.5),
        (0.5, 0.5),
        (0.6, 0.5),
        (0.0, 2.000001),
        ('0.0', 0.5),
    ],
)
def test_remember_provider_word_invalid_interval_abstains_segment(monkeypatch, start, end):
    _flags_on(monkeypatch)
    segment = {'text': 'hi there', 'start': 0.0, 'end': 2.0}
    remember_provider_word(segment, 0.0, 0.5, 'hi')
    remember_provider_word(segment, start, end, 'bad')
    assert segment[PROVIDER_WORD_RANGES_KEY] == []
    assert segment[PROVIDER_WORDS_ABSTAIN_KEY] is True
    remember_provider_word(segment, 0.6, 1.0, 'there')
    assert segment[PROVIDER_WORD_RANGES_KEY] == []


def test_remember_provider_word_overflow_abstains_and_blocks_readding(monkeypatch):
    _flags_on(monkeypatch)
    segment = {'text': 'x', 'start': 0.0, 'end': 400.0}
    for i in range(256):
        remember_provider_word(segment, i * 1.5, i * 1.5 + 1.0, 'w')
    assert len(segment[PROVIDER_WORD_RANGES_KEY]) == 256
    remember_provider_word(segment, 399.0, 400.0, 'w')
    assert segment[PROVIDER_WORD_RANGES_KEY] == []
    assert segment[PROVIDER_WORDS_ABSTAIN_KEY] is True


def test_project_provider_words_maps_inward_and_preserves_gaps():
    send_map = _map((0, 0, 10 * RATE))
    segment = {
        'start': 0.0,
        'end': 5.0,
        PROVIDER_WORD_RANGES_KEY: [(0.0, 1.5), (3.5, 5.0)],
    }
    assert project_provider_words(segment, send_map, RATE) == ((0, 24000), (56000, 80000))
    assert PROVIDER_WORD_RANGES_KEY not in segment
    assert PROVIDER_WORDS_ABSTAIN_KEY not in segment


def test_project_provider_words_rounds_endpoints_inward():
    send_map = _map((0, 0, 10 * RATE))
    segment = {
        'start': 0.0,
        'end': 1.0,
        PROVIDER_WORD_RANGES_KEY: [(0.000001, 0.499999)],
    }
    assert project_provider_words(segment, send_map, RATE) == ((1, 7999),)


def test_project_provider_words_merges_only_touching_or_overlapping():
    send_map = _map((0, 0, 10 * RATE))
    segment = {
        'start': 0.0,
        'end': 2.0,
        PROVIDER_WORD_RANGES_KEY: [(0.5, 1.0), (1.0, 1.5), (0.0, 0.25), (1.75, 2.0)],
    }
    assert project_provider_words(segment, send_map, RATE) == ((0, 4000), (8000, 24000), (28000, 32000))


def test_project_provider_words_abstain_marker_and_oversize_return_empty():
    send_map = _map((0, 0, 10 * RATE))
    segment = {'start': 0.0, 'end': 1.0, PROVIDER_WORD_RANGES_KEY: [(0.0, 0.5)], PROVIDER_WORDS_ABSTAIN_KEY: True}
    assert project_provider_words(segment, send_map, RATE) == ()
    assert PROVIDER_WORD_RANGES_KEY not in segment
    assert PROVIDER_WORDS_ABSTAIN_KEY not in segment
    oversize = {'start': 0.0, 'end': 400.0, PROVIDER_WORD_RANGES_KEY: [(i, i + 1) for i in range(257)]}
    assert project_provider_words(oversize, send_map, RATE) == ()
    missing = {'start': 0.0, 'end': 1.0}
    assert project_provider_words(missing, send_map, RATE) == ()


@pytest.mark.parametrize(
    'ranges,expected',
    [
        ([(0.0, 0.5), ('x', 0.6)], ((0, 8000),)),
        ([(float('nan'), 0.5)], ()),
        ([(0.5, 0.4)], ()),
        ([(-0.1, 0.5)], ()),
        ([(0.0, 0.5), (0.9, 1.5)], ((0, 8000), (14400, 24000))),
        ([(0.0, 2.5)], ()),
        ([(0.0001, 0.0002)], ((2, 3),)),
    ],
)
def test_project_provider_words_drops_only_invalid_intervals(ranges, expected):
    send_map = _map((0, 0, 10 * RATE))
    segment = {'start': 0.0, 'end': 2.0, PROVIDER_WORD_RANGES_KEY: ranges}
    assert project_provider_words(segment, send_map, RATE) == expected


def test_project_provider_words_drops_out_of_segment_bounds_interval():
    send_map = _map((0, 0, 10 * RATE))
    segment = {
        'start': 0.0,
        'end': 1.0,
        PROVIDER_WORD_RANGES_KEY: [(0.0, 0.5), (1.5, 2.0)],
    }
    assert project_provider_words(segment, send_map, RATE) == ((0, 8000),)


def test_project_provider_words_never_bridges_send_discontinuity():
    send_map = _map((0, 0, 4 * RATE), (8 * RATE, 6 * RATE, 2 * RATE))
    segment = {
        'start': 0.0,
        'end': 10.0,
        PROVIDER_WORD_RANGES_KEY: [(0.0, 1.0), (8.0, 8.5)],
    }
    assert project_provider_words(segment, send_map, RATE) == ((0, 16000), (6 * RATE, int(6.5 * RATE)))


def test_project_provider_words_word_crossing_capture_gap_yields_nothing():
    send_map = _map((0, 0, RATE), (RATE, 3 * RATE, RATE))
    segment = {
        'start': 0.0,
        'end': 2.0,
        PROVIDER_WORD_RANGES_KEY: [(0.5, 1.5)],
    }
    assert project_provider_words(segment, send_map, RATE) == ()


def test_project_provider_words_word_crossing_provider_hole_yields_nothing():
    send_map = _map((0, 0, RATE), (2 * RATE, 4 * RATE, RATE))
    segment = {
        'start': 0.0,
        'end': 3.0,
        PROVIDER_WORD_RANGES_KEY: [(0.5, 2.5)],
    }
    assert project_provider_words(segment, send_map, RATE) == ()


def _translated(word_ranges, *, project_times=True):
    timeline = CaptureTimeline(sample_rate=RATE)
    epoch = ProviderEpochTranslator(timeline, RATE, project_times=project_times)
    for i in range(10):
        timeline.accept(b'\x01\x00' * (RATE // 10), 1000.0 + (i + 1) * 0.1, float(i))
        epoch.note_accepted(i * (RATE // 10), RATE // 10)
    segment = {'id': 's1', 'speaker': 'SPEAKER_00', 'start': 0.0, 'end': 0.2, 'text': 'hi there', 'is_user': False}
    if word_ranges is not None:
        segment[PROVIDER_WORD_RANGES_KEY] = word_ranges
    original = copy.deepcopy(segment)
    return epoch, segment, original, epoch.translate([segment])


def test_translate_attaches_mapped_word_ranges_and_leaves_original_untouched():
    epoch, segment, original, translated = _translated([(0.0, 0.1), (0.1, 0.2)])
    assert segment == original
    assert len(translated) == 1
    out = translated[0]
    assert out[CAPTURE_WORD_RANGES_KEY] == ((0, RATE // 5),)
    assert PROVIDER_WORD_RANGES_KEY not in out
    assert PROVIDER_WORDS_ABSTAIN_KEY not in out


def test_translate_span_only_segment_gains_no_word_ranges():
    _, _, _, translated = _translated(None)
    assert len(translated) == 1
    assert CAPTURE_WORD_RANGES_KEY not in translated[0]


def test_translate_abstained_words_produce_empty_capture_ranges():
    timeline = CaptureTimeline(sample_rate=RATE)
    epoch = ProviderEpochTranslator(timeline, RATE)
    for i in range(4):
        timeline.accept(b'\x01\x00' * (RATE // 10), 1000.0 + (i + 1) * 0.1, float(i))
        epoch.note_accepted(i * (RATE // 10), RATE // 10)
    segment = {
        'id': 's1',
        'speaker': 'SPEAKER_00',
        'start': 0.0,
        'end': 0.2,
        'text': 'x',
        PROVIDER_WORDS_ABSTAIN_KEY: True,
    }
    translated = epoch.translate([segment])
    assert translated[0][CAPTURE_WORD_RANGES_KEY] == ()
    assert PROVIDER_WORDS_ABSTAIN_KEY not in translated[0]


def test_translate_unplaced_and_rejected_segments_strip_raw_word_metadata():
    timeline = CaptureTimeline(sample_rate=RATE)
    epoch = ProviderEpochTranslator(timeline, RATE)
    for i in range(4):
        timeline.accept(b'\x01\x00' * (RATE // 10), 1000.0 + (i + 1) * 0.1, float(i))
        epoch.note_accepted(i * (RATE // 10), RATE // 10)
    segments = epoch.translate(
        [
            {
                'id': 'unplaced',
                'speaker': 'SPEAKER_00',
                'start': 5.0,
                'end': 5.5,
                'text': 'x',
                PROVIDER_WORD_RANGES_KEY: [(5.0, 5.4)],
            },
            {
                'id': 'bad',
                'speaker': 'SPEAKER_00',
                'start': 'nan',
                'end': 0.2,
                'text': 'x',
                PROVIDER_WORD_RANGES_KEY: [(0.0, 0.1)],
            },
        ]
    )
    assert len(segments) == 2
    for out in segments:
        assert PROVIDER_WORD_RANGES_KEY not in out
        assert PROVIDER_WORDS_ABSTAIN_KEY not in out
        assert CAPTURE_WORD_RANGES_KEY not in out


def _dg_result(*words):
    return SimpleNamespace(
        channel=SimpleNamespace(
            alternatives=[
                SimpleNamespace(
                    transcript=' '.join(w.punctuated_word for w in words),
                    words=list(words),
                )
            ]
        )
    )


def _dg_word(start, end, text, speaker=0):
    return SimpleNamespace(speaker=speaker, start=start, end=end, punctuated_word=text)


async def _capture_dg_on_message(monkeypatch):
    captured = {}

    async def fake_connect(on_message, on_error, *args, **kwargs):
        captured['on_message'] = on_message
        return None

    monkeypatch.setattr(streaming, 'connect_to_deepgram_with_backoff', fake_connect)
    collected = []
    await streaming.process_audio_dg(collected.extend, 'en', RATE, 1)
    return captured['on_message'], collected


async def test_deepgram_adapter_attaches_word_ranges_when_flags_on(monkeypatch):
    _flags_on(monkeypatch)
    on_message, collected = await _capture_dg_on_message(monkeypatch)
    on_message(
        None,
        _dg_result(_dg_word(0.0, 0.5, 'hi'), _dg_word(0.6, 1.0, 'there'), _dg_word(1.1, 1.4, 'you', speaker=1)),
    )
    assert len(collected) == 2
    assert collected[0][PROVIDER_WORD_RANGES_KEY] == [(0.0, 0.5), (0.6, 1.0)]
    assert collected[1][PROVIDER_WORD_RANGES_KEY] == [(1.1, 1.4)]


async def test_deepgram_adapter_flags_off_payloads_byte_identical(monkeypatch):
    _flags_off(monkeypatch)
    on_message, collected = await _capture_dg_on_message(monkeypatch)
    result = _dg_result(_dg_word(0.0, 0.5, 'hi'), _dg_word(0.6, 1.0, 'there'))
    on_message(None, result)
    on_message(None, result)
    assert (
        collected
        == [
            {
                'speaker': 'SPEAKER_0',
                'start': 0.0,
                'end': 1.0,
                'text': 'hi there',
                'is_user': False,
                'person_id': None,
            }
        ]
        * 2
    )


def test_soniox_tokens_attach_preseconds_adjusted_word_ranges(monkeypatch):
    _flags_on(monkeypatch)
    segments = drive(
        [
            {
                'tokens': [
                    token('alpha ', 2000, 2400),
                    token('beta', 2500, 2900),
                    token('Done', 3000, 3100),
                    {'text': '<end>', 'is_final': True},
                    token('skip', 3200, 3300, translation_status='translation'),
                ]
            }
        ],
        preseconds=2,
    )
    assert [s['text'] for s in segments] == ['alpha', 'betaDone']
    assert segments[0][PROVIDER_WORD_RANGES_KEY] == [(pytest.approx(0.0), pytest.approx(0.4))]
    assert segments[1][PROVIDER_WORD_RANGES_KEY] == [
        (pytest.approx(0.5), pytest.approx(0.9)),
        (pytest.approx(1.0), pytest.approx(1.1)),
    ]


def test_soniox_tokens_flag_off_segments_unchanged(monkeypatch):
    _flags_off(monkeypatch)
    segments = drive([{'tokens': [token('alpha ', 0, 400), token('beta', 500, 900)]}])
    for segment in segments:
        assert PROVIDER_WORD_RANGES_KEY not in segment
        assert PROVIDER_WORDS_ABSTAIN_KEY not in segment
