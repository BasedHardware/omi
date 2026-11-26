"""Execute recording-builder and sweeper query shapes without external effects."""

from datetime import datetime, timedelta
from importlib import import_module
from unittest.mock import patch

from tests.support.firestore_query_drivers import (
    CoveredByEntry,
    DriverEntry,
    SHAPE_UID,
    FROZEN_NOW,
    FROZEN_LATER,
    ref_collection,
    ref_transaction,
)
from utils.other.list_budget import ListReadBudget


def _pending_source(client, combo, trial):
    if combo.get('conversation_id'):
        return
    client.queue_results(
        [
            client.snapshot(
                f'users/{SHAPE_UID}/conversations/source',
                {
                    'id': 'source',
                    'recording': True,
                    'started_at': FROZEN_NOW,
                    'finished_at': FROZEN_NOW,
                    'status': 'completed',
                },
            )
        ]
    )


def _finish_source(client, combo, trial):
    client.queue_results(
        [
            client.snapshot(
                f'users/{SHAPE_UID}/conversations/source',
                {
                    'source': 'omi',
                    'recording': True,
                    'created_at': FROZEN_NOW,
                    'started_at': FROZEN_NOW,
                    'finished_at': FROZEN_NOW,
                    'status': 'completed',
                    'external_data': {'recording_session_id': 'shape-session'},
                },
            )
        ]
    )


def _named_finish_sources(client, combo, trial):
    """A just-sealed capture and the ended window it fed; Finish may name either one."""
    base = f'users/{SHAPE_UID}/conversations'
    client.documents[f'{base}/source'] = {
        'source': 'omi',
        'recording': True,
        'created_at': FROZEN_NOW,
        'started_at': FROZEN_NOW,
        'finished_at': FROZEN_NOW,
        'status': 'completed',
        'external_data': {'recording_session_id': 'shape-session'},
    }
    client.documents[f'{base}/window'] = {
        'v3_derived': True,
        'started_at': FROZEN_NOW,
        'finished_at': FROZEN_NOW,
        'status': 'processing',
        'v3_recording_ids': ['source'],
    }


def _finish_clock(client):
    """The cut is fresh, so the predecessor read runs."""

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_NOW

    return patch('database.conversations_v3_finish_predecessors.datetime', Clock)


def _pick_none(rows, now):
    return None


def _decode(client):
    return patch('database.conversations_v3.decode_row', side_effect=lambda uid, snapshot: snapshot.to_dict())


def _transaction_without_rpc(client):
    # The driver loads the target under its outbound-network guard.
    target = import_module('database.conversations_v3_live')
    return patch.object(target.firestore, 'transactional', side_effect=lambda fn: fn)


