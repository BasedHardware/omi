"""Bounded, conversation-local batch voice continuity; no I/O or enrollment learning.

Anchors are immutable: retries and multipart crops cannot overweight a voice or
walk its centroid toward a different speaker. Only the assignment transaction
may persist the encrypted registry with the transcript and projection receipt.
"""

from copy import deepcopy
import json
import math

from utils.stt.speaker_identity import canonical_speaker_label
from utils.speakers.policy import CROSS_SCOPE_CLUSTER, MATCH_MARGIN, MIN_EVIDENCE_SECONDS

FIELD = 'batch_voice_registry'
MAX_VOICES = 32
MAX_BINDINGS = 256
MAX_VECTOR_DIMENSIONS = 512
MAX_REGISTRY_BYTES = 192 * 1024


def linking_enabled():
    # This stage boundary deliberately overrides policies pinned before rollout.
    from config.policy import kill_switch

    return kill_switch('BATCH_PIPELINE_VOICE_LINKING_ENABLED')


def decode_registry(value, uid):
    """Invalid ciphertext abstains; never accept a legacy plaintext voice store."""
    if not isinstance(value, str) or len(value) > MAX_REGISTRY_BYTES * 2:
        return {}
    from utils import encryption

    try:
        decoded = encryption.decrypt(value, uid)
        if decoded == value:
            return {}
        result = json.loads(decoded)
        if not isinstance(result, dict) or result.get('version') != 1:
            return {}
        if len(json.dumps(result)) > MAX_REGISTRY_BYTES:
            return {}
        if not isinstance(result.get('voices'), dict) or not isinstance(result.get('bindings'), dict):
            return {}
        if len(result['voices']) > MAX_VOICES or len(result['bindings']) > MAX_BINDINGS:
            return {}
        return result
    except (TypeError, ValueError):
        return {}


def encode_registry(registry, uid):
    from utils import encryption

    payload = json.dumps(registry, separators=(',', ':'), allow_nan=False)
    if len(payload.encode()) > MAX_REGISTRY_BYTES:
        raise ValueError('batch voice registry size limit')
    return encryption.encrypt(payload, uid)


