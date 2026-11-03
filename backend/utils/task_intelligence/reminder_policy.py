"""Explicit-reminder validation on notes output. No model, store, or provider calls.

Lexical checks may veto or retain review work; they never extract a task. The notes
packet is still the sole producer of task descriptions and cited claims.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import calendar
import hashlib
import json
import re
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.explicit_reminders import FLAG as FLAG, POLICY_REVISION as POLICY_REVISION, enabled as enabled
from models.task_due import ReminderOrigin, TaskDue
from utils.conversations.owner_attribution import speaker_role_map

REMINDER_RULES = '''EXPLICIT REMINDER CLAIMS (explicit-reminders-v1)
- Use this schema in the SAME notes extraction; never add an extraction call.
- For a direct future "remind me" or "don't let me forget" request, including errands,
  emit reminder_intent.kind=explicit_reminder and exact source_segment_ids. This does
  not require a wake word. Keep unknown speakers as review candidates; never guess
  the owner from a name, cluster number, calendar, or legacy is_user label.
- Copy the exact spoken date/time substring into reminder_intent.due_expression;
  do not supply a guessed year, timezone or hour. Leave due_at empty for reminders:
  the server resolves precision from the source clock, never processing time.
- Quoted/reported, hypothetical, current-session AI commands, ongoing/completed
  narration and other people's promises are not explicit owner reminders. Label
  them quoted/hypothetical/current_session/status/waiting_on, respectively.
- "Investigate this now" is a current-session command; "remind me tomorrow to
  review the investigation" is a future reminder. Explicit "remind me to get fuel"
  survives; "getting fuel now" alone is status. Never rewrite manual tasks.
- Other people's promises stay waiting-on follow-ups, never the owner's commitments.
  Broad call/waiting-on inference is deferred; do not admit it via this reminder path.
'''


def source_input(conversation: Any) -> dict[str, Any]:
    """Minimal recorded-clock/identity input for notes and its retry fingerprint."""
    fields = (
        'id',
        'text',
        'start',
        'end',
        'speaker_id',
        'speaker_id_scope',
        'is_user',
        'person_id',
        'speaker_label_source',
        'speaker_identity_status',
        'speaker_match_source',
    )
    return {
        'started_at': getattr(conversation, 'recorded_start', None) or getattr(conversation, 'started_at', None),
        'capture_timezone': getattr(conversation, 'capture_timezone', None),
        'transcript_segments': [
            {key: getattr(row, key, None) for key in fields}
            for row in getattr(conversation, 'transcript_segments', ()) or ()
        ],
    }


def instructions(base: str) -> str:
    return base + '\n\n' + REMINDER_RULES if enabled() else base


@dataclass(frozen=True)
class SpeakerEvidence:
    owner: str = 'unknown'
    revision: str = 'speaker-role-map-v1'


def speaker_evidence(segments: Sequence[Any], *, cited_ids: set[str] | None = None) -> SpeakerEvidence:
    """Only seam to identity. Reuse its decisions; do not infer new identities here."""
    roles = speaker_role_map(segments)
    values = {roles.for_segment(row).role for row in segments if cited_ids is None or row.id in cited_ids}
    owner = 'user' if values == {'primary_user'} else 'other' if values == {'other'} else 'unknown'
    decision_bytes = json.dumps(
        [
            [
                getattr(row, key, None)
                for key in (
                    'id',
                    'speaker_id',
                    'speaker_id_scope',
                    'is_user',
                    'person_id',
                    'speaker_label_source',
                    'speaker_identity_status',
                    'speaker_match_source',
                )
            ]
            for row in segments
        ],
        default=str,
        sort_keys=True,
    ).encode()
    return SpeakerEvidence(owner, 'speaker-role-map-v1:' + hashlib.sha256(decision_bytes).hexdigest()[:32])


def _unresolved(expression: str, reason: str) -> TaskDue:
    return TaskDue(kind='unresolved', expression=expression, reason=reason)


def resolve_due(expression: str | None, *, source_at: datetime | None, capture_timezone: str | None) -> TaskDue:
    """Bounded deterministic grammar; unsupported/ambiguous speech stays unresolved.

    ISO dates/times, English month/day (including ordinals), today and tomorrow.
    DST folds/gaps require an explicit offset. Past explicit dates are preserved.
    """
    if not expression:
        return TaskDue(kind='none')
    if not source_at or source_at.utcoffset() is None:
        return _unresolved(expression, 'missing_source_clock')
    try:
        zone = ZoneInfo(capture_timezone or '')
    except (ValueError, ZoneInfoNotFoundError):
        return _unresolved(expression, 'missing_capture_timezone')
    local_source = source_at.astimezone(zone)
    text = re.sub(r'^(?:on|at|by)\s+', '', expression.strip().lower()).strip(' .')
    # Explicit ISO datetimes carry their own hour; never fill one for a date.
    if re.fullmatch(r'\d{4}-\d\d-\d\d[t ]\d\d:\d\d(?::\d\d)?(?:z|[+-]\d\d:\d\d)?', text):
        try:
            instant = datetime.fromisoformat(text.replace('z', '+00:00'))
            if instant.utcoffset() is None:
                first = instant.replace(tzinfo=zone, fold=0)
                second = instant.replace(tzinfo=zone, fold=1)
                if first.utcoffset() != second.utcoffset():
                    return _unresolved(expression, 'dst_gap_or_fold')
                if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != instant:
                    return _unresolved(expression, 'dst_gap_or_fold')
                instant = first
            elif instant.astimezone(zone).utcoffset() != instant.utcoffset():
                return _unresolved(expression, 'offset_timezone_conflict')
            return TaskDue(
                kind='instant',
                instant=instant.astimezone(timezone.utc),
                timezone=zone.key,
                expression=expression,
                year_basis='spoken',
            )
        except ValueError:
            return _unresolved(expression, 'invalid_date_or_time')
    basis = 'spoken'
    try:
        if re.fullmatch(r'\d{4}-\d\d-\d\d', text):
            resolved = date.fromisoformat(text)
        elif text in {'today', 'tomorrow'}:
            resolved = local_source.date() + timedelta(days=text == 'tomorrow')
            basis = 'source_relative'
        else:
            ordinals = [
                'first',
                'second',
                'third',
                'fourth',
                'fifth',
                'sixth',
                'seventh',
                'eighth',
                'ninth',
                'tenth',
                'eleventh',
                'twelfth',
                'thirteenth',
                'fourteenth',
                'fifteenth',
                'sixteenth',
                'seventeenth',
                'eighteenth',
                'nineteenth',
                'twentieth',
                'twenty first',
                'twenty second',
                'twenty third',
                'twenty fourth',
                'twenty fifth',
                'twenty sixth',
                'twenty seventh',
                'twenty eighth',
                'twenty ninth',
                'thirtieth',
                'thirty first',
            ]
            text = text.replace('-', ' ')
            months = {name.lower(): n for n, name in enumerate(calendar.month_name) if name}
            match = re.fullmatch(r'([a-z]+)\s+(?:the\s+)?(.+?)(?:,?\s+(\d{4}))?', text)
            if not match or match[1] not in months:
                return _unresolved(expression, 'unsupported_or_ambiguous_expression')
            token = re.sub(r'(\d)(?:st|nd|rd|th)$', r'\1', match[2])
            day = int(token) if token.isdigit() else ordinals.index(token) + 1
            month = months[match[1]]
            if match[3]:
                resolved = date(int(match[3]), month, day)
            else:
                # A direct future reminder uses the next valid occurrence, including leap day.
                basis = 'next_future_occurrence'
                resolved = None
                for year in range(local_source.year, local_source.year + 9):
                    try:
                        candidate = date(year, month, day)
                    except ValueError:
                        continue
                    if candidate >= local_source.date():
                        resolved = candidate
                        break
                if resolved is None:
                    return _unresolved(expression, 'invalid_date')
        return TaskDue(
            kind='date', date=resolved.isoformat(), timezone=zone.key, expression=expression, year_basis=basis
        )
    except (ValueError, OverflowError):
        return _unresolved(expression, 'invalid_date')


_DIRECT = re.compile(r"^(?:please\s+)?(?:hey\s+omi[,!]?\s+)?(?:remind me\b|don['’]?t let me forget\b)", re.I)
# This conservative grammar deliberately abstains on narration before a reminder.


def prepare_reminder(
    item: Any,
    *,
    conversation: Any,
    extracted_at: datetime,
    evidence: Callable[[Sequence[Any]], SpeakerEvidence] | None = None,
) -> Any | None:
    """Validate an extracted claim and return a precision-safe copy, or decline it."""
    intent = getattr(item, 'reminder_intent', None)
    if intent is None:
        return item
    if (
        not enabled()
        or intent.kind != 'explicit_reminder'
        or getattr(item, 'candidate_action', None) in {'update', 'complete'}
    ):
        return None
    ids: set[str] = set(getattr(item, 'source_segment_ids', ()) or ())
    all_segments = getattr(conversation, 'transcript_segments', ()) or ()
    cited = [row for row in all_segments if getattr(row, 'id', None) in ids]
    if not ids or ids != {row.id for row in cited}:
        return None
    if not all(_DIRECT.match(row.text.strip()) for row in cited):
        return None
    expression = intent.due_expression
    if expression and not any(expression.casefold() in row.text.casefold() for row in cited):
        return None
    speaker = evidence(cited) if evidence else speaker_evidence(all_segments, cited_ids=ids)
    if speaker.owner == 'other':
        # Other people's promises/follow-ups need their own labeled consumer.
        return None
    start = getattr(conversation, 'recorded_start', None) or getattr(conversation, 'started_at', None)
    source_at = start + timedelta(seconds=max(0, min(row.start for row in cited))) if start else None
    if source_at is not None and source_at.utcoffset() is None:
        source_at = None
    capture_timezone = getattr(conversation, 'capture_timezone', None)
    due = resolve_due(expression, source_at=source_at, capture_timezone=capture_timezone)
    # Revision contains evidence hashes only, never text in diagnostics or ids.
    revision = hashlib.sha256(
        json.dumps(
            [(row.id, row.start, row.end, row.text) for row in cited],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    previous_origin = getattr(item, 'reminder_origin', None)
    if (
        previous_origin is not None
        and previous_origin.policy_revision == POLICY_REVISION
        and previous_origin.input_revision == revision
        and previous_origin.speaker_evidence_revision == speaker.revision
        and previous_origin.source_at == source_at
    ):
        # Revalidating already-extracted/cached notes is not another extraction.
        extracted_at = previous_origin.extracted_at
    origin = ReminderOrigin(
        input_revision=revision,
        speaker_evidence_revision=speaker.revision,
        source_at=source_at,
        extracted_at=extracted_at,
        review_reason='owner_unresolved' if speaker.owner == 'unknown' else None,
    )
    context: str = getattr(item, 'context', None) or ''
    if due.kind == 'date' and due.date and due.date not in context:
        context = f'{context} Due {due.date} (all day, {due.timezone}).'.strip()
    if due.kind == 'unresolved' and due.expression and due.expression not in context:
        context = f'{context} Date needs review: {due.expression}.'.strip()
    if speaker.owner == 'unknown' and not context.startswith('Review speaker:'):
        context = f'Review speaker: confirm who requested this reminder. {context}'.strip()
    updates = dict(
        context=context,
        due=due.model_dump(mode='python'),
        due_at=due.instant,
        reminder_origin=origin.model_dump(mode='python'),
        capture_owner=speaker.owner,
        capture_kind='explicit_command',
        concrete_deliverable=True,
        ownership_confidence=1.0 if speaker.owner == 'user' else 0.0,
    )
    # Revalidate SDK/fallback models without relying on Pydantic class identity.
    return type(item).model_validate({**item.model_dump(mode='python'), **updates})
