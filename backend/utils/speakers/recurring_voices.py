"""Pure, precision-first policy for private batch-only recurring voices."""

from collections import Counter

from utils.speakers import auto_enroll as pools
from utils.stt.speaker_match import select_speaker_match, arbitrate_owner_matches

MAX_PROFILES = 25
MAX_NEW = 3
CANDIDATE_AGE = 30 * 86400
MIN_SECONDS = 30


def active(profile, now):
    entries = pools.active(profile.get('entries') or [], now)
    if not entries:
        return None
    if profile.get('state') == 'candidate' and now - min(e['at'] for e in entries) >= CANDIDATE_AGE:
        return None
    current = {**profile, 'entries': entries}
    if current.get('state') != 'rejected' and len({e['conversation_id'] for e in entries}) < 2:
        current['state'] = 'candidate'
        current.pop('bound_person_id', None)
        current.pop('bound_conversation_id', None)
    return current


def vector(profile, now, owner):
    return pools.vector(profile.get('entries') or [], now, owner)


def retract(profile, conversations):
    entries = [e for e in profile['entries'] if e['conversation_id'] not in conversations]
    if not entries:
        return None
    if entries == profile['entries'] and profile.get('bound_conversation_id') not in conversations:
        return profile
    result = {**profile, 'entries': entries}
    result.pop('bound_person_id', None)
    result.pop('bound_conversation_id', None)
    result['state'] = (
        'rejected' if profile.get('state') == 'rejected' else 'recurring' if len(entries) >= 2 else 'candidate'
    )
    return result


