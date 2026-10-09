"""One durable item per proactive evaluation, shared by every client surface."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from config.proactivity_v2 import ProactivityDenied, Producer, active_plan, daily_cap, producer_for, utc_now
from database._client import get_customer_firestore_client
from database import proactivity_redis
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status

logger = logging.getLogger(__name__)

ITEMS = 'proactivity_items'
DAYS = 'proactivity_budget_days'
CONTROLS = 'proactivity_producer_controls'
PREFERENCES = 'proactivity_preferences'
POSITIVE = frozenset({'opened', 'accepted', 'thumbs_up', 'replied'})
ACTIONS = POSITIVE | {'shown', 'thumbs_down', 'producer_disabled', 'dismissed', 'timeout'}


def client_or_default(client: Any = None) -> Any:
    return client if client is not None else get_customer_firestore_client()


def user_ref(client: Any, uid: str) -> Any:
    if not uid or '/' in uid:
        raise ProactivityDenied('invalid_owner')
    return client.collection('users').document(uid)


def item_ref(client: Any, uid: str, item_id: str) -> Any:
    if len(item_id) != 32 or any(c not in '0123456789abcdef' for c in item_id):
        raise ProactivityDenied('not_found')
    return user_ref(client, uid).collection(ITEMS).document(item_id)


def data_at(ref: Any, tx: Any = None) -> dict[str, Any]:
    snapshot = ref.get(transaction=tx) if tx is not None else ref.get()
    return snapshot.to_dict() or {} if snapshot.exists else {}


def read_owner(client: Any, uid: str, tx: Any = None) -> tuple[dict[str, Any], str]:
    user = data_at(user_ref(client, uid), tx)
    marker_ref = client.collection('account_deletions').document(uid)
    snapshot = marker_ref.get(transaction=tx) if tx is not None else marker_ref.get()
    marker = snapshot.to_dict() or {}
    status = normalize_account_deletion_status(marker_exists=snapshot.exists, raw_status=marker.get('wipe_status'))
    if not user or account_deletion_blocks_access(status):
        raise ProactivityDenied('not_found')
    generation = hashlib.sha256(
        f'{uid}:{user.get("created_at", "")}:{marker.get("wipe_job_id", "")}'.encode()
    ).hexdigest()
    return user, generation


def source_ref(client: Any, uid: str, kind: str, source_id: str) -> Any:
    if kind not in {'conversation', 'action_item'} or not source_id or '/' in source_id:
        raise ProactivityDenied('invalid_source')
    return (
        user_ref(client, uid)
        .collection('conversations' if kind == 'conversation' else 'action_items')
        .document(source_id)
    )


def source_visible(client: Any, uid: str, item: dict[str, Any], tx: Any = None) -> bool:
    source = data_at(source_ref(client, uid, item['source_kind'], item['source_id']), tx)
    return bool(source) and not source.get('deleted') and not source.get('is_deleted')


def admission_records(client: Any, uid: str, producer: Producer, tx: Any, now: datetime) -> tuple[str, int]:
    user, generation = read_owner(client, uid, tx)
    preference = data_at(user_ref(client, uid).collection(PREFERENCES).document(producer.name), tx)
    control = data_at(client.collection(CONTROLS).document(producer.name), tx)
    if preference.get('enabled') is False or control.get('state') == 'killed':
        raise ProactivityDenied('producer_disabled')
    if control.get('version') != producer.version or now - control.get(
        'checked_at', datetime.min.replace(tzinfo=timezone.utc)
    ) > timedelta(seconds=60):
        raise ProactivityDenied('health_unavailable')
    if producer.name == 'conversation_mentor_v2' and user.get('mentor_notification_frequency', 0) <= 0:
        raise ProactivityDenied('disabled')
    cap, _ = daily_cap(active_plan(user, now))
    if cap <= 0:
        raise ProactivityDenied('not_paid')
    return generation, cap


def claim_item(
    *,
    uid: str,
    producer: str,
    source_kind: str,
    source_id: str,
    source_revision: str,
    source_event_id: str,
    source_surface: str = 'server',
    firestore_client: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    client = client_or_default(firestore_client)
    now = now or utc_now()
    row = producer_for(producer)
    if not source_revision or not source_event_id or max(len(source_revision), len(source_event_id)) > 128:
        raise ProactivityDenied('invalid_source')
    identity = json.dumps(
        [uid, producer, row.version, source_id, source_revision, source_event_id], separators=(',', ':')
    )
    identity_hash = hashlib.sha256(identity.encode()).hexdigest()[:32]
    ref = item_ref(client, uid, identity_hash)
    item = dict(
        schema_version=1,
        item_id=identity_hash,
        producer=producer,
        producer_version=row.version,
        source_kind=source_kind,
        source_id=source_id,
        source_revision=source_revision,
        source_event_id=source_event_id,
        source_surface=source_surface,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=90),
        state='claimed',
        terminal_reason='',
        claim_token=secrets.token_hex(16),
        attempts={},
        reserved_micro_usd=0,
        charged_micro_usd=0,
        estimated_cost_micro_usd=0,
        cost_status='none',
        delivered=False,
        delivery_channel='none',
        delivery_surface='',
        push_state='eligible' if row.push_earned else 'not_earned',
        acted_24h=False,
        negative=False,
        dismissed=False,
        outcomes={},
        delivered_count=0,
        acted_count=0,
        negative_count=0,
        unknown_count=0,
    )

    @firestore.transactional
    def transact(tx: Any):
        generation, _ = admission_records(client, uid, row, tx, now)
        prior = data_at(ref, tx)
        visible = source_visible(client, uid, item, tx)
        if prior:
            # Only the one-call due-event producer can reclaim an abandoned claim.
            # Its deterministic gateway call ID also fences a late original worker.
            if producer != 'commitment_followup' or prior['state'] != 'claimed':
                raise ProactivityDenied('duplicate')
            if prior['account_generation'] != generation or not visible:
                raise ProactivityDenied('not_found')
            if now < prior['updated_at'] + timedelta(minutes=5):
                raise ProactivityDenied('claim_in_progress')
            if prior['attempts'] or now >= prior['created_at'] + timedelta(hours=24):
                # Never redispatch after ANY durable attempt, including ambiguous spend.
                # Preserve attempts and money for accounting reconciliation.
                prior.update(state='failed', terminal_reason='abandoned_claim', updated_at=now)
                tx.set(ref, prior)
                return None
            prior.update(claim_token=item['claim_token'], updated_at=now)
            tx.set(ref, prior)
            return prior
        if not visible:
            raise ProactivityDenied('not_found')
        item['account_generation'] = generation
        tx.create(ref, item)
        return item

    claimed = transact(client.transaction())
    if claimed is None:
        raise ProactivityDenied('duplicate')
    return claimed


def publish_item(
    *,
    uid: str,
    item_id: str,
    claim_token: str,
    encrypted_content: str = '',
    state: str = 'ready',
    reason: str = '',
    source_guard: dict[str, Any] | None = None,
    firestore_client: Any = None,
    now: datetime | None = None,
) -> None:
    client = client_or_default(firestore_client)
    ref = item_ref(client, uid, item_id)
    now = now or utc_now()
    if state not in {'ready', 'silent', 'failed', 'suppressed'}:
        raise ValueError('invalid terminal state')

    @firestore.transactional
    def transact(tx: Any):
        item = data_at(ref, tx)
        if not item:
            raise ProactivityDenied('not_found')
        if state == 'ready':
            producer = producer_for(item['producer'])
            generation, _ = admission_records(client, uid, producer, tx, now)
            visible = source_visible(client, uid, item, tx)
            if source_guard is not None:
                # A producer can fence its already-observed canonical revision without writing the source.
                source = data_at(source_ref(client, uid, item['source_kind'], item['source_id']), tx)
                defaults = {'completed': False, 'status': 'active', 'deleted': False, 'is_deleted': False}
                if set(source_guard) - {'completed', 'status', 'due_at', 'deleted', 'is_deleted'}:
                    raise ProactivityDenied('invalid_source_guard')
                if any(source.get(key, defaults.get(key)) != value for key, value in source_guard.items()):
                    raise ProactivityDenied('source_changed')

        else:
            _, generation = read_owner(client, uid, tx)
            visible = True  # Bookkeeping must survive disablement or source deletion.
        if generation != item['account_generation'] or not visible:
            raise ProactivityDenied('not_found')
        if item['state'] != 'claimed' or item['claim_token'] != claim_token:
            raise ProactivityDenied('duplicate')
        if state == 'ready' and now >= item['created_at'] + timedelta(hours=24):
            raise ProactivityDenied('expired')
        if state == 'ready' and (not encrypted_content or item['cost_status'] != 'estimated'):
            raise ProactivityDenied('cost_unsettled')
        item.update(state=state, terminal_reason=reason, content=encrypted_content, updated_at=now)
        if state == 'ready':
            item['feed_available_at'] = now
        tx.set(ref, item)

    transact(client.transaction())


def record_mentor_chat(
    *,
    uid: str,
    item_id: str,
    claim_token: str,
    status: str,
    message_id: str = '',
    firestore_client: Any = None,
    now: datetime | None = None,
) -> None:
    """Confirm the message/item association only after the chat write returns."""
    if status not in {'persisted', 'failed'} or (status == 'persisted' and not message_id):
        raise ValueError('invalid chat result')
    client = client_or_default(firestore_client)
    ref = item_ref(client, uid, item_id)
    now = now or utc_now()

    @firestore.transactional
    def transact(tx: Any):
        _, generation = read_owner(client, uid, tx)
        item = data_at(ref, tx)
        if not item or item['account_generation'] != generation or item['expires_at'] <= now:
            raise ProactivityDenied('not_found')
        if (
            item['producer'] != 'conversation_mentor_v2'
            or item['state'] != 'ready'
            or item['claim_token'] != claim_token
        ):
            raise ProactivityDenied('invalid_chat_item')
        if item.get('mentor_chat_state') == 'persisted':
            if item.get('mentor_chat_message_id') != message_id:
                raise ProactivityDenied('chat_conflict')
            return
        item.update(mentor_chat_state=status, updated_at=now)
        if status == 'persisted':
            item.update(mentor_chat_message_id=message_id, mentor_chat_persisted_at=now)
        tx.set(ref, item)

    transact(client.transaction())


def record_usefulness_score(
    *,
    uid: str,
    item_id: str,
    claim_token: str,
    score: float,
    firestore_client: Any = None,
    now: datetime | None = None,
) -> None:
    """Persist one content-free judge score under the existing claim/deletion fence."""
    if type(score) not in {int, float} or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError('invalid usefulness score')
    client = client_or_default(firestore_client)
    ref = item_ref(client, uid, item_id)
    now = now or utc_now()

    @firestore.transactional
    def transact(tx: Any):
        _, generation = read_owner(client, uid, tx)
        item = data_at(ref, tx)
        if not item or item['account_generation'] != generation or item['expires_at'] <= now:
            raise ProactivityDenied('not_found')
        if item['producer'] != 'conversation_mentor_v2':
            raise ProactivityDenied('invalid_producer')
        if item['state'] != 'claimed' or item['claim_token'] != claim_token:
            raise ProactivityDenied('duplicate')
        if 'usefulness_score' in item:
            if item['usefulness_score'] != score:
                raise ProactivityDenied('score_conflict')
            return
        item.update(usefulness_score=float(score), updated_at=now)
        tx.set(ref, item)

    transact(client.transaction())


def record_outcome(
    *,
    uid: str,
    item_id: str,
    event_id: str,
    action: str,
    surface: str,
    channel: str,
    firestore_client: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if (
        action not in ACTIONS
        or surface not in {'server', 'ios', 'android', 'macos', 'windows'}
        or channel not in {'feed', 'push'}
    ):
        raise ProactivityDenied('invalid_outcome')
    client = client_or_default(firestore_client)
    ref = item_ref(client, uid, item_id)
    now = now or utc_now()

    @firestore.transactional
    def transact(tx: Any):
        _, generation = read_owner(client, uid, tx)
        item = data_at(ref, tx)
        if (
            not item
            or item['state'] != 'ready'
            or item['expires_at'] <= now
            or item['account_generation'] != generation
        ):
            raise ProactivityDenied('not_found')
        visible = source_visible(client, uid, item, tx)
        if not visible:
            raise ProactivityDenied('not_found')
        pref_ref = user_ref(client, uid).collection(PREFERENCES).document(item['producer'])
        pref = data_at(pref_ref, tx)
        events = item['outcomes']
        for kind, event in events.items():
            if event['event_id'] == event_id and kind != action:
                raise ProactivityDenied('event_conflict')
        response = dict(item_id=item_id, recorded=False, acted_24h=item['acted_24h'], negative=item['negative'])
        if action in events:
            return response
        # A thread reply proves exposure only to a durably associated chat message.
        # This fence also protects direct server reducer callers, not only reply mapping.
        if (
            surface == 'server'
            and action == 'replied'
            and not (item.get('mentor_chat_message_id') or item['delivered'])
        ):
            raise ProactivityDenied('chat_unconfirmed')
        # A mentor reply or client action can prove exposure; independent task completion cannot.
        confirms_exposure = action == 'shown' or (
            action in POSITIVE
            and not (surface == 'server' and action == 'accepted' and not item.get('push_accepted_at'))
        )
        if not item['delivered'] and confirms_exposure:
            anchor = now
            if surface == 'server':
                anchor = (
                    item.get('mentor_chat_persisted_at', now)
                    if action == 'replied'
                    else item.get('push_accepted_at', now)
                )
            if anchor > item['created_at'] + timedelta(hours=24) or now > anchor + timedelta(hours=24):
                raise ProactivityDenied('expired')
            item.update(
                delivered=True,
                delivered_count=1,
                delivered_at=anchor,
                delivery_channel=channel,
                delivery_surface=surface,
            )
        events[action] = dict(
            event_id=event_id,
            at=now,
            source='server' if surface == 'server' else 'client',
            surface=surface,
            channel=channel,
        )
        if action in POSITIVE:
            item.setdefault('first_action', action)
            item.setdefault('first_action_at', now)
            if item['delivered'] and item['delivered_at'] <= now <= item['delivered_at'] + timedelta(hours=24):
                item.update(acted_24h=True, acted_count=1)
        if action in {'thumbs_down', 'producer_disabled'}:
            item.update(negative=True, negative_count=1)
            item.setdefault('negative_at', now)
            item.setdefault('negative_kind', action)
        if action == 'dismissed':
            item['dismissed'] = True
        if action == 'producer_disabled':
            pref.update(enabled=False, updated_at=now)
        item['updated_at'] = now
        tx.set(ref, item)
        if action == 'producer_disabled':
            tx.set(pref_ref, pref)
        return dict(item_id=item_id, recorded=True, acted_24h=item['acted_24h'], negative=item['negative'])

    result = transact(client.transaction())
    if result['recorded']:
        logger.info(
            'proactivity_v2_outcome action=%s surface=%s channel=%s acted=%s negative=%s',
            action,
            surface,
            channel,
            result['acted_24h'],
            result['negative'],
        )
        if action == 'shown':
            logger.info('proactivity_v2_feed_exposed surface=%s channel=%s', surface, channel)
    return result


def record_server_outcome(
    item_id: str, action: str, *, uid: str, firestore_client: Any = None, now: datetime | None = None
) -> dict[str, Any]:
    if action not in {'accepted', 'replied'}:
        raise ProactivityDenied('invalid_outcome')
    client = client_or_default(firestore_client)
    item = data_at(item_ref(client, uid, item_id))
    if not item:
        raise ProactivityDenied('not_found')
    expected = 'replied' if item['producer'] == 'conversation_mentor_v2' else 'accepted'
    if action != expected:
        raise ProactivityDenied('invalid_outcome')
    return record_outcome(
        uid=uid,
        item_id=item_id,
        action=action,
        surface='server',
        channel='push' if item.get('push_accepted_at') else 'feed',
        event_id=f'server:{item_id}:{action}',
        firestore_client=client,
        now=now,
    )


def feed_query(client: Any, uid: str, start: datetime, limit: int) -> Any:
    return (
        user_ref(client, uid)
        .collection(ITEMS)
        .where(filter=FieldFilter('state', '==', 'ready'))
        .where(filter=FieldFilter('created_at', '>=', start))
        .order_by('created_at', direction='DESCENDING')
        .order_by('__name__', direction='DESCENDING')
        .limit(limit)
    )


def list_feed(
    *, uid: str, limit: int = 20, cursor: str = '', firestore_client: Any = None, now: datetime | None = None
) -> tuple[list[dict[str, Any]], str, bool]:
    if not 1 <= limit <= 50:
        raise ProactivityDenied('invalid_cursor')
    now = now or utc_now()
    client = client_or_default(firestore_client)
    _, generation = read_owner(client, uid)
    query = feed_query(client, uid, now - timedelta(days=30), limit)
    if cursor:
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if token['v'] != 1 or token['owner'] != hashlib.sha256(uid.encode()).hexdigest():
                raise ValueError('cursor owner')
            stamp = datetime.fromisoformat(token['at'])
            if stamp.tzinfo is None:
                raise ValueError('cursor time')
            query = query.start_after({'created_at': stamp, '__name__': item_ref(client, uid, token['id'])})
        except (ValueError, KeyError, TypeError) as exc:
            raise ProactivityDenied('invalid_cursor') from exc
    docs = list(query.stream())
    result = []
    for doc in docs:
        item = doc.to_dict()
        pref = data_at(user_ref(client, uid).collection(PREFERENCES).document(item['producer']))
        if (
            item['account_generation'] == generation
            and not item['dismissed']
            and pref.get('enabled') is not False
            and (item['delivered'] or now <= item['created_at'] + timedelta(hours=24))
            and source_visible(client, uid, item)
        ):
            result.append(item)
    more = len(docs) == limit
    next_cursor = ''
    if docs and more:
        last = docs[-1].to_dict()
        token = dict(
            v=1, owner=hashlib.sha256(uid.encode()).hexdigest(), at=last['created_at'].isoformat(), id=last['item_id']
        )
        next_cursor = base64.urlsafe_b64encode(json.dumps(token).encode()).decode()
    return result, next_cursor, more


def cohort_query(client: Any, name: str, start: datetime, end: datetime) -> Any:
    return (
        client.collection_group(ITEMS)
        .where(filter=FieldFilter('producer', '==', name))
        .where(filter=FieldFilter('created_at', '>=', start))
        .where(filter=FieldFilter('created_at', '<', end))
        .order_by('created_at')
        .order_by('acted_count')
        .order_by('charged_micro_usd')
        .order_by('delivered_count')
        .order_by('negative_count')
        .order_by('unknown_count')
    )


def metric_verdict(producer: Producer, totals: dict[str, int]) -> str:
    delivered, acted = totals['delivered_count'], totals['acted_count']
    # The engagement verdict is certain even when cost usage is incomplete.
    if delivered >= producer.kill_min_deliveries and acted / delivered < producer.min_acted_24h_rate:
        return 'killed'
    if totals['unknown_count']:
        return 'unknown'
    if delivered < producer.kill_min_deliveries:
        return 'collecting'
    if totals['charged_micro_usd'] > acted * producer.max_micro_usd_per_acted_item:
        return 'killed'
    return 'passing'


def refresh_health(name: str, *, firestore_client: Any = None, now: datetime | None = None) -> dict[str, Any]:
    client = client_or_default(firestore_client)
    now = now or utc_now()
    producer = producer_for(name)
    ref = client.collection(CONTROLS).document(name)
    current = data_at(ref)
    if current.get('state') == 'killed':
        raise ProactivityDenied('producer_disabled')
    if current.get('version') == producer.version and current.get(
        'checked_at', now - timedelta(days=1)
    ) >= now - timedelta(seconds=60):
        return current
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=2)
    start = end - timedelta(days=7)
    fields = ('delivered_count', 'acted_count', 'negative_count', 'charged_micro_usd', 'unknown_count')
    aggregate = cohort_query(client, name, start, end).sum(fields[0], alias=fields[0])
    for field in fields[1:]:
        aggregate = aggregate.sum(field, alias=field)
    totals = {field: 0 for field in fields}
    for row in aggregate.get():
        for value in row:
            totals[value.alias] = int(value.value or 0)
    verdict = metric_verdict(producer, totals)
    if verdict == 'unknown':
        raise ProactivityDenied('health_unavailable')
    control = dict(
        version=producer.version,
        state='killed' if verdict == 'killed' else 'enabled',
        verdict=verdict,
        checked_at=now,
        cohort_start=start,
        cohort_end=end,
        totals=totals,
        negative_alert=totals['negative_count'] > totals['delivered_count'] * 0.05,
    )

    @firestore.transactional
    def transact(tx: Any):
        prior = data_at(ref, tx)
        if prior.get('state') == 'killed':
            raise ProactivityDenied('producer_disabled')
        if prior.get('checked_at', start) > now:
            return prior
        tx.set(ref, control)
        return control

    result = transact(client.transaction())
    if result['state'] == 'killed':
        logger.warning(
            'proactivity_v2_producer_killed producer=%s version=%s verdict=%s', name, producer.version, verdict
        )
        raise ProactivityDenied('producer_disabled')
    return result


def claim_push(*, uid: str, item_id: str, firestore_client: Any = None, now: datetime | None = None) -> dict[str, Any]:
    client = client_or_default(firestore_client)
    now = now or utc_now()
    ref = item_ref(client, uid, item_id)
    day_ref = user_ref(client, uid).collection(DAYS).document(now.strftime('%Y-%m-%d'))
    digest = hashlib.sha256(uid.encode()).hexdigest()
    key = f'proactivity:v2:{{{digest}}}:push:{now.strftime("%Y-%m-%d")}'
    reset = int((now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=3)).timestamp())
    script = "local n=tonumber(redis.call('GET',KEYS[1]) or '0'); if n>=9 then return 0 end; redis.call('INCR',KEYS[1]); redis.call('EXPIREAT',KEYS[1],ARGV[1]); return 1"
    try:
        if not proactivity_redis.get_client().eval(script, 1, key, reset):
            raise ProactivityDenied('push_limit')
    except ProactivityDenied:
        raise
    except Exception as exc:
        raise ProactivityDenied('unavailable') from exc

    @firestore.transactional
    def transact(tx: Any):
        item = data_at(ref, tx)
        if not item:
            raise ProactivityDenied('not_found')
        producer = producer_for(item['producer'])
        generation, _ = admission_records(client, uid, producer, tx, now)
        day = data_at(day_ref, tx)
        visible = source_visible(client, uid, item, tx)
        if (
            not visible
            or generation != item['account_generation']
            or not producer.push_earned
            or item['state'] != 'ready'
            or item['push_state'] != 'eligible'
            or item['delivered']
            or item['dismissed']
            or item['negative']
            or now >= item['created_at'] + timedelta(hours=24)
        ):
            raise ProactivityDenied('push_suppressed')
        if day.get('push_count', 0) >= 9:
            raise ProactivityDenied('push_limit')
        day.update(
            push_count=day.get('push_count', 0) + 1,
            updated_at=now,
            expires_at=now + timedelta(days=90),
            account_generation=generation,
        )
        item.update(push_state='claimed', updated_at=now)
        tx.set(ref, item)
        tx.set(day_ref, day)
        return item

    return transact(client.transaction())


def finish_push(
    *, uid: str, item_id: str, status: str, firestore_client: Any = None, now: datetime | None = None
) -> None:
    if status not in {'accepted', 'failed', 'unknown', 'suppressed'}:
        raise ValueError('invalid push status')
    client = client_or_default(firestore_client)
    now = now or utc_now()
    ref = item_ref(client, uid, item_id)

    @firestore.transactional
    def transact(tx: Any):
        _, generation = read_owner(client, uid, tx)
        item = data_at(ref, tx)
        if not item or item['account_generation'] != generation:
            raise ProactivityDenied('not_found')
        if item['push_state'] != 'claimed':
            return
        item.update(push_state=status, updated_at=now)
        if status == 'accepted':
            item['push_accepted_at'] = now
        tx.set(ref, item)

    transact(client.transaction())


def validate_push(*, uid: str, item_id: str, firestore_client: Any = None, now: datetime | None = None) -> None:
    """Last read fence immediately before external dispatch; never consumes quota twice."""
    client = client_or_default(firestore_client)
    now = now or utc_now()

    @firestore.transactional
    def transact(tx: Any):
        item = data_at(item_ref(client, uid, item_id), tx)
        if not item:
            raise ProactivityDenied('not_found')
        producer = producer_for(item['producer'])
        generation, _ = admission_records(client, uid, producer, tx, now)
        visible = source_visible(client, uid, item, tx)
        if (
            not visible
            or generation != item['account_generation']
            or not producer.push_earned
            or item['state'] != 'ready'
            or item['push_state'] != 'claimed'
            or item['negative']
            or item['delivered']
            or item['dismissed']
            or now >= item['created_at'] + timedelta(hours=24)
        ):
            raise ProactivityDenied('push_suppressed')

    transact(client.transaction())


def purge_source_items(*, uid: str, source_kind: str, source_id: str, firestore_client: Any = None) -> None:
    """Clear derived content after source deletion, keeping content-free cost evidence."""
    client = client_or_default(firestore_client)
    query = user_ref(client, uid).collection(ITEMS).where(filter=FieldFilter('source_id', '==', source_id))
    for snapshot in query.stream():
        ref = snapshot.reference

        @firestore.transactional
        def purge(tx: Any):
            item = data_at(ref, tx)
            if not item or item['source_kind'] != source_kind or source_visible(client, uid, item, tx):
                return
            item.pop('content', None)
            item.update(state='suppressed', terminal_reason='source_deleted', updated_at=utc_now())
            tx.set(ref, item)

        purge(client.transaction())
