"""
Read-only service for "what do I owe people?".

Lists the account owner's open commitments that Omi captured from conversations,
grouped by the person each one was made to, with the source conversation as a
citation. Used by the REST router (desktop chat).

It never creates, accepts, edits or completes a task, and never calls a model. The
other person is worked out at read time from who was speaking around the cited
transcript lines (``resolve_counterparty``); nothing new is stored. ``owner_name`` on
summary items names the OWNER of an item, not the person it is owed to, so it is
never used here. Attribution carries names only, and contact details in free text are
removed where recognised (``redact_contact_details``), so a follow-up draft has to
resolve the handle through the person's contacts.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

import database.action_items as action_items_db
import database.conversations as conversations_db
import database.users as users_db
from utils.task_predicates import is_open_conversation_task
from utils.retrieval.safety import safe_isoformat
from utils.retrieval.tool_services.conversations import parse_iso_date

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 90
TASK_SCAN_LIMIT = 200
CONVERSATION_CAP = 25
DEFAULT_LIMIT_PEOPLE = 10
MAX_LIMIT_PEOPLE = 20
MAX_PER_PERSON = 5
MAX_COMMITMENTS = 30
MAX_UNATTRIBUTED = 10
# The ask usually comes just before the promise ("can you send it?" / "I'll send it").
LOOK_BACK_SEGMENTS = 2
# ...but only when it is part of the same exchange. A reply to a question normally
# follows within seconds; 90 s leaves room for a pause or a long answer while
# excluding a goodbye half an hour before a note-to-self. Measured from the earlier
# segment's end to the first cited segment's start.
LOOK_BACK_SECONDS = 90.0
DESCRIPTION_CHARS = 200
TITLE_CHARS = 120
EXCERPT_CHARS = 240
CONTEXT_CHARS = 160
NAME_CHARS = 80
# Speech-to-text segment boundaries overlap: an ask can still be ending when the reply
# starts. Allow the earlier line to end up to this long after the cited line starts.
LOOK_BACK_OVERLAP_SECONDS = 5.0

# Strongest first. A group shows the weakest basis among its items.
_BASIS_RANK = {'speaker': 0, 'speakers': 0, 'conversation': 1, 'none': 2}

# ----------------------------------------------------------------- redaction

_EMAIL = re.compile(r'[\w.+%-]+@[\w-]+(?:\.[\w-]+)+')
# How speech-to-text writes an address out loud: "priya at gmail dot com", "sam dot lee
# at acme dot com". "Look at this dot com" has the same shape, so a spoken address also
# needs a mail provider as its domain or a contact cue just before it.
_SPOKEN_EMAIL = re.compile(
    r'\b[\w+-]+(?: dot [\w+-]+)* at (?P<domain>[\w-]+)(?: dot [\w-]+)* dot '
    r'(?:com|org|net|edu|gov|io|co|in|uk|us|ca|au|de|ai|me|app|dev|info|biz)\b',
    re.IGNORECASE,
)
_MAIL_PROVIDERS = frozenset(
    {
        'gmail',
        'googlemail',
        'yahoo',
        'outlook',
        'hotmail',
        'live',
        'icloud',
        'me',
        'aol',
        'proton',
        'protonmail',
        'zoho',
    }
)
_EMAIL_CUE = re.compile(
    r'\b(?:e-?mail|mail|address|inbox|contact|reach (?:me|her|him|us|them)|write to'
    r'|send (?:it|this|that|them|the \w+)? ?to|ping)\b',
    re.IGNORECASE,
)
# A run of digits with phone-style separators. Colons, slashes, commas, currency
# symbols and percent signs end a run, so times (15:30), dates (10/11/2026), amounts
# ($1,200.50) and percentages never form one.
_DIGIT_RUN = re.compile(r'(?<![\w$€£¥₹:/,.])\+?\(?\d[\d ().-]*\d\)?(?![\w%/:$€£¥₹]|[.,]\d)')
_MIN_REDACTED_DIGITS = 7
# Digit groupings that read as a phone number on their own: 555-0100, (415) 555-0100,
# 415 555 0100, 1 415 555 0100, 020 7946 0958, 98765 43210, 01 23 45 67 89.
_PHONE_SHAPES = frozenset({(3, 4), (3, 3, 4), (1, 3, 3, 4), (3, 4, 4), (2, 4, 4), (5, 5), (2, 2, 2, 2, 2)})
# Pieces of a run that are not contact details: dates, year ranges, IPv4 addresses
# and short decimals (amounts, measurements).
_KEEP_PIECE = re.compile(
    r'\d{4}[-. ]\d{1,2}[-. ]\d{1,2}|\d{1,2}[-. ]\d{1,2}[-. ]\d{4}'
    r'|(?:19|20)\d{2}\s?[-–]\s?(?:19|20)\d{2}'
    r'|\d{1,3}(?:\.\d{1,3}){3}'
    r'|\d+\.\d{1,2}'
)
_YEAR = re.compile(r'(?:19|20)\d{2}')
_PHONE_CUE = re.compile(
    r'\b(?:call(?:s|ed|ing)?|text(?:s|ed|ing)?|phone|number|mobile|cell|whats ?app|ring|dial|tel|sms|reach (?:me|her|him|them))\b',
    re.IGNORECASE,
)
# A reference word makes the number an identifier ([number]), even after "number".
_ID_CUE = re.compile(
    r'\b(?:order|invoice|ticket|pnr|booking|reference|ref|tracking|account|case|confirmation|serial|receipt|po|id)'
    r'(?: (?:number|no\.?|#))?(?!\w)',
    re.IGNORECASE,
)
# An unseparated run this long reads as an account, card or ID number (and covers a bare
# 10-digit phone number with no cue), so it is never shown in full.
_MIN_ID_DIGITS = 9
# 123-45-6789 (SSN), 1234 5678 9012 (Aadhaar), 4111 1111 1111 1111 / 3782 822463 10005 (cards).
_ID_SHAPES = frozenset({(3, 2, 4), (4, 4, 4), (4, 4, 4, 4), (4, 6, 5)})
_RANGE = re.compile(r'(\d+)\s?[-–]\s?(\d+)')
# A number followed by a unit or a counted noun is a measure, not a phone number.
_UNIT_AFTER = re.compile(
    r'\s*(?:%|percent|samples?|units?|items?|people|users?|customers?|pieces?|copies|pages?|words?|rows?'
    r'|records?|seats?|steps?|km|kg|g|mg|ml|l|m|cm|mm|miles?|meters?|metres?|kilometers?|lbs?|grams?'
    r'|seconds?|minutes?|hours?|days?|weeks?|months?|years?|dollars?|rupees?|euros?|pounds?|usd|inr|eur|gbp'
    r'|bytes?|kb|mb|gb|tb)\b',
    re.IGNORECASE,
)
_PHONE_LIKE_NAME = re.compile(r'^[\d\s()+\-.]{5,}$')


def _redact_spoken_email(match: re.Match) -> str:
    left_context = match.string[max(0, match.start() - 32) : match.start()]
    if match.group('domain').casefold() in _MAIL_PROVIDERS or _EMAIL_CUE.search(left_context):
        return '[email]'
    return match.group(0)


def _digit_count(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def _last_cue_position(pattern: re.Pattern, text: str) -> int:
    positions = [match.end() for match in pattern.finditer(text)]
    return positions[-1] if positions else -1


def _is_range(piece: str) -> bool:
    """ "500-1000": two numbers joined by a bare hyphen, rising. 555-0100 is not one."""
    match = _RANGE.fullmatch(piece)
    return bool(match) and not match.group(2).startswith('0') and int(match.group(2)) > int(match.group(1))


def _placeholder(piece: str, left_context: str, right_context: str) -> Optional[str]:
    """[phone], [number], or None to keep a plain figure such as "sold 1500000 units"."""
    if piece.startswith('+'):
        return '[phone]'
    # The cue nearest the number decides: "order shipped, call me on ..." is a phone.
    phone_cue = _last_cue_position(_PHONE_CUE, left_context)
    id_cue = _last_cue_position(_ID_CUE, left_context)
    if id_cue >= 0 and id_cue >= phone_cue:
        return '[number]'
    if phone_cue >= 0:
        return '[phone]'
    groups = tuple(len(group) for group in re.split(r'\D+', piece) if group)
    measured = bool(_UNIT_AFTER.match(right_context))
    if groups in _PHONE_SHAPES and not measured and not _is_range(piece):
        return '[phone]'
    # Card, national-ID and other long account-style numbers: not contact details, but
    # not for the model's context either. A sequence of years ("2019 2020 2021") stays.
    if len(groups) == 1 and groups[0] >= _MIN_ID_DIGITS:
        return '[number]'
    if groups in _ID_SHAPES and not all(_YEAR.fullmatch(group) for group in re.split(r'\D+', piece) if group):
        return '[number]'
    return None


def _redact_digit_run(match: re.Match) -> str:
    run = match.group(0)
    if _digit_count(run) < _MIN_REDACTED_DIGITS or _KEEP_PIECE.fullmatch(run):
        return run
    left_context = match.string[max(0, match.start() - 32) : match.start()]
    right_context = match.string[match.end() : match.end() + 24]
    tokens = run.split(' ')
    # A year, date or IP can run into a number ("on 2026-10-12 415 555 0100"): keep
    # those pieces and judge the rest on its own. A leading year is only split off when
    # what follows is long enough to be a number by itself.
    out: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            piece = ' '.join(pending)
            placeholder = (
                _placeholder(piece, left_context, right_context)
                if _digit_count(piece) >= _MIN_REDACTED_DIGITS
                else None
            )
            out.append(placeholder or piece)
            pending.clear()

    for index, token in enumerate(tokens):
        rest_digits = _digit_count(' '.join(tokens[index + 1 :]))
        if _KEEP_PIECE.fullmatch(token) or (
            not pending and _YEAR.fullmatch(token) and rest_digits >= _MIN_REDACTED_DIGITS
        ):
            flush()
            out.append(token)
        else:
            pending.append(token)
    flush()
    return ' '.join(out)


def redact_contact_details(text: str) -> str:
    """Remove contact details where recognised.

    Email addresses become ``[email]``: written ones, and spoken ones ("priya at gmail
    dot com") with a mail provider domain or a contact cue (email, reach me, send it to,
    write to...) nearby. A run of seven or more digits becomes ``[phone]`` when it starts
    with ``+``, follows a phone cue (call, text, number, mobile, WhatsApp...) or is
    grouped like a phone number (555-0100, (415) 555-0100, 98765 43210) and is not a
    rising range ("500-1000") or followed by a unit ("samples", "kg"). It becomes
    ``[number]`` after a reference word (order, invoice, PNR, ticket, account...), when it
    is an unseparated run of nine or more digits, or when it is grouped like an SSN,
    Aadhaar or card number. Plain figures of eight digits or fewer, dates, times,
    amounts, percentages, version numbers, year ranges and IP addresses stay.
    Spelled-out digits and short extensions are not recognised.
    """
    text = _SPOKEN_EMAIL.sub(_redact_spoken_email, _EMAIL.sub('[email]', text))
    return _DIGIT_RUN.sub(_redact_digit_run, text)


def _clip(value: Any, limit: int) -> str:
    """One redacted line, at most ``limit`` characters, cut on a word boundary when possible."""
    text = redact_contact_details(' '.join(str(value or '').split()))
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(' ')
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(' ,;:') + '…'


# ------------------------------------------------------------------- helpers


@dataclass(frozen=True)
class Attribution:
    names: tuple[str, ...] = ()
    person_ids: tuple[str, ...] = ()
    basis: str = 'none'
    # True when the person was inferred rather than seen speaking on their own line in
    # the exchange: the model must hedge it ("probably for Priya").
    likely: bool = False

    @property
    def key(self) -> tuple[str, ...]:
        return tuple(sorted(self.person_ids))


UNATTRIBUTED = Attribution()


def _fold(value: str) -> str:
    """Case- and accent-insensitive form for comparing names."""
    decomposed = unicodedata.normalize('NFKD', value)
    return ' '.join(''.join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold().split())


def _display_name(value: Any) -> Optional[str]:
    """A usable person name, or None. Anything that looks like an address or number is dropped."""
    if not isinstance(value, str):
        return None
    name = ' '.join(value.split())[:NAME_CHARS].strip()
    if not name or '@' in name or _PHONE_LIKE_NAME.match(name) or redact_contact_details(name) != name:
        return None
    return name


def _timestamp(value: Any) -> Optional[float]:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(value, str):
        try:
            return _timestamp(datetime.fromisoformat(value.replace('Z', '+00:00')))
        except ValueError:
            return None
    return None


def _seconds(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _ordered_unique(values: Iterable[Any]) -> list:
    seen: dict = {}
    for value in values:
        if value:
            seen.setdefault(value, None)
    return list(seen)


def _structured(conversation: Mapping[str, Any]) -> Mapping[str, Any]:
    structured = conversation.get('structured')
    return structured if isinstance(structured, Mapping) else {}


# --------------------------------------------------------------------- facts


@dataclass(frozen=True)
class _ConversationFacts:
    """Everything the person rule needs from one conversation, computed once per read."""

    segments: tuple[Mapping[str, Any], ...]
    index_by_id: Mapping[str, int]
    # Distinct people tagged on their own non-user lines, in order of appearance.
    other_people: tuple[str, ...]
    # Some non-user line carries no person: someone unidentified was there.
    unidentified_voice: bool
    unnamed_roster_humans: int


@dataclass(frozen=True)
class _TaskEvidence:
    summary_item: Optional[Mapping[str, Any]]
    cited: tuple[Mapping[str, Any], ...]
    window: tuple[Mapping[str, Any], ...]


def _speaker_key(segment: Mapping[str, Any]) -> tuple[str, str]:
    """('person', id) for a line tagged with its own person, else an unknown voice.

    Diarization labels are never used to name anyone: the desktop puts every remote voice
    on one system-audio label and undiarized captures put everyone on a default label, so
    a person tagged on one line of a label says nothing about its other lines.
    """
    person_id = segment.get('person_id')
    if person_id:
        return ('person', str(person_id))
    label = segment.get('speaker') if isinstance(segment.get('speaker'), str) else segment.get('speaker_id')
    return ('unknown', str(label or ''))


def _conversation_facts(conversation: Mapping[str, Any]) -> _ConversationFacts:
    segments = tuple(s for s in conversation.get('transcript_segments') or [] if isinstance(s, Mapping))
    index_by_id: dict[str, int] = {}
    for index, segment in enumerate(segments):
        if segment.get('id') is not None:
            index_by_id.setdefault(str(segment['id']), index)
    voices = [_speaker_key(s) for s in segments if not s.get('is_user')]
    unnamed = sum(
        1
        for participant in _structured(conversation).get('participants') or []
        if isinstance(participant, Mapping)
        and not participant.get('is_ai_agent')
        and not _display_name(participant.get('name'))
    )
    return _ConversationFacts(
        segments=segments,
        index_by_id=index_by_id,
        other_people=tuple(_ordered_unique(value for kind, value in voices if kind == 'person')),
        unidentified_voice=any(kind == 'unknown' for kind, _ in voices),
        unnamed_roster_humans=unnamed,
    )


def linked_summary_item(task_id: str, conversation: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """The conversation summary item promoted into this task, linked by id only (never by text)."""
    for item in _structured(conversation).get('action_items') or []:
        if isinstance(item, Mapping) and task_id and item.get('target_task_id') == task_id:
            return item
    return None


def cited_segment_ids(task: Mapping[str, Any], summary_item: Optional[Mapping[str, Any]]) -> list[str]:
    conversation_id = task.get('conversation_id')
    for ref in task.get('provenance') or []:
        if not isinstance(ref, Mapping) or ref.get('kind') != 'conversation' or ref.get('id') != conversation_id:
            continue
        ids = _ordered_unique(str(i) for i in ref.get('transcript_segment_ids') or [] if i)
        if ids:
            return ids
    return _ordered_unique(str(i) for i in (summary_item or {}).get('source_segment_ids') or [] if i)


def _same_exchange(earlier: Mapping[str, Any], first: Mapping[str, Any]) -> bool:
    """An earlier line belongs to the exchange only if its clock says so.

    It must start before the first cited line and end between LOOK_BACK_SECONDS before
    it and LOOK_BACK_OVERLAP_SECONDS after it starts (overlapping speech). Missing
    timing, or clocks that run backwards (a merged recording restarting near zero),
    are no proof of the same exchange.
    """
    earlier_start, earlier_end = _seconds(earlier.get('start')), _seconds(earlier.get('end'))
    first_start = _seconds(first.get('start'))
    if earlier_start is None or earlier_end is None or first_start is None:
        return False
    gap = first_start - earlier_end
    return earlier_start < first_start and -LOOK_BACK_OVERLAP_SECONDS <= gap <= LOOK_BACK_SECONDS


def _task_evidence(
    task: Mapping[str, Any], conversation: Mapping[str, Any], facts: _ConversationFacts
) -> _TaskEvidence:
    summary_item = linked_summary_item(str(task.get('id') or ''), conversation)
    cited_indexes = sorted(
        {facts.index_by_id[i] for i in cited_segment_ids(task, summary_item) if i in facts.index_by_id}
    )
    if not cited_indexes:
        return _TaskEvidence(summary_item, (), ())
    first = facts.segments[cited_indexes[0]]
    window_indexes = set(cited_indexes)
    for index in range(cited_indexes[0] - 1, max(-1, cited_indexes[0] - 1 - LOOK_BACK_SEGMENTS), -1):
        if not _same_exchange(facts.segments[index], first):
            break
        window_indexes.add(index)
    return _TaskEvidence(
        summary_item,
        tuple(facts.segments[i] for i in cited_indexes),
        tuple(facts.segments[i] for i in sorted(window_indexes)),
    )


def _window_speakers(evidence: _TaskEvidence) -> list[tuple[str, str]]:
    """Distinct non-user voices in the exchange."""
    return _ordered_unique(_speaker_key(s) for s in evidence.window if not s.get('is_user'))


def _needed_person_ids(evidence: _TaskEvidence, facts: _ConversationFacts) -> list[str]:
    ids = [value for kind, value in _window_speakers(evidence) if kind == 'person']
    return ids + list(facts.other_people[:1] if len(facts.other_people) == 1 else ())


# ------------------------------------------------------------------ the rule


def _resolve(evidence: _TaskEvidence, facts: _ConversationFacts, people_by_id: Mapping[str, str]) -> Attribution:
    window = _window_speakers(evidence)
    if window:
        if all(kind == 'person' and value in people_by_id for kind, value in window):
            return Attribution(
                names=tuple(people_by_id[value] for _, value in window),
                person_ids=tuple(value for _, value in window),
                basis='speaker' if len(window) == 1 else 'speakers',
            )
        # Someone in the exchange is untagged or unknown, so nobody can be credited
        # with certainty, and the one-voice fallback below would ignore them.
        return UNATTRIBUTED

    one_voice = len(facts.other_people) == 1 and not facts.unidentified_voice and not facts.unnamed_roster_humans
    if one_voice and facts.other_people[0] in people_by_id:
        person_id = facts.other_people[0]
        return Attribution(names=(people_by_id[person_id],), person_ids=(person_id,), basis='conversation', likely=True)
    return UNATTRIBUTED


def resolve_counterparty(
    task: Mapping[str, Any],
    conversation: Optional[Mapping[str, Any]],
    people_by_id: Mapping[str, str],
) -> Attribution:
    """Who a user-owned commitment was made to. Pure: no reads, no model, no name guessing.

    1. Non-user lines in the cited lines plus up to two lines just before them in the
       same exchange (see ``_same_exchange``). Every one must be tagged with a known
       person; any untagged line makes the item unattributed.
    2. Otherwise, if exactly one person spoke in the whole conversation, every other
       non-user line is tagged with them, and no unnamed human is on the meeting
       roster: that person, as a likely 'conversation' basis.
    3. Otherwise unattributed, as is any task whose conversation is gone.
    """
    if not conversation:
        return UNATTRIBUTED
    facts = _conversation_facts(conversation)
    return _resolve(_task_evidence(task, conversation, facts), facts, people_by_id)


# ------------------------------------------------------------------ the read


def _resolve_since(since: Optional[str], now: datetime) -> datetime:
    if not since:
        return now - timedelta(days=DEFAULT_WINDOW_DAYS)
    return min(max(parse_iso_date(since, 'since'), now - timedelta(days=MAX_WINDOW_DAYS)), now)


def _match_person(attribution: Attribution, person_filter: str) -> Optional[str]:
    """'exact', 'partial' or None.

    "Priya" finding "Priya Shah" is a normal match. "Sam Rivera" finding a contact saved as
    "Sam" is partial: the query names more than the contact does, so it may be another Sam
    and the model checks. (Several people matching one query is flagged by the caller.)
    """
    query = set(person_filter.split())
    best: Optional[str] = None
    for name in attribution.names:
        tokens = set(_fold(name).split())
        if not query or not tokens:
            continue
        if query <= tokens:
            return 'exact'
        if tokens <= query:
            best = 'partial'
    return best


def _attribution_payload(attribution: Attribution) -> dict:
    return {
        'names': list(attribution.names),
        'person_ids': list(attribution.person_ids),
        'basis': attribution.basis,
        'likely': attribution.likely,
    }


def _commitment(
    task: Mapping[str, Any],
    conversation: Optional[Mapping[str, Any]],
    evidence: Optional[_TaskEvidence],
    attribution: Attribution,
) -> dict:
    item: dict[str, Any] = {
        'task_id': str(task.get('id') or ''),
        'description': _clip(task.get('description'), DESCRIPTION_CHARS),
        'due_at': safe_isoformat(task.get('due_at')),
        'due_certainty': None,
        'created_at': safe_isoformat(task.get('created_at')),
        'conversation_id': str(task.get('conversation_id') or ''),
        'conversation_title': None,
        'conversation_started_at': None,
        'excerpt': None,
        'context': None,
        'attribution': _attribution_payload(attribution),
        'partial_match': False,
    }
    if conversation and evidence:
        item['conversation_title'] = _clip(_structured(conversation).get('title'), TITLE_CHARS) or None
        item['conversation_started_at'] = safe_isoformat(
            conversation.get('started_at') or conversation.get('created_at')
        )
        item['excerpt'] = _clip(' '.join(str(s.get('text') or '') for s in evidence.cited), EXCERPT_CHARS) or None
        if evidence.summary_item:
            item['context'] = _clip(evidence.summary_item.get('context'), CONTEXT_CHARS) or None
            if evidence.summary_item.get('due_certainty') in {'confirmed', 'tentative'}:
                item['due_certainty'] = evidence.summary_item['due_certainty']
    return item


def _sort_key(item: Mapping[str, Any]) -> tuple[float, float]:
    """Soonest due first (undated last), then newest."""
    due = _timestamp(item.get('due_at'))
    created = _timestamp(item.get('created_at')) or 0.0
    return (due if due is not None else float('inf'), -created)


def _empty_totals() -> dict:
    return {'people': 0, 'commitments': 0, 'unattributed': 0, 'excluded_unknown_owner': 0, 'not_checked': 0}


def _error(text: str) -> dict:
    return {
        'result_text': text,
        'since': None,
        'groups': [],
        'unattributed': [],
        'sources': [],
        'totals': _empty_totals(),
        'truncated': False,
    }


def _group_commitments(attributed: list[tuple[Attribution, dict]], limit_people: int) -> tuple[list[dict], int, bool]:
    """Group by person, sort, and apply the people, per-person and overall caps."""
    grouped: dict[tuple[str, ...], list[tuple[Attribution, dict]]] = {}
    for attribution, item in attributed:
        grouped.setdefault(attribution.key, []).append((attribution, item))
    ordered = []
    for members in grouped.values():
        items = sorted((item for _, item in members), key=_sort_key)
        first = members[0][0]
        basis = max((attribution.basis for attribution, _ in members), key=lambda b: _BASIS_RANK.get(b, 2))
        likely = any(attribution.likely for attribution, _ in members)
        ordered.append((_sort_key(items[0]), first, basis, likely, items))
    ordered.sort(key=lambda entry: entry[0])

    truncated = len(ordered) > limit_people
    budget = MAX_COMMITMENTS
    groups = []
    for _, first, basis, likely, items in ordered[:limit_people]:
        shown = items[: min(MAX_PER_PERSON, budget)]
        truncated = truncated or len(shown) < len(items)
        if not shown:
            continue
        budget -= len(shown)
        groups.append(
            {
                'names': list(first.names),
                'person_ids': list(first.person_ids),
                'basis': basis,
                'likely': likely,
                'partial_match': any(item['partial_match'] for item in items),
                'open_count': len(items),
                'commitments': shown,
            }
        )
    return groups, len(ordered), truncated


def _sources(groups: list[dict], unattributed: list[dict], visible: Mapping[str, Mapping[str, Any]]) -> list[dict]:
    sources: dict[str, dict] = {}
    for item in [c for group in groups for c in group['commitments']] + unattributed:
        conversation_id = item['conversation_id']
        if conversation_id not in visible or conversation_id in sources:
            continue
        sources[conversation_id] = {
            'kind': 'conversation',
            'source_id': conversation_id,
            'title': _clip(item.get('conversation_title') or 'Conversation', 160),
            'preview': item.get('excerpt') or '',
            'created_at': item.get('conversation_started_at'),
        }
    return list(sources.values())


def _result_text(groups: list[dict], unattributed: list[dict], totals: dict, truncated: bool, since: datetime) -> str:
    since_label = since.strftime('%Y-%m-%d')
    if not groups and not unattributed:
        lines = [f"No open commitments to other people found since {since_label}."]
    else:
        lines = [f"Open commitments you made to other people since {since_label}:"]
        for group in groups:
            parts = [
                c['description'] + (f" (due {c['due_at']})" if c.get('due_at') else '') for c in group['commitments']
            ]
            who = ', '.join(group['names']) + (' (likely)' if group['likely'] else '')
            who += ' (partial name match)' if group['partial_match'] else ''
            lines.append(f"- {who} ({group['open_count']}): {'; '.join(parts)}")
        if unattributed:
            parts = [c['description'] for c in unattributed]
            lines.append(f"- Person not identified ({totals['unattributed']}): {'; '.join(parts)}")
    if totals['excluded_unknown_owner']:
        lines.append(
            f"{totals['excluded_unknown_owner']} more captured item(s) have an unclear owner and are not shown."
        )
    if totals['not_checked']:
        lines.append(f"{totals['not_checked']} older item(s) were not checked.")
    if truncated:
        lines.append("Some commitments were left out to keep this short.")
    return '\n'.join(lines)


def get_commitments_result(
    uid: str,
    since: Optional[str] = None,
    person: Optional[str] = None,
    limit_people: int = DEFAULT_LIMIT_PEOPLE,
    now: Optional[datetime] = None,
) -> dict:
    """Owner-scoped read: one task query, one conversation batch, one people batch."""
    now = now or datetime.now(timezone.utc)
    try:
        since_dt = _resolve_since(since, now)
    except ValueError as e:
        return _error(f"Error: Invalid since format: {e}")
    limit_people = max(1, min(int(limit_people), MAX_LIMIT_PEOPLE))
    person_filter = _fold(person or '')

    try:
        # One row past the cap tells a full page from a cut one, and the scan report
        # says when soft-deleted rows used up the stream before older live ones.
        scan_report: dict[str, Any] = {}
        rows = list(
            action_items_db.get_action_items(
                uid=uid,
                completed=False,
                start_date=since_dt,
                limit=TASK_SCAN_LIMIT + 1,
                extra_fields=('provenance',),
                scan_report=scan_report,
            )
            or []
        )
        scan_cut = len(rows) > TASK_SCAN_LIMIT or bool(scan_report.get('hit_limit'))
        kept: list[dict] = []
        excluded_unknown_owner = 0
        for row in rows[:TASK_SCAN_LIMIT]:
            if not is_open_conversation_task(row):
                continue
            owner = row.get('owner') or 'unknown'
            if owner == 'user':
                kept.append(row)
            elif owner == 'unknown':
                excluded_unknown_owner += 1
            # owner == 'other' is "what people owe me", deliberately out of scope.

        kept.sort(key=lambda task: -(_timestamp(task.get('created_at')) or 0.0))
        conversation_ids = _ordered_unique(str(task['conversation_id']) for task in kept)
        read_ids = conversation_ids[:CONVERSATION_CAP]
        conversations = conversations_db.get_conversations_by_id_without_photos(uid, read_ids) if read_ids else []
        # Deleted and discarded conversations never come back; locked ones lose their content.
        visible = {
            str(c.get('id')): c for c in conversations or [] if isinstance(c, Mapping) and not c.get('is_locked')
        }
        facts = {conversation_id: _conversation_facts(c) for conversation_id, c in visible.items()}

        read_set = set(read_ids)
        checked = [task for task in kept if str(task['conversation_id']) in read_set]
        not_checked = len(kept) - len(checked)
        evidence: dict[int, _TaskEvidence] = {}
        for index, task in enumerate(checked):
            conversation_id = str(task['conversation_id'])
            if conversation_id in visible:
                evidence[index] = _task_evidence(task, visible[conversation_id], facts[conversation_id])

        person_ids = _ordered_unique(
            pid
            for index, task in enumerate(checked)
            if index in evidence
            for pid in _needed_person_ids(evidence[index], facts[str(task['conversation_id'])])
        )
        people_by_id: dict[str, str] = {}
        for person_doc in users_db.get_people_by_ids(uid, person_ids) if person_ids else []:
            name = _display_name(person_doc.get('name')) if isinstance(person_doc, Mapping) else None
            if name and person_doc.get('id'):
                people_by_id[str(person_doc['id'])] = name

        attributed: list[tuple[Attribution, dict]] = []
        unattributed_all: list[dict] = []
        for index, task in enumerate(checked):
            conversation_id = str(task['conversation_id'])
            conversation = visible.get(conversation_id)
            task_evidence = evidence.get(index)
            attribution = (
                _resolve(task_evidence, facts[conversation_id], people_by_id)
                if conversation is not None and task_evidence is not None
                else UNATTRIBUTED
            )
            item = _commitment(task, conversation, task_evidence, attribution)
            if attribution.basis == 'none':
                unattributed_all.append(item)
                continue
            match = _match_person(attribution, person_filter) if person_filter else 'exact'
            if match:
                item['partial_match'] = match == 'partial'
                attributed.append((attribution, item))
        if person_filter and len({attribution.key for attribution, _ in attributed}) > 1:
            # "Priya" matched more than one person: none of them is certainly the one meant.
            for _, item in attributed:
                item['partial_match'] = True
    except Exception as e:
        # Type only: messages from the store can carry task or transcript text.
        logger.error('get_commitments_result failed: %s', type(e).__name__)
        return _error("Error: Could not load commitments right now.")

    if person_filter:
        # "What do I owe Priya?" answers only with items attributed to that name.
        # Unattributed and unclear-owner items are about nobody in particular, so they
        # are not reported against the person either.
        unattributed_all = []
        excluded_unknown_owner = 0

    groups, total_people, truncated = _group_commitments(attributed, limit_people)
    unattributed_all.sort(key=_sort_key)
    unattributed = unattributed_all[:MAX_UNATTRIBUTED]
    truncated = truncated or len(unattributed_all) > MAX_UNATTRIBUTED or not_checked > 0 or scan_cut
    totals = {
        'people': total_people,
        'commitments': len(attributed),
        'unattributed': len(unattributed_all),
        'excluded_unknown_owner': excluded_unknown_owner,
        'not_checked': not_checked,
    }
    return {
        'result_text': _result_text(groups, unattributed, totals, truncated, since_dt),
        'since': since_dt.isoformat(),
        'groups': groups,
        'unattributed': unattributed,
        'sources': _sources(groups, unattributed, visible),
        'totals': totals,
        'truncated': truncated,
    }
