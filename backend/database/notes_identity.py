"""Provisional people and the notes model's own bindings, committed with its note.

Only exact stored identifiers resolve people. This path writes no biometric
artifacts or teaching obligations. The current manual receipt remains authority.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any

from database.person_aliases import normalized_person_alias
from utils.manual_speaker_assignments import apply_manual_assignments


def key(value: Any) -> str:
    return ' '.join(value.casefold().split()) if isinstance(value, str) else ''


def person_id_for(name: str, email: str) -> str:
    return 'notes-' + hashlib.sha256(key(email or name).encode()).hexdigest()[:32]


def emails_for(person: dict) -> set[str]:
    return {key(e) for e in [person.get('email'), *(person.get('emails') or [])] if key(e)}


def identifier_retraction(person: dict, conversation_id: str) -> dict:
    """Remove only identifiers contributed by this note; retain other provenance."""
    contributions = dict(person.get('notes_identity_identifiers') or {})
    added = contributions.pop(conversation_id, None)
    if not added:
        return {}
    retained_aliases = {key(a) for c in contributions.values() for a in c.get('aliases', [])}
    retained_emails = {key(e) for c in contributions.values() for e in c.get('emails', [])}
    removed_aliases = {key(a) for a in added.get('aliases', [])} - retained_aliases
    removed_emails = {key(e) for e in added.get('emails', [])} - retained_emails
    rejected = set(person.get('notes_identity_rejected_conversations') or []) | {conversation_id}
    rejected_identifiers = dict(person.get('notes_identity_rejected_identifiers') or {})
    rejected_identifiers[conversation_id] = {**added, 'name': person.get('name')}
    return {
        **(
            {'is_dismissed': True, 'dismissed_at': datetime.now(timezone.utc)}
            if added.get('created') and not contributions
            else {}
        ),
        'aliases': [a for a in person.get('aliases') or [] if key(a) not in removed_aliases],
        'email': None if key(person.get('email')) in removed_emails else person.get('email'),
        'emails': [e for e in person.get('emails') or [] if key(e) not in removed_emails],
        'notes_identity_identifiers': contributions,
        'notes_identity_rejected_conversations': sorted(rejected),
        'notes_identity_rejected_identifiers': rejected_identifiers,
    }


def stage_notes_identity(transaction, user_ref, write_data, existing, *, decode_segments, decode_receipt, encode):
    """Read all referenced people before staging any writes. Return final segments.

    Catalog IDs are from this user's bounded notes context read; documents are
    re-read here so dismissals, rejections and concurrent manual edits win.
    Deterministic exact-email/name IDs fence repeat creation without name parsing.
    """
    context = write_data.pop('_notes_identity', None)
    if context is None:
        return None
    level = existing.get('data_protection_level') or write_data.get('data_protection_level') or 'standard'
    uid = user_ref.id
    conversation_id = write_data['id']
    segments = decode_segments(
        uid, write_data.get('transcript_segments', []), bool(write_data.get('transcript_segments_compressed'))
    )
    receipt = decode_receipt(
        uid, existing.get('manual_speaker_assignments'), bool(existing.get('manual_speaker_assignments_compressed'))
    )
    user = user_ref.get(transaction=transaction).to_dict() or {}
    owner_names = {key(n) for n in [user.get('name'), *context.get('owner_names', [])] if key(n)}
    owner_emails = {key(e) for e in [user.get('email'), *context.get('owner_emails', [])] if key(e)}
    participants = (write_data.get('structured') or {}).get('participants') or []
    participants = [
        p for p in participants if key(p.get('name')) not in owner_names and key(p.get('email')) not in owner_emails
    ]
    write_data['structured']['participants'] = participants
    participants = [p for p in participants if not p.get('is_ai_agent') and key(p.get('name'))]
    receipt_people = {
        decision.get('person_id') or (decision.get('rejection') or {}).get('person_id')
        for section in ('speakers', 'segments')
        for decision in (receipt.get(section) or {}).values()
        if isinstance(decision, dict)
    }
    ids = (
        set(context.get('catalog_ids') or [])
        | {person_id_for(p['name'], p.get('email') or '') for p in participants}
        | {pid for pid in receipt_people if pid}
    )
    people_ref = user_ref.collection('people')
    people = {pid: people_ref.document(pid).get(transaction=transaction).to_dict() for pid in sorted(ids)}
    probes = [
        {**s, 'person_id': '__notes_probe__', 'is_user': False, 'speaker_match_source': 'notes_inferred'}
        for s in segments
    ]
    protected = {
        s.get('id')
        for s in apply_manual_assignments(probes, receipt)
        if s.get('person_id') != '__notes_probe__'
        or s.get('is_user')
        or s.get('speaker_match_source') != 'notes_inferred'
    }
    pending = {}
    bindings = {}
    now = datetime.now(timezone.utc)
    for participant in participants:
        name = normalized_person_alias(participant['name'])
        if not name:
            continue
        asserted_bindings = participant.get('speaker_bindings') or []
        bound_segments = [s for s in segments if s.get('speaker_id') in asserted_bindings]
        if bound_segments and all(s.get('id') in protected or s.get('is_user') for s in bound_segments):
            continue
        email = key(participant.get('email'))
        rejected_identifiers = [
            (p.get('notes_identity_rejected_identifiers') or {}).get(conversation_id, {}) for p in people.values() if p
        ]
        if any(
            key(name) in {key(r.get('name')), *(key(a) for a in r.get('aliases') or [])}
            or (email and email in {key(e) for e in r.get('emails') or []})
            for r in rejected_identifiers
        ):
            continue
        matching = [pid for pid, person in people.items() if person and email and email in emails_for(person)]
        if not matching:
            matching = [
                pid
                for pid, person in people.items()
                if person and key(name) in {key(person.get('name')), *(key(a) for a in person.get('aliases') or [])}
            ]
        if len(matching) > 1:
            continue  # an ambiguous exact identifier must not join two people
        pid = matching[0] if matching else person_id_for(name, email)
        person = people.get(pid)
        if person and (
            person.get('is_dismissed') or conversation_id in (person.get('notes_identity_rejected_conversations') or [])
        ):
            continue
        created = person is None
        if person is None:
            person = dict(
                id=pid,
                name=name,
                created_at=now,
                speech_samples=[],
                speech_samples_version=3,
                creation_source='notes_inferred',
                confidence='unverified',
            )
        person = dict(person)
        contributions = dict(person.get('notes_identity_identifiers') or {})
        contribution = dict(contributions.get(conversation_id) or {'aliases': [], 'emails': [], 'created': created})
        aliases = list(person.get('aliases') or [])
        alias = normalized_person_alias(participant.get('alias'))
        if alias and key(alias) not in {key(a) for a in [person['name'], *aliases]}:
            aliases.append(alias)
            contribution['aliases'] = [*contribution.get('aliases', []), alias]
        stored_emails = emails_for(person)
        if email and email not in stored_emails:
            person['emails'] = [*(person.get('emails') or []), email]
            if not person.get('email'):
                person['email'] = email
            contribution['emails'] = [*contribution.get('emails', []), email]
        contributions[conversation_id] = contribution
        person.update(aliases=aliases, notes_identity_identifiers=contributions, updated_at=now)
        people[pid] = person
        pending[pid] = (created or pending.get(pid, (False,))[0], person)
        for speaker_id in participant.get('speaker_bindings') or []:
            if isinstance(speaker_id, int) and not isinstance(speaker_id, bool) and speaker_id >= 0:
                bindings.setdefault(speaker_id, set()).add(pid)
    # A number reused across merged scopes does not identify one speaker.
    for segment in segments:
        if segment.get('speaker_match_source') == 'notes_inferred' and segment.get('id') not in protected:
            segment.update(
                person_id=None, speaker_identity_status='unknown', speaker_label_source=None, speaker_match_source=None
            )
        choices = bindings.get(segment.get('speaker_id'), set())
        scopes = {s.get('speaker_id_scope') for s in segments if s.get('speaker_id') == segment.get('speaker_id')}
        if len(choices) != 1 or len(scopes) > 1 or segment.get('is_user') or segment.get('id') in protected:
            continue
        segment.update(
            person_id=next(iter(choices)),
            speaker_identity_status='not_user',
            speaker_label_source='auto',
            speaker_match_source='notes_inferred',
        )
    segments = apply_manual_assignments(segments, receipt)
    encoded = encode({'transcript_segments': segments}, uid, level)
    write_data.update(encoded)
    write_data['notes_screen_frame_count'] = context.get('frame_count', 0)
    write_data['notes_written_at'] = now
    for pid, (created, person) in pending.items():
        ref = people_ref.document(pid)
        if created:
            transaction.create(ref, person)
        else:
            transaction.update(ref, person)
    return segments


def claim_late_evidence(transaction, conversation_ref, *, marker_at, fingerprint):
    """One automatic notes refresh per conversation; explicit titles veto it."""
    data = conversation_ref.get(transaction=transaction).to_dict() or {}
    if (
        data.get('deleted')
        or data.get('status') != 'completed'
        or (isinstance(data.get('user_title'), str) and data['user_title'].strip())
        or data.get('notes_screen_frame_count') != 0
        or not data.get('notes_written_at')
        or marker_at <= data['notes_written_at']
        or data.get('notes_evidence_reprocess_claimed')
    ):
        return False
    transaction.update(conversation_ref, {'notes_evidence_reprocess_claimed': fingerprint})
    return True
