"""Outline-first and compact views over hosted MCP conversation detail reads.

Paging itself lives in ``helpers.transcript_page`` and ``detail_cursors``. This
module adds the steps an agent takes before and while paging a long
conversation:

- ``view="outline"`` returns the card plus the stored note sections, each
  anchored to the span of transcript segments it cites, and no transcript;
- ``offset`` starts a transcript read at a segment index, for example a
  section's ``first_segment``;
- ``format="lines"`` renders a page as one ``[h:mm:ss] Speaker: text`` line per
  speaker turn, about a third of the size of the per-segment JSON.
"""

from typing import Any, Dict, List, Optional, Tuple

from prometheus_client import REGISTRY, Counter

from utils.mcp_server.errors import ToolExecutionError

FORMATS = ('segments', 'lines')
VIEWS = ('transcript', 'outline')
OFFSET_MAX = 1_000_000
SECTION_HEADING_MAX_CHARS = 200
OUTLINE_MAX_SECTIONS = 100

VIEW_INPUT: Dict[str, Any] = {
    'type': 'string',
    'enum': list(VIEWS),
    'default': 'transcript',
    'description': 'outline: card plus note sections with the segment range each cites, no transcript. '
    'transcript: one page of transcript.',
}
FORMAT_INPUT: Dict[str, Any] = {
    'type': 'string',
    'enum': list(FORMATS),
    'default': 'segments',
    'description': 'lines: one "[h:mm:ss] Speaker: text" line per speaker turn in conversation.transcript, '
    'about a third of the size. segments: JSON rows in conversation.transcript_segments.',
}
OFFSET_INPUT: Dict[str, Any] = {
    'type': 'integer',
    'minimum': 0,
    'maximum': OFFSET_MAX,
    'default': 0,
    'description': 'Start the transcript at this segment index, such as a section first_segment. '
    'Ignored when cursor is given, so a section read can keep its options while it pages.',
}
SECTIONS_OUTPUT: Dict[str, Any] = {
    'type': 'array',
    'items': {
        'type': 'object',
        'properties': {
            'index': {'type': 'integer'},
            'heading': {'type': 'string'},
            'kind': {'type': ['string', 'null']},
            'first_segment': {'type': ['integer', 'null']},
            'segment_count': {'type': ['integer', 'null']},
            'start': {'type': ['number', 'null']},
            'end': {'type': ['number', 'null']},
        },
    },
}
LINES_OUTPUT: Dict[str, Any] = {
    'type': 'string',
    'description': 'This page of transcript as one line per speaker turn (format=lines)',
}
RANGE_OUTPUT: Dict[str, Any] = {
    'type': ['array', 'null'],
    'items': {'type': 'integer'},
    'description': 'First and last segment index on this page, null when the page is empty (format=lines)',
}

_PAGES_LABELS = ['tool', 'view', 'format', 'position', 'more']


def _pages_counter() -> Counter:
    """Module-reload-safe: isolated handler loads reuse the one registered collector."""
    existing = getattr(REGISTRY, '_names_to_collectors', {}).get('omi_mcp_transcript_pages_total')
    if existing is not None:
        if not isinstance(existing, Counter) or list(getattr(existing, '_labelnames', ())) != _PAGES_LABELS:
            raise ValueError('omi_mcp_transcript_pages_total already registered with a different shape')
        return existing
    return Counter(
        'omi_mcp_transcript_pages',
        'Hosted MCP conversation detail pages served, by tool, view, format, page position and whether more remain',
        _PAGES_LABELS,
    )


MCP_TRANSCRIPT_PAGES_TOTAL = _pages_counter()


def parse_choice(arguments: Dict[str, Any], name: str, choices: Tuple[str, ...]) -> str:
    value = arguments.get(name)
    if value is None:
        return choices[0]
    if value not in choices:
        raise ToolExecutionError(f"{name} must be one of: {', '.join(choices)}", code=-32602)
    return value


def start_offset(arguments: Dict[str, Any]) -> Optional[int]:
    """The explicit segment index to start at, or None when the read starts at the beginning or a cursor.

    The cursor holds the exact position, so an agent resending its original offset
    with it does not restart the read. Out-of-range values are errors, not clamped.
    """
    value = arguments.get('offset')
    if value is None or arguments.get('cursor') is not None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ToolExecutionError('Invalid offset: expected integer.', code=-32602)
    try:
        offset = int(value)
    except ValueError as exc:
        raise ToolExecutionError('Invalid offset: expected integer.', code=-32602) from exc
    if not 0 <= offset <= OFFSET_MAX:
        raise ToolExecutionError(f'offset must be between 0 and {OFFSET_MAX}.', code=-32602)
    return offset


