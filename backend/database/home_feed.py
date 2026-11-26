"""Side-effect-free compact feed and explicit bounded projection preparation.

Initial coverage walks document IDs, never a guessed created-time window. After
coverage, content-free dirty ownership receipts drive incremental preparation.
A source mutation and coverage invalidation share the existing Commit fence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import json
import hashlib

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.types import Write
from config.episodes import home_hide_below_floor_rows_enabled, home_step_projection_enabled
from config import episode_live_members as live_members
from prometheus_client import Counter, Histogram

from database._client import get_firestore_client, run_transactional
from database import conversations
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.conversation_payload import read_conversation_payload
from utils.conversation_payload import PAYLOAD_FIELD, ConversationProjectionTooLarge, InvalidConversationPayload
from utils.conversations import transcribing_hold
from utils.conversations.fragment_visibility import SETTLING_FIELDS, is_relevance_discarded
from utils.conversations.home_titles import SUMMARY_DEBT_FIELDS, display_title
from database.home_feed_writer import CONTROL, SCHEMA
from database.home_feed_queries import EPISODES, CONVERSATIONS, STANDALONE
from utils.encryption import ENCRYPTION_SECRET, decrypt
from utils.home_feed.projection import stamp, reveal_display, content, seal_display, utc
from utils.home_feed.paging import decode_cursor, encode_cursor, merge_page
from utils.conversations import home_step
from utils.conversations.fragment_visibility import is_completed_below_floor

PREPARE_LIMIT = 50
MAX_MEMBERS = 512
MEMBERS_PER_PREPARE = 40
MAX_PREPARE_READS = 400
MAX_PREPARE_BYTES = 2 * 1024 * 1024
# Never read transcripts, photos, member lists or the episode's full content on GET.
FEED_FIELDS = [
    'home_sort_at',
    'home_display',
    'home_display_version',
    'home_projection_schema',
    'home_visible',
    'home_standalone',
    'home_member_count',
    'home_sources',
    'home_status',
    'home_step',
    'record_projection_revision',
    'user_title',
    'home_starred',
    'home_is_locked',
    'home_has_tasks',
    'home_finished_at',
    'home_started_at',
]
CONVERSATION_FIELDS = [
    'v3_derived',
    'recording',
    'home_hidden',
    'id',
    'started_at',
    'created_at',
    'recorded_start',
    'recorded_end',
    'finished_at',
    'status',
    'structured',
    PAYLOAD_FIELD,
    'data_protection_level',
    'user_title',
    'starred',
    'is_locked',
    'discarded',
    'deleted',
    'sync_merged_into',
    'dream_duplicate_of',
    'episode_id',
    'source',
    'has_content',
    'has_photos',
    'sync_relevance',
    'relevance_decision',
    'sync_relevance_user_kept',
    'sync_processing_hold',
    'bridge_pending',
    'record_projection_revision',
    'record_lane_owner',
    'sync_live_target',
    'record_audio_closed',
    'server_batch_audio_closed',
    'record_phase',
    'finalization_status',
    'summary_retryable',
    'record_upload_failed',
    'summary_delivery',
    'summary_backfill_blocked',
    'home_content_invalidated',
    'home_source_version',
    'home_prepared',
    'home_prepared_source_version',
    'home_legacy_source_updated_at',
    'home_compat_owner',
    'sync_bridge_pending',
    'folder_user_set',
    'episode_transcription_pending_at',
    'episode_transcription_deadline_at',
    'server_batch_audio_start',
    'server_batch_audio_end',
    *SETTLING_FIELDS,
    *SUMMARY_DEBT_FIELDS,
    *transcribing_hold.READ_FIELDS,
]
EPISODE_FIELDS = [
    'id',
    'created_at',
    'started_at',
    'recorded_start',
    'recorded_end',
    'last_activity_at',
    'closed_at',
    'status',
    'conversation_ids',
    'discarded_conversation_ids',
    'duplicate_conversation_ids',
    'recorded_merged_into',
    'emoji',
    'content',
    'composed_at',
    'composed_member_ids',
    'compose_excluded_live_member_ids',
    'composed_membership',
    'summary_needs_regeneration',
    'home_content_member_versions',
    'home_member_prepare_cursor',
    'home_display',
    'home_prepare_state',
    'home_prepared_generation',
    'home_needs_prepare',
    'home_content_epoch',
]
WORK = Counter('omi_home_feed_preparation_documents_total', 'Explicit preparation reads and writes', ['kind'])
FEED_WORK = Counter('omi_home_feed_work_total', 'Compact feed units', ['kind'])
FEED_LATENCY = Histogram('omi_home_feed_seconds', 'Compact feed request latency')
FEED_OUTCOME = Counter('omi_home_feed_requests_total', 'Compact feed request results', ['outcome'])


class PreparationRequired(RuntimeError):
    pass


class AccountUnavailable(RuntimeError):
    pass


class PreparationTooLarge(RuntimeError):
    pass


def _user(client, uid):
    return client.collection('users').document(uid)


def _control(user):
    return user.collection('episode_links').document(CONTROL)


def _eligible_by_metadata(row, *, episode_member=False):
    if (
        not row
        or row.get('recording')
        or row.get('home_hidden')
        or row.get('_home_deleted')
        or is_relevance_discarded(row)
        or row.get('sync_merged_into')
    ):
        return False
    if row.get('v3_derived'):
        # The v3 planner owns Home visibility; failed tiles remain recoverable rows.
        return conversations.is_visible_conversation(row, presentation=True)
    if episode_member:
        # Existing episode Home rows preserve failed transcription recovery.
        visibility = {**row, 'status': 'completed'} if row.get('status') == 'failed' else row
        return conversations.is_visible_conversation(visibility) and not (
            home_hide_below_floor_rows_enabled() and is_completed_below_floor(row)
        )
    return conversations.is_visible_conversation(row, presentation=True)


def _visible(row, *, episode_member=False):
    return _eligible_by_metadata(row, episode_member=episode_member) and (
        bool(row.get('v3_derived'))
        or episode_member
        or home_step.classify(row) not in {home_step.NOISE, home_step.FAILED}
    )


def _retained(episode):
    excluded = set(episode.get('discarded_conversation_ids') or []) | set(
        episode.get('duplicate_conversation_ids') or []
    )
    return [cid for cid in dict.fromkeys(episode.get('conversation_ids') or []) if cid not in excluded]


def _revision(snapshot):
    value = getattr(snapshot, 'update_time', None)
    return value.isoformat() if isinstance(value, datetime) else None


def _member_home_version(row):
    if row.get('home_source_version'):
        return row['home_source_version']
    original = utc(row.get('home_legacy_source_updated_at')) or utc(row.get('_home_snapshot_updated_at'))
    return f'legacy:{original.isoformat()}' if original else None


def _legacy_episode_display(uid, row):
    """Decode saved legacy display only during explicit, member-validated preparation."""
    try:
        saved = json.loads(decrypt(row.get('content'), uid))
    except (ValueError, TypeError, AttributeError):
        return None
    return (
        content({**row, 'title': saved.get('title'), 'lede': saved.get('lede')}, 'episode')
        if isinstance(saved, dict)
        else None
    )


def _conversation_projection(uid, row):
    result = stamp(uid, row, 'conversation')
    if not result:
        # Unknown recorded clocks stay unknown and cannot fabricate a sorted
        # recording. Existing legacy APIs remain available for these records.
        raise PreparationRequired('home_feed_unknown_recorded_time')
    result.update(
        home_prepared=True,
        home_prepared_source_version=row.get('home_source_version'),
        home_visible=_visible(row),
        home_standalone=True,
        home_member_count=1,
        home_sources=[str(row['source'])[:64]] if row.get('source') else [],
        home_status=str(row.get('status') or 'completed'),
        home_step=home_step.classify(row),
        home_starred=bool(row.get('starred')),
        home_is_locked=bool(row.get('is_locked')),
        home_finished_at=(
            None if row.get('status') == 'in_progress' else utc(row.get('recorded_end')) or utc(row.get('finished_at'))
        ),
    )
    if not row.get('home_source_version'):
        result['home_legacy_source_updated_at'] = utc(row.get('home_legacy_source_updated_at')) or utc(
            row.get('_home_snapshot_updated_at')
        )
    if row.get('home_content_invalidated'):
        result['home_display'] = seal_display(
            uid, {'schema': SCHEMA, 'title': '', 'emoji': '', 'preview': '', 'summary_available': False}
        )
    return result


def prepare(uid: str, *, firestore_client: Any = None) -> dict[str, Any]:
    """One bounded transaction; only called by explicit authenticated POST.

    At most 50 requested source/receipt candidates, 40 member snapshots, 400 requested document reads
    and 400 derived writes. Stop at a 2 MiB processed-JSON target, allowing a
    final selected document after a 3 MiB pre-read ceiling. Chunk reads
    reserve their document count and encoded payload size within a 4 MiB
    combined allowance. An 8 MiB protobuf guard bounds the staged Commit.
    Unconsumed work remains in content-free dirty receipts or member cursors.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = _user(client, uid)
    control_ref = _control(user)

    @firestore.transactional
    def body(tx):
        counts = {'reads': 0, 'requested': 0, 'bytes': 0, 'members': 0}
        hard_bytes = MAX_PREPARE_BYTES + 2 * 1024 * 1024

        def charge(doc, kind):
            counts['reads'] += 1
            counts['bytes'] += len(json.dumps(doc.to_dict() or {}, default=str).encode())
            WORK.labels(kind=kind).inc()
            return doc

        def available(reserve=1):
            return counts['requested'] + reserve <= MAX_PREPARE_READS and counts['bytes'] < hard_bytes - 1024 * 1024

        def reserve_chunks(documents, size):
            if counts['requested'] + documents > MAX_PREPARE_READS or counts['bytes'] + size > hard_bytes:
                raise PreparationTooLarge('home_feed_prepare_payload_budget')
            counts['requested'] += documents
            counts['reads'] += documents
            counts['bytes'] += size
            WORK.labels(kind='requested_read_upper_bound').inc(documents)
            WORK.labels(kind='payload_chunk_read').inc(documents)

        def load_notes(doc, row, *, episode_member=False):
            if (
                PAYLOAD_FIELD not in row
                or 'structured' in row
                or row.get('is_locked')
                or row.get('data_protection_level') == 'private'
                or row.get('home_content_invalidated')
                or not _eligible_by_metadata(row, episode_member=episode_member)
            ):
                return True
            try:
                hydrated = read_conversation_payload(
                    client, tx, doc, field_paths=['structured'], reserve_chunks=reserve_chunks
                )
            except PreparationTooLarge:
                return False
            except (InvalidConversationPayload, ConversationProjectionTooLarge) as error:
                raise PreparationRequired('home_feed_payload_unavailable') from error
            if 'structured' in hydrated:
                row['structured'] = hydrated['structured']
            return True

        def get(ref, fields=None, kind='metadata_read'):
            if not available():
                raise PreparationTooLarge('home_feed_prepare_read_budget')
            counts['requested'] += 1
            WORK.labels(kind='requested_read_upper_bound').inc()
            return charge(ref.get(field_paths=fields, transaction=tx), kind)

        def collect(query, kind, requested):
            # Streaming can prefetch the full query limit before early cancel.
            # Reserve that upper bound; consumed snapshots are a separate metric.
            if not available(requested):
                raise PreparationTooLarge('home_feed_prepare_read_budget')
            counts['requested'] += requested
            WORK.labels(kind='requested_read_upper_bound').inc(requested)
            result = []
            for doc in query.stream(transaction=tx):
                result.append(charge(doc, kind))
                if counts['bytes'] >= MAX_PREPARE_BYTES or not available():
                    break
            return result

        deletion = get(client.collection('account_deletions').document(uid), ['wipe_status'])
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('wipe_status')
        ):
            raise AccountUnavailable('home_feed_account_unavailable')
        privacy = get(
            client.collection('batch_pipeline_privacy').document(hashlib.sha256(uid.encode()).hexdigest()),
            ['blocked', 'purging', 'memo_blocked', 'memo_token'],
        )
        if any((privacy.to_dict() or {}).get(field) for field in ('blocked', 'purging', 'memo_blocked')):
            raise AccountUnavailable('home_feed_account_unavailable')
        snapshot = get(control_ref)
        state = snapshot.to_dict() or {}
        phase = state.get('phase', 'conversations')
        ready_members = home_step_projection_enabled()
        policy_changed = state.get('schema') == SCHEMA and state.get('ready_members') != ready_members
        rebuild_all = state.get('rebuild_all', False) or policy_changed
        if state.get('policy_dirty') or policy_changed:
            phase, rebuild_all = 'conversations', True
        cursor = None if state.get('policy_dirty') or policy_changed else state.get('cursor')
        if state.get('schema') != SCHEMA:
            phase, cursor = 'conversations', None
        generation = state.get('generation', '')
        policy_epoch = state.get('policy_epoch', '')
        invalidated_episodes = set()
        pending = []
        scanned_history = phase in ('conversations', 'episodes')
        checked_dirty = False
        if phase in ('conversations', 'episodes'):
            collection = user.collection('conversations') if phase == 'conversations' else user.collection('episodes')
            query = collection.order_by('__name__').limit(PREPARE_LIMIT)
            if cursor:
                query = query.start_after({'__name__': collection.document(cursor)})
            query = query.select(CONVERSATION_FIELDS if phase == 'conversations' else EPISODE_FIELDS)
            pending = [(phase, doc) for doc in collect(query, 'source_read', PREPARE_LIMIT)]
            if not pending:
                phase, cursor = ('episodes', None) if phase == 'conversations' else ('dirty', None)
        if phase == 'dirty' and not scanned_history:
            checked_dirty = True
            receipt_limit = PREPARE_LIMIT // 2
            links = collect(
                user.collection('episode_links')
                .where(filter=FieldFilter('home_dirty', '==', True))
                .select(['episode_id', 'home_dirty'])
                .limit(receipt_limit),
                'receipt_read',
                receipt_limit,
            )
            pending.extend(('dirty_link', doc) for doc in links)
            if counts['bytes'] < MAX_PREPARE_BYTES:
                dirty_episodes = collect(
                    user.collection('episodes')
                    .where(filter=FieldFilter('home_needs_prepare', '==', True))
                    .select(EPISODE_FIELDS)
                    .limit(PREPARE_LIMIT - receipt_limit),
                    'source_read',
                    PREPARE_LIMIT - receipt_limit,
                )
                pending.extend(('episodes', doc) for doc in dirty_episodes)
        rows, source_snapshots, episodes_to_build, receipt_updates = {}, {}, {}, {}
        processed = []
        for kind, doc in pending:
            raw = doc.to_dict() or {}
            if kind == 'dirty_link':
                if not available(4) or counts['bytes'] >= MAX_PREPARE_BYTES:
                    break
                cid = doc.id
                source = get(user.collection('conversations').document(cid), CONVERSATION_FIELDS, 'source_read')
                if source.exists:
                    row: dict[str, Any] = dict(source.to_dict() or {}, id=cid, _home_force_prepare=True)
                    row['_home_snapshot_updated_at'] = getattr(source, 'update_time', None)
                    row['created_at'] = utc(row.get('created_at')) or getattr(source, 'create_time', None)
                    rows[cid] = row
                    source_snapshots[cid] = source
                if raw.get('episode_id'):
                    episodes_to_build[raw['episode_id']] = None
                    invalidated_episodes.add(raw['episode_id'])
                receipt_updates[cid] = False
            elif kind == 'conversations':
                row = dict(raw, id=doc.id)
                row['_home_snapshot_updated_at'] = getattr(doc, 'update_time', None)
                row['created_at'] = utc(row.get('created_at')) or getattr(doc, 'create_time', None)
                rows[doc.id] = row
                source_snapshots[doc.id] = doc
            else:
                episodes_to_build[doc.id] = doc
            processed.append((kind, doc))
        for cid, row in list(rows.items()):
            if (
                not rebuild_all
                and not row.get('_home_force_prepare')
                and row.get('home_prepared')
                and row.get('home_prepared_source_version') == row.get('home_source_version')
            ):
                rows.pop(cid)
                continue
            if not available(2):
                receipt_updates[cid] = True
                rows.pop(cid)
                continue
            if get(user.collection('deleted_conversations').document(cid), []).exists:
                row['_home_deleted'] = True
            link = get(user.collection('episode_links').document(cid), ['episode_id']).to_dict() or {}
            if not load_notes(source_snapshots[cid], row):
                receipt_updates[cid] = True
                rows.pop(cid)
                continue
            eid = link.get('episode_id') or row.get('episode_id')
            if eid:
                episodes_to_build[eid] = episodes_to_build.get(eid)
                if row.get('_home_force_prepare'):
                    invalidated_episodes.add(eid)
        episode_updates, source_updates = {}, {}
        for eid, existing in episodes_to_build.items():
            if not available(4):
                if existing is not None:
                    episode_updates[eid] = (existing.reference, {'home_needs_prepare': True})
                for cid, row in rows.items():
                    if row.get('episode_id') == eid:
                        receipt_updates[cid] = True
                continue
            doc = existing or get(user.collection('episodes').document(eid), EPISODE_FIELDS, 'source_read')
            if not doc.exists:
                continue
            row = dict(doc.to_dict() or {}, id=eid)
            row['created_at'] = utc(row.get('created_at')) or getattr(doc, 'create_time', None)
            ids = _retained(row)
            excluded_live_ids = (
                set(row.get('compose_excluded_live_member_ids') or []) if live_members.enabled() else set()
            )
            membership = hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()
            staged: dict[str, Any] = row.get('home_prepare_state') or {}
            if (
                eid in invalidated_episodes
                or staged.get('epoch') != row.get('home_content_epoch', '')
                or staged.get('policy_epoch') != policy_epoch
                or staged.get('membership') != membership
                or staged.get('ready_members') != ready_members
            ):
                staged = {
                    'epoch': row.get('home_content_epoch', ''),
                    'ready_members': ready_members,
                    'policy_epoch': policy_epoch,
                    'membership': membership,
                    'offset': 0,
                    'visible': 0,
                    'locked': False,
                    'starred': False,
                    'has_tasks': False,
                    'sources': [],
                    'display': None,
                    'certified': True,
                    'legacy_valid': bool(utc(row.get('composed_at')))
                    and (set(row.get('composed_member_ids') or []) | excluded_live_ids) == set(ids)
                    and (row.get('composed_membership') is None or set(row['composed_membership']) == set(ids))
                    and not row.get('summary_needs_regeneration'),
                    'member_versions': {},
                }
            if (
                eid not in invalidated_episodes
                and not row.get('home_needs_prepare')
                and staged.get('offset') == len(ids)
            ):
                continue
            offset = int(staged['offset'])
            oversized = len(ids) > MAX_MEMBERS
            # Until composition, the compact recording cards are the actual
            # readable notes and pending units. No member wire/hydration on GET.
            member_cards = ready_members and (row.get('status') == 'live' or not utc(row.get('composed_at')))
            proof = row.get('home_content_member_versions') or {}
            for cid in ids[offset:]:
                if counts['members'] >= MEMBERS_PER_PREPARE or not available(3) or counts['bytes'] >= MAX_PREPARE_BYTES:
                    break
                tombstoned = get(user.collection('deleted_conversations').document(cid), []).exists
                link = get(user.collection('episode_links').document(cid), ['episode_id']).to_dict() or {}
                member = get(user.collection('conversations').document(cid), CONVERSATION_FIELDS, 'member_read')
                counts['members'] += 1
                raw = dict(member.to_dict() or {}, id=cid) if member.exists else {}
                if member.exists:
                    raw['_home_snapshot_updated_at'] = getattr(member, 'update_time', None)
                    raw['created_at'] = utc(raw.get('created_at')) or getattr(member, 'create_time', None)
                    if tombstoned:
                        raw['_home_deleted'] = True
                    owner = link.get('episode_id') or raw.get('episode_id') or raw.get('home_compat_owner')
                    belongs = owner in {None, eid}
                    if belongs and not load_notes(member, raw, episode_member=True):
                        break
                    visible = belongs and _visible(raw, episode_member=True)
                    projection = _conversation_projection(uid, raw)
                    if belongs:
                        projection['home_standalone'] = oversized or member_cards
                        if owner is None:
                            projection['home_compat_owner'] = eid
                        source_updates[cid] = projection
                    if visible:
                        staged['visible'] += 1
                        staged['locked'] = staged['locked'] or bool(raw.get('is_locked'))
                        staged['starred'] = staged['starred'] or bool(raw.get('starred'))
                        staged['has_tasks'] = staged['has_tasks'] or bool(
                            (raw.get('structured') or {}).get('action_items')
                        )
                        if raw.get('source'):
                            staged['sources'] = sorted(set(staged['sources']) | {str(raw['source'])[:64]})[:16]
                        if staged['display'] is None:
                            staged['display'] = seal_display(uid, content(raw, 'conversation'))
                    excluded_live = cid in excluded_live_ids and live_members.capturing(raw)
                    staged['certified'] = (
                        staged['certified']
                        and belongs
                        and (excluded_live or (bool(proof.get(cid)) and proof.get(cid) == _member_home_version(raw)))
                        and not tombstoned
                    )
                    original = utc(raw.get('home_legacy_source_updated_at')) or utc(raw['_home_snapshot_updated_at'])
                    composed = utc(row.get('composed_at'))
                    staged['legacy_valid'] = (
                        staged.get('legacy_valid', False)
                        and visible
                        and not raw.get('home_source_version')
                        and not raw.get('home_content_invalidated')
                        and original is not None
                        and composed is not None
                        and (excluded_live or original <= composed)
                    )
                    staged.setdefault('member_versions', {})[cid] = _member_home_version(raw)
                else:
                    staged['certified'] = False
                    staged['legacy_valid'] = False
                staged['offset'] += 1
            complete = staged['offset'] == len(ids)
            projection: dict[str, Any] = {'home_prepare_state': staged, 'home_needs_prepare': not complete}
            if complete:
                compact = reveal_display(uid, staged['display']) or {
                    'schema': SCHEMA,
                    'title': '',
                    'emoji': '',
                    'preview': '',
                    'summary_available': False,
                }
                if staged['certified'] and not staged['locked']:
                    compact = reveal_display(uid, row.get('home_display')) or compact
                elif staged.get('legacy_valid') and not staged['locked']:
                    compact = _legacy_episode_display(uid, row) or compact
                    projection['home_content_member_versions'] = staged['member_versions']
                if staged['locked']:
                    compact = {'schema': SCHEMA, 'title': '', 'emoji': '', 'preview': '', 'summary_available': False}
                projection.update(stamp(uid, row, 'episode'))
                projection.update(
                    home_display=seal_display(uid, compact),
                    home_visible=bool(staged['visible'])
                    and not oversized
                    and not member_cards
                    and not bool(row.get('recorded_merged_into')),
                    home_member_count=staged['visible'],
                    home_sources=staged['sources'],
                    home_status='in_progress' if row.get('status') == 'live' else 'completed',
                    home_step=None,
                    home_starred=staged['starred'],
                    home_is_locked=staged['locked'],
                    home_has_tasks=staged['has_tasks'],
                    home_finished_at=(
                        None
                        if row.get('status') == 'live'
                        else utc(row.get('recorded_end')) or utc(row.get('last_activity_at'))
                    ),
                    home_prepared_generation=generation,
                    home_compatibility_reason='membership_budget' if oversized else None,
                )
            episode_updates[eid] = (doc.reference, projection)
        for cid, row in rows.items():
            if cid not in source_updates:
                source_updates[cid] = _conversation_projection(uid, row)
        writes = len(source_updates) + len(episode_updates) + len(receipt_updates) + 1
        if writes > 400:
            raise PreparationTooLarge('home_feed_prepare_write_budget')
        for cid, projection in source_updates.items():
            tx.update(user.collection('conversations').document(cid), projection)
        for ref, projection in episode_updates.values():
            tx.update(ref, projection)
        for cid, dirty in receipt_updates.items():
            tx.set(user.collection('episode_links').document(cid), {'home_dirty': dirty}, merge=True)
        if phase in ('conversations', 'episodes') and processed:
            cursor = processed[-1][1].id
        ready = checked_dirty and not pending
        tx.set(
            control_ref,
            {
                'schema': SCHEMA,
                'phase': phase,
                'cursor': cursor,
                'ready': ready,
                'ready_members': ready_members,
                'policy_dirty': False,
                'rebuild_all': rebuild_all and not ready,
            },
            merge=True,
        )
        commit_bytes = sum(len(Write.serialize(write)) for write in getattr(tx, '_write_pbs', ()))
        if commit_bytes > 8 * 1024 * 1024:
            raise PreparationTooLarge('home_feed_prepare_commit_budget')
        WORK.labels(kind='commit_bytes').inc(commit_bytes)
        WORK.labels(kind='projection_write').inc(writes)
        WORK.labels(kind='processed_bytes').inc(counts['bytes'])
        return {'ready': ready, 'processed': len(processed), 'has_more': not ready}

    return run_transactional(client, body)


