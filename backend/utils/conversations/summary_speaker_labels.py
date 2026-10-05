"""Conservative, deterministic admission of evidence from the saved notes call.

This module also owns the post-persistence assignment transaction. The database
layer deliberately holds no ``utils/`` imports, so the orchestration lives here
(same layer as the other ``firestore.transactional`` stages) and calls the thin
persistence helpers in ``database/summary_speaker_labels``.
"""

import hashlib
import json
import logging
import unicodedata
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from google.cloud import firestore

from config.summary_speaker_labels import summary_speaker_labels_enabled
from database import _client
from database import conversations as conversations_db
from database import summary_speaker_labels as persistence
from database.conversations import effective_user_title
from models.summary_speaker_labels import SpeakerCandidate
from models.transcript_segment import SpeakerIdentityStatus
from utils.conversations.meeting_participants import MeetingRoster, looks_like_ai_agent_name
from utils.conversations.transcript_hash import canonicalize_segment_for_storage
from utils.speaker_permissions import named_speaker_prompts_allowed

logger = logging.getLogger(__name__)

# The bounded catalog read stays in the database layer (its query shape is
# registered there); re-export so callers and tests patch one stable name.
read_summary_people_catalog = persistence.read_summary_people_catalog
CATALOG_LIMIT = persistence.CATALOG_LIMIT

_MEETING_ROSTER_SOURCES = frozenset(
    {'system_calendar', 'macos_calendar', 'google_calendar', 'outlook_calendar', 'google', 'outlook', 'screen_activity'}
)
_NAME_PARTICLES = frozenset({'of', 'to', 'de', 'del', 'da', 'di', 'van', 'von', 'der', 'den', 'la', 'le'})
_INTRO_DISCOURSE_WORDS = frozenset(
    {
        'hello',
        'hi',
        'hey',
        'howdy',
        'greetings',
        'welcome',
        'bonjour',
        'hola',
        'ciao',
        'from',
        'at',
        'with',
        'is',
        'am',
        'i',
    }
)
_NAME_TOKEN = r"[^\W\d_]+(?:[-'’][^\W\d_]+)*"


