"""Synthetic long complementary capture pair for containment bound coverage.

Builds a ~2h desktop meeting (2,500 non-overlapping segments at 2.88s spacing,
2.4s durations) against a 1,250-segment pendant capture whose own-voice
utterances match the desktop even-index own-voice segments with sparse ASR
substitutions; desktop odd-index segments carry remote speech. Raw sizes
deliberately exceed the retired 1,024-segment / 16,000-word scan budgets.
"""

from datetime import datetime, timedelta, timezone

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

VOCAB = (
    'agenda budget calendar deadline effort forecast growth hiring invoice journal knowledge ledger '
    'memo notebook outlook payroll quarter roadmap schedule timeline update vendor workflow '
    'assembly battery calibration deposit enclosure firmware gasket housing inspection '
    'microphone packaging sensor shipment tolerance voltage warranty '
    'anchor beacon channel doorway engine fabric gateway harbor island journey kingdom '
    'lantern meadow network orchard pioneer quarry river signal tower umbrella valley window'
).split()

REMOTE_VOCAB = (
    'agree answer aside comment digress follow interject mention note observe opinion '
    'question react reply respond summarize tangent'
).split()

DESKTOP_SECONDS = 7200.0
DESKTOP_SKEW_SECONDS = 0.5
SEGMENT_LEAD_SECONDS = 7.0
SEGMENT_STEP = 2.88
SEGMENT_DURATION = 2.4
DESKTOP_SEGMENTS = 2500
PENDANT_SEGMENTS = 1250


def utterance(index):
    """Distinct natural-vocabulary utterance of 14 words for pendant segment index."""
    words = [VOCAB[(index * 7 + offset * 37) % len(VOCAB)] + '%04d' % index for offset in range(13)]
    words.insert(5, 'topic%04d' % index)
    return ' '.join(words)


def remote_line(index):
    """Distinct remote-participant line for the desktop odd-index segments."""
    words = [REMOTE_VOCAB[(index * 5 + offset * 11) % len(REMOTE_VOCAB)] for offset in range(9)]
    words.insert(3, 'remote%04d' % index)
    return ' '.join(words)


def variant(text):
    """Sparse ASR noise: two substitutions plus three spread insertions."""
    words = text.split()
    words[4], words[9] = 'zz' + words[4], 'zz' + words[9]
    words.insert(12, 'mm')
    words.insert(7, 'hum')
    words.insert(2, 'uh')
    return ' '.join(words)


def disjoint_utterance(index):
    """Utterance sharing no vocabulary with any generated meeting utterance."""
    return ' '.join('x%04d_%d' % (index, offset) for offset in range(14))


def segment(text, start, is_user=True, end=None, **extra):
    return {
        'text': text,
        'start': start,
        'end': start + SEGMENT_DURATION if end is None else end,
        'is_user': is_user,
        'speaker': 'SPEAKER_00',
        **extra,
    }


def row(id, source, start, end, segments, **extra):
    return {
        'id': id,
        'source': source,
        'status': 'completed',
        'discarded': False,
        'started_at': T0 + timedelta(seconds=start),
        'finished_at': T0 + timedelta(seconds=end),
        'transcript_segments': segments,
        **extra,
    }


