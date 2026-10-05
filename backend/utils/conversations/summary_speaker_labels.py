"""Conservative, deterministic admission of evidence from the saved notes call."""

import unicodedata
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from models.summary_speaker_labels import SpeakerCandidate
from models.transcript_segment import SpeakerIdentityStatus
from utils.conversations.meeting_participants import MeetingRoster, looks_like_ai_agent_name

_MEETING_ROSTER_SOURCES = frozenset(
    {'system_calendar', 'macos_calendar', 'google_calendar', 'outlook_calendar', 'google', 'outlook', 'screen_activity'}
)
_NAME_PARTICLES = frozenset({'of', 'to', 'de', 'del', 'da', 'di', 'van', 'von', 'der', 'den', 'la', 'le'})
_NAME_TOKEN = r"[^\W\d_]+(?:[-'’][^\W\d_]+)*"


def normalized_name(name: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', name).casefold().split())


def explicit_introduction_names(text: str) -> list[Optional[str]]:
    """Read every explicit span; None reserves an ambiguous introduction.

    Reuse main's lead-ins and CJK validation without its first-hit/short-name
    filtering. A bare copula cannot hide a later explicit introduction. Never
    trim discourse or clause words to guess where a name starts or ends.
    """
    from utils.speaker_identification import (
        PATTERN_TO_LANG,
        SPEAKER_NAME_STOPWORDS,
        _is_explicit_introduction,
        _is_valid_cjk_speaker_name,
        patterns_to_check,
    )

    names: list[Optional[str]] = []
    for pattern in patterns_to_check:
        for match in re.finditer(pattern, text):
            if not _is_explicit_introduction(pattern, match):
                continue
            start, end = match.span(len(match.groups()))
            captured = text[start:end]
            if re.search(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7a3]', captured):
                names.append(
                    normalized_name(captured)
                    if _is_valid_cjk_speaker_name(captured, PATTERN_TO_LANG.get(pattern))
                    else None
                )
                continue
            name_first = start == match.start()
            # Extend even a one-letter capture before deciding it is too short.
            while preceding := re.search(r'(' + _NAME_TOKEN + r")[-'’]$", text[:start]):
                start = preceding.start(1)
            while following := re.match(r"[-'’](" + _NAME_TOKEN + r')', text[end:]):
                end += following.end(1)
            if name_first:
                while previous := re.search(r'(' + _NAME_TOKEN + r')\s+$', text[:start]):
                    start = previous.start(1)
            else:
                while following := re.match(r'\s+(' + _NAME_TOKEN + r')', text[end:]):
                    end += following.end(1)
            span = text[start:end]
            tokens = span.split()
            valid = len(span) >= 2 and all(
                (0 < i < len(tokens) - 1 and normalized_name(token) in _NAME_PARTICLES)
                or (token[0].isupper() and normalized_name(token) not in SPEAKER_NAME_STOPWORDS)
                for i, token in enumerate(tokens)
            )
            names.append(normalized_name(span) if valid else None)
    return names


def full_real_name(name: str) -> bool:
    # CJK explicit forms capture a complete validated name without spaces.
    return len(name.split()) >= 2 or bool(re.fullmatch(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7a3]{2,6}', name))


def transcript_identity(segments: list[dict]) -> list[tuple]:
    # Bind to source text and cluster scope, not the mutable label projection.
    return [tuple(s.get(key) for key in ('id', 'text', 'speaker_id', 'speaker_id_scope')) for s in segments]


@dataclass(frozen=True)
class AdmittedSpeaker:
    name: str
    is_owner: bool
    speaker_id: int
    segment_ids: tuple[str, ...]
    evidence_segment_ids: tuple[str, ...]
    person_id: Optional[str]
    may_create: bool


def select_candidates(
    candidates: list[SpeakerCandidate],
    segments: list[dict],
    receipt: dict,
    roster: Optional[MeetingRoster],
    *,
    allow_named: bool,
) -> list[AdmittedSpeaker]:
    """Reject the whole participant on a contradictory or unsupported binding.

    Existing labels (even without confidence/provenance) are conservatively
    reserved. Manual selected-segment decisions reserve the entire key, including
    unassignments and rejections. No positive or negative decision is overwritten.
    """
    if not roster or len(candidates) > 32:
        return []
    from utils.speaker_identification import SPEAKER_NAME_STOPWORDS

    by_key: dict[int, list[dict]] = {}
    by_id: dict[str, dict] = {}
    for segment in segments:
        speaker_id, segment_id = segment.get('speaker_id'), segment.get('id')
        if not isinstance(speaker_id, int) or isinstance(speaker_id, bool) or not isinstance(segment_id, str):
            return []
        by_key.setdefault(speaker_id, []).append(segment)
        if segment_id in by_id:
            return []  # ambiguous evidence identity
        by_id[segment_id] = segment
    claims = Counter(
        (b.speaker_id, scope)
        for c in candidates
        for b in c.bindings
        for scope in {by_id[sid].get('speaker_id_scope') for sid in b.evidence_segment_ids if sid in by_id}
    )
    owner_names = {normalized_name(e.display_name) for e in roster.entries if e.kind == 'owner' and e.display_name}
    human_entries = [e for e in roster.entries if e.kind == 'human' and e.display_name]
    agent_names = {normalized_name(e.display_name) for e in roster.entries if e.kind == 'ai_agent' and e.display_name}
    result = []
    owner_claimed = any(
        s.get('is_user') or s.get('speaker_identity_status') == SpeakerIdentityStatus.user for s in segments
    ) or any(
        isinstance(d, dict) and d.get('is_user')
        for section in ('speakers', 'segments')
        for d in (receipt.get(section) or {}).values()
    )
    for candidate in candidates:
        name = normalized_name(candidate.name)
        if not candidate.bindings or candidate.is_ai_agent or name in agent_names or looks_like_ai_agent_name(name):
            continue
        if candidate.is_owner:
            if name not in owner_names or owner_claimed:
                continue
        elif not allow_named or name in owner_names:
            continue  # entitlement at selection, before person lookup/create
        if (
            not name
            or len(name) > 80
            or len(name.split()) > 5
            or any(not (c.isalpha() or c in " '-.") for c in name)
            or name in SPEAKER_NAME_STOPWORDS
            or name in {'speaker', 'unknown', 'user', 'owner', 'candidate', 'participant', 'guest'}
        ):
            continue
        named_entries = [e for e in human_entries if normalized_name(e.display_name or '') == name]
        linked = {e.person_id for e in named_entries if e.person_id}
        if len(linked) > 1:
            continue
        admitted = []
        for binding in candidate.bindings:
            evidence = [by_id.get(sid) for sid in binding.evidence_segment_ids]
            scopes = {s.get('speaker_id_scope') for s in evidence if s is not None}
            if len(scopes) != 1:
                admitted = []
                break
            scope = next(iter(scopes))
            cluster = [s for s in by_key.get(binding.speaker_id, []) if s.get('speaker_id_scope') == scope]
            if (
                binding.confidence != 'high'
                or not 1 <= len(binding.evidence_segment_ids) <= 2
                or claims[(binding.speaker_id, scope)] != 1
                or not cluster
                or any(s.get('person_id') or s.get('is_user') or s.get('speaker_label_source') for s in cluster)
                or (
                    candidate.is_owner
                    and any(s.get('speaker_identity_status') == SpeakerIdentityStatus.not_user for s in cluster)
                )
                or str(binding.speaker_id) in (receipt.get('speakers') or {})
                or any(s.get('id') in (receipt.get('segments') or {}) for s in cluster)
                or any(
                    isinstance(d, dict) and d.get('speaker_id') == binding.speaker_id
                    for d in (receipt.get('segments') or {}).values()
                )
                or any(
                    not s or s.get('speaker_id') != binding.speaker_id or not (s.get('text') or '').strip()
                    for s in evidence
                )
                or len(set(binding.evidence_segment_ids)) != len(binding.evidence_segment_ids)
            ):
                admitted = []
                break
            evidence = [s for s in evidence if s is not None]
            explicit_name = any(name in explicit_introduction_names(s['text']) for s in evidence)
            # Contrary self-introductions anywhere in this scoped key invalidate the
            # whole candidate, even when the model cites a convenient subset.
            contrary = any(introduced != name for s in cluster for introduced in explicit_introduction_names(s['text']))
            if contrary or (binding.evidence_kind == 'self_introduction' and not explicit_name):
                admitted = []
                break
            # Context can attach an existing exact person without a literal
            # name in these turns. Creation needs a full explicit introduction
            # or a full real name from main's actual calendar/call roster.
            may_create = (explicit_name and full_real_name(name)) or (
                full_real_name(name) and any(e.source in _MEETING_ROSTER_SOURCES for e in named_entries)
            )
            admitted.append(
                AdmittedSpeaker(
                    candidate.name.strip(),
                    candidate.is_owner,
                    binding.speaker_id,
                    tuple(s['id'] for s in cluster if s.get('id')),
                    tuple(binding.evidence_segment_ids),
                    next(iter(linked), None),
                    may_create,
                )
            )
        result.extend(admitted)
    # Multiple separate owner objects are not a proof that both are the owner.
    if len({a.name for a in result if a.is_owner}) > 1:
        result = [a for a in result if not a.is_owner]
    return result
