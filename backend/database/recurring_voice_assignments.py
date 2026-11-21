"""Read-phase recurring binding/retraction inside the manual assignment transaction."""

from datetime import datetime, timezone
from types import SimpleNamespace

from config.batch_conversation_speakers import recurring_enabled_for
from database import recurring_voices as store
from utils.speaker_learning_policy import winning_receipt_decision
from utils.speakers import auto_enroll as pools, recurring_voices as policy
from utils.stt.voiceprints import usable_person_voiceprint


def prepare(
    transaction,
    user,
    owner,
    conversation_id,
    before,
    segments,
    receipt,
    resolved,
    *,
    person_id=None,
    person=None,
    is_user=False,
    rejection=None,
    train=True,
):
    if not pools.retained(owner):
        return None, []
    selected = set(resolved)
    voices = {s.get('recurring_voice_id') for s in before if s.get('id') in selected and s.get('recurring_voice_id')}
    if not voices:
        return None, []
    profiles = store.read_profiles(transaction, user, owner)
    events = []
    authority = [
        SimpleNamespace(speaker_id_scope=s.get('speaker_id_scope'), provider_speaker=s.get('provider_speaker'))
        for s in before
    ]
    enabled = recurring_enabled_for(user.id, authority)
    now = datetime.now(timezone.utc).timestamp()
    for vid in voices:
        profile = profiles.get(vid)
        if profile is None:
            continue
        # A rejection is a negative identity receipt, not another training sample.
        if rejection or is_user:
            profile.pop('bound_person_id', None)
            profile.pop('bound_conversation_id', None)
            profile['state'] = 'rejected'
            events.append('rejected')
            continue
        decisions = [winning_receipt_decision(receipt, s) for s in segments if s.get('recurring_voice_id') == vid]
        people = {d.get('person_id') for d in decisions if d and d.get('person_id')}
        conflict = len(people) > 1 or (person_id and profile.get('bound_person_id') not in (None, person_id))
        if conflict:
            sources = {conversation_id, profile.get('bound_conversation_id')}
            following = policy.retract(profile, sources)
            if following:
                following.pop('bound_person_id', None)
                following.pop('bound_conversation_id', None)
                following['state'] = 'recurring' if len(following['entries']) >= 2 else 'candidate'
                profiles[vid] = following
            else:
                profiles.pop(vid)
            continue
        if (
            not enabled
            or not train
            or not person_id
            or not person
            or person.get('is_dismissed')
            or person.get(pools.REVOKED_FIELD)
        ):
            continue
        # The current receipt must authorize the exact selected segments. Carried
        # assignments cannot bind an inferred profile to a person's identity.
        relevant = [s for s in segments if s.get('id') in selected and s.get('recurring_voice_id') == vid]
        if not relevant or any(
            not (d := winning_receipt_decision(receipt, s))
            or d.get('person_id') != person_id
            or d.get('is_user')
            or d.get('source') == 'carried'
            or d.get('use_for_speech_training') is False
            for s in relevant
        ):
            continue
        current = policy.active(profile, now)
        if current is None or current['state'] == 'rejected' or len(current['entries']) < 2:
            continue
        reference = pools.unit(
            pools.usable(user.id, {**person, 'id': person_id}, owner) or usable_person_voiceprint(person)
        )
        incoming = pools.unit(policy.vector(current, now, owner.get('speaker_embedding')))
        if reference is None or incoming is None or 1 - reference @ incoming > pools.MAX_DISTANCE:
            continue
        if profile.get('bound_person_id') != person_id:
            events.append('bound')
        profiles[vid] = {
            **current,
            'state': 'bound',
            'bound_person_id': person_id,
            'bound_conversation_id': conversation_id,
        }
    return profiles, events
