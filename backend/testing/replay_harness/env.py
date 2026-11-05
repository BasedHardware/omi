"""Loopback-only replay environment. No ADC, vendor calls or real Redis."""

from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest.mock import patch

from testing.hermetic_network import block_outbound_network, block_local_redis
from testing.replay_harness.gate_resources import CURRENT_SCOPE, journal_writes

NAMESPACE = 'batch_pipeline_test_replayharness'


def emulator_endpoint() -> str:
    return validate_emulator_endpoint(os.getenv('FIRESTORE_EMULATOR_HOST', ''))


def validate_emulator_endpoint(endpoint):
    host, separator, port = endpoint.rpartition(':')
    if host not in ('127.0.0.1', 'localhost') or not separator or not port.isdigit() or not 0 < int(port) < 65536:
        raise RuntimeError('replay requires a loopback FIRESTORE_EMULATOR_HOST; no cloud fallback')
    return endpoint


def refuse_client(*args, **kwargs):
    raise RuntimeError('offline replay refuses cloud client construction')


@dataclass
class ReplayEnvironment:
    harness: object
    storage: object
    redis: object
    clock: object
    stack: ExitStack

    @property
    def store(self):
        return self.harness.store


@contextmanager
def replay_environment(runtime_env=None):
    endpoint = emulator_endpoint()
    import google.auth
    from google.cloud import firestore, storage
    import grpc

    # C-core gRPC bypasses Python sockets. Only this exact emulator channel can
    # be opened, including by the explicitly anonymous client factory below.
    original_insecure = grpc.insecure_channel

    def local_channel(target, *args, **kwargs):
        if isinstance(target, bytes):
            target = target.decode('ascii')
        if target != endpoint:
            raise RuntimeError('replay refuses non-emulator gRPC channel')
        return original_insecure(target, *args, **kwargs)

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def check_address(sock, address):
        if sock.family == socket.AF_UNIX:
            return
        if (
            not isinstance(address, tuple)
            or address[0] not in ('127.0.0.1', 'localhost')
            or address[1] != int(endpoint.rsplit(':', 1)[1])
        ):
            raise RuntimeError('replay refuses non-emulator socket')

    def connect(sock, address):
        check_address(sock, address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check_address(sock, address)
        return original_connect_ex(sock, address)

    # Clear every inherited provider/credential/feature setting. The sole
    # retained endpoint was checked above. No .env loader is invoked here.
    settings = {name: os.environ[name] for name in ('PATH', 'TMPDIR', 'SYSTEMROOT') if name in os.environ}
    settings.update(
        {
            'FIRESTORE_EMULATOR_HOST': endpoint,
            'FIREBASE_PROJECT_ID': 'demo-omi-isolated-tests',
            'GOOGLE_CLOUD_PROJECT': 'demo-omi-isolated-tests',
            'OMI_ENV_STAGE': 'local',
            'PROVIDER_MODE': 'offline',
            'MEMORY_ENABLED': 'on',
            'ENCRYPTION_SECRET': 'replay-harness-synthetic-encryption-key-0000',
            'OPENAI_API_KEY': 'fake-key-for-hermetic-replay',
            'BUCKET_BATCH_PIPELINE': 'replay-staged',
            'BUCKET_PRIVATE_CLOUD_SYNC': 'replay-chunks',
            'BUCKET_AUDIO_DERIVED': 'replay-derived',
            'BATCH_PIPELINE_RECORD_PROTOCOL_READY': 'true',
            'RECORD_DRAIN_BATCH': '100',
            'RECORD_DRAIN_CONCURRENCY': '16',
        }
    )
    if runtime_env is not None:
        runtime_env.apply(settings)
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, settings, clear=True))
        stack.enter_context(block_outbound_network())
        stack.enter_context(block_local_redis())
        stack.enter_context(patch.object(socket.socket, 'connect', connect))
        stack.enter_context(patch.object(socket.socket, 'connect_ex', connect_ex))
        stack.enter_context(patch.object(grpc, 'secure_channel', refuse_client))
        stack.enter_context(patch.object(grpc, 'insecure_channel', local_channel))
        stack.enter_context(patch.object(storage, 'Client', refuse_client))
        stack.enter_context(patch.object(google.auth, 'default', refuse_client))
        from testing.store_fixtures import make_emulator

        harness = make_emulator()
        stack.callback(harness.close)
        scope = CURRENT_SCOPE.get()
        if scope:
            # Parent chooses this token before launch, so recovery owns a precise namespace.
            harness.uid_suffix = scope['token']
            stack.enter_context(journal_writes(harness.store.client, scope))
        # make_emulator allocated a private client + namespace. Give this lane
        # a discoverable prefix while retaining its unique run token.
        from database.batch_pipeline_store import FirestoreStore

        harness.store = FirestoreStore(f'{NAMESPACE}_{harness.uid_suffix}', firestore_client=harness.store.client)
        store = harness.store
        harness.namespace = store.namespace

        def cleanup_namespace():
            # Delete only this run's namespace and synthetic customer documents.
            for collection in store.client.collections():
                if collection.id.startswith(store.namespace + '_'):
                    for doc in collection.stream():
                        doc.reference.delete()
            for uid in getattr(harness, 'replay_users', ()):
                user = store.client.collection('users').document(uid)
                for collection in user.collections():
                    for doc in collection.stream():
                        doc.reference.delete()
                user.delete()

        stack.callback(cleanup_namespace)
        stack.enter_context(patch.object(firestore, 'Client', refuse_client))
        from database import _client

        stack.enter_context(patch.object(_client, 'get_firestore_client', lambda: store.client))
        # Legacy aliases imported by product helpers resolve through this lazy
        # proxy as well as call-time get_firestore_client().
        for attribute in ('_firestore_client', '_customer_firestore_client', '_data_plane_firestore_client'):
            stack.enter_context(patch.object(_client, attribute, store.client))
        import fakeredis
        from testing.pipeline_sim.clock import VirtualClock
        from utils.other.local_storage import LocalBlob, LocalBucket, LocalStorageClient
        from utils.other import storage as product_storage, local_storage
        from database import redis_db

        scratch = Path(scope['root']) if scope else Path('/Volumes/Ephemeral/scratch')
        root = Path(
            stack.enter_context(TemporaryDirectory(prefix='replay-harness-', dir=scratch if scratch.is_dir() else None))
        )

        class ReplayBlob(LocalBlob):
            def upload_from_file(self, stream, **kwargs):
                # ArtifactStore writes its authenticated stream via this SDK
                # method. Preserve the local adapter's create-only precondition.
                self.upload_from_string(stream.read(), **kwargs)

        class ReplayBucket(LocalBucket):
            def list_blobs(self, prefix='', *args, **kwargs):
                if local.archive_listing_failure and prefix.startswith('raw-live/'):
                    raise TimeoutError('synthetic raw archive listing failure')
                return super().list_blobs(prefix, *args, **kwargs)

            def blob(self, name, generation=None):
                return ReplayBlob(self, name, generation)

        class ReplayStorage(LocalStorageClient):
            archive_listing_failure = False

            def bucket(self, name):
                return ReplayBucket(self.root, name)

        local = ReplayStorage(root / 'gcs')
        fake_redis = fakeredis.FakeRedis(decode_responses=True)
        stack.callback(fake_redis.close)
        stack.enter_context(patch.object(product_storage, '_get_storage_client', lambda: local))
        stack.enter_context(patch.object(local_storage, 'create_storage_client', lambda: local))
        # Override the import-time bucket constant if a test process previously
        # imported storage under different ambient defaults.
        stack.enter_context(patch.object(product_storage, 'private_cloud_sync_bucket', 'replay-chunks'))
        stack.enter_context(patch.object(redis_db, 'r', fake_redis))
        environment = ReplayEnvironment(harness, local, fake_redis, VirtualClock(1_800_000_000), stack)

        def cleanup_replay_documents():
            for ref in getattr(environment, 'replay_documents', ()):
                ref.delete()

        stack.callback(cleanup_replay_documents)
        yield environment
