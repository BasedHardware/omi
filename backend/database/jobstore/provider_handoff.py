"""Explicit dark binding for ordinary provider upload custody.

Admission uses the production upload transaction. Terminal sealing uses the
production typed Units transaction. Customer projection, dispatch effects and
native/partial/coalesced admission remain separate, unqualified adapters.
There is deliberately no runtime factory or legacy-queue fallback here.
"""

from dataclasses import asdict
import math
from typing import cast

from config.policy import BatchUnitPolicy
from database.batch_pipeline_projection_protocol import normalized_binding
from database.jobstore import codec
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.handoff import bounded
from database.jobstore.units import Units
from database.privacy_fence import owner_key
from utils.batch_pipeline.contracts import WorkItem, WorkResult
from utils.batch_pipeline.provider_stt_admission import SttRoute, ProviderReason, ProviderService

PROTOCOL = 'typed_provider_v1'


def _schedule(value):
    if not isinstance(value, dict) or set(value) != {'fresh', 'owner_turn', 'custody_deadline'}:
        raise AuthorityRefused('explicit provider class, rotation and custody deadline required')
    if (
        type(value['fresh']) is not bool
        or type(value['owner_turn']) is not int
        or not 0 <= value['owner_turn'] < 2**63
        or type(value['custody_deadline']) not in {int, float}
        or not math.isfinite(value['custody_deadline'])
        or value['custody_deadline'] <= 0
    ):
        raise AuthorityRefused('invalid provider schedule')
    return dict(value)


def provider_plan_enqueue(binding, plan):
    if not isinstance(plan, dict) or set(plan) != set(binding.segment_ids):
        raise AuthorityRefused('complete explicit provider sibling schedule required')
    schedules = {key: _schedule(value) for key, value in plan.items()}

    def enqueue(tx, item, now, *, policy):
        if policy.stt_route != 'provider' or item.requires_compute_admission or item.shadow:
            raise AuthorityRefused('ordinary funded provider work required')
        if tx.get('jobs', item.segment_id):
            raise AuthorityRefused('duplicate provider segment in immutable admission plan')
        route = SttRoute(policy.stt_route, policy.provider_reason, policy.provider_service, binding.language or 'multi')
        tx.put(
            'jobs',
            item.segment_id,
            {
                **item.to_dict(),
                'priority': int(item.priority),
                'owner_key': owner_key(item.owner_id),
                'policy': policy.to_dict(),
                'policy_source': 'admission',
                'enqueued_at': now,
                'state': 'provider_pending',
                'stt_route': asdict(route),
                'typed_provider': {'protocol': PROTOCOL, **schedules[item.segment_id]},
            },
        )
        return True

    return enqueue


def validate_provider_payload(payload, *, binding=None):
    """Validate again at SQL ingress; an FS document is not a trusted plan."""
    jobs = payload.get('jobs', {})
    if not isinstance(jobs, dict) or not jobs:
        raise AuthorityRefused('missing provider siblings')
    try:
        first = normalized_binding(next(iter(jobs.values()))['projection_binding'])
        if binding is not None and first != binding:
            raise AuthorityRefused('provider projection binding changed')
        if first.record_origin or first.native_record or first.partial_record or set(jobs) != set(first.segment_ids):
            raise AuthorityRefused('ordinary complete provider sibling census required')
        if set(payload) != {'jobs', 'intakes'} or set(payload['intakes']) - {first.job_id}:
            raise AuthorityRefused('provider intake census mismatch')
        for identity, source in jobs.items():
            item = WorkItem(**{key: source[key] for key in WorkItem.__dataclass_fields__ if key in source})
            policy = BatchUnitPolicy.from_dict(source['policy'])
            route = SttRoute(**source['stt_route'])
            schedule = dict(source['typed_provider'])
            if schedule.pop('protocol') != PROTOCOL:
                raise AuthorityRefused('unknown typed provider protocol')
            _schedule(schedule)
            if (
                set(source)
                != set(item.to_dict())
                | {
                    'owner_key',
                    'policy',
                    'policy_source',
                    'enqueued_at',
                    'state',
                    'stt_route',
                    'typed_provider',
                    'projection_binding',
                }
                or item.segment_id != identity
                or item.owner_id != first.owner_id
                or item.privacy_generation != first.privacy_generation
                or item.requires_compute_admission
                or item.shadow
                or source['owner_key'] != owner_key(first.owner_id)
                or normalized_binding(source['projection_binding']) != first
                or source['state'] != 'provider_pending'
                or source['policy_source'] != 'admission'
                or not policy.batch_enabled
                or policy.stt_route != 'provider'
                or asdict(route)
                != asdict(
                    SttRoute(
                        policy.stt_route,
                        cast(ProviderReason, policy.provider_reason),
                        cast(ProviderService, policy.provider_service),
                        first.language or 'multi',
                    )
                )
                or type(source['enqueued_at']) not in {int, float}
                or not math.isfinite(source['enqueued_at'])
                or source['enqueued_at'] < 0
                or schedule['custody_deadline'] <= source['enqueued_at']
            ):
                raise AuthorityRefused('provider source binding mismatch')
        # Reserve room BEFORE acknowledging source custody for the full intent,
        # sealed source/result references and exported envelope. No transcript
        # bytes enter this packet; bounded durable WorkResult refs do.
        if 2 * len(codec.canonical(payload).encode()) + 16384 * len(jobs) + 65536 > 256_000:
            raise AuthorityRefused('provider completion envelope budget exceeded')
    except (KeyError, TypeError, ValueError, StopIteration) as error:
        raise AuthorityRefused('invalid provider admission plan') from error
    return first


