"""Voice-profile preferences, tag-prompt pacing state, and owner voice confirmations."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from google.cloud import firestore

from utils.owner_voice_evidence import owner_base

from ._client import get_firestore_client, run_transactional
from .speaker_profile_authority import owner_teaching_authorized

SETTINGS_DEFAULTS: Dict[str, bool] = {
    'speaker_tag_prompts_enabled': True,
    'save_other_voice_profiles': True,
}
OWNER_VOICE_CONFIRMATIONS_MAX = 5
ANSWERED_PROMPT_RETENTION = timedelta(days=7)
_STATE_COLLECTION = 'speaker_tag_prompts'
_STATE_DOCUMENT = 'state'


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, str) and value.strip():
        try:
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)) if isinstance(value, datetime) else None


def _resolve_settings(data: Dict[str, Any]) -> Dict[str, bool]:
    return {
        key: default if data.get(key) is None else bool(data.get(key)) for key, default in SETTINGS_DEFAULTS.items()
    }


def get_voice_profile_settings(uid: str, *, firestore_client: Any = None) -> Dict[str, bool]:
    data = _client(firestore_client).collection('users').document(uid).get().to_dict() or {}
    return _resolve_settings(data)


def get_voice_profile_context(uid: str, *, firestore_client: Any = None) -> Tuple[Dict[str, bool], bool]:
    """Settings plus whether the owner has a voiceprint, from one user-document read."""
    data = _client(firestore_client).collection('users').document(uid).get().to_dict() or {}
    return _resolve_settings(data), bool(data.get('speaker_embedding'))


def set_voice_profile_settings(uid: str, updates: Dict[str, bool], *, firestore_client: Any = None) -> None:
    unknown = set(updates) - set(SETTINGS_DEFAULTS)
    if unknown:
        raise ValueError(f'Unknown voice profile setting(s): {", ".join(sorted(unknown))}')
    if not updates:
        return
    ref = _client(firestore_client).collection('users').document(uid)
    ref.set({key: bool(value) for key, value in updates.items()}, merge=True)


def _state_ref(uid: str, firestore_client: Any = None) -> Any:
    return (
        _client(firestore_client)
        .collection('users')
        .document(uid)
        .collection(_STATE_COLLECTION)
        .document(_STATE_DOCUMENT)
    )


def get_tag_prompt_state(uid: str, *, firestore_client: Any = None) -> Dict[str, Any]:
    return _state_ref(uid, firestore_client).get().to_dict() or {}


def _pruned_answers(state: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    cutoff = (as_utc(now) or datetime.now(timezone.utc)) - ANSWERED_PROMPT_RETENTION
    answered = state.get('answered') or {}
    return {k: at_utc for k, at in answered.items() if (at_utc := as_utc(at)) is not None and at_utc >= cutoff}


def record_tag_prompts_shown(uid: str, now: datetime, *, firestore_client: Any = None) -> bool:
    """Stamp a shown set. Returns True when this was the first set ever shown."""
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional
    def stamp(transaction: Any) -> bool:
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        first = not state.get('first_shown_at')
        update: Dict[str, Any] = {
            'last_shown_at': now,
            'shown_sets': int(state.get('shown_sets') or 0) + 1,
        }
        if first:
            update['first_shown_at'] = now
        if snapshot.exists:
            if state.get('last_empty_check_at') is not None:
                update['last_empty_check_at'] = firestore.DELETE_FIELD
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)
        return first

    return run_transactional(client, stamp)


def mark_tag_prompts_empty(uid: str, now: datetime, *, firestore_client: Any = None) -> None:
    """Remember that nothing was worth asking, so repeated opens skip the 48h scan."""
    _state_ref(uid, firestore_client).set({'last_empty_check_at': now}, merge=True)


def record_tag_prompts_dismissed(uid: str, now: datetime, *, firestore_client: Any = None) -> int:
    """Count a set closed without any answer. Returns the new streak length."""
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional
    def bump(transaction: Any) -> int:
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        streak = int(state.get('consecutive_dismissals') or 0) + 1
        update = {'consecutive_dismissals': streak, 'last_dismissed_at': now}
        if snapshot.exists:
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)
        return streak

    return run_transactional(client, bump)


def record_tag_prompt_answered(uid: str, prompt_id: str, now: datetime, *, firestore_client: Any = None) -> None:
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional
    def record(transaction: Any) -> None:
        snapshot = ref.get(transaction=transaction)
        answered = _pruned_answers(snapshot.to_dict() or {}, now)
        answered[prompt_id] = now
        update = {'answered': answered, 'consecutive_dismissals': 0, 'last_answered_at': now}
        if snapshot.exists:
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)

    run_transactional(client, record)


def answered_prompt_ids(state: Dict[str, Any], now: Optional[datetime] = None) -> set:
    return set(_pruned_answers(state, now or datetime.now(timezone.utc)))


def add_owner_voice_confirmation(
    uid: str,
    embedding: Sequence[float],
    pool: Callable[[List[List[float]]], List[float]],
    *,
    conversation_id: str,
    expected_receipt_generation: Optional[int] = None,
    segment_ids: Optional[List[str]] = None,
    card_generation: Optional[int] = None,
    firestore_client: Any = None,
) -> int:
    """Pool a confirmed owner clip into the owner's voiceprint in one transaction."""
    client = _client(firestore_client)
    ref = client.collection('users').document(uid)

    @firestore.transactional
    def pool_in(transaction: Any) -> int:
        if expected_receipt_generation is not None and not owner_teaching_authorized(
            transaction, ref, uid, conversation_id, segment_ids, expected_receipt_generation, card_generation
        ):
            return 0
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        base = owner_base(data)
        now = datetime.now(timezone.utc)
        confirmations = list(data.get('owner_voice_confirmations') or [])
        # One contribution per conversation: retries and repeated cards cannot
        # consume the entire bounded bank or amplify a single recording.
        confirmations = [item for item in confirmations if item.get('conversation_id') != conversation_id]
        confirmations.append(
            {
                'embedding': list(embedding),
                'conversation_id': conversation_id,
                'segment_ids': list(segment_ids or []),
                'generation': expected_receipt_generation,
                'at': now,
            }
        )
        confirmations = confirmations[-OWNER_VOICE_CONFIRMATIONS_MAX:]
        vectors = ([list(base)] if base else []) + [list(item['embedding']) for item in confirmations]
        update: Dict[str, Any] = {
            'speaker_embedding': pool(vectors),
            'speaker_embedding_updated_at': now,
            'owner_voice_pooled_at': now,
            'owner_voice_confirmations': confirmations,
        }
        if base:
            update['speaker_embedding_base'] = list(base)
        if snapshot.exists:
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)
        return len(confirmations)

    return run_transactional(client, pool_in)


