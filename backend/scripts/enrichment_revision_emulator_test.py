# LIFECYCLE: permanent
"""PL-439: a derived refresh revision race cannot retire owed enrichment.

Run the production consumer and settlement driver against legacy Firestore,
replacement Postgres and the simulator. Only the callback's external work and
consumer clock are injected. Complete qualification requires
OMI_REQUIRE_STORE_BACKENDS=all; claims, leases, wakes and settlement are real.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import pytest

from database.action_item_refresh import RefreshRevisionChanged
from database.outbox import Claim, Outcome
from testing.store_fixtures import outbox_backend  # noqa: F401
from utils.enrichment import consumer as consumer_module
from utils.enrichment.consumer import EnrichmentConsumer
from utils.workers.consumer import http_response, run_push

pytestmark = pytest.mark.integration
T0 = 1_000_000.0
LEASE = 120.0


@pytest.fixture
def ob(outbox_backend, monkeypatch):  # noqa: F811
    outbox_backend.store_harness.seed_user('o')
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    # Exercise the ship-on default, independently of the caller's environment.
    monkeypatch.delenv('ENRICHMENT_REVISION_RACE_RETRY_ENABLED', raising=False)
    monkeypatch.setattr(consumer_module, 'time', SimpleNamespace(time=lambda: T0, monotonic=lambda: T0))
    return outbox_backend


def put(ob):
    owner = ob.store_harness.uid('o')
    return ob.outbox.enqueue(
        ob.key(owner, 'owed'),
        owner,
        ob.payload('owed', language='en', first_pending_at=T0),
        T0,
        policy_id='pl439-pinned-policy',
        now=T0,
    )


class ObservingConsumer(EnrichmentConsumer):
    """Record the actual claims delivered by the unchanged production driver."""

    def __init__(self, outbox, callback):
        super().__init__(outbox, process=callback)
        self.claims = []

    def process(self, claim, heartbeat):
        self.claims.append(claim)
        return super().process(claim, heartbeat)


@pytest.mark.parametrize('races', [1, 3])
def test_pl439_revision_race_retries_same_wake_without_a_new_mark(ob, races):
    queued = put(ob)
    calls = []

    def callback(*args):
        calls.append(args)
        if len(calls) <= races:
            raise RefreshRevisionChanged()

    consumer = ObservingConsumer(ob.outbox, callback)
    wakes = list(ob.wakes)
    for attempt in range(races):
        result = run_push(consumer, ob.outbox, queued.row_id, queued.wake_token, now=T0 + attempt)
        assert result.outcome is Outcome.RETRY
        response = http_response(result)
        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'retry', 'reason': 'persistence_fenced'}
        assert ob.wakes == wakes, 'a revision race retains the original delivery, without another writer or wake'

    done = run_push(consumer, ob.outbox, queued.row_id, queued.wake_token, now=T0 + races)
    assert done.outcome is Outcome.DONE
    assert http_response(done).status_code == 200
    assert len(calls) == races + 1
    assert len({claim.lease_token for claim in consumer.claims}) == races + 1
    for attempt, claim in enumerate(consumer.claims, 1):
        assert claim.attempt == attempt
        assert claim.row_id == queued.row_id and claim.wake_token == queued.wake_token
        assert claim.owner_id == ob.store_harness.uid('o')
        assert claim.policy_id == 'pl439-pinned-policy'
        assert claim.payload['first_pending_at'] == T0
        assert claim.payload['conversation_id'] == 'owed' and claim.payload['language'] == 'en'
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + races + 1) is Outcome.STALE
    assert len(calls) == races + 1


def test_pl439_late_revision_race_cannot_release_the_replacement_owner(ob):
    queued = put(ob)
    replacements = []

    def callback(*_):
        replacements.append(ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + LEASE + 1))
        assert isinstance(replacements[0], Claim)
        raise RefreshRevisionChanged()

    consumer = ObservingConsumer(ob.outbox, callback)
    result = run_push(consumer, ob.outbox, queued.row_id, queued.wake_token, now=T0)
    assert result.outcome is Outcome.STALE
    replacement = replacements[0]
    assert replacement.attempt == 2 and replacement.lease_token != consumer.claims[0].lease_token
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + LEASE + 2) is Outcome.BUSY
    assert not ob.outbox.ack(consumer.claims[0], 'processed', now=T0 + LEASE + 2)
    assert ob.outbox.ack(replacement, 'processed', now=T0 + LEASE + 2)


@pytest.mark.parametrize('mode', ['untyped_lookalike', 'kill_switch'])
def test_pl439_only_the_enabled_typed_revision_race_releases_its_lease(ob, monkeypatch, mode):
    queued = put(ob)
    error = ValueError('refresh conversation revision changed')
    if mode == 'kill_switch':
        monkeypatch.setenv('ENRICHMENT_REVISION_RACE_RETRY_ENABLED', 'false')
        error = RefreshRevisionChanged()

    def callback(*_):
        raise error

    with pytest.raises(type(error)) as raised:
        run_push(EnrichmentConsumer(ob.outbox, process=callback), ob.outbox, queued.row_id, queued.wake_token, now=T0)
    assert raised.value is error
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 1) is Outcome.BUSY
    recovered = ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + LEASE + 1)
    assert isinstance(recovered, Claim) and recovered.attempt == 2
    assert ob.outbox.ack(recovered, 'processed', now=T0 + LEASE + 2)
