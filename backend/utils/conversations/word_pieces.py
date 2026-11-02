"""Word-sized provider pieces on writers that never reach combine_segments.

Soniox emits one segment per word and leaves joining to the live tail merge. Sync
intake sorts pieces into a transcript instead, so each stays its own stored line.
"""

import re
from typing import Any, Collection, Iterable, Mapping, Optional

_MAX_GAP_SECONDS = 3.0
_MAX_JOINED_CHARS = 125
_SENTENCE_ENDERS = ('.', '?', '!')
_SAME_CLOCK_SLOP_SECONDS = 0.01
_MIN_REPEAT_WORDS = 5
_MIN_REPEAT_SHARE = 0.7
_REPEAT_WINDOW_SECONDS = 600.0
_IDENTITY_FIELDS = (
    'stt_provider',
    'speaker_id_scope',
    'speaker_id',
    'speaker',
    'is_user',
    'person_id',
    'speaker_match_source',
    'speaker_label_source',
    'audio_alignment',
    'audio_capture_run',
    'speech_profile_processed',
)


def _tokens(text: Optional[str]) -> list[str]:
    return re.findall(r"[^\W_]+", (text or '').lower(), flags=re.UNICODE)


def _is_word(segment: Mapping[str, Any]) -> bool:
    return len((segment.get('text') or '').split()) == 1


def _stream(segment: Mapping[str, Any]) -> Optional[tuple[str, str]]:
    provider, scope = segment.get('stt_provider'), segment.get('speaker_id_scope')
    return (provider, scope) if provider and scope else None


def drop_replayed_words(existing: list[dict], incoming: list[dict], *, clock: str = 'start') -> list[dict]:
    """Drop retried provider pieces: a repeated ID, or a word the same stream already covers.

    Text dedupe exempts one-word lines, and a joined word no longer has its own exact
    range, so a redelivered batch would otherwise append the same words again. Lines with
    no provider stream keep the recovery contract, where a receipt-only replay reappends.
    """
    ids = {segment.get('id') for segment in existing if segment.get('id')}
    spans: dict[tuple[str, str, Any], list[tuple[float, float]]] = {}
    for segment in existing:
        stream = _stream(segment)
        if stream is not None:
            start = float(segment[clock])
            spans.setdefault((*stream, segment.get('speaker')), []).append(
                (start, start + float(segment['end']) - float(segment['start']))
            )
    kept = []
    for segment in incoming:
        stream = _stream(segment)
        if stream is not None and segment.get('id') in ids:
            continue
        if stream is not None and _is_word(segment):
            start = float(segment[clock])
            end = start + float(segment['end']) - float(segment['start'])
            if any(
                left - _SAME_CLOCK_SLOP_SECONDS <= start and end <= right + _SAME_CLOCK_SLOP_SECONDS
                for left, right in spans.get((*stream, segment.get('speaker')), ())
            ):
                continue
        if segment.get('id'):
            ids.add(segment['id'])
        kept.append(segment)
    return kept


def other_provider_phrases(existing: Iterable[dict], *, clock: str = 'start') -> dict[tuple[str, ...], list]:
    """Three-word phrases per stored line, as (provider, start) for ``repeats_another_provider``."""
    phrases: dict[tuple[str, ...], list] = {}
    for segment in existing:
        provider = segment.get('stt_provider')
        if provider and not _is_word(segment):
            tokens = _tokens(segment.get('text'))
            for index in range(len(tokens) - 2):
                phrases.setdefault(tuple(tokens[index : index + 3]), []).append((provider, float(segment[clock])))
    return phrases


def repeats_another_provider(text: Optional[str], provider: str, start: float, phrases: Mapping) -> bool:
    """Whether most of this text is speech another provider already wrote near this moment.

    Compared by words because the late provider's clock can sit minutes away from the
    stored line. A word a repeat adds beyond the stored line is lost with it, so the share is high.
    """
    tokens = _tokens(text)
    if len(tokens) < _MIN_REPEAT_WORDS:
        return False
    covered: set[int] = set()
    for index in range(len(tokens) - 2):
        if any(
            other != provider and abs(when - start) <= _REPEAT_WINDOW_SECONDS
            for other, when in phrases.get(tuple(tokens[index : index + 3]), ())
        ):
            covered.update((index, index + 1, index + 2))
    return len(covered) / len(tokens) >= _MIN_REPEAT_SHARE