def readable_segments(segments: Any) -> List[Dict[str, Any]]:
    """The segments paging indexes: dict rows only, in stored order (as ``helpers.transcript_page``)."""
    return [segment for segment in segments if isinstance(segment, dict)] if isinstance(segments, list) else []


def outline_sections(conversation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Stored note sections, each anchored to the span of transcript segments it cites.

    Returns at most ``OUTLINE_MAX_SECTIONS + 1`` entries, so the caller can report
    ``sections_truncated`` without walking an unbounded stored list.
    """
    structured = conversation.get('structured')
    sections = structured.get('sections') if isinstance(structured, dict) else None
    if not isinstance(sections, list):
        return []
    source = readable_segments(conversation.get('transcript_segments'))
    index_of = {str(s['id']): i for i, s in enumerate(source) if s.get('id') is not None}
    result: List[Dict[str, Any]] = []
    for number, section in enumerate(sections):
        if len(result) > OUTLINE_MAX_SECTIONS:
            break
        if not isinstance(section, dict):
            continue
        cited = section.get('source_segment_ids')
        cited = cited if isinstance(cited, list) else []
        positions = sorted(index_of[str(i)] for i in cited if str(i) in index_of)
        first: Optional[int] = positions[0] if positions else None
        last: Optional[int] = positions[-1] if positions else None
        kind = section.get('kind')
        # Cited segments can overlap or be stored out of time order, so the window
        # spans every cited segment rather than the first and last index.
        starts = [t for t in (_seconds(source[p].get('start')) for p in positions) if t is not None]
        ends = [t for t in (_seconds(source[p].get('end')) for p in positions) if t is not None]
        result.append(
            {
                'index': number,
                'heading': str(section.get('heading') or '')[:SECTION_HEADING_MAX_CHARS],
                'kind': kind if isinstance(kind, str) else None,
                'first_segment': first,
                'segment_count': (last - first + 1) if first is not None and last is not None else None,
                'start': min(starts) if starts else None,
                'end': max(ends) if ends else None,
            }
        )
    return result


def _seconds(value: Any) -> Optional[float]:
    try:
        return max(0.0, round(float(value), 1))
    except (TypeError, ValueError, OverflowError):
        return None


def _clock(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError, OverflowError):
        return '?:??:??'
    return f'{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}'


def render_lines(items: List[Dict[str, Any]]) -> str:
    """One line per speaker turn: consecutive segments of one speaker are joined.

    Turns join only when both the canonical ``speaker_key`` and the label match:
    two people who share a label (two contacts with one name) stay apart, and so
    do rows of one diarization cluster whose names were corrected per segment. A
    continued fragment of an oversized segment joins the previous line, so a
    reassembled page reads as the speaker said it.
    """
    turns: List[List[Any]] = []
    for item in items:
        label = str(item.get('speaker_label') or 'Unknown')
        key = item.get('speaker_key')
        key = (key, label)
        text = str(item.get('text') or '').strip()
        if turns and turns[-1][0] == key:
            turns[-1][3] = (turns[-1][3] + ' ' + text).strip()
        else:
            turns.append([key, item.get('start'), label, text])
    return '\n'.join(f'[{_clock(start)}] {label}: {text}' for _key, start, label, text in turns)


def lines_fields(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The lines rendering of a page, with the segment indexes it covers for citing and re-reading."""
    indexes = [item['segment_index'] for item in items if isinstance(item.get('segment_index'), int)]
    return {
        'transcript': render_lines(items),
        'transcript_range': [indexes[0], indexes[-1]] if indexes else None,
    }


def rendered_segments(conversation: Dict[str, Any], fmt: str) -> Dict[str, Any]:
    """The conversation as the chosen format pages it.

    ``lines`` renders ``text`` only, so it pages over ``text`` only: otherwise a page
    boundary inside ``original_text`` would spend continuation calls on lines with
    no speech. Returns a shallow copy; the fetched document is not changed.
    """
    segments = conversation.get('transcript_segments')
    if fmt != 'lines' or not isinstance(segments, list):
        return conversation
    return {
        **conversation,
        'transcript_segments': [
            {k: v for k, v in s.items() if k != 'original_text'} if isinstance(s, dict) else s for s in segments
        ],
    }


def count_page(tool: str, view: str, fmt: str, first: bool, more: bool) -> None:
    try:
        MCP_TRANSCRIPT_PAGES_TOTAL.labels(
            tool, view, fmt, 'first' if first else 'continuation', 'true' if more else 'false'
        ).inc()
    except Exception:  # noqa: BLE001 - telemetry must never fail a read
        pass
