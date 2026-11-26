"""Exercise the real endpoint and Firestore transactions with an isolated Bark transport."""

from base64 import urlsafe_b64encode
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.api_core.exceptions import Aborted
from google.auth import crypt, jwt
from google.auth.exceptions import TransportError

from google.cloud import firestore
import httpx

from .app import OPERATOR_SA, SCHEDULER_SA, create_app
from .bark import BARK_ENDPOINT, Bark
from . import oidc
from .oidc import OIDCVerifier, fetch_certificates
from .publisher import REDIS
from .store import ATTEMPT_LEASE, RETRY_DELAY, Store

SECRET = b'local-fixture-signing-key-only-0000'
AUDIENCE = 'https://fixture.invalid'
PUBLISH = '/v1/publish/grafana-redis'
DRAIN = '/internal/drain'
AUTH = {'Authorization': 'fixture-scheduler'}
PROJECT = 'demo-omi-paging'


class PagerVerificationFixture(unittest.TestCase):
    def test_actual_oidc_verification_with_cached_and_bounded_transport(self):
        now = datetime.now(timezone.utc)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        identity = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'pager fixture')])
        cert = (
            x509.CertificateBuilder()
            .subject_name(identity)
            .issuer_name(identity)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .sign(key, hashes.SHA256())
        )
        signer = crypt.RSASigner(key, 'fixture-key')
        outbound = []
        monotonic_time = 100

        def fetch(request):
            outbound.append(request)
            return httpx.Response(
                200,
                headers={'Cache-Control': 'public, max-age=30', 'Age': '10'},
                json={'fixture-key': cert.public_bytes(serialization.Encoding.PEM).decode()},
            )

        def token(**overrides):
            claims = {
                'iss': 'https://accounts.google.com',
                'aud': AUDIENCE + DRAIN,
                'email': SCHEDULER_SA,
                'email_verified': True,
                'iat': int(now.timestamp()) - 1,
                'exp': int(now.timestamp()) + 60,
            }
            return jwt.encode(signer, {**claims, **overrides}).decode()

        def authorize(value):
            return verifier('Bearer ' + value, AUDIENCE + DRAIN, SCHEDULER_SA)

        client = httpx.Client(transport=httpx.MockTransport(fetch))
        self.addCleanup(client.close)
        verifier = OIDCVerifier(lambda timeout: fetch_certificates(client, timeout), clock=lambda: monotonic_time)
        self.assertFalse(authorize('invalid.token.signature'))
        self.assertFalse(authorize(token(exp='malformed')))
        nested = urlsafe_b64encode(b'[' * 1100 + b'0' + b']' * 1100).rstrip(b'=').decode()
        self.assertFalse(authorize(token().split('.')[0] + '.' + nested + '.AAAA'))
        self.assertFalse(outbound)
        self.assertTrue(authorize(token()))
        self.assertTrue(authorize(token()))
        self.assertEqual(len(outbound), 1)
        self.assertEqual(outbound[0].url, httpx.URL('https://www.googleapis.com/oauth2/v1/certs'))
        self.assertTrue(all(0 < value <= 2 for value in outbound[0].extensions['timeout'].values()))
        for overrides in (
            {'aud': AUDIENCE + '/internal/ack'},
            {'iss': 'https://fixture.invalid'},
            {'email': OPERATOR_SA},
            {'email_verified': False},
            {'exp': int(now.timestamp()) - 1},
        ):
            with self.subTest(overrides=overrides):
                self.assertFalse(authorize(token(**overrides)))
        header_payload, signature = token().rsplit('.', 1)
        corrupt = ('A' if signature[0] != 'A' else 'B') + signature[1:]
        self.assertFalse(authorize(header_payload + '.' + corrupt))
        self.assertEqual(len(outbound), 1)
        monotonic_time += 20
        self.assertTrue(authorize(token()))
        self.assertEqual(len(outbound), 2)

    def test_invalid_certificate_is_never_cached(self):
        attempts = []

        def fetch(request):
            attempts.append(request)
            return httpx.Response(200, headers={'Cache-Control': 'max-age=3600'}, json={'kid': 'malformed'})

        with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
            verifier = OIDCVerifier(lambda timeout: fetch_certificates(client, timeout))
            for _ in range(2):
                with self.assertRaises(TransportError):
                    verifier.certificates('https://www.googleapis.com/oauth2/v1/certs', 'GET')
        self.assertEqual(len(attempts), 2)

    def test_stalled_certificate_process_is_reaped_before_next_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'first'
            script = (
                "import json, pathlib, sys, time\n"
                "marker = pathlib.Path(sys.argv[1])\n"
                "if not marker.exists():\n"
                "    marker.write_text('one pending lookup')\n"
                "    time.sleep(3)\n"
                "else:\n"
                "    print(json.dumps({'body': '{}', 'cache_control': '', 'age': '0'}))\n"
            )
            command = (sys.executable, '-c', script, str(marker))
            with patch.object(oidc, '_CERT_COMMAND', command):
                with self.assertRaises(subprocess.TimeoutExpired):
                    oidc.fetch_in_process(0.25)
                self.assertTrue(marker.exists())
                self.assertEqual(oidc.fetch_in_process(1)['body'], '{}')

    def test_certificate_request_maps_total_process_timeout_to_transport_error(self):
        verifier = OIDCVerifier(Mock(side_effect=subprocess.TimeoutExpired(('fixture',), 2)))
        with self.assertRaises(TransportError) as error:
            verifier.certificates('https://www.googleapis.com/oauth2/v1/certs', 'GET')
        self.assertIsInstance(error.exception.__cause__, subprocess.TimeoutExpired)
        self.assertIsNone(verifier.certs)
        self.assertFalse(verifier.lock.locked())

    def test_pinned_sdk_commit_exhaustion_returns_retryable_503(self):
        sdk_transaction = Mock(_read_only=False, _max_attempts=2, _id=b'fixture')
        sdk_transaction._commit.side_effect = Aborted('fixture commit contention')
        db = Mock()
        db.transaction.return_value = sdk_transaction
        store = Store(db)
        now = datetime.now(timezone.utc)
        store.read = Mock(
            return_value={
                'state': 'retry',
                'next_at': now,
                'expires_at': now + timedelta(minutes=1),
                'resolved_at': None,
                'attempts': [{'number': 1}],
                'route': REDIS.route_id,
                'recipient': REDIS.recipient,
                'channel': REDIS.channel,
            }
        )
        bark = Mock()
        app = create_app(store, bark, SECRET, AUDIENCE, True, clock=lambda: now, authorize=lambda *_: True)
        store.due = lambda _: iter(('a' * 64,))
        response = app.test_client().post(DRAIN)
        self.assertEqual((response.status_code, response.json), (503, {'error': 'store_unavailable'}))
        self.assertEqual(sdk_transaction._commit.call_count, 2)
        sdk_transaction._rollback.assert_called_once()
        bark.send.assert_not_called()

        def invalid_state(*_):
            raise ValueError('invalid delivery state') from Aborted('unrelated cause')

        store.read = invalid_state
        app.testing = True
        with self.assertRaisesRegex(ValueError, 'invalid delivery state'):
            app.test_client().post(DRAIN)


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

    def admit(self, *alerts, retry_unavailable=False):
        response = self.publish(*alerts)
        if retry_unavailable:
            for delay in (0.05, 0.1, 0.2):
                if response.status_code != 503 or response.get_json() != {'error': 'store_unavailable'}:
                    break
                # Grafana retries transient Firestore contention with the same event ID.
                time.sleep(delay)
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
            receipts = list(pool.map(lambda _: self.admit(alert, retry_unavailable=True), range(6)))
            self.assertEqual(Counter(r['state'] for r in receipts), {'queued': 1, 'duplicate': 5})
            self.assertEqual(len({r['delivery_id'] for r in receipts}), 1)
            drains = list(pool.map(lambda _: self.drain(), range(6)))
        attempted = 0
        for response in drains:
            if response.status_code == 503:
                # The emulator can exhaust its transaction retries under
                # contention. Check the exact retryable result, then retry
                # after all competing claims have finished.
                self.assertEqual(response.get_json(), {'error': 'store_unavailable'})
            else:
                self.assertEqual(response.status_code, 200, response.get_json())
                attempted += response.get_json()['attempted']
        retry = self.drain()
        self.assertEqual(retry.status_code, 200, retry.get_json())
        self.assertEqual(attempted + retry.get_json()['attempted'], 1)
        self.assertEqual(self.delivery(receipts[0])['state'], 'provider_accepted')
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