def long_complementary_pair():
    """Pendant wearer speech is contained in the desktop meeting, both orders."""
    pendant_segments = [segment(utterance(index), index * SEGMENT_STEP * 2.0) for index in range(PENDANT_SEGMENTS)]
    desktop_segments = []
    for index in range(DESKTOP_SEGMENTS):
        start = index * SEGMENT_STEP + SEGMENT_LEAD_SECONDS
        if index % 2 == 0:
            desktop_segments.append(segment(variant(utterance(index // 2)), start))
        else:
            desktop_segments.append(segment(remote_line(index // 2), start, is_user=False))
    pendant = row('pendant', 'omi', 0.0, DESKTOP_SECONDS, pendant_segments)
    desktop = row('desktop', 'desktop', -DESKTOP_SKEW_SECONDS, DESKTOP_SECONDS + SEGMENT_LEAD_SECONDS, desktop_segments)
    return pendant, desktop


def long_unrelated_pair():
    """Same layout with pendant vocabulary disjoint from the meeting."""
    pendant, desktop = long_complementary_pair()
    pendant['transcript_segments'] = [
        segment(disjoint_utterance(index), index * SEGMENT_STEP * 2.0) for index in range(PENDANT_SEGMENTS)
    ]
    return pendant, desktop


SKEW_SECONDS = 2100.0
SKEW_UTTERANCES = 100
SKEW_STEP = 20.0
SKEW_DURATION = 2.0
SKEW_COUNT_SAMPLE_INDICES = {index * (SKEW_UTTERANCES - 1) // 31 for index in range(32)}


def length_skewed_pair():
    """Count-strided sampling matched 32 short utterances; word-mass sampling sees the disjoint bulk."""
    pendant_segments = []
    desktop_segments = []
    for index in range(SKEW_UTTERANCES):
        start = index * SKEW_STEP
        if index in SKEW_COUNT_SAMPLE_INDICES:
            pendant_text = ' '.join('match%dword%d' % (index, word) for word in range(8))
            desktop_text = pendant_text
        else:
            pendant_text = ' '.join('small%dword%d' % (index, word) for word in range(128))
            desktop_text = ' '.join('other%dword%d' % (index, word) for word in range(128))
        pendant_segments.append(segment(pendant_text, start, end=start + SKEW_DURATION))
        desktop_segments.append(segment(desktop_text, start, end=start + SKEW_DURATION))
    for extra in range(10):
        start = extra * 200.0 + 5.0
        desktop_segments.append(segment('extra remote words', start, is_user=False, end=start + SKEW_DURATION))
    desktop_segments.sort(key=lambda item: item['start'])
    pendant = row('pendant', 'omi', 0.0, SKEW_SECONDS, pendant_segments)
    desktop = row('desktop', 'desktop', 0.0, SKEW_SECONDS, desktop_segments)
    return pendant, desktop


COLLAPSE_SECONDS = 1400.0
COLLAPSE_UTTERANCES = 33
COLLAPSE_MASS = 4
COLLAPSE_STEP = 40.0


def quantile_collapse_pair():
    """Four massive exact-match utterances absorb 22 of 32 quantile hits.

    Word-mass sampling must count repeated hits as coverage weight; otherwise
    the few disjoint sampled words misreport coverage. The exact-match head is
    deliberately strong enough that the symmetric trigram rule confirms too.
    """
    pendant_segments = []
    desktop_segments = []
    for index in range(COLLAPSE_UTTERANCES):
        start = index * COLLAPSE_STEP
        if index < COLLAPSE_MASS:
            text = ' '.join('mass%dw%d' % (index, word) for word in range(128))
            pendant_segments.append(segment(text, start, end=start + 30.0))
            desktop_segments.append(segment(text, start, end=start + 30.0))
        else:
            pendant_segments.append(
                segment(' '.join('small%dw%d' % (index, word) for word in range(8)), start, end=start + 2.0)
            )
            desktop_segments.append(
                segment(' '.join('other%dw%d' % (index, word) for word in range(8)), start, end=start + 2.0)
            )
    for extra in range(10):
        start = extra * 100.0 + 35.0
        desktop_segments.append(segment('extra remote words', start, is_user=False, end=start + 2.0))
    desktop_segments.sort(key=lambda item: item['start'])
    pendant = row('pendant', 'omi', 0.0, COLLAPSE_SECONDS, pendant_segments)
    desktop = row('desktop', 'desktop', 0.0, COLLAPSE_SECONDS, desktop_segments)
    return pendant, desktop


FAVORABLE_UTTERANCES = 64
FAVORABLE_WORDS = 16
FAVORABLE_SAMPLE_INDICES = {((i * (64 * 16 - 1) // 31) // 16) for i in range(32)}


def favorable_subset_pair():
    assert len(FAVORABLE_SAMPLE_INDICES) == 32
    assert all(index < FAVORABLE_UTTERANCES for index in FAVORABLE_SAMPLE_INDICES)
    pendant_segments = []
    desktop_segments = []
    matched = set()
    for index in range(FAVORABLE_UTTERANCES):
        start = 40.0 + 30.0 * index
        words = ['fav%02dw%d' % (index, word) for word in range(FAVORABLE_WORDS)]
        pendant_segments.append(segment(' '.join(words), start, end=start + 8.0))
        if index in FAVORABLE_SAMPLE_INDICES:
            target = list(words)
            target[4], target[8], target[12] = 'zzzfive', 'zzznine', 'zzzthirteen'
            target.insert(7, 'hum')
            target.insert(2, 'uh')
            matched.add(index)
        else:
            target = ['other%02dw%d' % (index, word) for word in range(FAVORABLE_WORDS + 1)]
        desktop_segments.append(segment(' '.join(target), start, end=start + 8.0))
    assert matched == FAVORABLE_SAMPLE_INDICES
    assert len(set(range(FAVORABLE_UTTERANCES)) - matched) == 32
    pendant = row('pendant', 'omi', 0.0, 2000.0, pendant_segments)
    desktop = row('desktop', 'desktop', 0.0, 2000.0, desktop_segments)
    return pendant, desktop