def drop_repeated_word_runs(existing: list[dict], incoming: list[dict], *, clock: str = 'start') -> list[dict]:
    """Drop runs of one-word pieces that repeat a line another provider already wrote."""
    phrases = other_provider_phrases(existing, clock=clock)
    if not phrases:
        return incoming
    runs: list[list[dict]] = []
    for segment in incoming:
        run = runs[-1] if runs else None
        if (
            run
            and _is_word(segment)
            and _is_word(run[-1])
            and _stream(segment) == _stream(run[-1])
            and segment.get('speaker') == run[-1].get('speaker')
            and float(segment[clock]) - float(run[-1][clock]) < _MAX_GAP_SECONDS
        ):
            run.append(segment)
        else:
            runs.append([segment])
    kept: list[dict] = []
    for run in runs:
        provider = run[0].get('stt_provider')
        text = ' '.join(segment.get('text') or '' for segment in run)
        if not (
            provider and _is_word(run[0]) and repeats_another_provider(text, provider, float(run[0][clock]), phrases)
        ):
            kept.extend(run)
    return kept


def _absorb_word(into: dict, word: dict) -> None:
    into['text'] = f"{into['text'].rstrip()} {word['text'].strip()}"
    into['end'] = max(into['end'], word['end'])
    theirs = {item.get('lang'): item.get('text') for item in word.get('translations') or []}
    into['translations'] = [
        {**item, 'text': f"{item.get('text')} {theirs[item.get('lang')]}"}
        for item in into.get('translations') or []
        if item.get('lang') in theirs
    ]
    if into.get('audio_source') or word.get('audio_source'):
        into['audio_source'] = None
    left_start, left_end = into.get('audio_capture_start'), into.get('audio_capture_end')
    right_start, right_end = word.get('audio_capture_start'), word.get('audio_capture_end')
    if (
        left_start is None
        or left_end is None
        or right_start is None
        or right_end is None
        or max(left_start, right_start) > min(left_end, right_end)
    ):
        into['audio_capture_start'] = into['audio_capture_end'] = None
    else:
        into['audio_capture_start'], into['audio_capture_end'] = min(left_start, right_start), max(left_end, right_end)
    if into.get('provider_speaker') != word.get('provider_speaker'):
        into['provider_speaker'] = {'id': -1, 'scope': 'ambiguous'}
    into['speaker_grouping_shadow'] = into['speaker_grouping_shadow_expires_at'] = None


def join_word_pieces(
    segments: Iterable[dict],
    *,
    joinable_ids: Optional[Collection[str]] = None,
    protected_ids: Collection[str] = (),
) -> list[dict]:
    """Join one-word pieces into the same speaker's preceding piece from the same stream.

    ``segments`` must be in transcript order. Another provider's interleaved line does
    not end a run, since it is a separate transcription; another speaker on this stream
    does. Only ``joinable_ids`` may be absorbed (all when None), so an append leaves
    stored history alone. ``protected_ids`` are named by a manual receipt and stay whole.
    """
    joined: list[dict] = []
    last: dict[tuple[str, str], dict] = {}
    for segment in segments:
        stream = _stream(segment)
        if stream is None or segment.get('audio_alignment') == 'unplaced':
            joined.append(segment)
            continue
        previous = last.get(stream)
        if (
            previous is not None
            and _is_word(segment)
            and (joinable_ids is None or segment.get('id') in joinable_ids)
            and segment.get('id') not in protected_ids
            and previous.get('id') not in protected_ids
            and all(previous.get(field) == segment.get(field) for field in _IDENTITY_FIELDS)
            and segment['start'] >= previous['start']
            and segment['end'] >= previous['end']
            and segment['start'] - previous['end'] < _MAX_GAP_SECONDS
            and not (
                len(previous.get('text') or '') >= _MAX_JOINED_CHARS
                and (previous.get('text') or '').rstrip().endswith(_SENTENCE_ENDERS)
            )
        ):
            _absorb_word(previous, segment)
            continue
        last[stream] = segment
        joined.append(segment)
    return joined
