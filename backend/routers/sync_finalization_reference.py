"""Private policy adapters for a claimed ordinary sync finalization.

Workerd retains the finalization job and its lease. The receiver accepts only
the configured worker identity and checks the durable owner before doing work.
An ambiguous side effect remains reserved for drain reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
import os
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from google.api_core.exceptions import FailedPrecondition, NotFound
from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from database import episode_write_fence
from database._client import get_firestore_client
from database.account_deletion_policy import account_deletion_marker_blocks_access
from utils.cloud_tasks import verify_configured_cloud_tasks_oidc
from utils.conversations.minimum_derived import intentional_short_clip_minimum
from utils.conversations.reprocess_contract import DERIVED_EFFECTS_TRANSCRIPT_FIELD, derived_effects_transcript_digest
from utils.llm.known_spellings import spelling_context_run

router = APIRouter()
Identifier = Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{1,256}$')]
Positive = Annotated[int, Field(strict=True, gt=0)]
RECEIPTS = 'go_sync_reference_operations'
APP_OUTPUT_FIELDS = ('apps_results', 'suggested_summarization_apps')


def _notes_source_projection(conversation) -> dict:
    from utils.conversations.recorded_time import write_span
    from utils.summary_quality import content_units

    payload = conversation.model_dump()
    payload['status'] = 'completed'
    span = write_span(payload, arrival_at=datetime.now(timezone.utc))
    return {
        **{key: value.isoformat() if isinstance(value, datetime) else value for key, value in span.items()},
        'content_word_units': content_units(conversation.transcript_segments),
    }


def _empty_discard_home(uid, row, source):
    from utils.home_feed.projection import stamp

    structured = {**(row.get('structured') or {})}
    structured['title'] = structured.get('title', '') if row.get('title_locked') else ''
    structured['overview'] = row.get('user_overview') or ''
    structured['sections'] = []
    structured.setdefault('emoji', '💬')
    final = {**row, 'structured': structured}
    start = source['recorded_start']
    final['recorded_start'] = datetime.fromisoformat(start) if start else None
    fields = stamp(uid, final, 'conversation')
    return {key: value.isoformat() if isinstance(value, datetime) else value for key, value in fields.items()}


def _notes_title_evidence(stored: dict, conversation) -> dict | None:
    from database.conversations import effective_user_title
    from utils.conversations.home_titles import title_for_stability
    from utils.summary_quality import valid_title

    if effective_user_title(stored.get('user_title')) or stored.get('title_locked'):
        return None
    raw_title = title_for_stability({**stored, 'transcript_segments': conversation.transcript_segments})
    previous_units = stored.get('title_content_units')
    if not isinstance(previous_units, (int, float)) or isinstance(previous_units, bool) or not isfinite(previous_units):
        previous_units = 0
    return {'prior': raw_title, 'valid_prior': valid_title(raw_title), 'previous_units': previous_units}


class ReferenceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    owner: Identifier
    conversation: Identifier
    job: Identifier
    revision: Positive
    sync_revision: Positive
    queue_epoch: Positive
    step: Literal[
        'meeting',
        'notes',
        'effects',
        'effects-episode',
        'deferred-effects',
        'targets',
        'episode-start',
        'episode-reconcile',
        'relevance-nano',
        'relevance-jev',
        'notes-actions',
    ]
    operation: Annotated[str, StringConstraints(pattern=r'^op_[0-9a-f]{40}$')]
    action_items: Annotated[list, Field(max_length=64)] | None = None

    def expected_operation(self) -> str:
        material = f'{self.job}\0sync-reference:{self.step}:{self.sync_revision}'
        return 'op_' + sha256(material.encode()).hexdigest()[:40]


def _authorize(request: Request) -> int:
    return verify_configured_cloud_tasks_oidc(
        request,
        audience=os.getenv('WORKER_SYNC_FINALIZATION_REFERENCE_AUDIENCE', ''),
        invoker_sa=os.getenv('WORKER_SYNC_FINALIZATION_REFERENCE_CALLER', ''),
    )


def _owns(row: dict, job: dict, req: ReferenceRequest) -> bool:
    epoch = row.get('finalization_owner_epoch')
    mirror_epoch = job.get('go_lease_epoch')
    return (
        row.get('finalization_engine') == job.get('finalization_engine') == 'go'
        and type(epoch) is int
        and epoch > 0
        and job.get('finalization_owner_epoch') == epoch
        and row.get('finalization_job_id') == req.job
        and row.get('finalization_revision') == job.get('finalization_revision') == req.revision
        and job.get('processing_trigger') == 'sync_update'
        and job.get('uid') == req.owner
        and job.get('conversation_id') == req.conversation
        and job.get('status') == 'leased'
        and job.get('go_queue_epoch') == req.queue_epoch
        and type(mirror_epoch) is int
        and mirror_epoch > 0
        and mirror_epoch == job.get('lease_epoch')
        and not job.get('requires_byok')
    )


def _eligible(row: dict) -> bool:
    if row.get('record_lane_owner') in {'batch_live_v1', 'batch_sync_v1'}:
        return False
    if row.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}:
        return False
    return not any(
        row.get(key)
        for key in (
            'deleted',
            'is_deleted',
            'is_locked',
            'recording',
            'v3_derived',
            'deferred',
            'sync_merged_into',
            'sync_bridge_pending',
            'capture_group',
        )
    )


def _current_fanout(row: dict, job: dict, req: ReferenceRequest) -> bool:
    if row.get('status') != 'completed':
        return False
    if _is_empty_discard(row, req) and row.get('go_empty_discard_fanout_epoch') == req.queue_epoch:
        return True
    inline_epoch = row.get('go_sync_inline_fanout_epoch')
    inline_revision = row.get('go_sync_inline_fanout_revision')
    if (
        type(inline_epoch) is int
        and inline_epoch == req.queue_epoch
        and type(inline_revision) is int
        and inline_revision == req.sync_revision
    ):
        return True
    return (
        job.get('fanout_status') == 'leased'
        and job.get('fanout_lease_epoch') == job.get('lease_epoch')
        and job.get('go_fanout_sync_revision') == req.sync_revision
    )


def _is_empty_discard(row: dict, req: ReferenceRequest) -> bool:
    decision = row.get('relevance_decision')
    return (
        req.step == 'episode-reconcile'
        and row.get('discarded') is True
        and row.get('go_sync_minimum_discarded') is True
        and row.get('go_sync_minimum_revision') == req.sync_revision
        and isinstance(decision, dict)
        and decision.get('reason') == 'empty_transcript'
        and decision.get('verdict') == 'discard'
    )


def _stage_empty_discard_episode(client, txn, row_ref, row, req):
    from config.episodes import episodes_enabled_for
    from database import episodes
    from utils.episodes import client_gate, composer
    from utils.home_feed.projection import stamp

    episode = None
    if episodes_enabled_for(req.owner) and client_gate.client_seen(req.owner):
        episode = episodes.stage_discarded_member(
            txn, client, req.owner, req.conversation, after_discard=composer.empty_discard_deferral
        )
    # Older workers did not stage the projection with the discard.
    if row.get('go_sync_empty_discard_home_revision') != req.sync_revision:
        fields = stamp(req.owner, row, 'conversation')
        if fields:
            txn.update(row_ref, fields | {'go_sync_empty_discard_home_revision': req.sync_revision})
    # The contribution itself is the durable receipt. No reservation is needed
    # for a single transaction, and a replay cannot remove it twice.
    return 'empty_discard_settled', episode


def _operation_keys(req: ReferenceRequest) -> tuple[str, ...]:
    if req.step != 'effects-episode':
        return (req.operation,)
    return tuple(
        req.model_copy(update={'step': step}).expected_operation() for step in ('effects', 'episode-reconcile')
    )


def _deletion_blocks(client, txn, req):
    marker = client.collection('account_deletions').document(req.owner).get(transaction=txn)
    user = client.collection('users').document(req.owner)
    tombstone = user.collection('deleted_conversations').document(req.conversation).get(transaction=txn)
    return tombstone.exists or account_deletion_marker_blocks_access(
        marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
    )


@dataclass
class _JobVersion:
    row: dict = field(default_factory=dict)
    updated_at: datetime | None = None


def _read_or_reserve(
    client,
    req: ReferenceRequest,
    *,
    reserve: bool,
    job_version: _JobVersion | None = None,
):
    user = client.collection('users').document(req.owner)
    job_ref = client.collection('conversation_finalization_jobs').document(req.job)
    row_ref = user.collection('conversations').document(req.conversation)

    @firestore.transactional
    def claim(txn, prior=None):
        row = row_ref.get(transaction=txn).to_dict() or {}
        if prior is None:
            snapshot = job_ref.get(transaction=txn)
            job = snapshot.to_dict() or {}
            observed = _JobVersion(job, snapshot.update_time)
        else:
            job = prior.row
            observed = prior
        if not _owns(row, job, req):
            return 'ownership_changed', None
        if row.get('sync_content_revision') != req.sync_revision:
            return 'source_changed', None
        if (req.step in {'notes', 'notes-actions'} or req.step.startswith('relevance-')) and (
            row.get('status') not in {'processing', 'completed'} or row.get('discarded')
        ):
            return 'ownership_changed', None
        if not _eligible(row):
            return 'unsupported_row', None
        if req.step in {'effects', 'effects-episode', 'targets', 'episode-reconcile'} and not _current_fanout(
            row, job, req
        ):
            return 'ownership_changed', None
        if req.step in {'effects', 'effects-episode', 'targets'} and (
            row.get('discarded')
            or row.get('terminal_no_derived_effects')
            or (
                req.step in {'effects', 'effects-episode'}
                and row.get('go_sync_minimum_revision') == req.sync_revision
                and (not intentional_short_clip_minimum(row) or row.get('go_sync_minimum_discarded') is not False)
            )
        ):
            return 'unsupported_row', None
        if not reserve:
            # Notes can return transcript content. The live episode gate can
            # close an idle episode, including for older workers that ask
            # for it separately. Metadata and action normalization only read.
            if req.step in {'notes', 'episode-start'} and _deletion_blocks(client, txn, req):
                return 'ownership_changed', None
            return 'owned', row, observed
        journal = job.get(RECEIPTS) or {}
        keys = _operation_keys(req)
        settled = sum(journal.get(key) == 'settled' for key in keys)
        if settled == len(keys):
            if req.step.startswith('relevance-'):
                results = job.get('go_sync_reference_relevance') or {}
                if req.operation not in results:
                    return 'operation_unsettled', None
                return 'relevance_replayed', results[req.operation]
            return 'settled', None
        if any(value != 'settled' for value in journal.values()):
            return 'operation_unsettled', None
        if req.step == 'effects-episode' and settled:
            return 'use_separate_steps', None
        if len(journal) + len(keys) > 16:
            return 'operation_unsettled', None
        if _deletion_blocks(client, txn, req):
            return 'ownership_changed', None
        if _is_empty_discard(row, req):
            return _stage_empty_discard_episode(client, txn, row_ref, row, req)
        option = client.write_option(last_update_time=prior.updated_at) if prior is not None else None
        txn.update(job_ref, {f'{RECEIPTS}.{key}': 'reserved' for key in keys}, option=option)
        return 'owned', row, observed

    if req.step == 'episode-reconcile':
        from database.transcript_pointer import run_preloaded_transactional

        return run_preloaded_transactional(client, claim)[:2]

    prior = job_version if reserve and job_version and job_version.updated_at else None
    txn = client.transaction()
    result = None
    if prior is not None:
        try:
            result = claim(txn, prior)
        except (FailedPrecondition, NotFound):
            result = None
        if result is None or result[0] != 'owned':
            # A cached journal cannot authorize a read-only replay or a
            # refusal. Re-read both documents unless the CAS committed.
            txn = client.transaction()
            result = None
    if result is None:
        result = claim(txn)
    if result[0] == 'owned':
        observed = result[2]
        if reserve and job_version is not None:
            journal = observed.row.get(RECEIPTS) or {}
            reserved = {key: 'reserved' for key in _operation_keys(req)}
            job_version.row = {**observed.row, RECEIPTS: journal | reserved}
            job_version.updated_at = txn.write_results[0].update_time
        elif not reserve:
            if job_version is not None:
                job_version.row, job_version.updated_at = observed.row, observed.updated_at
    return result[:2]


def _current_output_row(client, txn, req: ReferenceRequest, job: dict, *, row=None):
    user = client.collection('users').document(req.owner)
    ref = user.collection('conversations').document(req.conversation)
    if row is None:
        row = ref.get(transaction=txn).to_dict() or {}
    if (
        not _owns(row, job, req)
        or not _eligible(row)
        or row.get('sync_content_revision') != req.sync_revision
        or not _current_fanout(row, job, req)
        or _deletion_blocks(client, txn, req)
    ):
        return ref, None
    return ref, row


def _effect_fields(row: dict, before: dict, patch: dict) -> dict:
    if (
        row.get('discarded')
        or row.get('terminal_no_derived_effects')
        or row.get('data_protection_level') != before.get('data_protection_level')
        or row.get('transcript_segments') != before.get('transcript_segments')
        or row.get('transcript_segments_compressed') != before.get('transcript_segments_compressed')
    ):
        return {}
    # An app edit wins independently of the transcript effects checkpoint.
    fields = (
        {key: patch[key] for key in APP_OUTPUT_FIELDS if key in patch}
        if all(row.get(key) == before.get(key) for key in APP_OUTPUT_FIELDS)
        else {}
    )
    digest = DERIVED_EFFECTS_TRANSCRIPT_FIELD
    # Corrections can change the effective transcript without changing its stored blob.
    same_input = all(
        row.get(key) == before.get(key) for key in ('has_transcript_corrections', 'transcript_correction_overlay')
    )
    if before.get('go_sync_minimum_revision') is not None:
        same_input = same_input and all(
            row.get(key) == before.get(key)
            for key in ('go_sync_minimum_revision', 'go_sync_minimum_discarded', 'structured', 'relevance_decision')
        )
    if digest in patch and row.get(digest) == before.get(digest) and same_input:
        fields[digest] = patch[digest]
    return fields


def _settle(
    client,
    req: ReferenceRequest,
    *,
    effects_write: tuple[dict, dict] | None = None,
    relevance_result=None,
    job_version: _JobVersion | None = None,
    episode: _EpisodeFence | None = None,
) -> bool:
    job_ref = client.collection('conversation_finalization_jobs').document(req.job)

    @firestore.transactional
    def commit(txn, prior=None):
        job = prior.row if prior is not None else job_ref.get(transaction=txn).to_dict() or {}
        keys = _operation_keys(req)
        journal = job.get(RECEIPTS) or {}
        if job.get('finalization_engine') != 'go' or any(journal.get(key) != 'reserved' for key in keys):
            return False
        projects_home = req.step in {'effects-episode', 'episode-reconcile'}
        row = None
        compose = None
        if projects_home or effects_write is not None:
            ref, row = _current_output_row(client, txn, req, job)
            if row is None and episode is not None and not episode.checked and req.step == 'effects-episode':
                # Effects ran, but no episode writer was authorized. Resolve
                # only effects and preserve the ability to retry the episode.
                effects, episode_key = keys
                fields = {f'{RECEIPTS}.{effects}': 'settled', f'{RECEIPTS}.{episode_key}': firestore.DELETE_FIELD}
                option = client.write_option(last_update_time=prior.updated_at) if prior is not None else None
                txn.update(job_ref, fields, option=option)
                return 'episode_refused'
            memo = None
            if row is not None and episode is not None and episode.memo_row is not None:
                from database import episode_attach_memo

                memo = episode_attach_memo.completion_write(
                    txn, client, req.owner, req.conversation, episode.memo_row, None, finalized=True, current=row
                )
            fields = {}
            if row is not None and effects_write is not None:
                fields = _effect_fields(row, *effects_write)
            if row is not None and projects_home:
                from utils.home_feed.projection import stamp

                fields.update(stamp(req.owner, row | fields, 'conversation'))
            if row is not None and episode is not None and episode.compose_deferral is not None:
                from database import episodes

                episode_id, deferral = episode.compose_deferral
                compose = episodes.stage_uncomposed_deferral(txn, client, req.owner, episode_id, deferral)
            if fields:
                txn.update(ref, fields)
            if memo is not None:
                memo_ref, memo_fields, _ = memo
                txn.update(memo_ref, memo_fields)
        # Record the original operation even if a sync append advanced its input.
        # Handback may only proceed after a reservation's outcome is resolved.
        job_fields: dict[str, Any] = {f'{RECEIPTS}.{key}': 'settled' for key in keys}
        if req.step.startswith('relevance-'):
            job_fields[f'go_sync_reference_relevance.{req.operation}'] = relevance_result
        option = client.write_option(last_update_time=prior.updated_at) if prior is not None else None
        txn.update(job_ref, job_fields, option=option)
        if not projects_home or row is not None:
            return 'compose_needed' if projects_home and compose is False else 'current'
        return 'superseded'

    def run(prior=None):
        if episode is not None and episode.memo_row is not None:
            from database.transcript_pointer import run_preloaded_transactional

            return run_preloaded_transactional(client, commit, prior, transient=True)
        return commit(client.transaction(), prior)

    result = None
    if job_version is not None and job_version.updated_at is not None:
        try:
            result = run(job_version)
        except (FailedPrecondition, NotFound):
            pass
    if result is None:
        result = run()
    if episode is not None:
        if result in {'current', 'compose_needed'}:
            from utils.episodes import composer
            from utils.episodes.service import Collaborators

            collaborators = Collaborators(firestore_client=client, finalizing_conversation_id=req.conversation)
            for schedule, args, kwargs in episode.schedules:
                kwargs['collaborators'] = collaborators
                schedule(*args, **kwargs)
            if result == 'compose_needed' and (deferral := episode.compose_deferral) is not None:
                composer.schedule(req.owner, deferral[0], collaborators=collaborators, trigger='member_final')
        elif result == 'episode_refused':
            episode.refused = True
    return result in {'current', 'compose_needed', 'superseded'}


class _EpisodeFence:
    def __init__(self, client, req, source):
        self.client = client
        self.req = req
        self.source_id = req.conversation
        self.source = source
        self.checked = False
        self.refused = False
        self.memo_row = None
        self.compose_deferral = None
        self.schedules = []

    def __call__(self, txn, client, uid, source_id, source_row):
        req = self.req
        if uid == req.owner and not self.refused:
            job = client.collection('conversation_finalization_jobs').document(req.job).get(transaction=txn)
            data = job.to_dict() or {}
            receipts = data.get(RECEIPTS) or {}
            if all(receipts.get(key) == 'reserved' for key in _operation_keys(req)):
                _, row = _current_output_row(
                    client, txn, req, data, row=source_row if source_id == req.conversation else None
                )
                # The orchestration planned against a pre-effects snapshot.
                # Refuse changed inputs, while permitting its own membership
                # writes and unrelated projection updates during recovery.
                source_fields = (
                    'transcript_segments',
                    'transcript_segments_compressed',
                    'transcript_correction_overlay',
                    'has_transcript_corrections',
                    'data_protection_level',
                    'started_at',
                    'finished_at',
                    'recorded_start',
                    'recorded_end',
                    'source',
                    'structured',
                    'sync_merged_from',
                )
                if row is not None and all(row.get(key) == self.source.get(key) for key in source_fields):
                    self.checked = True
                    return
        self.refused = True
        raise episode_write_fence.EpisodeWriteRefused

    def stage_compose_deferral(self, uid, episode_id, fields):
        if self.refused or uid != self.req.owner:
            return False
        if self.compose_deferral is None:
            self.compose_deferral = (episode_id, fields)
        return self.compose_deferral[0] == episode_id

    def before_paid(self):
        @firestore.transactional
        def verify(txn):
            self(txn, self.client, self.req.owner, None, None)

        verify(self.client.transaction())

    def finalize_memo(self, row):
        self.memo_row = row


def _clear_unstarted_episode(client, req, job_version):
    job_ref = client.collection('conversation_finalization_jobs').document(req.job)
    effects, episode = _operation_keys(req)
    fields = {f'{RECEIPTS}.{effects}': 'settled', f'{RECEIPTS}.{episode}': firestore.DELETE_FIELD}
    if job_version is not None and job_version.updated_at is not None:
        try:
            job_ref.update(fields, option=client.write_option(last_update_time=job_version.updated_at))
            return
        except (FailedPrecondition, NotFound):
            pass

    @firestore.transactional
    def clear(txn):
        job = job_ref.get(transaction=txn).to_dict() or {}
        journal = job.get(RECEIPTS) or {}
        if job.get('finalization_engine') == 'go' and all(journal.get(key) == 'reserved' for key in (effects, episode)):
            txn.update(job_ref, fields)

    clear(client.transaction())


class _RelevanceOperation:
    """Reserve and replay only the paid arm actually selected by the shared policy."""

    def __init__(self, client, req, job_version=None):
        self.client = client
        self.req = req
        self.job_version = job_version
        self.refusal = None

    def __call__(self, arm, call):
        req = self.req.model_copy(update={'step': f'relevance-{arm}'})
        req.operation = req.expected_operation()
        job = self.job_version.row if self.job_version is not None else {}
        journal = job.get(RECEIPTS) or {}
        results = job.get('go_sync_reference_relevance') or {}
        if journal.get(req.operation) == 'settled' and req.operation in results:
            return results[req.operation]
        status, value = _read_or_reserve(self.client, req, reserve=True, job_version=self.job_version)
        if status == 'relevance_replayed':
            return value
        if status != 'owned':
            self.refusal = status
            return None
        result = call()
        if not _settle(self.client, req, relevance_result=result, job_version=self.job_version):
            self.refusal = 'operation_unsettled'
            return None
        if self.job_version is not None:
            # A later arm gets a fresh version after this receipt is settled.
            journal = self.job_version.row.get(RECEIPTS) or {}
            results = self.job_version.row.get('go_sync_reference_relevance') or {}
            self.job_version.row[RECEIPTS] = journal | {req.operation: 'settled'}
            self.job_version.row['go_sync_reference_relevance'] = results | {req.operation: result}
            self.job_version.updated_at = None
        return result


def _notes_actions(req, row) -> dict:
    from zoneinfo import ZoneInfo

    from database import notifications
    from models.structured import Structured
    from models.structured_extraction import ExtractedActionItem
    from utils.llm.action_item_normalization import normalize_action_item_due_dates
    from utils.llm.meeting_notes_validation import validate_structured_source_segment_ids

    actions = []
    for value in req.action_items or ():
        try:
            actions.append(ExtractedActionItem.model_validate(value).to_action_item())
        except ValidationError:
            continue
    if not actions:
        return {'action_items': []}
    now = datetime.now(timezone.utc)
    try:
        timezone_name = notifications.get_user_time_zone(req.owner)
        zone = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    except (KeyError, ValueError):
        zone = timezone.utc
    for item in actions:
        item.created_at = now
    normalize_action_item_due_dates(actions, user_tz=zone, now=now, log_past_due_clears=True)
    structured = Structured(action_items=actions)
    validate_structured_source_segment_ids(
        structured, [segment.get('id') for segment in row.get('transcript_segments') or () if isinstance(segment, dict)]
    )
    return {'action_items': [item.model_dump(mode='json') for item in structured.action_items]}


@spelling_context_run
def _adapt(client, req: ReferenceRequest):
    from database.conversation_effect_fence import GoConversationEffectSource
    from database.conversations import encode_conversation_for_write, prepare_conversation_for_read
    from utils.conversations import terminal_settled
    from utils.conversations.factory import deserialize_conversation
    from utils.conversations.processing_trigger import ProcessingTrigger
    from utils.episodes import member_notes

    if req.operation != req.expected_operation():
        return JSONResponse(status_code=400, content={'error': 'invalid_operation'})
    if req.step.startswith('relevance-'):
        # Only the in-process notes planner may enter the metered arm.
        return JSONResponse(status_code=400, content={'error': 'invalid_operation'})
    if req.step == 'deferred-effects':
        # A Python lazy worker cannot execute a Go-owned obligation. Until a
        # Go lazy worker owns that protocol, this mode cannot join the cohort.
        return JSONResponse(status_code=409, content={'error': 'unsupported_row'})
    mutating = req.step in {'effects', 'effects-episode', 'episode-reconcile'}
    job_version = _JobVersion() if req.step in {'notes', 'effects-episode'} else None
    status, row = _read_or_reserve(client, req, reserve=mutating, job_version=job_version)
    if status == 'settled':
        return {'combined': True} if req.step == 'effects-episode' else {}
    if status == 'use_separate_steps':
        return {'combined': False}
    if status == 'empty_discard_settled':
        if row is not None:
            from utils.episodes import composer, service

            composer.schedule_for_conversation(
                req.owner,
                req.conversation,
                collaborators=service.Collaborators(
                    firestore_client=client, finalizing_conversation_id=req.conversation
                ),
                episode=row,
            )
        return {}
    if row is None:
        return JSONResponse(status_code=409, content={'error': status})
    if req.step == 'meeting':
        # The Python evidence wait is only applicable to capture-end and
        # client-finalize. The durable trigger here is exclusively sync_update.
        return {}
    if req.step == 'targets':
        # Older workers can still ask. Ordinary sync emits a creation webhook
        # only on discarded -> visible, a transition this worker cannot claim.
        return {'targets': []}
    stored = row
    row = prepare_conversation_for_read(stored, req.owner, firestore_client=client)
    if row is None:
        return JSONResponse(
            status_code=409, content={'error': 'operation_unsettled' if mutating else 'unsupported_row'}
        )
    if req.step == 'notes-actions':
        return _notes_actions(req, row)
    if req.step == 'notes':
        from config.open_loops import open_loops_enabled
        from utils.conversations.fragment_visibility import is_user_curated
        from utils.conversations.sync_notes_request import notes_request

        conversation = deserialize_conversation({**row, 'id': req.conversation})
        # Match the serving processor's before_notes gate. An empty segment
        # list cannot give a live episode ownership of member notes.
        if conversation.transcript_segments and member_notes.waits(req.owner, row, ProcessingTrigger.SYNC_UPDATE):
            return JSONResponse(status_code=409, content={'error': 'live_episode_notes'})
        relevance = _RelevanceOperation(client, req, job_version=job_version)
        plan = notes_request(
            client, req.owner, conversation, user_kept=is_user_curated(row), run_relevance_model=relevance
        )
        if relevance.refusal:
            return JSONResponse(status_code=409, content={'error': relevance.refusal})
        if plan is None:
            return JSONResponse(status_code=409, content={'error': 'unsupported_row'})
        plan['source_projection'] = _notes_source_projection(conversation)
        plan['source_projection']['title_evidence'] = _notes_title_evidence(stored, conversation)
        minimum = plan.get('minimum') or {}
        if minimum.get('discarded') and minimum.get('reason') == 'empty_transcript':
            plan['source_projection']['empty_discard_home'] = _empty_discard_home(
                req.owner, stored, plan['source_projection']
            )
        plan['terminal_family_enabled'] = terminal_settled.serving(req.owner)
        plan['open_loops_enabled'] = open_loops_enabled()
        plan['episode_checked'] = True
        plan['inline_fanout'] = True
        return plan
    if req.step == 'episode-start':
        return {'wait': member_notes.waits(req.owner, row, ProcessingTrigger.SYNC_UPDATE)}
    effects_write = None
    if req.step in {'effects', 'effects-episode'}:
        from utils.conversations.process_conversation import apply_eager_sync_enrichment, apply_settled_enrichment

        conversation = deserialize_conversation({**row, 'id': req.conversation})
        digest = derived_effects_transcript_digest(conversation.transcript_segments)
        outputs: dict[str, Any] = {DERIVED_EFFECTS_TRANSCRIPT_FIELD: digest}
        if stored.get('go_sync_minimum_revision') == req.sync_revision:
            # The minimum extracts no new actions. Let the ordinary task writer
            # reconcile any previous refresh obligations before stamping it.
            conversation.structured.action_items = []
            apply_settled_enrichment(req.owner, conversation, include_vector=False)
        else:
            effect_source = GoConversationEffectSource(
                req.conversation, req.sync_revision, stored['finalization_owner_epoch'], req.job, req.revision
            )
            apply_eager_sync_enrichment(req.owner, conversation, effect_source=effect_source)
            outputs.update(
                apps_results=[result.model_dump() for result in conversation.apps_results],
                suggested_summarization_apps=conversation.suggested_summarization_apps,
            )
        changed = {key: value for key, value in outputs.items() if stored.get(key) != value}
        if changed:
            patch = encode_conversation_for_write(req.owner, changed, stored.get('data_protection_level', 'standard'))
            effects_write = (stored, patch)
    combined = req.step == 'effects-episode'
    episode = None
    if combined or req.step == 'episode-reconcile':
        from utils.episodes.service import Collaborators, on_conversation_finalized

        episode = _EpisodeFence(client, req, stored)
        collaborators = Collaborators(firestore_client=client, finalized_memo=episode.finalize_memo)
        # The Home read projection localizes minimum titles. Attachment and its
        # completion memo must use the persisted structured data instead.
        episode_row = row
        if (
            stored.get('go_sync_minimum_revision') == req.sync_revision
            and stored.get('summary_blocked_reason') == 'content_below_floor'
        ):
            episode_row = {**row, 'structured': stored.get('structured')}
        try:
            with episode_write_fence.use(episode):
                outcome = on_conversation_finalized(
                    req.owner,
                    req.conversation,
                    episode_row,
                    trigger=ProcessingTrigger.SYNC_UPDATE.value,
                    collaborators=collaborators,
                )
        except episode_write_fence.EpisodeWriteRefused:
            outcome = 'ownership_changed'
        if episode.refused:
            if combined and not episode.checked:
                _clear_unstarted_episode(client, req, job_version)
            return JSONResponse(status_code=409, content={'error': 'ownership_changed'})
        if outcome == 'skipped_deleted':
            return JSONResponse(status_code=409, content={'error': 'ownership_changed'})
        if outcome in {'error', 'conflict'}:
            return JSONResponse(status_code=409, content={'error': 'operation_unsettled'})
    if not _settle(client, req, effects_write=effects_write, job_version=job_version, episode=episode):
        error = 'ownership_changed' if episode is not None and episode.refused else 'operation_unsettled'
        return JSONResponse(status_code=409, content={'error': error})
    return {'combined': True} if combined else {}


@router.post('/internal/finalization/sync-reference', include_in_schema=False)
def adapt_sync_finalization(req: ReferenceRequest, _authorized: int = Depends(_authorize)):
    return _adapt(get_firestore_client(), req)