def entries():
    return (
        DriverEntry(
            'database.conversations_v3_context.earlier_titles',
            base={'uid': SHAPE_UID, 'start': FROZEN_NOW, 'end': FROZEN_LATER},
            neutrals={'budget': (ListReadBudget(deadline_monotonic=10**30, max_documents=53), 'RPC/read budget only')},
        ),
        DriverEntry(
            'database.conversations_v3.load',
            base={'uid': SHAPE_UID},
            domains={'conversation_id': [None, 'source']},
            setup=_pending_source,
            patchers=(_decode,),
        ),
        DriverEntry(
            'database.conversations_v3_finish_predecessors.attach',
            base={
                'coll': ref_collection(f'users/{SHAPE_UID}/conversations'),
                'recordings': {
                    'finish': {
                        'id': 'finish',
                        'started_at': FROZEN_NOW,
                        'finished_at': FROZEN_NOW,
                        'v3_manual_end': True,
                        'external_data': {'recording_origin_id': 'shape-origin'},
                    }
                },
                'existing': {},
            },
            patchers=(_finish_clock,),
        ),
        DriverEntry(
            'database.conversations_v3._mark_successor_pending',
            base={
                'coll': ref_collection(f'users/{SHAPE_UID}/conversations'),
                'recordings': {
                    'source': {
                        'id': 'source',
                        'started_at': FROZEN_NOW,
                        'finished_at': FROZEN_NOW,
                        'transcript_segments': [{'text': 'shape', 'start': 0, 'end': 1}],
                        'v3_rotation_cap_seconds': 300.0,
                    }
                },
            },
        ),
        DriverEntry(
            'database.conversations_v3.load_derive',
            base={'uid': SHAPE_UID, 'since': FROZEN_NOW, 'until': FROZEN_LATER, 'run_id': 'shape-run'},
            domains={'rederive': [False, True]},
        ),
        DriverEntry(
            'database.conversations_v3_rederive.load_live_rederive',
            base={'uid': SHAPE_UID, 'since': FROZEN_NOW, 'until': FROZEN_LATER, 'run_id': 'shape-run'},
        ),
        DriverEntry(
            'database.conversations_v3.backfill_window_metadata',
            base={'uid': SHAPE_UID, 'since': FROZEN_NOW, 'until': FROZEN_LATER},
        ),
        DriverEntry(
            'database.conversations_v3_live.recent_windows',
            base={'uid': SHAPE_UID, 'now': FROZEN_NOW, 'max_idle': timedelta(hours=2)},
            domains={'finished_before': [None, FROZEN_NOW]},
            neutrals={'max_rows': (200, 'read bound only')},
        ),
        DriverEntry(
            'database.conversations_v3_live.live_window',
            base={'uid': SHAPE_UID, 'now': FROZEN_NOW, 'max_idle': timedelta(hours=2)},
            neutrals={'pick': (_pick_none, 'row selection only; no window is live, so both bands read')},
        ),
        DriverEntry(
            'database.conversations_v3_live.request_recording_finish',
            base={'uid': SHAPE_UID, 'now': FROZEN_NOW},
            setup=_finish_source,
            patchers=(_transaction_without_rpc,),
        ),
        DriverEntry(
            'database.conversations_v3_live.request_named_finish',
            base={'uid': SHAPE_UID, 'now': FROZEN_NOW},
            domains={'named_id': ['source', 'window']},
            setup=_named_finish_sources,
            patchers=(_transaction_without_rpc,),
        ),
        CoveredByEntry(
            'database.conversations_v3_live._live_window_or_deleting',
            covered_by=(
                'database.conversations_v3_live.request_recording_finish',
                'database.conversations_v3_live.request_named_finish',
            ),
            reason='Both recording-scoped Finish transactions run the same live-window recheck before any write.',
        ),
        CoveredByEntry(
            'database.conversations_v3_live._recent_finish_sources',
            covered_by=('database.conversations_v3_live.request_recording_finish',),
            reason='The Finish transaction scans the same bounded source query on every call.',
        ),
        DriverEntry(
            'database.conversations_v3.merge_donors_have_tasks',
            base={'uid': SHAPE_UID, 'donor_ids': ['donor-one', 'donor-two']},
            domains={'transaction': [None, ref_transaction()]},
        ),
        DriverEntry(
            'database.conversations_v3.pending_backfill_processing',
            base={'uid': SHAPE_UID},
            domains={'after': [None, 'last-foreign']},
            neutrals={'deadline': (float('inf'), 'RPC deadline only; an expired budget issues no query')},
        ),
        DriverEntry('database.conversations_v3.backfill_run_documents', base={'uid': SHAPE_UID, 'run_id': 'shape-run'}),
        DriverEntry('database.conversations_v3_backfill_runs.list_runs', base={'uid': SHAPE_UID}),
        DriverEntry(
            'database.conversations_v3_backfill_runs.list_priors', base={'uid': SHAPE_UID, 'run_id': 'shape-run'}
        ),
        DriverEntry('database.conversations_v3_backfill_runs._live_run_ids', base={'uid': SHAPE_UID}),
        DriverEntry(
            'database.conversations_v3_backfill_runs.purge_conversation_priors',
            base={'uid': SHAPE_UID, 'conversation_ids': ['shape-conversation'], 'reason': 'deleted'},
            neutrals={'keep_level': (None, 'only filters which existing prior documents are stubbed; no query shape')},
        ),
        DriverEntry('database.conversations_v3_backfill_runs.pending_starts', base={'limit': 20}),
        DriverEntry('database.conversations_v3_processing.pending_created', base={'uid': SHAPE_UID}),
        # Owner-level End instants (flag end_open_conversation): single-field range reads on the cut time.
        DriverEntry('database.conversations_v3_manual_cuts.around', base={'uid': SHAPE_UID, 'at': FROZEN_NOW}),
        DriverEntry('database.conversations_v3_manual_cuts.load', base={'uid': SHAPE_UID, 'since': FROZEN_NOW}),
        DriverEntry(
            'utils.conversations.v3.service.has_pending',
            base={'uid': SHAPE_UID},
            domains={'deferred': [(), ('preview-source',)]},
        ),
        DriverEntry('utils.conversations.v3.service.pending_processing', base={'uid': SHAPE_UID}),
        DriverEntry('utils.conversations.v3.service.sweep'),
        DriverEntry('utils.conversations.v3.service.measure_legacy_users'),
    )