IGNORED_VOICES_LIMIT = 200


def ignored_voice_key(conversation_id: str, speaker_id: int) -> str:
    return f'{conversation_id}:{speaker_id}'


def ignored_voices(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Stored "Not a Person" markers, newest first."""
    entries = [
        entry
        for entry in (state.get('ignored_voices') or {}).values()
        if isinstance(entry, dict) and entry.get('conversation_id') and isinstance(entry.get('speaker_id'), int)
    ]
    return sorted(
        entries,
        key=lambda entry: as_utc(entry.get('ignored_at')) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def ignored_voice_keys(state: Dict[str, Any]) -> set:
    return {ignored_voice_key(entry['conversation_id'], entry['speaker_id']) for entry in ignored_voices(state)}


def _newer_superseding_decision(
    client: Any,
    transaction: Any,
    uid: str,
    conversation_id: str,
    speaker_id: int,
    generation: Optional[int],
) -> bool:
    """True when a newer whole-voice decision already superseded this exclusion.

    Mirrors ``manual_rejected_speakers`` semantics: a speaker-scoped decision
    or a non-``segment_only`` segment decision at a newer generation unseats
    the exclusion — a positive assignment, and equally a different rejection
    kind (``not_me`` / ``not_person`` / an unnamed card answer), because the
    ignored-voice marker exists only for ``not_a_person``. A ``segment_only``
    (range) entry does not unseat a whole-voice decision.
    """
    if generation is None:
        return False
    # Imported lazily: database.conversations pulls a wide model graph whose
    # import order must not depend on this module (utils.speaker_identification
    # imports voice_profiles first, and a module-level import here once broke
    # test collection with a partially initialized database.conversations).
    from .conversations import conversations_collection
    from . import conversations

    conversation_ref = (
        client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    )
    raw = conversation_ref.get(transaction=transaction).to_dict() or {}
    receipt = conversations.decode_manual_speaker_assignments(
        uid, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )
    entries: List[Dict[str, Any]] = []
    speaker_entry = (receipt.get('speakers') or {}).get(str(speaker_id))
    if isinstance(speaker_entry, dict):
        entries.append(speaker_entry)
    entries.extend(
        entry
        for entry in (receipt.get('segments') or {}).values()
        if isinstance(entry, dict) and entry.get('speaker_id') == speaker_id
    )
    return any(not entry.get('segment_only') and entry.get('generation', 0) > generation for entry in entries)


def record_ignored_voice(
    uid: str,
    conversation_id: str,
    speaker_id: int,
    now: datetime,
    *,
    assignment_generation: Optional[int] = None,
    firestore_client: Any = None,
) -> None:
    """Remember a voice the user said is not a person (bounded, newest kept)."""
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional
    def record(transaction: Any) -> None:
        if _newer_superseding_decision(client, transaction, uid, conversation_id, speaker_id, assignment_generation):
            # A newer decision (positive assignment, or a non-not_a_person
            # rejection like not_me) already replaced this exclusion; recording
            # the stale-generation marker would re-ignore a voice the user
            # reassigned while this request was in flight.
            return
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        existing = ignored_voices(state).copy()
        existing_marker = next(
            (
                e
                for e in existing
                if ignored_voice_key(str(e['conversation_id']), int(e['speaker_id']))
                == ignored_voice_key(conversation_id, speaker_id)
            ),
            None,
        )
        if (
            existing_marker is not None
            and assignment_generation is not None
            and isinstance(existing_marker.get('assignment_generation'), int)
            and existing_marker['assignment_generation'] > assignment_generation
        ):
            # A newer exclusion (or a later decision that re-recorded this
            # marker) already owns the voice. Overwriting it with this older
            # write's marker would strand the newer exclusion's restore
            # linkage: Settings restores by matching the marker's generation
            # against the receipt, and remove would drop only this older
            # generation's receipt entries while the newer rejection stays
            # active but can no longer be restored.
            return
        entry: Dict[str, Any] = {'conversation_id': conversation_id, 'speaker_id': speaker_id, 'ignored_at': now}
        if assignment_generation is not None:
            entry['assignment_generation'] = assignment_generation
        kept = [
            e
            for e in existing
            if ignored_voice_key(str(e['conversation_id']), int(e['speaker_id']))
            != ignored_voice_key(conversation_id, speaker_id)
        ]
        kept = [entry, *kept][:IGNORED_VOICES_LIMIT]
        update = {
            'ignored_voices': {ignored_voice_key(str(e['conversation_id']), int(e['speaker_id'])): e for e in kept}
        }
        if snapshot.exists:
            transaction.update(ref, update)
        else:
            transaction.create(ref, update)

    run_transactional(client, record)


def remove_ignored_voice(
    uid: str, conversation_id: str, speaker_id: int, prompt_ids: list, *, firestore_client: Any = None
) -> bool:
    """Undo "Not a Person": drop the marker and forget those answered prompts so Omi may ask again."""
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional
    def remove(transaction: Any) -> bool:
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        ignored = dict(state.get('ignored_voices') or {})
        marker = ignored.pop(ignored_voice_key(conversation_id, speaker_id), None)
        if marker is None:
            return False
        # Imported lazily to keep this module's import order independent of the
        # wide database.conversations graph (see _newer_positive_decision).
        from .conversations import conversations_collection
        from . import conversations

        conversation_ref = (
            client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
        )
        raw = conversation_ref.get(transaction=transaction).to_dict() or {}
        receipt = conversations.decode_manual_speaker_assignments(
            uid, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
        )
        speakers = dict(receipt.get('speakers') or {})
        # Restore eligibility without undoing a newer manual label or guessing
        # which decision created a legacy marker without a generation fence.
        # One voice can also carry stacked not_a_person exclusions from
        # several generations — a whole-voice exclusion later narrowed by a
        # selected-segment one, or overlapping clients excluding different
        # segment sets — while the marker only remembers the newest
        # generation. A restore must therefore clear every exclusion decision
        # no newer than the marker: an older one left standing keeps the voice
        # excluded and prompt-suppressed after its sole marker (and Settings
        # restore affordance) is gone. Genuinely newer decisions keep their
        # authority and stay restorable through their own marker.
        receipt_changed = False
        marker_generation = marker.get('assignment_generation')

        def _restorable_exclusion(entry: dict) -> bool:
            # Droppable: not_a_person exclusions at/below the marker's
            # generation, plus the legacy pre-receipt-kind unnamed shape
            # (no rejection, no positive identity) those tests and documents
            # already promise restore clears. Explicit not_me / not_person
            # answers and every positive decision stay untouched.
            generation = entry.get('generation')
            rejection = entry.get('rejection') or {}
            kind = rejection.get('kind', 'not_a_person')
            return (
                isinstance(generation, int)
                and generation <= marker_generation
                and kind == 'not_a_person'
                and not entry.get('person_id')
                and not entry.get('is_user')
            )

        restorable_speaker = speakers.get(str(speaker_id))
        if (
            marker_generation is not None
            and isinstance(restorable_speaker, dict)
            and _restorable_exclusion(restorable_speaker)
        ):
            speakers.pop(str(speaker_id), None)
            receipt['speakers'] = speakers
            receipt_changed = True
        # Live-sheet bulk exclusions store segment-scoped decisions; a restore
        # must drop those too, or the speaker stays manually decided (and
        # prompt-suppressed) while the marker is gone from Settings.
        if marker_generation is not None:
            segments = {
                segment_id: entry
                for segment_id, entry in (receipt.get('segments') or {}).items()
                if not (
                    isinstance(entry, dict) and entry.get('speaker_id') == speaker_id and _restorable_exclusion(entry)
                )
            }
            if segments != dict(receipt.get('segments') or {}):
                if segments:
                    receipt['segments'] = segments
                else:
                    receipt.pop('segments', None)
                receipt_changed = True
        if receipt_changed:
            receipt['generation'] = receipt.get('generation', 0) + 1
            # Imported lazily for the same import-order reason as above.
            from . import conversations

            transaction.update(
                conversation_ref,
                conversations.encode_conversation_for_write(
                    uid, {'manual_speaker_assignments': receipt}, raw.get('data_protection_level', 'standard')
                ),
            )
        answered = {k: v for k, v in (state.get('answered') or {}).items() if k not in set(prompt_ids)}
        transaction.update(ref, {'ignored_voices': ignored, 'answered': answered})
        return True

    return run_transactional(client, remove)


def clear_ignored_voices(
    uid: str,
    conversation_id: str,
    speaker_ids: List[int],
    *,
    assignment_generation: Optional[int] = None,
    firestore_client: Any = None,
) -> int:
    """Drop ignored-voice markers a newer positive assignment supersedes.

    A later person/user assignment replaces the exclusion (the live sheet is
    reversible by design), so the marker that keeps the voice listed under
    Settings > Ignored Voices must not outlive the decision it recorded.

    Like the record path, the clear is fenced by assignment generation: a
    delayed clear from an older positive request must not remove a marker a
    newer decision recorded, or the voice would silently leave Settings >
    Ignored Voices and could no longer be restored from there.
    """

    if not speaker_ids:
        return 0
    client = _client(firestore_client)
    ref = _state_ref(uid, client)

    @firestore.transactional  # pyright: ignore[reportUntypedFunctionDecorator]
    def clear(transaction: Any) -> int:
        snapshot = ref.get(transaction=transaction)
        state = snapshot.to_dict() or {}
        ignored = dict(state.get('ignored_voices') or {})
        removed = 0
        for speaker_id in speaker_ids:
            key = ignored_voice_key(conversation_id, speaker_id)
            marker = ignored.get(key)
            if marker is None:
                continue
            marker_generation = marker.get('assignment_generation')
            if (
                assignment_generation is not None
                and isinstance(marker_generation, int)
                and marker_generation > assignment_generation
            ):
                # A newer decision (e.g. a re-exclusion) recorded this marker
                # after the positive request that queued this clear committed;
                # the newer decision owns the voice, so keep its marker.
                continue
            ignored.pop(key, None)
            removed += 1
        if removed:
            transaction.update(ref, {'ignored_voices': ignored})
        return removed

    return run_transactional(client, clear)
