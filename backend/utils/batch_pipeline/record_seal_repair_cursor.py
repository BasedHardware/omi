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
    def __init__(self, client, secret):
        if len(secret) < 32:
            raise ValueError('cursor key required')
        self.cipher = AESGCM(hmac.digest(secret, PURPOSE, 'sha256'))
        self.ref = client.collection('batch_pipeline_prod_maintenance').document('record_seal_repair_cursor_v1')

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
        if len(parts) < 4 or len(parts) % 2 or parts[-2] != 'conversations' or not all(parts):
            raise ValueError('invalid maintenance frontier')
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
            finished = cursor['finished_at']
            # datetime.isoformat/fromisoformat truncates Firestore nanoseconds,
            # which can otherwise make a full equal-finish page repeat forever.
            if isinstance(finished, DatetimeWithNanoseconds):
                stamp = finished.timestamp_pb()
            else:
                stamp = Timestamp()
                stamp.FromDatetime(finished)
            value = {'path': cursor['path'], 'seconds': stamp.seconds, 'nanos': stamp.nanos}
            if 'horizon' in cursor:
                # This boundary originates from datetime.now, not Firestore.
                value['horizon'] = cursor['horizon'].isoformat()
        nonce = os.urandom(12)
        blob = nonce + self.cipher.encrypt(nonce, json.dumps(value).encode(), PURPOSE)
        self.ref.set({'version': 1, 'cursor': blob}, timeout=budget.timeout(), retry=None)
        budget.check()
