"""Opt-in, consent-pinned replay secrets and memory-only product decoding.

Only synthetic document names reach Firestore. String/byte field values cross
its SDK boundary as random equality tokens, backed by a per-run memory table.
This preserves equality queries and transactions, but is not a string-ordering
emulator. Decrypted runs are restricted to capture_upload/titling boundaries.
"""

from contextlib import contextmanager, ExitStack, redirect_stdout, redirect_stderr
from dataclasses import dataclass, field, replace
import hashlib
import logging
import os
from pathlib import Path
import secrets
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from testing.replay_harness.guard import CaptureRefused, consenting_uid, private_text, without_uid


def add_arguments(parser):
    for name in ('secret', 'uid', 'consent'):
        parser.add_argument(f'--{name}-file', type=Path)


def file_options(args):
    return {f'{name}_file': getattr(args, f'{name}_file') for name in ('secret', 'uid', 'consent')}


@dataclass(repr=False)
class Decryption:
    uid: str = field(repr=False)
    secret: bytes = field(repr=False)

    def validate(self, case):
        if case.manifest.tier != 'C':
            return
        corpus = case.corpus
        pins = set()
        if corpus.get('owner_sha256'):
            pins.add(corpus['owner_sha256'])
        pins.update(row['owner_key'] for row in corpus.get('results', {}).values() if row.get('owner_key'))
        # Older captures pin the owner in immutable artifact references instead
        # of a top-level field. No pin means no proof: refuse, never infer it
        # from the salted token or the operator's consent file alone.
        for row in [*corpus.get('artifacts', {}).values(), *corpus.get('blob_refs', [])]:
            uri = row.get('uri', '')
            if '/owners/' in uri:
                pins.add(uri.split('/owners/', 1)[1].split('/', 1)[0])
        expected = hashlib.sha256(self.uid.encode()).hexdigest()
        if pins != {expected} or not isinstance(corpus.get('owner_token'), str) or not corpus['owner_token']:
            raise CaptureRefused('case owner does not match consent pin')
        if set(case.manifest.stages) - {'capture_upload', 'titling'}:
            raise CaptureRefused('decryption supports capture_upload and titling only')


def load_decryption(*, secret_file=None, uid_file=None, consent_file=None):
    if not any((secret_file, uid_file, consent_file)):
        return None
    if not all((secret_file, uid_file, consent_file)):
        raise CaptureRefused('decryption requires private secret, uid and consent files')
    uid = consenting_uid(uid_file, consent_file)
    secret = private_text(secret_file).rstrip('\r\n').encode()
    if len(secret) < 32:
        raise CaptureRefused('decryption secret must contain at least 32 bytes')
    return Decryption(uid, secret)


@contextmanager
def quiet_product():
    """Discard Python/native/vendor output; never buffer it or redirect to disk."""
    disabled = logging.root.manager.disable
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(fd) for fd in (1, 2)]
    try:
        with open(os.devnull, 'w') as sink:
            for fd in (1, 2):
                os.dup2(sink.fileno(), fd)
            logging.disable(sys.maxsize)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
    finally:
        logging.disable(disabled)
        for fd, original in zip((1, 2), saved):
            os.dup2(original, fd)
            os.close(original)


@contextmanager
def opaque_firestore():
    from google.cloud.firestore_v1 import _helpers

    encode, decode = _helpers.encode_value, _helpers.decode_value
    forward, reverse = {}, {}
    lock = threading.RLock()

    def encode_value(value):
        if isinstance(value, (str, bytes)):
            with lock:
                key = (type(value), value)
                if key not in forward:
                    token = 'replay-opaque-' + secrets.token_hex(32)
                    forward[key] = token
                    reverse[token] = value
                return encode(forward[key])
        return encode(value)

    def decode_value(value, client):
        result = decode(value, client)
        with lock:
            return reverse.get(result, result) if isinstance(result, str) else result

    try:
        with patch.object(_helpers, 'encode_value', encode_value), patch.object(_helpers, 'decode_value', decode_value):
            yield
    finally:
        forward.clear()
        reverse.clear()


class CapturedStorage:
    """Read captured ciphertext in place; artifact plaintext never touches storage."""

    def __init__(self, case, uid):
        self.case, self.uid = case, uid
        self.refs = {
            without_uid(row['uri'], case.corpus['owner_token'], uid): row
            for row in case.corpus.get('blob_refs', [])
            if row.get('status') == 'captured'
        }

    def bucket(self, name):
        def blob(object_name, generation=None):
            uri = f'gs://{name}/{object_name}#{generation}'
            row = self.refs.get(uri)
            if row is None:
                raise FileNotFoundError('captured artifact unavailable')
            path = self.case.directory / row['path']
            if self.case.directory not in path.resolve().parents:
                raise CaptureRefused('artifact escaped case directory')
            body = path.read_bytes()

            def check(**kwargs):
                if kwargs.get('if_generation_match') != int(generation):
                    raise CaptureRefused('artifact generation mismatch')

            def download(**kwargs):
                check(**kwargs)
                return body

            return SimpleNamespace(size=len(body), generation=int(generation), reload=check, download_as_bytes=download)

        return SimpleNamespace(blob=blob)


@contextmanager
def product_decryption(case, environment, credentials):
    """Keep real derivation/decoders and AEAD checks; adapt identities only at IO."""
    from utils import encryption
    from utils.batch_pipeline import artifacts, artifact_policy

    original_derive = encryption.derive_key
    original_read = artifacts.ArtifactStore._read
    # Isolate product's process-global key cache, including from previous runs.
    with ExitStack() as stack:
        stack.enter_context(patch.object(encryption, 'ENCRYPTION_SECRET', credentials.secret))
        stack.enter_context(patch.object(encryption, '_DERIVED_KEY_CACHE', {}))
        key = original_derive(credentials.uid)

        def key_for(uid):
            if uid not in {credentials.uid, getattr(environment, 'replay_uid', None)}:
                raise CaptureRefused('decryption requested for an unpinned owner')
            return key

        stack.enter_context(patch.object(encryption, 'derive_key', key_for))
        storage = CapturedStorage(case, credentials.uid)

        def read(store, item, uri, kind, limit, **kwargs):
            identities = getattr(environment, 'replay_identities', {})
            reverse = {value: original for original, value in identities.items()}
            reverse[environment.replay_uid] = credentials.uid
            # WorkItem AAD includes original owner, conversation, unit and URI.
            restored = without_uid(
                {name: getattr(item, name) for name in ('owner_id', 'segment_id', 'conversation_id', 'audio_uri')},
                case.corpus['owner_token'],
                credentials.uid,
            )
            restored = environment.restore_replay_identities(restored, reverse)
            restored['owner_id'] = credentials.uid
            original = replace(item, **restored)
            uri = without_uid(uri, case.corpus['owner_token'], credentials.uid)
            parsed = urlsplit(uri)
            reader = artifact_policy.create_artifact_store(
                SimpleNamespace(namespace='batch_pipeline_prod'), storage, parsed.netloc, credentials.secret
            )
            reader.authorize = lambda ignored: store.authorize(item)
            return original_read(reader, original, uri, kind, limit, **kwargs)

        stack.enter_context(patch.object(artifacts.ArtifactStore, '_read', read))
        environment.decryption = True
        try:
            yield
        finally:
            encryption.clear_derived_key_cache()
            environment.decryption = False