def _vector(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_VECTOR_DIMENSIONS:
        return None
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        return None
    norm = math.sqrt(sum(x * x for x in value))
    return [x / norm for x in value] if norm > 0 and math.isfinite(norm) else None


def _identity(value):
    if not isinstance(value, dict):
        return None
    return 'user' if value.get('is_user') else 'person:' + str(value['person_id']) if value.get('person_id') else None


def _manual_identities(speaker_id, receipt, segments):
    identities = set()
    speakers = receipt.get('speakers') or {}
    decision = speakers.get(str(speaker_id))
    identity = _identity(decision)
    if isinstance(decision, dict) and (decision.get('rejection') or {}).get('kind') == 'not_me':
        identity = '!user'
    if identity:
        identities.add(identity)
    overrides = receipt.get('segments') or {}
    for segment in segments:
        if segment.get('speaker_id') == speaker_id:
            identity = _identity(overrides.get(segment.get('id')))
            if identity:
                identities.add(identity)
    return identities


def link_unit_voices(
    registry, evidence, segments, allocator, *, receipt=None, existing=(), enabled=True, conversation_id=None
):
    """Bind scoped labels before allocation, returning a new bounded registry.

    Existing bindings always win, including while disabled. New links require
    compatible immutable embedding provenance, five clean seconds, a unique
    nearest anchor, and no competing incoming voice claiming that anchor.
    """
    receipt = receipt or {}
    scope = evidence.get('scope')
    generation = evidence.get('privacy_generation')
    if not isinstance(scope, str) or not scope.startswith('final:batch:') or len(scope) > 160:
        return registry
    if type(generation) is not int or generation < 0:
        return registry
    state = (
        deepcopy(registry)
        if registry.get('privacy_generation') == generation and registry.get('conversation_id') == conversation_id
        else {}
    )
    if not state:
        state = {
            'version': 1,
            'privacy_generation': generation,
            'conversation_id': conversation_id,
            'voices': {},
            'bindings': {},
        }
    voices, bindings = state['voices'], state['bindings']
    allocator.hydrate_receipt({'speakers': {str(sid): {} for sid in bindings.values() if type(sid) is int}})
    labels = sorted(
        {
            canonical_speaker_label(str(s.get('speaker')))
            for s in segments
            if s.get('speaker_id_scope') == scope and s.get('speaker')
        }
    )
    if len(labels) > MAX_BINDINGS:
        return state
    provenance = evidence.get('provenance') or {}
    space = evidence.get('embedding_space')
    signature = [space, provenance.get('embedding_model'), provenance.get('embedding_revision')]
    compatible = all(isinstance(value, str) and 0 < len(value) <= 160 for value in signature)
    centroids = evidence.get('centroids') or {}
    if not isinstance(centroids, dict):
        centroids = {}
    centroids = {canonical_speaker_label(str(key)): value for key, value in centroids.items()}
    candidates, vectors, identities = {}, {}, {}
    for label in labels:
        key = scope + '/' + label
        bound = bindings.get(key)
        if type(bound) is int and bound >= 0:
            allocator.bind(scope, label, bound)
            continue
        # Persisted transcript scopes remain authoritative if the registry filled.
        allocated = allocator.lookup(scope, label)
        samples = [s for s in segments if canonical_speaker_label(str(s.get('speaker'))) == label]
        incoming_names = {_identity(s) for s in samples} - {None}
        incoming_manual = {_identity((receipt.get('segments') or {}).get(s.get('id'))) for s in samples} - {None}
        identities[label] = incoming_manual or incoming_names
        sample = centroids.get(label) or {}
        if not isinstance(sample, dict):
            sample = {}
        seconds = sample.get('evidence_seconds', 0)
        vector = _vector(sample.get('embedding'))
        valid = type(seconds) in (float, int) and math.isfinite(seconds) and seconds >= MIN_EVIDENCE_SECONDS
        if enabled and compatible and valid and vector is not None:
            vectors[label] = vector
        if allocated is not None or label not in vectors:
            continue
        occupied = {s.get('speaker_id') for s in existing if s.get('speaker_id_scope') == scope}
        ranked = []
        for sid, voice in voices.items():
            if not isinstance(voice, dict) or not str(sid).isdigit():
                continue
            if int(sid) in occupied or voice.get('signature') != signature or scope in (voice.get('units') or []):
                continue
            anchor = _vector(voice.get('embedding'))
            if anchor is None or len(anchor) != len(vector):
                continue
            manual = _manual_identities(int(sid), receipt, existing)
            if len(manual) > 1 or manual and identities[label] and manual != identities[label]:
                continue
            distance = 1 - sum(a * b for a, b in zip(vector, anchor))
            ranked.append((distance, int(sid)))
        ranked.sort()
        if (
            ranked
            and CROSS_SCOPE_CLUSTER.accepts(ranked[0][0])
            and (len(ranked) == 1 or ranked[1][0] - ranked[0][0] >= MATCH_MARGIN)
        ):
            candidates[label] = ranked[0][1]
    # Two unit voices near one prior voice are both ambiguous, rather than
    # allowing input order to choose the winner and force the other elsewhere.
    contested = {sid for sid in candidates.values() if list(candidates.values()).count(sid) > 1}
    for label in labels:
        key = scope + '/' + label
        if key in bindings:
            continue
        before = deepcopy(state)
        sid = candidates.get(label)
        if sid is not None and sid not in contested:
            allocator.bind(scope, label, sid)
        segment = {'speaker_id_scope': scope, 'speaker': label}
        allocator.assign(segment)
        sid = segment['speaker_id']
        if len(bindings) < MAX_BINDINGS:
            bindings[key] = sid
        if label in vectors and len(bindings) <= MAX_BINDINGS:
            voice = voices.get(str(sid))
            if voice is not None and voice.get('signature') == signature:
                units = voice.setdefault('units', [])
                if scope not in units and len(units) < MAX_BINDINGS:
                    units.append(scope)
            elif len(voices) < MAX_VOICES:
                voices[str(sid)] = {'embedding': vectors[label], 'signature': signature, 'units': [scope]}
        if len(json.dumps(state, separators=(',', ':')).encode()) > MAX_REGISTRY_BYTES:
            state = before
            voices, bindings = state['voices'], state['bindings']
    return state


def arbitrate_linked_owner_claims(segments, receipt):
    """Distinct automatic voices may not simultaneously claim the owner."""
    from utils.manual_speaker_assignments import manual_assignment_decision

    manual = set()
    for segment in segments:
        decision = manual_assignment_decision(segment, receipt)
        if decision and decision.get('is_user') and not decision.get('segment_only'):
            manual.add(segment.get('speaker_id'))
    owners = {s.get('speaker_id') for s in segments if s.get('is_user')}
    if len(owners) <= 1 and not (manual and owners - manual):
        return segments

    result = []
    for segment in segments:
        decision = manual_assignment_decision(segment, receipt)
        if segment.get('is_user') and segment.get('speaker_id') not in manual and not decision:
            segment = {
                **segment,
                'is_user': False,
                'person_id': None,
                'speaker_identity_status': 'ambiguous',
                'speaker_match_source': 'batch_owner_contention',
            }
        result.append(segment)
    return result
