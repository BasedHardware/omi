"""Executable query profiles for bounded dream worker and feedback reads."""

from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import patch

from config.dream_agent import Caps
from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry, SHAPE_UID as UID


def producer_mode(client):
    return patch.dict(
        'os.environ', {'DREAM_AGENT_ENABLED': 'true', 'DREAM_AGENT_ELIGIBILITY': 'all', 'REVIEW_SURFACE_MODE': 'on'}
    )


def trim_overflow(client):
    from database import dream_store

    # Exercise the oldest query even though the shape recorder has neutral data.
    return patch.object(dream_store, 'dirty_count', side_effect=[501, 501, 0])


def finish_lease():
    return {
        'run_id': 'shape-run',
        'day': '2026-10-08',
        'started_at': datetime(2026, 10, 8, tzinfo=timezone.utc),
        'watermark': datetime(1970, 1, 1, tzinfo=timezone.utc),
        'score': 1,
        'mode': 'shadow',
        'reservation_usd': 0.24,
        'budget_charge_usd': 0.24,
        'admission_refunded': False,
        'max_usd_per_token': 0.00001,
        'spend_scope': 'user',
        'dirty_dropped': 0,
        'dirty_dropped_reported': 0,
    }


def finish_state(client, args, trial):
    client.documents['dream_users/' + UID] = {'lease': finish_lease(), 'score': 1}


def admission_state(client, args, trial):
    client.documents['dream_users/' + UID] = {'score': 1}


def entries():
    return (
        DriverEntry(
            'utils.dream_seed.load',
            base={'uid': UID},
            neutrals={'caps': (Caps(), 'seed size and model ceilings; no filter changes')},
        ),
        DriverEntry(
            'database.dream_history.history_page',
            base={'uid': UID},
            domains={
                'collection': ['conversations', 'action_items', 'people', 'memory_items'],
                'after': [None, 'one'],
                'limit': [1, 40],
            },
        ),
        DriverEntry(
            'database.dream_history.history_count',
            base={'uid': UID},
            domains={'collection': ['conversations', 'action_items', 'people', 'memory_items']},
        ),
        DriverEntry(
            'database.dream_history.history_from_key',
            base={'uid': UID},
            domains={
                'collection': ['conversations', 'action_items', 'people', 'memory_items'],
                'key': ['00000000', 'ffffffff'],
            },
        ),
        DriverEntry(
            'database.dream_scheduler.candidates',
            patchers=(producer_mode,),
            domains={'limit': [1, 100]},
            neutrals={'now': (datetime(2026, 10, 12, tzinfo=timezone.utc), 'post-query priority only')},
        ),
        DriverEntry(
            'database.dream_scheduler.candidate_page',
            domains={'after': [None, 'one'], 'limit': [1, 100]},
            neutrals={'transaction': (None, 'transaction does not change query shape')},
        ),
        DriverEntry('database.dream_store.own_runs', base={'uid': UID}, domains={'limit': [1, 10, 20]}),
        DriverEntry(
            'database.dream_store.acquire',
            base={'uid': UID},
            domains={'trigger': ['schedule', 'manual']},
            neutrals={
                'caps': (Caps(), 'admission policy only'),
                'rng': (None, 'coin does not alter query shape'),
                'reclaim_sink': (None, 'count-only output after commit does not alter query shape'),
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
                'lease': finish_lease(),
                'report': {'status': 'complete'},
            },
            domains={
                'success': [True, False],
                'refund': [True, False],
                'count_failure': [True, False],
                'deferred': [[], ['conversations/one']],
            },
            neutrals={
                'now': (datetime(2026, 10, 9, tzinfo=timezone.utc), 'UTC reset metadata only'),
                'reviewed': ([], 'metadata writes only'),
                'seeded': ([], 'direct settlement document selection only'),
                'cleanup_cursor': (None, 'metadata writes only'),
                'consumed': ([], 'settlement metadata; watermark uses the separately driven dirty_refs builder'),
                'unavailable': ([], 'settlement metadata; watermark uses the separately driven dirty_refs builder'),
                'release': (True, 'post-query lease policy'),
            },
            setup=finish_state,
        ),
        DriverEntry(
            'database.dream_store.dirty_refs',
            base={'uid': UID},
            domains={'limit': [1, 32, 33, 400, 500], 'newest': [True, False]},
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
    COVERED_BY={
        'database.dream_scheduler.discover': CoveredByEntry(
            'database.dream_scheduler.discover',
            covered_by=('database.dream_scheduler.candidate_page',),
            reason='Discovery streams only through candidate_page (allowlist mode reads listed user documents by explicit ref instead); its chunked get_all calls read explicit document refs in bounded transactions that only initialize due rows and a cursor. SDK queue races are exercised in test_dream_queue_emulator.',
            expect_observed=False,
            body_digest='e614de2d842268bb1b96e7e7a12c885b3e1bbcef9bd63da881baccf177d1c722',
        )
    },
    SKIPS={},
)
