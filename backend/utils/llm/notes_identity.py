"""Server-owned identity evidence for notes. People search is spelling data, never a voice binding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from config.refactor_modes import default_on

IDENTITY_REPAIR_ENV = 'SPEAKER_IDENTITY_REPAIR_ENABLED'


def _pattern(name: str) -> re.Pattern[str]:
    return re.compile(r'(?<!\w)' + re.escape(name) + r'(?!\w)', re.IGNORECASE)


def _corrected_name(name: str, corrections: tuple[str, ...]) -> bool:
    # Corrections may mention the rejected name too ("It was Phong, not Michael").
    # Require an affirmative identity clause rather than a substring anywhere.
    cue = r'(?:speaker\s+[\w-]+\s+(?:is|was)|counterpart\s+(?:is|was)|it\s+was|talking\s+(?:to|with))\s+'
    for text in corrections:
        for match in re.finditer(cue + re.escape(name) + r'(?!\w)', text, re.IGNORECASE):
            clause = re.split(r'[,.;\n]', text[: match.start()])[-1]
            if not re.search(r"\b(?:not|never|\w+n['’]t)\b", clause, re.IGNORECASE):
                return True
    return False


@dataclass
class NotesIdentity:
    # These are copied from the speaker authority before any roster/name inference.
    speaker_names: tuple[tuple[str, str | None], ...] = ()
    meeting_names: tuple[str, ...] = ()
    owner_names: tuple[str, ...] = ()
    transcript: str = ''
    corrections: tuple[str, ...] = ()

    def supported(self, name: str, speaker: str | None = None) -> bool:
        owners = {value.casefold() for value in self.owner_names if value}
        owners.update(token for value in tuple(owners) for token in value.split())
        named = {key: value.casefold() for key, value in self.speaker_names if value}
        # Profile identity and attendance are context, not proof of which voice
        # spoke. Preserve owner aliases only for an actually bound owner voice.
        if speaker is not None and speaker in named:
            return named[speaker] == name.casefold() or (named[speaker] in owners and name.casefold() in owners)
        if name.casefold() in owners and any(value in owners for value in named.values()):
            return speaker is None
        if speaker is None and name.casefold() in named.values():
            return True
        return _corrected_name(name, self.corrections)


def notes_identity(prefix: Any, inputs: Mapping[str, Any], packet: Mapping[str, Any] | None = None) -> NotesIdentity:
    """Take only server-supplied, conversation-tied fields; never parse model evidence lines."""
    packet = packet or {}
    meeting: list[str] = list(getattr(prefix, 'meeting_names', ()))
    roster = inputs.get('roster')
    meeting.extend(
        entry.display_name for entry in getattr(roster, 'entries', ()) if entry.kind == 'human' and entry.display_name
    )
    for event in packet.get('calendar_overlap') or ():
        meeting.extend(name for name in event.get('participants') or () if isinstance(name, str))
    meeting.extend(
        row['name'] for row in packet.get('listed_participants') or () if row.get('kind') == 'human' and row.get('name')
    )
    meeting.extend(
        row['name']
        for row in packet.get('people_on_screen') or ()
        if row.get('call_seen_during_conversation') and row.get('name')
    )
    return NotesIdentity(
        speaker_names=getattr(prefix, 'speaker_names', ()),
        meeting_names=tuple(dict.fromkeys(meeting)),
        owner_names=tuple(
            name for name in (getattr(prefix, 'account_owner_name', None), *getattr(prefix, 'owner_names', ())) if name
        ),
        transcript=getattr(prefix, 'transcript_body', ''),
        corrections=tuple(
            str(row.get('note') or '') for row in inputs.get('user_corrections') or () if isinstance(row, Mapping)
        ),
    )


# IDs, citation arrays, enum fields and timestamps are not visible prose.
_TEXT_FIELDS = frozenset(
    (
        'title',
        'overview',
        'heading',
        'body_markdown',
        'description',
        'context',
        'owner_name',
        'text',
        'name',
        'evidence',
        'organization',
        'role',
        'email',
        'actor',
    )
)


def repair_identity(submission: Mapping[str, Any], identity: NotesIdentity) -> tuple[dict[str, Any], list[str]]:
    """Reject unsupported participant bindings, never catalog-only prose mentions.

    A heard name can survive as a hedged rendering, never as a verified participant
    or a title lead. No probabilities or speaker labels are invented here.
    """
    if not default_on(IDENTITY_REPAIR_ENV):
        return dict(submission), []
    people = [person for person in submission.get('participants') or () if isinstance(person, Mapping)]
    participant_names = {
        str(person.get('name') or '').strip()
        for person in people
        if not person.get('is_ai_agent')
        and not identity.supported(str(person.get('name') or '').strip(), person.get('speaker') or None)
    }
    blocked = participant_names
    blocked.discard('')
    blocked = {name for name in blocked if not re.fullmatch(r'(?i)(?:a speaker|speaker [A-Z])', name)}
    if not blocked:
        return dict(submission), []
    # A model may switch from a full catalog name to its first name mid-note.
    # Do not erase a first name shared by a supported identity.
    supported = (
        [name for _, name in identity.speaker_names if name] + list(identity.meeting_names) + list(identity.owner_names)
    )
    aliases = set(blocked)
    for name in blocked:
        tokens = name.split()
        if len(tokens) > 1 and _pattern(name).search(str(submission)):
            for token in (tokens[0], tokens[-1]):
                if len(token) > 2 and not any(token.casefold() in value.casefold().split() for value in supported):
                    aliases.add(token)
    names = sorted(aliases, key=len, reverse=True)
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(name) for name in names) + r')(?!\w)', re.IGNORECASE)
    title_pattern = re.compile(pattern.pattern + r"(?:['’]s)?", re.IGNORECASE)
    changed = False

    def scrub(value: Any, key: str = '') -> Any:
        nonlocal changed
        if isinstance(value, Mapping):
            return {field: scrub(child, field) for field, child in value.items()}
        if isinstance(value, list):
            return [scrub(child, key) for child in value]
        if not isinstance(value, str) or key not in _TEXT_FIELDS:
            return value

        def replace(match: re.Match[str]) -> str:
            name = match.group()
            if key == 'title':
                return ''
            if _pattern(name).search(identity.transcript):
                if any(_pattern(name).search(value) for value in participant_names):
                    return f'a speaker (name heard as “{name}”)'
                return f'“{name}” (as heard)'
            return 'a speaker'

        # Repairs also run after parsing and on salvaged submissions. Protect
        # the hedge we authored so repeated enforcement is idempotent.
        parts = (
            [value]
            if key == 'title'
            else re.split(r'(a speaker \(name heard as “[^”]+”\)|“[^”]+” \(as heard\))', value)
        )
        active_pattern = title_pattern if key == 'title' else pattern
        output = []
        for index, part in enumerate(parts):
            heard = re.search(r'“([^”]+)”', part) if index % 2 else None
            # A model can emit our hedge syntax too; the source must still contain the name.
            output.append(
                part if heard and _pattern(heard[1]).search(identity.transcript) else active_pattern.sub(replace, part)
            )
        result = ''.join(output)
        if key == 'title' and result != value:
            result = re.sub(r'^\W+|\W+$', '', result).strip()
            result = result or 'Conversation'
        changed |= result != value
        return result

    kept = [
        person for person in people if person.get('is_ai_agent') or str(person.get('name') or '').strip() not in blocked
    ]
    repaired = scrub({**submission, 'participants': kept})
    return repaired, ['unsupported_speaker_identity'] if changed or len(kept) != len(people) else []
