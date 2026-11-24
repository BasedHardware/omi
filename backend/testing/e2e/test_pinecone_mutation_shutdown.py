"""Exercise the serving shutdown hooks with hermetic dependencies and real tickets."""

import asyncio
from threading import get_ident

import pytest


@pytest.mark.parametrize('service', ['main', 'pusher'])
async def test_pinecone_mutation_shutdown_runs_before_other_cleanup(client, monkeypatch, service):
    import firebase_admin
    import main
    from database import pinecone_partition_state as state
    from database.pinecone_mutation_lifecycle import MutationRegistry
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    registry = MutationRegistry()
    monkeypatch.setattr(state, '_mutations', registry)
    for name in ('_begin_mutation', '_mark_mutation_uncertain'):
        monkeypatch.setattr(state, name, getattr(state, name).to_wrap)
    db = StrictFirestore()
    key = state.PartitionKey('synthetic-index', 'ns1', 'synthetic-owner')
    state.begin_mutation(key, affected_ids=['synthetic-vector'], firestore_client=db)
    event_loop_thread = get_ident()
    drain = state.drain_mutations

    def checked_drain():
        assert get_ident() != event_loop_thread
        return drain()

    monkeypatch.setattr(state, 'drain_mutations', checked_drain)

    async def stop_after_drain(**kwargs):
        route = state.get_route(key, firestore_client=db)
        assert route.pending_count == 0
        assert route.uncertain_count == 1
        raise RuntimeError('synthetic later cleanup failure')

    if service == 'main':
        assert main.shutdown_event in main.app.router.on_shutdown
        monkeypatch.setattr(main.app.state, 'messaging_runtime', None, raising=False)
        monkeypatch.setattr(main.app.state, 'batch_pipeline_serving', None, raising=False)
        monkeypatch.setattr(main.batch_pressure, 'stop', stop_after_drain)
        with pytest.raises(RuntimeError, match='later cleanup failure'):
            await main.shutdown_event()
    else:
        # The hermetic main app already initialized the default Firebase app.
        monkeypatch.setattr(firebase_admin, 'initialize_app', lambda *a, **kw: firebase_admin.get_app())
        import pusher.main as pusher

        async def startup():
            state.start_mutations()

        monkeypatch.setattr(pusher, 'startup_event', startup)
        monkeypatch.setattr(pusher, 'flush_active', stop_after_drain)
        with pytest.raises(RuntimeError, match='later cleanup failure'):
            async with pusher.lifespan(pusher.app):
                await asyncio.sleep(0)
    assert drain() == 0