class ProviderHandoff:
    def __init__(self, handoff):
        self.handoff = handoff
        self.units = Units(handoff.pool, handoff.fence, handoff.ticket, handoff=handoff)

    def deliver(self, identity):
        def persist(conn, payload, admission):
            binding = validate_provider_payload(payload)
            if binding.job_id != identity:
                raise AuthorityRefused('provider recording identity mismatch')
            row = self.handoff._required_row(conn, identity)
            intent = row['intent']
            targets = {
                source['conversation_id'] for source in payload['jobs'].values() if source.get('conversation_id')
            }
            if binding.target_conversation_id:
                targets.add(binding.target_conversation_id)
            if intent['uid'] != binding.owner_id or set(intent['conversation_ids']) != targets:
                raise AuthorityRefused('provider admission owner/target mismatch')
            # Actual A1 targets can expand through redirects. Reserve their
            # exact admission size before creating any PG units; retain the FS
            # source intent on refusal instead of accepting impossible export.
            packet = {
                key: row[key]
                for key in ('namespace', 'identity', 'owner_key', 'epoch', 'fingerprint', 'intent', 'admission')
            }
            packet['completion'] = {
                'protocol': PROTOCOL,
                'recording_id': identity,
                'units': [
                    {
                        'unit_id': segment,
                        'source': payload['jobs'][segment],
                        'state': 'result_ready',
                        'result': 'x' * 16384,
                        'settled_at': 0,
                    }
                    for segment in binding.segment_ids
                ],
            }
            packet['completion_hash'] = '0' * 64
            bounded(packet)
            for segment in binding.segment_ids:
                source = payload['jobs'][segment]
                plan = source['typed_provider']
                self.units.admit(
                    conn,
                    segment,
                    owner_key(binding.owner_id),
                    identity,
                    admission,
                    capture_at=source['capture_at'],
                    units_total=len(binding.segment_ids),
                    custody_deadline=plan['custody_deadline'],
                    fresh=plan['fresh'],
                    owner_turn=plan['owner_turn'],
                    now=source['enqueued_at'],
                    source=source,
                )

        return self.handoff.deliver(identity, persist)


def seal_recording(conn, handoff, recording):
    """Last terminal CAS, sibling census and immutable envelope share COMMIT."""
    identity = recording['recording_id']
    row = handoff._required_row(conn, identity)
    payload = row['intent']['payload']
    binding = validate_provider_payload(payload)
    result = conn.execute(
        'SELECT * FROM units WHERE namespace=%s AND recording_id=%s', (handoff.ticket.namespace, identity)
    )
    units = {
        item['unit_id']: item for item in (dict(zip((c.name for c in result.description), value)) for value in result)
    }
    if (
        binding.job_id != identity
        or recording['owner_key'] != row['owner_key']
        or recording['units_final'] != recording['units_total']
        or recording['units_total'] != len(binding.segment_ids)
        or set(units) != set(binding.segment_ids)
    ):
        raise AuthorityRefused('provider terminal census mismatch')
    sealed = []
    for segment in binding.segment_ids:
        unit = units[segment]
        if (
            unit['owner_key'] != row['owner_key']
            or unit['admission'] != row['admission']
            or fingerprint(unit['source']) != fingerprint(payload['jobs'][segment])
            or unit['state'] not in {'result_ready', 'quarantined', 'privacy_blocked'}
            or unit['settled_at'] is None
        ):
            raise AuthorityRefused('provider terminal source/admission mismatch')
        if unit['state'] == 'result_ready':
            if WorkResult(**unit['result']).segment_id != segment:
                raise AuthorityRefused('provider terminal result identity mismatch')
        elif unit['result'] is not None:
            raise AuthorityRefused('refused provider unit carries a result')
        sealed.append({key: unit[key] for key in ('unit_id', 'source', 'state', 'result', 'settled_at')})
    return handoff.complete(conn, identity, {'protocol': PROTOCOL, 'recording_id': identity, 'units': sealed})