@FEED_LATENCY.time()
def feed(
    uid: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
    episodes_admitted: bool = True,
    firestore_client: Any = None,
):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = _user(client, uid)
    deletion = client.collection('account_deletions').document(uid).get()
    if account_deletion_marker_blocks_access(
        marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('wipe_status')
    ):
        raise AccountUnavailable('home_feed_account_unavailable')
    authority_ref = client.collection('batch_pipeline_privacy').document(hashlib.sha256(uid.encode()).hexdigest())
    authority = authority_ref.get()
    authority_data = authority.to_dict() or {}
    if any(authority_data.get(field) for field in ('blocked', 'purging', 'memo_blocked')):
        raise AccountUnavailable('home_feed_account_unavailable')
    authority_version = _revision(authority)
    state_doc = _control(user).get()
    control = state_doc.to_dict() or {}
    if (
        control.get('schema') != SCHEMA
        or control.get('ready') is not True
        or control.get('ready_members') != home_step_projection_enabled()
    ):
        raise PreparationRequired('home_feed_preparation_required')
    generation = control.get('generation', '')
    policy = f'home:{SCHEMA}:{int(episodes_admitted)}'
    state = decode_cursor(uid, cursor, policy, ENCRYPTION_SECRET)
    if not episodes_admitted:
        state['episode']['done'] = True

    def fetch(kind, after, size):
        collection = user.collection('episodes') if kind == 'episode' else user.collection('conversations')
        spec = EPISODES if kind == 'episode' else STANDALONE if episodes_admitted else CONVERSATIONS
        query = spec.build(collection, {'visible': True, 'standalone': True}, field_filter_factory=FieldFilter)
        query = query.order_by('home_sort_at', direction=firestore.Query.DESCENDING).order_by(
            '__name__', direction=firestore.Query.DESCENDING
        )
        if after:
            query = query.start_after(
                {'home_sort_at': datetime.fromisoformat(after[0]), '__name__': collection.document(after[1])}
            )
        rows = [dict(doc.to_dict() or {}, id=doc.id) for doc in query.select(FEED_FIELDS).limit(size).stream()]
        FEED_WORK.labels(kind='source_documents').inc(len(rows))
        return rows

    def project(kind, row):
        display = reveal_display(uid, row.get('home_display'))
        if display is None or row.get('home_projection_schema') != SCHEMA:
            raise PreparationRequired('home_feed_preparation_required')
        locked = bool(row.get('home_is_locked'))
        title = display.get('title', '')
        if kind == 'conversation' and not conversations.effective_user_title(row.get('user_title')):
            ready_receipt = bool(
                home_step_projection_enabled()
                and row.get('home_step') == home_step.READY
                and row.get('record_projection_revision')
            )
            pending = display.get('notes_pending')
            # Old encrypted cards did not record whether notes live outside the
            # preview. Keep their headline on ready receipt-bearing rows until
            # a normal source write or prepare refreshes the display metadata.
            if pending is True or (pending is not False and not ready_receipt):
                title = display_title(title, display.get('preview', ''), label_recording=ready_receipt)
        return {
            'id': f'{kind}:{row["id"]}',
            'kind': kind,
            'detail_id': row['id'],
            'sort_at': row['home_sort_at'],
            'started_at': row.get('home_started_at'),
            'finished_at': row.get('home_finished_at'),
            'title': '' if locked else title,
            'emoji': '' if locked else display.get('emoji', ''),
            'preview': '' if locked else display.get('preview', ''),
            'status': row.get('home_status') or 'completed',
            'home_step': row.get('home_step'),
            'starred': bool(row.get('home_starred')),
            'is_locked': locked,
            'has_tasks': bool(row.get('home_has_tasks')),
            'member_count': row.get('home_member_count', 1),
            'sources': row.get('home_sources') or [],
            'summary_available': bool(display.get('summary_available')) and not locked,
            'revision': row['home_display_version'],
        }

    items, more, truncated = merge_page(state, fetch, project, limit=limit)
    # Do not publish snapshots crossing an acknowledged privacy/ownership write.
    final_authority = authority_ref.get()
    if any((final_authority.to_dict() or {}).get(field) for field in ('blocked', 'purging', 'memo_blocked')):
        raise AccountUnavailable('home_feed_account_unavailable')
    if _revision(final_authority) != authority_version:
        raise PreparationRequired('home_feed_preparation_required')
    final_deletion = client.collection('account_deletions').document(uid).get()
    if account_deletion_marker_blocks_access(
        marker_exists=final_deletion.exists, raw_status=(final_deletion.to_dict() or {}).get('wipe_status')
    ):
        raise AccountUnavailable('home_feed_account_unavailable')
    fresh = _control(user).get().to_dict() or {}
    if fresh.get('ready') is not True or fresh.get('generation', '') != generation:
        raise PreparationRequired('home_feed_preparation_required')
    FEED_WORK.labels(kind='cards').inc(len(items))
    FEED_WORK.labels(kind='payload_bytes').inc(len(json.dumps(items, default=str).encode()))
    FEED_OUTCOME.labels(outcome='ok').inc()
    return {
        'generation': generation,
        'items': items,
        'next_cursor': encode_cursor(uid, state, policy, ENCRYPTION_SECRET) if more else None,
        'has_more': more,
        'truncated': truncated,
    }
