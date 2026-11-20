"""Exercise the real endpoint and Firestore transactions with an isolated Bark transport."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hmac
import json
import os
import unittest

from google.cloud import firestore
import httpx

from .app import OPERATOR_SA, SCHEDULER_SA, create_app
from .bark import BARK_ENDPOINT, Bark
from .publisher import REDIS
from .store import ATTEMPT_LEASE, RETRY_DELAY, Store

SECRET = b'local-fixture-signing-key-only-0000'
AUDIENCE = 'https://fixture.invalid'
PUBLISH = '/v1/publish/grafana-redis'
DRAIN = '/internal/drain'
AUTH = {'Authorization': 'fixture-scheduler'}
PROJECT = 'demo-omi-paging'


class PagerFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith('127.0.0.1:'):
            raise RuntimeError('this fixture requires an isolated local emulator')
        cls.db = firestore.Client(project=PROJECT, database='pager')

    def setUp(self):
        for collection in ('pager_events', 'pager_deliveries', 'pager_recipient_limits'):
            for ref in self.db.collection(collection).list_documents():
                ref.delete()
        self.now = datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)
        self.operations = Counter()
        self.calls = []
        self.provider = []
        self.restart()

    def restart(self, enabled=True):
        def send(request):
            self.calls.append((str(request.url), json.loads(request.content)))
            outcome = self.provider.pop(0) if self.provider else 'accepted'
            if outcome == 'retry':
                raise httpx.ConnectError('fixture: no connection')
            if outcome == 'unknown':
                raise httpx.ReadTimeout('fixture: reply lost')
            return httpx.Response(200, json={'code': 200})

        def authorize(token, audience, principal):
            return (token, audience, principal) in (
                ('fixture-scheduler', AUDIENCE + DRAIN, SCHEDULER_SA),
                ('fixture-operator', AUDIENCE + '/internal/ack', OPERATOR_SA),
            )

        self.store = Store(self.db, lambda name: self.operations.update([name]))
        self.app = create_app(
            self.store,
            Bark('fixture-no-real-device', httpx.Client(transport=httpx.MockTransport(send), trust_env=False)),
            SECRET,
            AUDIENCE,
            enabled,
            clock=lambda: self.now,
            authorize=authorize,
        )

    def alert(self, status='firing', starts_at=None, **labels):
        return {
            'status': status,
            'startsAt': (starts_at or self.now).isoformat(),
            'endsAt': self.now.isoformat(),
            'fingerprint': '1cb79bfa5576ac26',
            'labels': {'alert_identity': REDIS.uid, 'paging_target': REDIS.target, **labels},
            'annotations': {'summary': 'fixture input that must never reach the audit or handset'},
        }

    def publish(self, *alerts, signed_at=None, signature_valid=True):
        body = json.dumps({'alerts': alerts}).encode()
        timestamp = str(int((signed_at or self.now).timestamp()))
        signature = hmac.digest(SECRET, timestamp.encode() + b':' + body, 'sha256').hex()
        return self.app.test_client().post(
            PUBLISH,
            data=body,
            headers={
                'X-Grafana-Alerting-Timestamp': timestamp,
                'X-Grafana-Alerting-Signature': signature if signature_valid else '0' * 64,
            },
        )

    def admit(self, *alerts):
        response = self.publish(*alerts)
        self.assertEqual(response.status_code, 202, response.get_json())
        return response.get_json()['receipts'][0]

    def drain(self, headers=AUTH):
        return self.app.test_client().post(DRAIN, headers=headers)

    def delivery(self, receipt):
        return self.store.delivery_ref(receipt['delivery_id']).get().to_dict()

    def test_authenticated_admission_idempotency_and_operation_counts(self):
        alert = self.alert()
        self.assertEqual(self.publish(alert, signature_valid=False).status_code, 401)
        self.assertEqual(self.publish(alert, signed_at=self.now - timedelta(minutes=6)).status_code, 401)
        self.assertEqual(self.publish(self.alert(paging_target='different-target')).status_code, 400)
        self.assertEqual(self.publish(self.alert(alert_identity='another-rule')).status_code, 400)
        self.assertEqual(self.app.test_client().post('/v1/publish/future').status_code, 404)
        self.assertFalse(self.operations)
        receipt = self.admit(alert)
        self.assertEqual(receipt['state'], 'queued')
        self.assertEqual(self.operations, {'read': 2, 'write': 2})
        self.operations.clear()
        self.assertEqual(self.admit(alert)['state'], 'duplicate')
        self.assertEqual(self.operations, {'read': 1})
        self.assertEqual(self.drain(headers={'Authorization': 'fixture-operator'}).status_code, 401)
        self.operations.clear()
        self.assertEqual(self.drain().get_json(), {'attempted': 1})
        self.assertEqual(self.operations, {'query': 1, 'query_result': 1, 'read': 3, 'write': 3})
        print(
            'Firestore fixture first admission: 2 lookups / 2 writes; duplicate: 1 lookup / 0 writes; '
            'first attempt: 1 query / 1 result / 3 lookups / 3 writes'
        )
        event = self.db.collection('pager_events').document(receipt['event_id']).get().to_dict()
        self.assertEqual(event['recipient'], 'oncall-primary')
        self.assertNotIn('annotations', event)
        endpoint, body = self.calls[0]
        self.assertEqual(endpoint, BARK_ENDPOINT)
        self.assertEqual(
            (body['group'], body['level'], body['volume'], body['call']), ('page-wake', 'critical', '5', '1')
        )
        self.assertNotIn('fixture input', json.dumps(body))
        self.assertEqual(self.delivery(receipt)['state'], 'provider_accepted')
        ack = '/internal/ack/' + receipt['delivery_id']
        self.assertNotIn('acknowledgement', self.delivery(receipt))
        self.assertEqual(self.app.test_client().post(ack, headers=AUTH).status_code, 401)
        self.assertEqual(
            self.app.test_client().post(ack, headers={'Authorization': 'fixture-operator'}).status_code, 200
        )
        self.assertEqual(self.delivery(receipt)['acknowledgement']['kind'], 'handset_witness')

    def test_concurrent_replay_and_drain_send_once(self):
        alert = self.alert()
        with ThreadPoolExecutor(max_workers=6) as pool:
            receipts = list(pool.map(lambda _: self.admit(alert), range(6)))
            self.assertEqual(Counter(r['state'] for r in receipts), {'queued': 1, 'duplicate': 5})
            self.assertEqual(len({r['delivery_id'] for r in receipts}), 1)
            counts = list(pool.map(lambda _: self.drain().get_json()['attempted'], range(6)))
        self.assertEqual(sum(counts), 1)
        self.restart()
        self.assertEqual(self.admit(alert)['state'], 'duplicate')
        self.assertEqual(self.drain().get_json(), {'attempted': 0})
        self.assertEqual(len(self.calls), 1)

    def test_reordered_resolution_is_quiet_and_does_not_touch_new_episode(self):
        old_start = self.now
        self.now += timedelta(minutes=1)
        newer = self.admit(self.alert())
        self.assertEqual(self.admit(self.alert('resolved', old_start))['state'], 'quiet_recovery')
        self.assertEqual(self.admit(self.alert(starts_at=old_start))['state'], 'suppressed_resolved')
        self.assertEqual(self.drain().get_json(), {'attempted': 1})
        self.assertEqual(self.delivery(newer)['state'], 'provider_accepted')
        new_start = self.now
        self.now += timedelta(minutes=1)
        self.assertEqual(self.admit(self.alert('resolved', new_start))['state'], 'quiet_recovery')
        self.assertEqual(self.admit(self.alert('resolved', new_start))['state'], 'duplicate')
        self.restart()
        self.assertEqual(self.drain().get_json(), {'attempted': 0})
        self.assertEqual(len(self.calls), 1)
        self.assertIsNotNone(self.delivery(newer)['resolved_at'])
        self.admit(self.alert())
        self.assertEqual(self.drain().get_json(), {'attempted': 1})

    def test_retry_survives_restart_and_clearing_cancels_next_attempt(self):
        start = self.now
        receipt = self.admit(self.alert())
        self.provider[:] = ['retry', 'retry']
        self.assertEqual(self.drain().get_json(), {'attempted': 1})
        self.assertEqual(self.delivery(receipt)['state'], 'retry')
        self.now += RETRY_DELAY
        self.restart(enabled=False)
        self.assertEqual(self.drain().status_code, 503)
        self.assertEqual(len(self.calls), 1)
        self.restart()
        self.operations.clear()
        self.assertEqual(self.drain().get_json(), {'attempted': 1})
        self.assertEqual(self.operations, {'query': 1, 'query_result': 1, 'read': 2, 'write': 2})
        print('Firestore fixture repeat attempt: 1 query / 1 result / 2 lookups / 2 writes')
        self.admit(self.alert('resolved', start))
        self.now += RETRY_DELAY * 3
        self.restart()
        self.assertEqual(self.drain().get_json(), {'attempted': 0})
        self.assertEqual(self.delivery(receipt)['state'], 'resolved')
        self.assertEqual([a['outcome'] for a in self.delivery(receipt)['attempts']], ['retryable', 'retryable'])

    def test_dead_claim_and_ambiguous_provider_are_never_retried(self):
        lost = self.admit(self.alert())
        self.assertEqual(self.store.claim(lost['delivery_id'], self.now)[0], 1)
        self.now += ATTEMPT_LEASE
        self.restart()
        self.assertEqual(self.drain().get_json(), {'attempted': 0})
        self.assertEqual(self.delivery(lost)['attempts'][0]['reason'], 'lease_expired')
        ambiguous = self.admit(self.alert())
        self.provider[:] = ['unknown']
        self.assertEqual(self.drain().get_json(), {'attempted': 1})
        self.now += timedelta(minutes=2)
        self.restart()
        self.assertEqual(self.drain().get_json(), {'attempted': 0})
        self.assertEqual(self.delivery(ambiguous)['state'], 'unknown')
        self.assertEqual(len(self.calls), 1)

    def test_wake_cap_and_stale_firing(self):
        for _ in range(6):
            self.admit(self.alert())
            self.assertEqual(self.drain().get_json(), {'attempted': 1})
            self.now += timedelta(seconds=1)
        receipt = self.admit(self.alert())
        self.assertEqual(self.drain().get_json(), {'attempted': 0})
        self.assertEqual(self.delivery(receipt)['state'], 'suppressed_cap')
        stale = self.admit(self.alert(starts_at=self.now - timedelta(minutes=16)))
        self.assertEqual(stale['state'], 'suppressed_stale')
        self.assertEqual(len(self.calls), 6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