def evaluate(
    centroids, prints, profiles, conversation_id, now, *, owner_reserved=False, created_ids=(), evidence_at=None
):
    """Return new profile state, cluster identities, events and match outcomes.

    Candidates compete for learning but cannot identify speech until recurrence.
    All person prints and all profiles share one calibrated margin arbitration.
    """
    evidence_at = now if evidence_at is None else evidence_at
    owner = prints.get('user')
    profiles = {vid: p for vid, raw in profiles.items() if (p := active(raw, now)) is not None}
    events = []
    roster = {f'person:{pid}': pools.unit(v) for pid, v in prints.items()}
    for vid, profile in profiles.items():
        roster['recurring:' + vid] = pools.unit(vector(profile, now, owner))
    roster = {key: v for key, v in roster.items() if v is not None}
    rows, decisions = {}, {}
    for speaker, cluster in centroids.items():
        v = pools.unit(cluster.get('embedding'))
        if v is None or cluster.get('evidence_seconds', 0) < 5:
            continue
        # Bound profiles use the same identity as their person's print, so two
        # prints of one confirmed person cannot create a spurious runner-up.
        row = {}
        for key, reference in roster.items():
            target = key
            if key.startswith('recurring:'):
                profile = profiles[key.split(':', 1)[1]]
                bound_person = profile.get('bound_person_id')
                pid = bound_person if isinstance(bound_person, str) else None
                authoritative = pools.unit(prints.get(pid)) if pid else None
                if pid and (authoritative is None or 1 - reference @ authoritative > pools.MAX_DISTANCE):
                    profile.pop('bound_person_id', None)
                    profile.pop('bound_conversation_id', None)
                    profile['state'] = 'recurring'
                elif pid:
                    target = 'person:' + pid
            row[target] = min(row.get(target, 2), float(1 - v @ reference))
        rows[speaker] = row
        # Owner arbitration expects the literal user key.
        if 'person:user' in row:
            row['user'] = row.pop('person:user')
        decisions[speaker] = select_speaker_match(row, threshold=0.50, margin=0.10)
    decisions = arbitrate_owner_matches(rows, decisions, owner_reserved=owner_reserved)
    counts = Counter(d.person_id for d in decisions.values() if d.person_id and d.person_id.startswith('recurring:'))
    labels, outcomes, created = {speaker: {} for speaker in centroids}, [], len(created_ids)
    for speaker, cluster in centroids.items():
        decision = decisions.get(speaker)
        winner = decision.person_id if decision else None
        v = pools.unit(cluster.get('embedding'))
        if winner == 'user' or (winner and winner.startswith('person:')):
            pid = winner.removeprefix('person:')
            labels[speaker] = {'person_id': pid}
            bound = [
                (float(1 - v @ pools.unit(vector(p, now, owner))), vid)
                for vid, p in profiles.items()
                if p.get('bound_person_id') == pid and pools.unit(vector(p, now, owner)) is not None
            ]
            if bound and min(bound)[0] < 0.50:
                profile_id = min(bound)[1]
                labels[speaker]['recurring_voice_id'] = profile_id
                outcomes.append('matched')
                if (
                    len(centroids) >= 2
                    and cluster.get('evidence_seconds', 0) >= MIN_SECONDS
                    and not owner_reserved
                    and pools.owner_safe(v, owner)
                ):
                    profile = profiles[profile_id]
                    contribution = dict(
                        vector=v.tolist(), conversation_id=conversation_id, seconds=cluster['evidence_seconds']
                    )
                    entries = pools.refresh(profile['entries'], contribution, now)
                    if entries is not None and pools.vector(entries, now, owner) is not None:
                        for entry in entries:
                            if entry['conversation_id'] == conversation_id:
                                entry['at'] = min(entry['at'], evidence_at)
                        profiles[profile_id] = {**profile, 'entries': entries}
                        events.append('refreshed')
            continue
        if pools.unit(owner) is None:
            outcomes.append('no_owner_print')
            continue
        if not pools.owner_safe(v, owner) or owner_reserved:
            outcomes.append('owner_excluded')
            continue
        if winner and counts[winner] > 1:
            outcomes.append('abstained_margin')
            continue
        profile_id = winner.split(':', 1)[1] if winner else None
        if profile_id and profiles[profile_id]['state'] == 'rejected':
            continue
        if profile_id and profiles[profile_id]['state'] in {'recurring', 'bound'}:
            labels[speaker] = {'recurring_voice_id': profile_id}
            outcomes.append('matched')
        if len(centroids) < 2 or cluster.get('evidence_seconds', 0) < MIN_SECONDS:
            continue
        if decision and not winner and rows.get(speaker) and min(rows[speaker].values()) <= 0.60:
            outcomes.append('abstained_margin')
            continue
        contribution = dict(vector=v.tolist(), conversation_id=conversation_id, seconds=cluster['evidence_seconds'])
        if profile_id:
            profile = profiles[profile_id]
            entries = pools.refresh(profile['entries'], contribution, now)
            if entries is None or pools.vector(entries, now, owner) is None:
                continue
            state = 'recurring' if len(entries) >= 2 else 'candidate'
            events.append('promoted' if profile['state'] == 'candidate' and state == 'recurring' else 'refreshed')
            for entry in entries:
                if entry['conversation_id'] == conversation_id:
                    entry['at'] = min(entry['at'], evidence_at)
            profiles[profile_id] = {**profile, 'entries': entries, 'state': state}
            if state == 'recurring':
                labels[speaker] = {'recurring_voice_id': profile_id}
                if profile['state'] == 'candidate':
                    outcomes.append('matched')
        elif created < MAX_NEW and now - evidence_at < CANDIDATE_AGE:
            # Stable per source+cluster: retries cannot amplify a contribution.
            import hashlib

            profile_id = hashlib.sha256(f'{conversation_id}:{speaker}'.encode()).hexdigest()[:32]
            if profile_id in profiles or profile_id in created_ids:
                continue  # A rejection tombstone is never resurrected by replay.
            if len(profiles) >= MAX_PROFILES:
                evictable = [
                    (max(e['at'] for e in p['entries']), vid) for vid, p in profiles.items() if p['state'] != 'rejected'
                ]
                if not evictable:
                    outcomes.append('cap')
                    continue
                profiles.pop(min(evictable)[1])
                events.append('evicted_cap')
            profiles[profile_id] = {'state': 'candidate', 'entries': [{**contribution, 'at': evidence_at}]}
            created += 1
            events.append('created')
            outcomes.append('new_candidate')
    return profiles, labels, events, outcomes


def near_misses(embedding, prints):
    v = pools.unit(embedding)
    if v is None:
        return []
    candidates = []
    for pid, raw in prints.items():
        reference = pools.unit(raw)
        if pid != 'user' and reference is not None and 0.50 <= 1 - v @ reference <= 0.60:
            candidates.append({'person_id': pid, 'level': 1, 'suggest': False})
    return candidates[:5]
