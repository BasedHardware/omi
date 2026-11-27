"""Split a stored batch segment whose words the whole-conversation pass gives to more than one voice.

The batch final pass relabels stored segments. A stored segment groups words by the unit's own diarization; the
whole-conversation pass often hears a voice change inside it. Without a split such a segment keeps its earlier
label (``failed_unassigned_words``): measured on an owner's gold-labeled conversations (2026-11-26), 40 % of
segments and 55 % of words, and the gap between the pass's per-word accuracy (0.99) and what production keeps
(0.61). A split relabels each piece with its own voice.

A split is exact on the stored text: a segment splits only when its assigned words spell its text token for
token (up to case and punctuation), and every piece takes a whole run of those tokens. Clocks move with the words: piece ``k`` starts where its
first word starts, relative to the segment's first word. The first piece keeps the segment's id, so references to
the segment (structured notes, action items) still resolve; later pieces take ``split_segment_id(id, k)``. A later
pass recognises the run of pieces as the projection segment they came from (:func:`expand_split`).

Splitting runs only on the first pass over a conversation's units, not on the identity-only retry
(``final_pass_retry.run_only``): by then structured notes may cite the segment, and a split would narrow that
citation to its first piece. Reading pieces back does not depend on the kill switch, so turning splitting off never
strands segments an earlier pass split.

Not split: manual segments, corrected text (``original_text``), translated segments, segments already split, and
segments of more than ``MAX_PIECES`` runs; runs shorter than ``MIN_RUN_WORDS`` words or ``MIN_RUN_SECONDS`` are
absorbed into the neighbouring run. Words in a
diarization gap join the run before them (or after, at the start) only while they are at most ``MAX_GAP_SHARE`` of
the segment's words; a segment mostly in a gap still abstains, as before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from uuid import NAMESPACE_URL, uuid5

# Operating point from the speaker lab (owner gold set, 12 conversations, 9,185 words, 2026-11-27): trusting every
# voice run (no absorption) and up to 8 pieces scored attribution 0.993 and owner precision 1.0; 3-word / 1 s
# absorption with 3 pieces scored 0.921 and 0.966.
MIN_RUN_WORDS = 1
MIN_RUN_SECONDS = 0.0
MAX_PIECES = 8
MAX_GAP_SHARE = 0.25
MAX_CHAIN = 16
_WORD = re.compile(r'[^\w]+')


def split_segment_id(segment_id: str, index: int) -> str:
    return str(uuid5(NAMESPACE_URL, f'{segment_id}:split:{index}'))


@dataclass(frozen=True)
class Run:
    voice: object
    first: int  # word index in the segment's words, inclusive
    last: int  # inclusive


def _tokens(text: str) -> list[str]:
    return (text or '').split()


def plan_runs(words: list[dict]) -> Optional[list[Run]]:
    """Runs of one voice over a segment's assigned words (in time order), after absorbing gaps and short runs.
    ``None`` when more than ``MAX_GAP_SHARE`` of the words are in a diarization gap."""

    gaps = sum(w['speaker'] is None for w in words)
    if gaps == len(words) or gaps > MAX_GAP_SHARE * len(words):
        return None
    voices = [w['speaker'] for w in words]
    # Gap words (no voice) take the voice before them, or the first voice after them at the start.
    first_voice = next(v for v in voices if v is not None)
    current = first_voice
    filled = []
    for voice in voices:
        current = voice if voice is not None else current
        filled.append(current)
    runs: list[Run] = []
    for index, voice in enumerate(filled):
        if runs and runs[-1].voice == voice:
            runs[-1] = Run(voice, runs[-1].first, index)
        else:
            runs.append(Run(voice, index, index))

    def short(run: Run) -> bool:
        seconds = words[run.last]['timestamp'][1] - words[run.first]['timestamp'][0]
        return run.last - run.first + 1 < MIN_RUN_WORDS or seconds < MIN_RUN_SECONDS

    # Absorb the shortest short run into its longer neighbour until none is left (or one run remains).
    while len(runs) > 1:
        shorts = [i for i, r in enumerate(runs) if short(r)]
        if not shorts:
            break
        i = min(shorts, key=lambda k: runs[k].last - runs[k].first)
        left_size = runs[i - 1].last - runs[i - 1].first if i > 0 else -1
        right_size = runs[i + 1].last - runs[i + 1].first if i + 1 < len(runs) else -1
        if left_size >= right_size:
            left = runs[i - 1]
            runs[i - 1] = Run(left.voice, left.first, runs[i].last)
        else:
            right = runs[i + 1]
            runs[i + 1] = Run(right.voice, runs[i].first, right.last)
        del runs[i]
        merged = []
        for run in runs:
            if merged and merged[-1].voice == run.voice:
                merged[-1] = Run(run.voice, merged[-1].first, run.last)
            else:
                merged.append(run)
        runs = merged
    return runs


def _norm(token: str) -> str:
    return _WORD.sub('', token.casefold())


def word_token_counts(words: list[dict], text: str) -> Optional[list[int]]:
    """Tokens of the stored text each word holds, when the words spell the text token for token, up to case and
    punctuation (the transcript grouper capitalises and punctuates; pieces keep the stored text). Else ``None``."""

    counts = [len(_tokens(w.get('text') or '')) for w in words]
    spelled = [_norm(t) for w in words for t in _tokens(w.get('text') or '')]
    if not words or 0 in counts or spelled != [_norm(t) for t in _tokens(text)]:
        return None
    return counts


def split_segment(segment, words: list[dict], runs: list[Run]) -> Optional[list]:
    """Pieces of ``segment`` (copies), one per run, or ``None`` when the words do not spell its text."""

    counts = word_token_counts(words, segment.text)
    if counts is None or len(runs) < 2:
        return None
    tokens = _tokens(segment.text)
    origin = words[0]['timestamp'][0]
    pieces = []
    offset = 0
    for k, run in enumerate(runs):
        n = sum(counts[run.first : run.last + 1])
        text = ' '.join(tokens[offset : offset + n])
        offset += n
        start = segment.start if k == 0 else segment.start + (words[run.first]['timestamp'][0] - origin)
        piece = segment.model_copy(deep=True)
        piece.id = segment.id if k == 0 else split_segment_id(segment.id, k)
        piece.text = text
        piece.start = min(max(start, segment.start), segment.end)
        pieces.append(piece)
    for a, b in zip(pieces, pieces[1:]):
        b.start = max(b.start, a.start)
        a.end = b.start
    pieces[-1].end = segment.end
    if any(p.end <= p.start for p in pieces):
        return None
    source = segment.audio_source if isinstance(segment.audio_source, dict) else None
    for piece in pieces:
        if source and source.get('type') == 'sync' and _is_number(source.get('start')):
            # A saved sync window is proof only while it equals origin + start/end; each piece keeps that origin.
            piece.audio_source = {
                **source,
                'start': source['start'] + (piece.start - segment.start),
                'end': source['start'] + (piece.end - segment.start),
            }
        if segment.audio_capture_start is not None and segment.audio_capture_end is not None:
            piece.audio_capture_start = segment.audio_capture_start + (piece.start - segment.start)
            piece.audio_capture_end = min(
                segment.audio_capture_end, segment.audio_capture_start + (piece.end - segment.start)
            )
    return pieces


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def refusal(segment) -> Optional[str]:
    """Why ``segment`` must not split, or ``None``."""

    if segment.speaker_label_source == 'manual':
        return 'manual'
    if segment.original_text is not None:
        return 'corrected_text'
    if segment.translations:
        return 'translated'
    return None


def expand_split(segment_id: str, stored: dict) -> list:
    """The stored pieces a projection segment became: itself, then ``split_segment_id(id, 1..)`` while stored."""

    chain = [stored[segment_id]] if segment_id in stored else []
    for k in range(1, MAX_CHAIN):
        piece = stored.get(split_segment_id(segment_id, k))
        if piece is None:
            break
        chain.append(piece)
    return chain


def assign_words_to_pieces(words: list[dict], pieces: list) -> Optional[list[str]]:
    """Piece id for each of a projection segment's words, by token position (``None`` when they do not spell the
    pieces' text)."""

    text = ' '.join(p.text for p in pieces)
    counts = word_token_counts(words, text)
    if counts is None:
        return None
    bounds, total = [], 0
    for piece in pieces:
        total += len(_tokens(piece.text))
        bounds.append(total)
    owners, position, index = [], 0, 0
    for count in counts:
        while position >= bounds[index]:
            index += 1
        if position + count > bounds[index]:
            return None  # a word straddles two pieces
        owners.append(pieces[index].id)
        position += count
    return owners


def unsplit_lines(segments) -> list[dict]:
    """For each split run among stored segments (dicts or models), the original line: its id, the first piece's
    start, the last piece's end and the pieces' joined text. Readers that recognise a published segment by its exact
    id and timing, or by overlapping text (the conversations-v3 planner), see the original line in its pieces."""

    def get(segment, key):
        return segment.get(key) if isinstance(segment, dict) else getattr(segment, key, None)

    by_id = {str(get(s, 'id')): s for s in segments if get(s, 'id')}
    lines = []
    for segment_id, segment in by_id.items():
        chain = expand_split(segment_id, by_id)
        if len(chain) > 1:
            lines.append(
                {
                    'id': segment_id,
                    'start': get(segment, 'start'),
                    'end': get(chain[-1], 'end'),
                    'text': ' '.join(get(piece, 'text') or '' for piece in chain),
                }
            )
    return lines


def derived_piece_ids(segments) -> set[str]:
    """Ids of the pieces after the first in every split run: the obligation key ignores them, so a split never opens
    a new final-pass obligation for the same unit membership."""

    by_id = {s.id: s for s in segments if s.id}
    return {piece.id for segment_id in by_id for piece in expand_split(segment_id, by_id)[1:]}
