"""Private maintenance frontier; no plaintext identities in durable state/logs."""

import hmac
import json
import os
from datetime import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from google.protobuf.timestamp_pb2 import Timestamp

PURPOSE = b'record-seal-repair-cursor-v1'


class RepairCursor:
    def __init__(self, client, secret, *, jobs=False, urgent=False):
        if len(secret) < 32:
            raise ValueError('cursor key required')
        self.cipher = AESGCM(hmac.digest(secret, PURPOSE, 'sha256'))
        self.jobs, self.urgent = jobs, urgent
        # Separate namespaces prevent an ascending frontier from skipping work in descending order.
        name = (
            'record_seal_repair_urgent_cursor_v1'
            if urgent
            else 'record_seal_repair_jobs_cursor_v2' if jobs else 'record_seal_repair_cursor_v2'
        )
        self.ref = client.collection('batch_pipeline_prod_maintenance').document(name)

    def read(self, budget):
        snapshot = self.ref.get(timeout=budget.timeout(), retry=None)
        budget.check()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        blob = data.get('cursor')
        if data.get('version') != 1 or not isinstance(blob, bytes) or not 28 <= len(blob) <= 16384:
            raise ValueError('invalid maintenance frontier')
        value = json.loads(self.cipher.decrypt(blob[:12], blob[12:], PURPOSE))
        if value is None:
            return None
        path = value['path']
        parts = path.split('/') if isinstance(path, str) else []
        valid = (
            (len(parts) == 2 and parts[0] == 'batch_pipeline_prod_jobs')
            if self.jobs
            else (len(parts) >= 4 and len(parts) % 2 == 0 and parts[-2] == 'conversations')
        )
        if not valid or not all(parts):
            raise ValueError('invalid maintenance frontier')
        if self.jobs and 'enqueued_at' in value:
            # Urgent cursors preserve raw scalar query positions even when a
            # malformed deadline is ineligible. Ordinary enqueue clocks stay numeric.
            allowed = (int, float, bool, str, type(None)) if self.urgent else (int, float)
            if type(value['enqueued_at']) not in allowed or 'horizon' not in value:
                raise ValueError('invalid maintenance frontier')
            cursor = {'path': path, 'enqueued_at': value['enqueued_at']}
        else:
            if type(value['seconds']) is not int or type(value['nanos']) is not int or not 0 <= value['nanos'] < 10**9:
                raise ValueError('invalid maintenance frontier')
            stamp = Timestamp(seconds=value['seconds'], nanos=value['nanos'])
            cursor = {'path': path, 'finished_at': DatetimeWithNanoseconds.from_timestamp_pb(stamp)}
        if 'horizon' in value:
            horizon = datetime.fromisoformat(value['horizon'])
            if horizon.tzinfo is None:
                raise ValueError('invalid maintenance frontier')
            cursor['horizon'] = horizon
        return cursor

    def write(self, cursor, budget):
        value = None
        if cursor is not None:
            age_order = self.jobs and 'enqueued_at' in cursor
            # Keep the legacy timestamp envelope too: an older binary can
            # still read this frontier as a hash cursor after a code rollback.
            finished = cursor['horizon'] if age_order else cursor['finished_at']
            # datetime.isoformat/fromisoformat truncates Firestore nanoseconds,
            # which can otherwise make a full equal-finish page repeat forever.
            if isinstance(finished, DatetimeWithNanoseconds):
                stamp = finished.timestamp_pb()
            else:
                stamp = Timestamp()
                stamp.FromDatetime(finished)
            value = {'path': cursor['path'], 'seconds': stamp.seconds, 'nanos': stamp.nanos}
            if age_order:
                value['enqueued_at'] = cursor['enqueued_at']
            if 'horizon' in cursor:
                # This boundary originates from datetime.now, not Firestore.
                value['horizon'] = cursor['horizon'].isoformat()
        nonce = os.urandom(12)
        blob = nonce + self.cipher.encrypt(nonce, json.dumps(value).encode(), PURPOSE)
        self.ref.set({'version': 1, 'cursor': blob}, timeout=budget.timeout(), retry=None)
        budget.check()