def normalized_name(name: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', name).replace('’', "'").casefold().split())


def explicit_introduction_names(text: str) -> list[Optional[str]]:
    """Read every explicit span; None reserves an ambiguous introduction.

    Reuse main's lead-ins and CJK validation without its first-hit/short-name
    filtering. A bare copula cannot hide a later explicit introduction. Never
    trim discourse or clause words to guess where a name starts or ends.
    """
    from utils.speaker_identification import (
        PATTERN_TO_LANG,
        SPEAKER_NAME_STOPWORDS,
        is_explicit_introduction,
        is_valid_cjk_speaker_name,
        patterns_to_check,
    )

    names: list[Optional[str]] = []
    for pattern in patterns_to_check:
        for match in re.finditer(pattern, text):
            if not is_explicit_introduction(pattern, match):
                continue
            start, end = match.span(len(match.groups()))
            captured = text[start:end]
            if re.search(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7a3]', captured):
                names.append(
                    normalized_name(captured)
                    if is_valid_cjk_speaker_name(captured, PATTERN_TO_LANG.get(pattern))
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
            valid = len(span) >= 2
            non_particles = 0
            for i, token in enumerate(tokens):
                normalized = normalized_name(token)
                if normalized in _INTRO_DISCOURSE_WORDS:
                    valid = False
                    break
                if normalized in _NAME_PARTICLES:
                    # Once two name tokens exist, another particle may begin
                    # an affiliation/location phrase. Never guess by trimming.
                    if i == 0 or i == len(tokens) - 1 or non_particles >= 2:
                        valid = False
                        break
                elif not token[0].isupper() or normalized in SPEAKER_NAME_STOPWORDS:
                    valid = False
                    break
                else:
                    non_particles += 1
            names.append(normalized_name(span) if valid else None)
    return names


def full_real_name(name: str, *, min_cjk_length: int = 2) -> bool:
    # CJK introductions/rosters can validate short names. Alias-only admission
    # is stricter because a two-character retained alias may be a given name.
    return len(name.split()) >= 2 or (
        len(name) >= min_cjk_length and bool(re.fullmatch(r'[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7a3]{2,6}', name))
    )


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
    # A roster that knows the owner only by first name still owns full-name
    # variants of it: admitting "David Nguyen" as another human while the owner
    # is "David" mislabels the account owner's own voice.
    owner_first_names = {next(iter(n.split()), '') for n in owner_names if len(n.split()) == 1}
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
        elif owner_first_names and name.split() and name.split()[0] in owner_first_names:
            # The roster's owner entry is only a first name; a multi-token
            # candidate starting with it is treated as an owner variant, not
            # another human.
            continue
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
        if len(named_entries) > 1 and not linked:
            # Two distinct roster attendees share this display name and neither
            # carries a resolved person: separate bindings for those voices could
            # conflate them onto one person or one deterministic id. Decline.
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
            # The compact prompt's speaker map collapses clusters by numeric id,
            # so a model citing this (unlabeled) scope may echo a name it only
            # saw bound in a different scope. Decline when any sibling scope of
            # this numeric key already carries an identity.
            sibling_scope_identity = [
                s
                for s in by_key.get(binding.speaker_id, [])
                if s.get('speaker_id_scope') != scope
                and (s.get('person_id') or s.get('is_user') or s.get('speaker_label_source'))
            ]
            if (
                binding.confidence != 'high'
                or not 1 <= len(binding.evidence_segment_ids) <= 2
                or claims[(binding.speaker_id, scope)] != 1
                or not cluster
                or sibling_scope_identity
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


def note_generation_digest(candidates, roster) -> Optional[str]:
    """Stable digest of the private note-identity evidence, or None without any.

    ``speaker_bindings`` are private and never persisted, so two reprocessing
    generations can share title/overview while carrying different candidates.
    Persisting this digest beside the note lets the assignment transaction
    decline a stale generation whose candidates no longer match the note.
    """
    candidates = list(candidates or [])
    if not candidates or roster is None:
        return None
    payload = {
        'candidates': [
            {
                'name': getattr(c, 'name', ''),
                'is_owner': bool(getattr(c, 'is_owner', False)),
                'is_ai_agent': bool(getattr(c, 'is_ai_agent', False)),
                'bindings': [
                    {
                        'speaker_id': getattr(b, 'speaker_id', None),
                        'confidence': getattr(b, 'confidence', None),
                        'evidence_kind': getattr(b, 'evidence_kind', None),
                        'evidence_segment_ids': list(getattr(b, 'evidence_segment_ids', []) or []),
                    }
                    for b in (getattr(c, 'bindings', None) or [])
                ],
            }
            for c in (candidates or [])
        ],
        'roster': [
            {
                'name': getattr(e, 'display_name', None),
                'kind': getattr(e, 'kind', None),
                'source': getattr(e, 'source', None),
                'person_id': getattr(e, 'person_id', None),
            }
            for e in (getattr(roster, 'entries', None) or [])
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def apply_summary_speaker_labels(uid: str, conversation, *, firestore_client=None) -> int:
    """Apply note-inferred labels in one post-persistence Firestore transaction.

    The note is already durable when this runs. The transaction re-checks source
    text, manual authority and current labels; any failure preserves the saved
    note, changes neither people nor labels, and never schedules teaching.
    """
    if not summary_speaker_labels_enabled():
        return 0
    candidates = getattr(conversation.structured, '_summary_speaker_candidates', [])
    roster = getattr(conversation.structured, '_summary_speaker_roster', None)
    if not candidates or not roster or conversation.discarded:
        return 0
    try:
        # A subscription read failure declines the entire stage, including owner;
        # never infer paid eligibility and never touch manual endpoints.
        allow_named = named_speaker_prompts_allowed(uid) if any(not c.is_owner for c in candidates) else False
        client = firestore_client if firestore_client is not None else _client.get_firestore_client()
        user_ref = client.collection('users').document(uid)
        conversation_ref = user_ref.collection('conversations').document(conversation.id)
        # Compare against storage-canonicalized identity: the completed-conversation
        # write path canonicalizes segment text (strips surrounding whitespace),
        # so a raw in-memory tuple would decline every padded-STT input.
        expected = transcript_identity(
            [dict(canonicalize_segment_for_storage(s.model_dump())) for s in conversation.transcript_segments]
        )
        expected_generation = note_generation_digest(candidates, roster)

        @firestore.transactional
        def commit(transaction):
            if not summary_speaker_labels_enabled():
                return None
            snapshot = conversation_ref.get(transaction=transaction)
            if not snapshot.exists:
                return None
            current = snapshot.to_dict() or {}
            if (
                current.get('deleted')
                or current.get('discarded')
                or current.get('is_locked')
                or current.get('status') != 'completed'
                or current.get('merged_into')
            ):
                return None
            note = current.get('structured') or {}
            note_title = note.get('title')
            if note_title is None:
                note_title = conversation.structured.title
            # ``persist_processing_result_with_lifecycle`` re-applies a preserved
            # user title over the generated one; the in-memory generated title
            # stays authoritative for the fence when the stored title is a
            # user-owned override (``user_title`` present and non-blank).
            if note_title != conversation.structured.title:
                user_title = note_title if effective_user_title(current.get('user_title')) == note_title else None
                if user_title is None:
                    return None
            if note.get('overview') != conversation.structured.overview:
                return None
            segments = conversations_db.decode_transcript_segments_verified(
                uid, current.get('transcript_segments'), bool(current.get('transcript_segments_compressed'))
            )
            if transcript_identity(segments) != expected:
                return None
            if current.get('summary_speaker_note_digest') != expected_generation:
                # The digest is stamped beside the note whenever this stage's
                # candidates exist (the notes call only emits them flag-on, and
                # the flag gates this stage too). A stored mismatch therefore
                # means the persisted note belongs to a different generation —
                # including a newer reprocess that replaced these private
                # candidates — so decline rather than apply stale labels.
                return None
            receipt = conversations_db.decode_manual_speaker_assignments(
                uid,
                current.get('manual_speaker_assignments'),
                bool(current.get('manual_speaker_assignments_compressed')),
            )
            selected = select_candidates(candidates, segments, receipt, roster, allow_named=allow_named)
            if not selected:
                return None
            people_ref = user_ref.collection('people')
            # Bounded catalog, no speech-profile/learning projection or N+1 reads.
            # A truncated catalog cannot establish uniqueness, so decline all names.
            people = []
            if any(not s.is_owner for s in selected):
                docs = read_summary_people_catalog(uid, transaction, firestore_client=client)
                if len(docs) > CATALOG_LIMIT:
                    return None
                people = [{**d.to_dict(), 'id': d.id} for d in docs]
            staged_people = {}
            assignments = {}
            for speaker in selected:
                person_id = None
                if not speaker.is_owner:
                    proposed_name = normalized_name(speaker.name)
                    matches = [
                        p
                        for p in people
                        if normalized_name(p.get('name') or '') == proposed_name
                        or (
                            full_real_name(proposed_name, min_cjk_length=3)
                            and proposed_name in [normalized_name(a) for a in p.get('aliases', [])]
                        )
                    ]
                    if speaker.person_id:
                        matches = [p for p in people if p['id'] == speaker.person_id]
                    if len(matches) > 1:
                        continue
                    if matches:
                        person = matches[0]
                        if (
                            person.get('deleted')
                            or person.get('status') in {'merged', 'dismissed'}
                            or person.get('is_ai_agent')
                        ):
                            continue
                        person_id = person['id']
                    elif speaker.person_id or not speaker.may_create:
                        continue
                    else:
                        person_id = persistence.summary_inferred_person_id(speaker.name)
                        staged_people[person_id] = speaker.name
                for sid in speaker.segment_ids:
                    assignments[sid] = (speaker, person_id)
            if not assignments:
                return None
            validated, payload = persistence.apply_summary_segment_updates(
                uid,
                conversation.id,
                segments,
                assignments,
                current.get('data_protection_level', 'standard'),
                conversations_db.encode_conversation_for_write,
            )
            for pid, person_name in staged_people.items():
                persistence.stage_summary_person_creation(transaction, people_ref, pid, person_name)
            transaction.update(conversation_ref, payload)
            return validated, len(assignments)

        committed = commit(client.transaction())
        if committed:
            segments, count = committed
            conversation.transcript_segments = segments
            conversations_db.invalidate_people_stats_cache(uid)
            logger.info('summary_speaker_labels outcome=applied segments=%d', count)
            return count
        logger.info('summary_speaker_labels outcome=declined')
    except Exception as error:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='conversation_notes',
            from_mode='summary_speaker_labels',
            to_mode='saved_note',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        logger.warning('summary_speaker_labels outcome=error exception_type=%s', type(error).__name__)
    return 0
