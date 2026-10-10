"""Executable query profiles for bounded dream worker and feedback reads."""

from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import patch

from config.dream_agent import Caps
from tests.support.firestore_query_drivers import DriverEntry, SHAPE_UID as UID


def producer_mode(client):
    return patch.dict('os.environ', {'DREAM_AGENT_MODE': 'shadow', 'DREAM_AGENT_UID_ALLOWLIST': UID})


def trim_overflow(client):
    from database import dream_store

    # Exercise the oldest query even though the shape recorder has neutral data.
    return patch.object(dream_store, 'dirty_count', side_effect=[501, 501, 0])


def finish_state(client, args, trial):
    client.documents['dream_users/' + UID] = {'lease': {'run_id': 'shape-run'}, 'score': 1}


def admission_state(client, args, trial):
    client.documents['dream_users/' + UID] = {'score': 1}


def entries():
    return (
        DriverEntry('database.dream_store.candidates', domains={'limit': [1, 100]}),
        DriverEntry('database.dream_store.own_runs', base={'uid': UID}, domains={'limit': [1, 10, 20]}),
        DriverEntry(
            'database.dream_store.acquire',
            base={'uid': UID},
            domains={'trigger': ['schedule', 'manual']},
            neutrals={
                'caps': (Caps(), 'admission policy only'),
                'canary': (False, 'cohort gate only'),
                'now': (datetime(2026, 10, 9, tzinfo=timezone.utc), 'UTC accounting day only'),
            },
            setup=admission_state,
            patchers=(producer_mode,),
        ),
        DriverEntry(
            'database.dream_store.dirty_count',
            base={'uid': UID},
            neutrals={'transaction': (None, 'transaction binding does not change query shape')},
        ),
        DriverEntry(
            'database.dream_store.mark_dirty',
            base={'uid': UID},
            domains={'refs': [[('conversations', 'one')], [('people', 'person'), ('conversations', 'two')]]},
            neutrals={'canary': (False, 'cohort gate only; admitted canary uses the identical queue builders')},
            patchers=(producer_mode,),
        ),
        DriverEntry('database.dream_store.trim_dirty', base={'uid': UID}, patchers=(trim_overflow,)),
        DriverEntry(
            'database.dream_store.finish',
            base={
                'uid': UID,
                'lease': {
                    'run_id': 'shape-run',
                    'day': '2026-10-08',
                    'started_at': datetime(2026, 10, 8, tzinfo=timezone.utc),
                    'watermark': datetime(1970, 1, 1, tzinfo=timezone.utc),
                    'score': 1,
                    'mode': 'shadow',
                    'reservation_usd': 0.24,
                    'dirty_dropped': 0,
                    'dirty_dropped_reported': 0,
                },
                'report': {'status': 'complete'},
            },
            domains={'success': [True, False], 'refund': [True, False], 'count_failure': [True, False]},
            neutrals={
                'consumed': ([], 'post-query acknowledgement versions'),
                'release': (True, 'post-query lease policy'),
            },
            setup=finish_state,
        ),
        DriverEntry(
            'database.dream_store.dirty_refs',
            base={'uid': UID},
            domains={'limit': [1, 400, 500], 'newest': [True, False]},
            neutrals={'transaction': (None, 'transaction binding does not change query shape')},
        ),
        DriverEntry(
            'database.dream_store.demoted_types',
            base={'uid': UID},
            neutrals={'caps': (Caps(), 'post-query policy only')},
        ),
        DriverEntry('database.dream_feedback.read_patterns', neutrals={'k': (20, 'post-query threshold only')}),
    )


registry_extension = SimpleNamespace(
    DRIVERS={entry.function: entry for entry in entries()},
    COVERED_BY={},
    SKIPS={},
)
