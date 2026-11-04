"""Lightweight C8 route admission, shared by native capture and CPU provider stages."""

from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal

from config.policy import BatchUnitPolicy
from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL, normalized_stt_language
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.scheduler import owner_key

PARAKEET_MODEL = 'nvidia/parakeet-tdt-0.6b-v3'
PENDING = 'provider_pending'

SttRouteName = Literal['parakeet', 'provider']
ProviderReason = Literal['none', 'byok', 'unsupported_language']
ProviderService = Literal['none', 'byok', 'soniox', 'deepgram', 'modulate']
_ROUTES = frozenset({'parakeet', 'provider'})
_PROVIDER_REASONS = frozenset({'none', 'byok', 'unsupported_language'})
_SERVICES = frozenset({'none', 'byok', 'soniox', 'deepgram', 'modulate'})


@dataclass(frozen=True)
class SttRoute:
    """Admission-time STT route; the contract (c) policy fields of the same names."""

    stt_route: SttRouteName
    provider_reason: ProviderReason
    provider_service: ProviderService
    language: str

    def __post_init__(self):
        if self.stt_route not in _ROUTES:
            raise ValueError('closed stt_route required')
        if self.provider_reason not in _PROVIDER_REASONS:
            raise ValueError('closed provider_reason required')
        if self.provider_service not in _SERVICES:
            raise ValueError('closed provider_service required')
        if (self.stt_route == 'provider') != (self.provider_service != 'none'):
            raise ValueError('a provider route names exactly one provider service')
        if not self.language or len(self.language) > 16:
            raise ValueError('bounded language required')


def resolve_route(language: str | None, *, byok: bool = False) -> SttRoute:
    """Decide once at admission. Unknown language is ``multi``: Parakeet, as legacy sync.

    BYOK uploads are routed like every other upload (David, 10-19): sync
    pre-recorded STT has never used a BYOK key, and enrichment runs on Omi's keys.
    ``provider_reason='byok'`` only records the admission-time funding decision,
    made while the validated keys were present, so later keyless stages never
    re-hold the unit (contract (c): admission decides once).
    """
    normalized = normalized_stt_language(language) or 'multi'
    if normalized in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL]:
        return SttRoute('parakeet', 'byok' if byok else 'none', 'none', normalized)
    return SttRoute('provider', 'byok' if byok else 'unsupported_language', 'modulate', normalized[:16])


def enqueue_in_transaction(
    tx, item: WorkItem, now: float, *, route: SttRoute, policy: BatchUnitPolicy, native_record: bool = False
) -> bool:
    """Write a provider unit outside the GPU ring; the admission ``enqueue`` hook.

    Mirrors ``Scheduler.enqueue_in_transaction``'s immutable-work check, owner
    revision fence and late-capture watermark, but never touches queues or
    control shards, so no GPU pull can lease it.
    """
    if route.stt_route != 'provider':
        raise ValueError('only provider routes bypass the GPU ring')
    if item.requires_compute_admission:
        raise ValueError('provider units are funded by the provider stage, not GPU compute admission')
    previous = tx.get('jobs', item.segment_id)
    immutable = {**item.to_dict(), 'priority': int(item.priority)}
    pending_record = previous.get('state') == 'record_pending'
    if pending_record and not native_record:
        raise ValueError('a pending recording cannot take the provider route')
    if pending_record and (
        previous.get('owner_id') != item.owner_id
        or previous.get('conversation_id') != item.conversation_id
        or previous.get('privacy_generation') != item.privacy_generation
    ):
        raise ValueError('pending recording owner cannot change')
    if previous and not pending_record:
        if any(
            previous.get(key) != value
            for key, value in immutable.items()
            if not (key == 'privacy_generation' and value is None)
        ) or previous.get('stt_route') != asdict(route):
            raise ValueError('segment ID reused with different immutable work')
        return False
    key = owner_key(item.owner_id)
    owner = tx.get('owners', key)
    watermark = owner.get('watermark')
    job = {
        # Unstamped work keeps the legacy document shape; readers default to None.
        **{key: value for key, value in immutable.items() if key != 'timing_store' or value is not None},
        'policy': policy.to_dict(),
        'policy_source': 'admission',
        'protocol_version': 1,
        'owner_key': key,
        'enqueued_at': now,
        'state': PENDING,
        'attempt': 0,
        'token': '',
        'lease_until': 0.0,
        'available_at': now,
        'merge_pending': True,
        'next': '',
        'stt_route': asdict(route),
        'late_capture': bool(
            watermark and (item.capture_at, item.segment_id) <= (watermark['capture_at'], watermark['segment_id'])
        ),
    }
    tx.put('jobs', item.segment_id, job)
    owner['revision'] = owner.get('revision', 0) + 1
    tx.put('owners', key, owner)
    return True


def provider_enqueue(
    route: SttRoute, outbox: Any, wakes: dict[str, str], *, native_record: bool = False
) -> Callable[..., bool]:
    """The admit() ``enqueue`` hook: the job row and its outbox row commit together.

    ``wakes`` collects ``row_id -> wake_token``; the caller calls ``outbox.wake``
    for each after the admission transaction commits (contract (b), invariant 4).
    A retried transaction body overwrites the same keys.
    """

    def enqueue(tx: Any, item: WorkItem, now: float, *, policy: BatchUnitPolicy) -> bool:
        created = enqueue_in_transaction(tx, item, now, route=route, policy=policy, native_record=native_record)
        if created:
            result = outbox.enqueue(
                item.segment_id, item.owner_id, {'segment_id': item.segment_id}, now, tx=tx, now=now
            )
            if result.wake_token:
                wakes[result.row_id] = result.wake_token
        return created

    return enqueue
