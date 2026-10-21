"""Non-prompt validation and sanitization for meeting-notes output.

These helpers were split out of ``conversation_processing`` so that module stays
focused on LLM orchestration. ``conversation_processing`` re-exports the names
callers and tests already import from it.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Sequence

from models.structured import Participant, Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.
from utils.conversations.meeting_participants import MeetingRoster

# v3 consumes whole citation units and protects Markdown code before every repair.
PRESENTATION_CONTRACT_VERSION = 'v3'


@dataclass
class PresentationContractReport:
    """Bounded, content-free evidence about generated-note conformance."""

    repairs: set[str] = field(default_factory=set)
    violations: set[str] = field(default_factory=set)

    @property
    def needs_revision(self) -> bool:
        return bool(self.violations)


def _validate_source_segment_ids(values: Any, valid_ids: set[str]) -> list[str]:
    """Keep valid, unique source IDs in model order; reject all other values."""

    if not valid_ids or not values:
        return []
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or value not in valid_ids or value in seen:
            continue
        seen.add(value)
        validated.append(value)
    return validated


def validate_structured_source_segment_ids(
    structured: Structured, transcript_segment_ids: Optional[Iterable[object]]
) -> Structured:
    """Drop fabricated/duplicate evidence references from any summary output.

    The caller supplies IDs from typed ``TranscriptSegment`` objects. This
    boundary intentionally has no transcript-string parser: external text and
    bracket-like content are not evidence of a persisted segment identity.
    """

    valid_ids = {
        segment_id for segment_id in (transcript_segment_ids or ()) if isinstance(segment_id, str) and segment_id
    }
    for section in structured.sections:
        section.source_segment_ids = _validate_source_segment_ids(section.source_segment_ids, valid_ids)
    for action_item in structured.action_items:
        action_item.source_segment_ids = _validate_source_segment_ids(action_item.source_segment_ids, valid_ids)
    return structured


_MARKDOWN_LINK_RE = re.compile(r'\[([^\]\n]*)\]\(([^)\n]*)\)')
_PARENTHETICAL_RE = r'(?<!\])\(((?:[^()\n]|\([^()\n]*\))+)\)'
_BRACKET_UNIT_RE = re.compile(r'\[[^\[\]\n]*\]\([^\n)]*\)|[\[［【][^\[\]［］【】\n]*[\]］】]')
_CITATION_UNIT_RE = re.compile(
    r'\[[^\[\]\n]*\]\([^\n)]*\)|' + _PARENTHETICAL_RE + r'|[\[［【][^\[\]［］【】\n]*[\]］】]'
)
_CODE_RE = re.compile(
    r'(?m)^[ \t]{0,3}(?P<fence>`{3,}|~{3,})[^\n]*\n[\s\S]*?'
    r'(?:^[ \t]{0,3}(?P=fence)[`~]*[ \t]*(?:\n|$)|\Z)|(?P<ticks>`+)(?!`)[\s\S]*?(?<!`)(?P=ticks)(?!`)'
)
_ID_LIKE_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z')
_CLUSTER_RE = re.compile(r'[?]?[0-9A-Za-z]{1,3}\Z')
_SAFE_MARKDOWN_SCHEMES = {'http', 'https', 'mailto'}
_REMOVAL_MARKER = '\x00'
_ADORNMENTS = str.maketrans('', '', '\u200b\u200c\u200d\u2060\ufeff')


def _id_pattern(source_id: str) -> re.Pattern[str]:
    return re.compile(rf'(?<![\w-]){re.escape(source_id)}(?![\w-])')


def _clean_after_removal(text: str) -> str:
    # Collapse adjacent removals first, so repeated empty shells leave no extra spaces.
    marker = re.escape(_REMOVAL_MARKER)
    text = re.sub(rf'{marker}(?:[ \t]*{marker})+', _REMOVAL_MARKER, text)
    text = re.sub(rf'[ \t]+{marker}[ \t]+', ' ', text)
    text = re.sub(rf'[ \t]+{marker}(?=[,.;:]|\n|$)', '', text)
    text = re.sub(rf'{marker}[ \t]+', '', text)
    return text.replace(_REMOVAL_MARKER, '').strip()


def _clean_separators(text: str) -> str:
    """Clean separators only inside a unit whose citation content was removed."""
    text = text.replace(_REMOVAL_MARKER, '').replace('\x01', '')
    text = re.sub(r'^[\s,;]+|[\s,;]+$', '', text)
    return re.sub(r'([,;])(?:\s*[,;])+', r'\1', text)


def _clean_parenthetical_removals(text: str) -> str:
    # Propagate an empty-shell marker outward through arbitrarily nested parens.
    # Unlike a whole citation, an emptied prose parenthetical preserves outer spacing.
    def clean(match: re.Match[str]) -> str:
        value = match.group(0)
        if _REMOVAL_MARKER not in value and '\x01' not in value:
            return value
        content = _clean_separators(value[1:-1])
        return '(' + content + ')' if content else '\x01'

    while True:
        cleaned = re.sub(r'\([^()\n]*\)', clean, text)
        if cleaned == text:
            return text
        text = cleaned


def _bracket_ids(content: str, valid_ids: set[str]) -> list[str]:
    tokens = [token for token in re.split(r'[\s,;]+', content.strip()) if token]
    if tokens and all(token in valid_ids for token in tokens):
        return tokens
    header = content.split()
    if len(header) == 2 and header[0] in valid_ids and _CLUSTER_RE.fullmatch(header[1]):
        return header[:1]
    return []


def _repair_note_citation_pass(
    text: str,
    valid_ids: set[str],
    *,
    safe_fallback: bool = True,
    report: Optional[PresentationContractReport] = None,
) -> tuple[str, list[str]]:
    """Render-time sweep and generation-time gate; never edit a partial bracket unit.

    Unknown single-token brackets are ambiguous in strict mode. Safe Markdown
    links take precedence over that grammar, including ID-shaped ordinary labels.
    Mixed brackets containing known IDs require revision, or unwrap their remaining prose in fallback.
    """
    report = report if report is not None else PresentationContractReport()
    protected: dict[str, str] = {}
    # Pick a collision-free namespace even for adversarial/user-written examples.
    prefix = '\ue000'
    while prefix in text:
        prefix += '\ue000'

    def protect(value: str) -> str:
        key = prefix + '\ue002' * len(protected) + '\ue001'
        protected[key] = value
        return key

    text = _CODE_RE.sub(lambda match: protect(match.group(0)), text)
    recovered: list[str] = []

    def remove(ids: list[str], reason: str = 'inline_source_citation') -> str:
        recovered.extend(ids)
        report.repairs.add(reason)
        return _REMOVAL_MARKER

    def unit(match: re.Match[str]) -> str:
        value = match.group(0)
        link = _MARKDOWN_LINK_RE.fullmatch(value)
        if link:
            label, destination = (part.strip() for part in link.groups())
            if not label:
                return remove([], 'empty_citation_dropped')
            if label in valid_ids:
                return remove([label])
            scheme = destination.split(':', 1)[0].casefold() if ':' in destination else ''
            if scheme not in _SAFE_MARKDOWN_SCHEMES:
                report.repairs.add('unsafe_markdown_link')
                return label
            return protect(value)
        if value.startswith('('):
            tokens = [token.strip() for token in re.split(r'[;,]', value[1:-1]) if token.strip()]
            ids = []
            for token in tokens:
                nested_link = _MARKDOWN_LINK_RE.fullmatch(token)
                candidate = nested_link.group(1).strip() if nested_link else token
                if candidate not in valid_ids:
                    return _BRACKET_UNIT_RE.sub(unit, value)
                ids.append(candidate)
            return remove(ids) if ids else value
        content = value[1:-1].translate(_ADORNMENTS).strip()
        ids = _bracket_ids(content, valid_ids)
        if ids:
            return remove(ids)
        tokens = [token for token in re.split(r'[\s,;]+', content) if token]
        mixed_ids = [token for token in tokens if token in valid_ids]
        if mixed_ids:
            if not safe_fallback:
                report.violations.add('source_id_in_prose')
                return protect(value)
            # Remove known tokens as a whole group, retaining remaining prose without a shell.
            remainder = re.sub(r'[^\s,;]+', lambda m: '' if m.group(0) in valid_ids else m.group(0), content)
            recovered.extend(mixed_ids)
            report.repairs.add('source_id_in_prose')
            return _clean_separators(remainder)
        if not re.sub(r'[\s,;]', '', content):
            return remove([], 'empty_citation_dropped')
        if re.fullmatch(r'(?i)(?:spk|speaker)[ _]\d+:?', content):
            return remove([], 'speaker_placeholder')
        # Numeric and footnote markers in notes have no chat citation list to resolve.
        unknown = _ID_LIKE_RE.fullmatch(content) or re.fullmatch(r'\^\d+', content)
        if unknown:
            if safe_fallback:
                return remove([], 'unknown_citation_dropped')
            report.violations.add('source_id_in_prose')
        return protect(value)

    text = _CITATION_UNIT_RE.sub(unit, text)
    for source_id in sorted(valid_ids, key=lambda value: (-len(value), value)):
        pattern = _id_pattern(source_id)
        if pattern.search(text):
            if safe_fallback:
                text = pattern.sub(_REMOVAL_MARKER, text)
                report.repairs.add('source_id_in_prose')
            else:
                report.violations.add('source_id_in_prose')
    without_speakers = _SPEAKER_PLACEHOLDER_RE.sub(_REMOVAL_MARKER, text)
    if without_speakers != text:
        report.repairs.add('speaker_placeholder')
    without_speakers = _clean_parenthetical_removals(without_speakers)
    text = _clean_after_removal(without_speakers) if _REMOVAL_MARKER in without_speakers else without_speakers
    if '\x01' in text:
        text = text.replace('\x01', '').strip()
    for key, value in reversed(protected.items()):
        text = text.replace(key, value)
    return text, list(dict.fromkeys(recovered))


def repair_note_citations(
    text: str,
    valid_ids: set[str],
    *,
    safe_fallback: bool = True,
    report: Optional[PresentationContractReport] = None,
) -> tuple[str, list[str]]:
    """Sweep to a fixed point: removing an inner unit may expose an outer shell."""
    recovered: list[str] = []
    while True:
        cleaned, ids = _repair_note_citation_pass(text, valid_ids, safe_fallback=safe_fallback, report=report)
        recovered.extend(ids)
        if cleaned == text:
            return cleaned, list(dict.fromkeys(recovered))
        text = cleaned


def visible_text_fields(structured: Structured) -> list[tuple[Any, str]]:
    fields: list[tuple[Any, str]] = [(structured, 'title'), (structured, 'overview')]
    for section in structured.sections:
        fields.extend(((section, 'heading'), (section, 'body_markdown')))
    for item in structured.action_items:
        fields.append((item, 'description'))
        if item.owner_name is not None:
            fields.append((item, 'owner_name'))
        if item.context is not None:
            fields.append((item, 'context'))
    for event in structured.events:
        fields.extend(((event, 'title'), (event, 'description')))
    for participant in structured.participants:
        for attribute in ('name', 'email', 'organization', 'role', 'evidence'):
            if getattr(participant, attribute, None) is not None:
                fields.append((participant, attribute))
    for insight in structured.insights:
        fields.append((insight, 'text'))
    return fields


def enforce_structured_presentation_contract(
    structured: Structured,
    transcript_segment_ids: Optional[Iterable[object]],
    *,
    safe_fallback: bool = False,
) -> PresentationContractReport:
    """Keep internal evidence identifiers out of user-visible generated notes.

    Citation-only syntax is repaired deterministically and moved into the typed
    evidence field. A known source ID in ordinary prose is ambiguous and asks
    the caller for one revision pass. ``safe_fallback`` removes that identifier
    after the revision budget is exhausted. Unknown UUID-like text is preserved.
    """

    report = PresentationContractReport()
    valid_ids = {
        segment_id for segment_id in (transcript_segment_ids or ()) if isinstance(segment_id, str) and segment_id
    }
    for owner in [*structured.sections, *structured.action_items]:
        before = list(owner.source_segment_ids)
        owner.source_segment_ids = _validate_source_segment_ids(before, valid_ids)
        if owner.source_segment_ids != before:
            report.repairs.add('invalid_source_reference')

    for owner, attribute in visible_text_fields(structured):
        value, recovered = repair_note_citations(
            getattr(owner, attribute, '') or '', valid_ids, safe_fallback=safe_fallback, report=report
        )
        if attribute in ('heading', 'body_markdown', 'description', 'context') and hasattr(owner, 'source_segment_ids'):
            owner.source_segment_ids = _validate_source_segment_ids([*owner.source_segment_ids, *recovered], valid_ids)
        setattr(owner, attribute, value)

    # Final invariant sweep over every visible field, including participant emails.
    # It also catches shells exposed by speaker/link repairs. Strict unknowns remain
    # violations for the bounded revision; the fallback sweep guarantees clean output.
    for owner, attribute in visible_text_fields(structured):
        value, _ = repair_note_citations(
            getattr(owner, attribute, '') or '', valid_ids, safe_fallback=safe_fallback, report=report
        )
        setattr(owner, attribute, value)
    return report


# Diarization placeholders are transcript machinery, not people. Prompt wording alone
# does not hold — v2 already forbade "Speaker 1 said that" and still leaked the token.
# `spk N` is the compact speaker-map key (SCA-454) and leaks the same way.
_SPEAKER_PLACEHOLDER_RE = re.compile(r'(?i)\b(?:spk|speaker)[ _]\d+\b:?[ \t]*')


def strip_speaker_placeholders(text: str) -> str:
    """Drop leftover Speaker N / SPEAKER_00 tokens rather than inventing a name."""
    if not text or not _SPEAKER_PLACEHOLDER_RE.search(text):
        return text
    cleaned = _SPEAKER_PLACEHOLDER_RE.sub('', text)
    cleaned = re.sub(r'[^\S\n]+', ' ', cleaned)
    cleaned = re.sub(r' *\n *', '\n', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def sanitize_structured_speaker_placeholders(structured: Structured) -> Structured:
    """Strip diarization placeholders from every user-visible notes field."""
    for owner, attribute in visible_text_fields(structured):
        value = getattr(owner, attribute, '')
        # Use the same code masking and whole speaker-unit removal as the gate.
        # Citation handling belongs to enforce_structured_presentation_contract.
        protected: list[str] = []
        prefix = '\ue000'
        while prefix in value:
            prefix += '\ue000'

        def mask(match: re.Match[str]) -> str:
            protected.append(match.group(0))
            return prefix + '\ue002' * len(protected) + '\ue001'

        value = _CODE_RE.sub(mask, value)
        value = re.sub(r'\[\s*(?:spk|speaker)[ _]\d+:?\s*\]', '', value, flags=re.IGNORECASE)
        value = strip_speaker_placeholders(value)
        for index, code in enumerate(protected):
            value = value.replace(prefix + '\ue002' * (index + 1) + '\ue001', code)
        setattr(owner, attribute, value or (None if attribute == 'owner_name' else value))
    return structured


# A two-name lead is used only while the led title fits in this many characters;
# past it the second name is dropped. It is not a title cap: a one-name lead is
# never shortened, and no title is ever truncated.
TWO_NAME_LEAD_MAX_CHARACTERS = 70

# Scripts written without spaces between words (Thai, Lao, Myanmar, Khmer, kana
# incl. halfwidth, CJK ideographs) and Hangul, whose particles attach to the name.
# Python's ``\w`` matches them all, so ``\w`` boundaries never form around a name.
_UNSPACED_SCRIPT_RANGES = (
    '\u0e00-\u0e7f'  # Thai
    '\u0e80-\u0eff'  # Lao
    '\u1000-\u109f'  # Myanmar
    '\u1780-\u17ff'  # Khmer
    '\u3040-\u30ff'  # hiragana, katakana
    '\u3400-\u4dbf\u4e00-\u9fff'  # CJK ideographs
    '\uac00-\ud7af'  # Hangul syllables
    '\uff66-\uff9f'  # halfwidth katakana
)
_UNSPACED_SCRIPT = re.compile(f'[{_UNSPACED_SCRIPT_RANGES}]')
# A word character that continues a spaced-script word; an unspaced-script
# neighbour is a boundary, so "与Sarah讨论预算" names Sarah while "Leeds" is not "Lee".
_SPACED_WORD_CHAR = f'[^\\W{_UNSPACED_SCRIPT_RANGES}]'
# Case endings and possessives: a name token this long also matches itself plus a
# short suffix ("Peters", "Markiem", "Иваном", "Sarahin"), and a name ending in a
# vowel also matches its stem plus a short suffix ("Сарой", "Anną", "Sárával").
# The suffix is never empty, so a bare stem ("and" for Andy, "Dan" for Dana) is
# not a mention.
_INFLECTED_NAME_MIN_CHARACTERS = 4
_INFLECTION_MAX_SUFFIX_CHARACTERS = 4
_NAME_VOWELS = frozenset('aeiouyàáâãäåąæèééêëęìíîïòóôõöøùúûüýаеёиоуыэюяіїє')
_APOSTROPHES = str.maketrans({'\u2019': "'"})


def _normalize_for_match(text: str) -> str:
    return unicodedata.normalize('NFC', text).translate(_APOSTROPHES)


def _name_pattern(name: str) -> re.Pattern[str]:
    escaped = re.escape(name)
    if _UNSPACED_SCRIPT.search(name):
        return re.compile(escaped, re.IGNORECASE)
    if len(name) >= _INFLECTED_NAME_MIN_CHARACTERS and len(name.split()) == 1:
        suffix = f'{_SPACED_WORD_CHAR}{{1,{_INFLECTION_MAX_SUFFIX_CHARACTERS}}}'
        forms = [escaped, f'{escaped}{suffix}']
        if name[-1].casefold() in _NAME_VOWELS:
            forms.append(f'{re.escape(name[:-1])}{suffix}')
        escaped = f'(?:{"|".join(forms)})'
    return re.compile(f'(?<!{_SPACED_WORD_CHAR}){escaped}(?!{_SPACED_WORD_CHAR})', re.IGNORECASE)


def _name_mentions(name: str) -> list[str]:
    """The full name, its first name, its surname (3+ characters), and any unspaced-script token.

    One unspaced-script character (a common family name such as 王) or a
    two-letter surname ("Li") is too common to count as a mention on its own.
    A single-token mention of 4+ characters also matches inflected forms; that
    over-matches some ordinary words ("Mark" in "Market", "Anna" in "Annual").
    A false match only keeps a title without a lead, so the matcher must never
    drive a change to a title the model wrote.
    """
    tokens = name.split()
    mentions = [name]
    if len(tokens) > 1:
        mentions.extend(
            token
            for index, token in enumerate(tokens)
            if (index == 0 and len(token) > 1)
            or (index == len(tokens) - 1 and len(token) > 2)
            or (len(token) > 1 and _UNSPACED_SCRIPT.search(token))
        )
    return mentions


def title_names_any_person(title: str, people: Iterable[str]) -> bool:
    """True when the title already names one of ``people`` (see ``_name_mentions``).

    Title and names are NFC-normalized and ’ reads as ' before matching.
    """
    title = _normalize_for_match(title)
    for name in people:
        name = _normalize_for_match(name).strip()
        if name and any(_name_pattern(mention).search(title) for mention in _name_mentions(name)):
            return True
    return False


def presentable_title_people(people: Sequence[str], transcript_segment_ids: Optional[Iterable[object]]) -> list[str]:
    """The title people whose names presentation would keep: no speaker placeholder, no transcript ID.

    The title lead runs after presentation sanitization, so a name that sanitization
    would strip must not reach the title through it.
    """
    valid_ids = [
        segment_id for segment_id in (transcript_segment_ids or ()) if isinstance(segment_id, str) and segment_id
    ]
    return [
        name
        for name in people
        if strip_speaker_placeholders(name) == name and not any(_id_pattern(i).search(name) for i in valid_ids)
    ]


def lead_title_with_people(title: str, people: Sequence[str]) -> tuple[str, bool]:
    """Lead a title that names none of the identified people with their names (#3602).

    The prompt asks the model to name the one or two most central of them; this
    deterministic repair covers only the case where it names nobody. A title that
    already names any of them is kept as written, however many it names: names
    cannot be removed from the model's prose without rewriting it, and replacing
    the title would lose its topic. ``Name: Title`` reads the same in every
    response language, joins at most two people, and never invents a title or a
    name.
    """
    stripped = title.strip()
    names = [name.strip() for name in people if name and name.strip()]
    if not stripped or not names or title_names_any_person(stripped, names):
        return title, False
    led = f'{" & ".join(names[:2])}: {stripped}'
    if len(led) > TWO_NAME_LEAD_MAX_CHARACTERS and len(names) > 1:
        led = f'{names[0]}: {stripped}'
    return led, True


def _name_in_transcript(name: str, transcript_body: str) -> bool:
    """Case-insensitive whole-name (word-boundary) match against the transcript body."""
    name = name.strip()
    if not name or not transcript_body:
        return False
    return re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', transcript_body, re.IGNORECASE) is not None


def validate_rich_meeting_notes(
    structured: Structured,
    *,
    transcript_body: str,
    roster: Optional[MeetingRoster],
    has_background_context: bool,
    background_body: str = '',
) -> Structured:
    """Server-side guardrails for rich-only fields; the flag-off path never runs this.

    Participants must be corroborated (roster name/email or a whole-name transcript
    match), the account owner is never a participant, and nameless participants
    survive only on a roster email. Insights exist only with background context,
    capped at 4 entries of <=30 words. At most one side_notes section survives,
    forced last with heading "Side notes" and 1-4 bullets.
    """
    roster_entries = list(roster.entries) if roster else []
    roster_by_name = {e.display_name.casefold(): e for e in roster_entries if e.display_name}
    roster_by_email = {e.email.casefold(): e for e in roster_entries if e.email}
    owner_names = {e.display_name.casefold() for e in roster_entries if e.kind == 'owner' and e.display_name}
    owner_emails = {e.email.casefold() for e in roster_entries if e.kind == 'owner' and e.email}
    # A first-name-only owner entry still owns bare repeats of that first name
    # in the model output.
    owner_first_tokens = {name.split()[0] for name in owner_names if len(name.split()) == 1}

    validated_participants: List[Participant] = []
    for participant in structured.participants:
        name = (participant.name or '').strip()
        email = (participant.email or '').strip()
        if name.casefold() in owner_names or email.casefold() in owner_emails:
            continue
        if owner_first_tokens and len(name.split()) == 1 and name.casefold() in owner_first_tokens:
            continue
        matched_entry = None
        if name:
            matched_entry = roster_by_name.get(name.casefold())
            # Screen text (a call's participant list, a profile opened during the
            # call) is a legitimate identity source alongside the transcript.
            if (
                matched_entry is None
                and not _name_in_transcript(name, transcript_body)
                and not (background_body and _name_in_transcript(name, background_body))
            ):
                continue
        elif email:
            matched_entry = roster_by_email.get(email.casefold())
            if matched_entry is None:
                continue
        else:
            continue
        # Keep an email only when it belongs to the same roster entry that
        # corroborated the participant — a name match must not inherit someone
        # else's roster email, and untrusted emails are dropped.
        if (
            email
            and matched_entry is not None
            and matched_entry.email
            and matched_entry.email.casefold() == email.casefold()
        ):
            participant.email = email
        else:
            participant.email = None
        if name:
            participant.name = name
        validated_participants.append(participant)
    structured.participants = validated_participants

    if not has_background_context:
        structured.insights = []
    else:
        kept = []
        for insight in structured.insights[:4]:
            words = insight.text.split()
            if len(words) > 30:
                insight.text = ' '.join(words[:30])
            if insight.text.strip():
                kept.append(insight)
        structured.insights = kept

    side_notes = [s for s in structured.sections if getattr(s, 'kind', 'main') == 'side_notes']
    main_sections = [s for s in structured.sections if getattr(s, 'kind', 'main') != 'side_notes']
    if side_notes:
        # Merge every side_notes section's bullets into one last section rather
        # than silently dropping earlier tangents.
        bullets: List[str] = []
        for section in side_notes:
            for line in (section.body_markdown or '').split('\n'):
                line = line.strip()
                if not line.startswith('-') or not line.lstrip('- ').strip():
                    continue
                if line not in bullets:
                    bullets.append(line)
        bullets = bullets[:4]
        if bullets:
            merged = side_notes[-1]
            merged.heading = 'Side notes'
            merged.body_markdown = '\n'.join(bullets)
            structured.sections = [*main_sections, merged]
        else:
            structured.sections = main_sections
    else:
        structured.sections = main_sections
    return structured
