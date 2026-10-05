"""Conservative, deterministic admission of evidence from the saved notes call."""

import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from models.summary_speaker_labels import SpeakerCandidate
from utils.conversations.meeting_participants import MeetingRoster, looks_like_ai_agent_name


def normalized_name(name: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', name).casefold().split())


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
    from utils.speaker_identification import SPEAKER_NAME_STOPWORDS, detect_speaker_introduction

    claims = Counter(b.speaker_id for c in candidates for b in c.bindings)
    by_key: dict[int, list[dict]] = {}
    by_id: dict[str, dict] = {}
    for segment in segments:
        by_key.setdefault(segment.get('speaker_id'), []).append(segment)
        if segment.get('id') in by_id:
            return []  # ambiguous evidence identity
        by_id[segment.get('id')] = segment
    owner_names = {normalized_name(e.display_name) for e in roster.entries if e.kind == 'owner' and e.display_name}
    human_entries = [e for e in roster.entries if e.kind == 'human' and e.display_name]
    agent_names = {normalized_name(e.display_name) for e in roster.entries if e.kind == 'ai_agent' and e.display_name}
    result = []
    owner_claimed = any(s.get('is_user') for s in segments) or any(
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
        named_entries = [e for e in human_entries if normalized_name(e.display_name) == name]
        linked = {e.person_id for e in named_entries if e.person_id}
        if len(linked) > 1:
            continue
        admitted = []
        for binding in candidate.bindings:
            cluster = by_key.get(binding.speaker_id, [])
            evidence = [by_id.get(sid) for sid in binding.evidence_segment_ids]
            if (
                binding.confidence != 'high'
                or claims[binding.speaker_id] != 1
                or not cluster
                or len({s.get('speaker_id_scope') for s in cluster}) != 1
                or any(s.get('person_id') or s.get('is_user') or s.get('speaker_label_source') for s in cluster)
                or str(binding.speaker_id) in (receipt.get('speakers') or {})
                or any(s.get('id') in (receipt.get('segments') or {}) for s in cluster)
                or any(
                    not s or s.get('speaker_id') != binding.speaker_id or not (s.get('text') or '').strip()
                    for s in evidence
                )
                or len(set(binding.evidence_segment_ids)) != len(binding.evidence_segment_ids)
            ):
                admitted = []
                break
            introductions = [detect_speaker_introduction(s['text']) for s in evidence]
            explicit_name = any(d and d.explicit and normalized_name(d.name) == name for d in introductions)
            # Contrary self-introductions anywhere in the key invalidate the
            # whole candidate, even when the model cites a convenient subset.
            contrary = any(
                d and d.explicit and normalized_name(d.name) != name
                for d in (detect_speaker_introduction(s['text']) for s in cluster)
            )
            if contrary or (binding.evidence_kind == 'self_introduction' and not explicit_name):
                admitted = []
                break
            # A real roster name plus high-confidence conversation evidence can
            # ground creation; transcript-only creation needs an explicit intro.
            # No arbitrary name mentioned elsewhere, email local part, or role.
            grounded = bool(named_entries) or explicit_name or candidate.is_owner
            if not grounded:
                admitted = []
                break
            admitted.append(
                AdmittedSpeaker(
                    candidate.name.strip(),
                    candidate.is_owner,
                    binding.speaker_id,
                    tuple(s['id'] for s in cluster if s.get('id')),
                    tuple(binding.evidence_segment_ids),
                    next(iter(linked), None),
                    grounded,
                )
            )
        result.extend(admitted)
    # Multiple separate owner objects are not a proof that both are the owner.
    if len({a.name for a in result if a.is_owner}) > 1:
        result = [a for a in result if not a.is_owner]
    return result
