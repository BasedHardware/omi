"""Standalone request-based Cloud Run pager."""

from datetime import datetime, timezone
import json
import logging
import os
import re

from flask import Flask, request
from google.api_core.exceptions import GoogleAPICallError, RetryError
from google.cloud import firestore
import httpx

from .bark import Bark
from .oidc import OIDCVerifier
from .publisher import parse_events, verify_signature
from .store import Store, TransactionRetriesExhausted

OPS_PROJECT = 'omi-paging-ops-prod'
OPS_DB = 'pager'
SCHEDULER_SA = f'pager-scheduler@{OPS_PROJECT}.iam.gserviceaccount.com'
OPERATOR_SA = f'pager-operator@{OPS_PROJECT}.iam.gserviceaccount.com'
LOG = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def create_app(store, bark, signing_secret, audience, sender_enabled, *, clock=utcnow, authorize=None):
    if authorize is None:
        authorize = OIDCVerifier()
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024

    @app.errorhandler(GoogleAPICallError)
    @app.errorhandler(RetryError)
    @app.errorhandler(TransactionRetriesExhausted)
    def store_unavailable(error):
        LOG.warning('pager store unavailable: %s', type(error).__name__)
        return {'error': 'store_unavailable'}, 503

    @app.get('/healthz')
    def health():
        return {'status': 'ok'}

    @app.post('/v1/publish/grafana-redis')
    def publish():
        now = clock()
        body = request.get_data(cache=False)
        if not verify_signature(
            signing_secret,
            request.headers.get('X-Grafana-Alerting-Timestamp', ''),
            request.headers.get('X-Grafana-Alerting-Signature', ''),
            body,
            now,
        ):
            return {'error': 'unauthorized'}, 401
        try:
            events = parse_events(json.loads(body), now)
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
            return {'error': 'invalid_publisher_event'}, 400

        receipts = []
        for event in events:
            disposition = store.admit(event, now)
            if disposition == 'duplicate':
                LOG.info('pager duplicate suppressed event_id=%s', event.event_id)
            receipts.append({'event_id': event.event_id, 'delivery_id': event.delivery_id, 'state': disposition})
        return {'receipts': receipts}, 202

    @app.post('/internal/drain')
    def drain():
        if not authorize(request.headers.get('Authorization', ''), audience + '/internal/drain', SCHEDULER_SA):
            return {'error': 'unauthorized'}, 401
        if not sender_enabled:
            return {'state': 'fenced'}, 503

        sent = 0
        for delivery_id in list(store.due(clock())):
            claim = store.claim(delivery_id, clock())
            if claim is None:
                continue
            number, route, recipient, channel = claim
            outcome, reason = bark.send(route, recipient, channel)
            store.finish(delivery_id, number, outcome, reason, clock())
            sent += 1
        return {'attempted': sent}

    @app.post('/internal/ack/<delivery_id>')
    def ack(delivery_id):
        if not authorize(request.headers.get('Authorization', ''), audience + '/internal/ack', OPERATOR_SA):
            return {'error': 'unauthorized'}, 401
        if not re.fullmatch(r'[0-9a-f]{64}', delivery_id) or not store.acknowledge(delivery_id, clock()):
            return {'error': 'delivery_not_acknowledgeable'}, 404
        return {'state': 'acknowledged'}

    return app


def production_app():
    if (
        os.environ['PAGER_FIRESTORE_PROJECT'] != OPS_PROJECT
        or os.environ['PAGER_FIRESTORE_DATABASE'] != OPS_DB
        or 'FIRESTORE_EMULATOR_HOST' in os.environ
        or 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ
    ):
        raise RuntimeError('pager requires its operations database and attached runtime identity')
    audience = os.environ['PAGER_AUDIENCE']
    if not re.fullmatch(r'https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app', audience):
        raise RuntimeError('pager requires its Cloud Run service URL as the audience prefix')
    secret = os.environ['PAGER_GRAFANA_HMAC'].encode()
    device_key = os.environ['PAGER_BARK_DEVICE_KEY']
    if len(secret) < 32 or not device_key.strip():
        raise RuntimeError('pager secrets are missing or invalid')
    sender = os.environ.get('PAGER_SENDER_ENABLED', 'false')
    if sender not in ('true', 'false'):
        raise RuntimeError('pager sender setting must be true or false')
    db = firestore.Client(project=OPS_PROJECT, database=OPS_DB)
    bark = Bark(device_key, httpx.Client(trust_env=False))
    return create_app(Store(db), bark, secret, audience, sender == 'true')
