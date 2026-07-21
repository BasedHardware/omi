#!/usr/bin/env python3
"""Export and check OpenAPI contracts.

Contract-surface decision for issue #8546:
- `docs/api-reference/openapi.json` is the public Mintlify Developer API contract.
- The public contract is generated from the real FastAPI app, but filtered to
  `/v1/dev/...` routes so internal, admin, task, and app-client routes are not
  published through Mintlify by accident.
- `docs/api-reference/app-client-openapi.json` is the first-party Flutter app
  client contract. It is also generated from the real FastAPI app, but filtered
  to the Firebase-authenticated routes consumed by the app.
- Public-like routes that intentionally stay out of Mintlify must be listed in
  `UNDOCUMENTED_PUBLIC_ROUTES` with a reason.

The bootstrap is hermetic: it disables dotenv loading, removes real credential
env vars, installs fake Firestore/Redis/GCS boundaries, patches Firebase app
initialization, and blocks non-local network while importing the app.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import socket
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from fastapi.routing import APIRoute
from fastapi.openapi.utils import get_openapi

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / 'backend'
E2E_DIR = BACKEND_DIR / 'testing' / 'e2e'
DEFAULT_SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'openapi.json'
DEFAULT_APP_CLIENT_SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
DEFAULT_INTEGRATION_PUBLIC_SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'integration-public-openapi.json'

DOCUMENTED_PUBLIC_PREFIXES = ('/v1/dev/',)
INTEGRATION_PUBLIC_PATHS = (
    '/v1/integrations/notification',
    '/v2/integrations/{app_id}/user/conversations',
    '/v2/integrations/{app_id}/user/memories',
    '/v2/integrations/{app_id}/memories',
    '/v2/integrations/{app_id}/conversations',
    '/v2/integrations/{app_id}/search/conversations',
    '/v2/integrations/{app_id}/notification',
    '/v2/integrations/{app_id}/tasks',
)
APP_CLIENT_PREFIXES = (
    '/v1/action-items',
    '/v1/agent',
    '/v1/announcements',
    '/v1/app',
    '/v1/app-capabilities',
    '/v1/app-categories',
    '/v1/apps',
    '/v1/calendar',
    '/v1/candidates',
    '/v1/conversations',
    '/v1/dev',
    '/v1/fair-use',
    '/v1/folders',
    '/v1/goals',
    '/v1/import',
    '/v1/integrations',
    '/v1/knowledge-graph',
    '/v1/mcp',
    '/v1/memories',
    '/v1/payment-methods',
    '/v1/payments',
    '/v1/paypal',
    '/v1/persons',
    '/v1/phone',
    '/v1/stripe',
    '/v1/sync',
    '/v1/task-integrations',
    '/v1/task-intelligence',
    '/v1/users',
    '/v1/wrapped',
    '/v1/work-intents',
    '/v1/workflow-migrations',
    '/v1/workstreams',
    '/v1/what-matters-now',
    '/v2/apps',
    '/v2/files',
    '/v2/firmware',
    '/v2/initial-message',
    '/v2/messages',
    '/v2/sync-capture-manifest',
    '/v2/sync-local-files',
    '/v2/tts',
    '/v2/voice-message',
    '/v2/voice-messages',
    '/v3/memories',
    '/v3/speech-profile',
    '/v3/upload-audio',
    '/v4/speech-profile',
)
AUDITED_PUBLIC_PREFIXES = (
    '/v1/dev/',
    '/v1/conversations',
)
UNDOCUMENTED_PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    (
        'POST',
        '/v1/conversations/shared/chat',
    ): 'Trusted frontend service OIDC route; it is not a browser or Developer API surface.',
    (
        'POST',
        '/v1/conversations',
    ): 'Firebase-authenticated first-party app route; public docs expose Developer API key conversation creation.',
    (
        'GET',
        '/v1/conversations',
    ): 'Firebase-authenticated first-party app route; public docs expose Developer API key conversation listing.',
    (
        'GET',
        '/v1/conversations/count',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}',
    ): 'Firebase-authenticated first-party app route; public docs expose the Developer API key conversation detail route.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/title',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/visibility',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/starred',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/folder',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'DELETE',
        '/v1/conversations/{conversation_id}/calendar-event',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'POST',
        '/v1/conversations/{conversation_id}/calendar-event',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'POST',
        '/v1/conversations/{conversation_id}/calendar-event/auto-link',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/summary',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/segments/text',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/segments/{segment_idx}/assign',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/segments/assign-bulk',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/assign-speaker/{speaker_id}',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'DELETE',
        '/v1/conversations/{conversation_id}',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}/recording',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}/photos',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}/transcripts',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}/finalization',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/events',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/action-items',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}/action-items',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}/action-items/count',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'PATCH',
        '/v1/conversations/{conversation_id}/action-items/{action_item_idx}',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'DELETE',
        '/v1/conversations/{conversation_id}/action-items',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}/shared',
    ): 'Unauthenticated shared-conversation route; not part of the Developer API key contract.',
    (
        'POST',
        '/v1/conversations/search',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'POST',
        '/v1/conversations/merge',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'GET',
        '/v1/conversations/{conversation_id}/suggested-apps',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'POST',
        '/v1/conversations/{conversation_id}/test-prompt',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'POST',
        '/v1/conversations/{conversation_id}/finalize',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'POST',
        '/v1/conversations/{conversation_id}/reprocess',
    ): 'Firebase-authenticated first-party app route; not part of the Developer API key contract.',
    (
        'POST',
        '/v1/conversations/from-segments',
    ): 'Firebase-authenticated app-client alias; public docs expose the Developer API key route only.',
}

APP_CLIENT_PUBLIC_PATHS = frozenset(
    {
        '/v1/action-items/shared/{token}',
        '/v1/conversations/{conversation_id}/shared',
        '/v2/messages/shared/{token}',
    }
)

HTTP_METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}

OPENAPI_TITLE = 'Omi Developer API'
APP_CLIENT_OPENAPI_TITLE = 'Omi App Client API'
INTEGRATION_PUBLIC_OPENAPI_TITLE = 'Omi Integration API'
OPENAPI_VERSION = '1.0.0'
OPENAPI_DESCRIPTION = (
    'Programmatic access to your Omi data - memories, conversations, action items, goals, folders, and API keys. '
    'Build custom integrations, analytics dashboards, and automation workflows.'
)
OPENAPI_CONTACT = {'name': 'Omi', 'url': 'https://omi.me'}
OPENAPI_LICENSE = {'name': 'MIT', 'url': 'https://github.com/BasedHardware/omi/blob/main/LICENSE'}
OPENAPI_SERVERS = [{'url': 'https://api.omi.me', 'description': 'Production'}]
OPENAPI_TAGS = [
    {'name': 'Memories', 'description': 'Read and write user memories - timeless facts, preferences, and insights.'},
    {
        'name': 'Conversations',
        'description': 'Create and retrieve conversation transcripts with AI-generated summaries.',
    },
    {'name': 'Folders', 'description': 'Retrieve user-defined folders for organizing conversations.'},
    {
        'name': 'Action Items',
        'description': 'Manage tasks and to-dos extracted from conversations or created manually.',
    },
    {'name': 'Goals', 'description': 'Manage user goals and progress history.'},
    {'name': 'API Keys', 'description': 'Create, list, and revoke developer API keys.'},
]
FIREBASE_BEARER_AUTH_SCHEME = {
    'type': 'http',
    'scheme': 'bearer',
    'bearerFormat': 'Firebase ID token',
    'description': 'Send `Authorization: Bearer <firebase_id_token>`.',
}
DEVELOPER_API_KEY_AUTH_SCHEME = {
    'type': 'http',
    'scheme': 'bearer',
    'bearerFormat': 'Omi Developer API key',
    'description': 'Send `Authorization: Bearer <omi_developer_api_key>`.',
}
INTEGRATION_API_KEY_AUTH_SCHEME = {
    'type': 'http',
    'scheme': 'bearer',
    'bearerFormat': 'Omi Integration API key',
    'description': 'Send `Authorization: Bearer <omi_integration_api_key>`.',
}
ERROR_RESPONSE_SCHEMA = {
    'type': 'object',
    'properties': {
        'detail': {
            'anyOf': [
                {'type': 'string'},
                {'type': 'array'},
                {'type': 'object'},
            ],
            'description': 'Error detail returned by the API.',
        }
    },
    'required': ['detail'],
    'title': 'ErrorResponse',
}
COMMON_RESPONSES = {
    '401': {'description': 'Missing or invalid authentication credentials.'},
    '403': {'description': 'Authenticated, but the token does not grant the required scope.'},
    '404': {'description': 'Requested resource was not found.'},
}
SIDE_EFFECT_PATHS = (
    BACKEND_DIR / 'google-credentials.json',
    BACKEND_DIR / '_temp',
    BACKEND_DIR / '_samples',
    BACKEND_DIR / '_segments',
    BACKEND_DIR / '_speech_profiles',
)
RESTORABLE_SIDE_EFFECT_PATHS = {
    BACKEND_DIR / '_temp': 'created by backend/main.py import-time temp-dir bootstrap',
    BACKEND_DIR / '_samples': 'created by backend/main.py import-time temp-dir bootstrap',
    BACKEND_DIR / '_segments': 'created by backend/main.py import-time temp-dir bootstrap',
    BACKEND_DIR / '_speech_profiles': 'created by backend/main.py import-time temp-dir bootstrap',
}


class OpenAPIContractError(RuntimeError):
    """Raised when the generated OpenAPI contract fails a deterministic check."""


def configure_hermetic_environment() -> None:
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    os.environ['LOCAL_DEVELOPMENT'] = 'true'
    os.environ['ENCRYPTION_SECRET'] = 'test-encryption-secret-for-openapi-testing-32chars!'
    os.environ['FIREBASE_PROJECT_ID'] = 'test-openapi-project'
    os.environ['GOOGLE_CLOUD_PROJECT'] = 'test-openapi-project'
    os.environ['REDIS_DB_HOST'] = 'localhost'
    os.environ['REDIS_DB_PORT'] = '6379'
    os.environ['REDIS_DB_PASSWORD'] = ''
    os.environ['DEEPGRAM_API_KEY'] = 'fake-deepgram-key'
    os.environ['OPENAI_API_KEY'] = 'fake-openai-key'
    os.environ['ANTHROPIC_API_KEY'] = 'fake-anthropic-key'
    os.environ['OPENROUTER_API_KEY'] = 'fake-openrouter-key'
    os.environ['GOOGLE_API_KEY'] = 'fake-google-key'
    os.environ['TYPESENSE_HOST'] = 'localhost'
    os.environ['TYPESENSE_HOST_PORT'] = '8108'
    os.environ['TYPESENSE_API_KEY'] = 'fake-typesense-key'
    os.environ['STRIPE_SECRET_KEY'] = ''
    os.environ['STRIPE_API_KEY'] = ''
    os.environ['ADMIN_KEY'] = ''

    for bucket_var in (
        'BUCKET_SPEECH_PROFILES',
        'BUCKET_POSTPROCESSING',
        'BUCKET_PRIVATE_CLOUD_SYNC',
        'BUCKET_TEMPORAL_SYNC_LOCAL',
        'BUCKET_MEMORIES_RECORDINGS',
        'BUCKET_APP_THUMBNAILS',
        'BUCKET_CHAT_FILES',
        'BUCKET_DESKTOP_UPDATES',
    ):
        os.environ[bucket_var] = bucket_var.lower().replace('bucket_', '').replace('_', '-')

    for secret_var in (
        'SERVICE_ACCOUNT_JSON',
        'GOOGLE_APPLICATION_CREDENTIALS',
        'PINECONE_API_KEY',
        'LANGCHAIN_API_KEY',
        'HUME_API_KEY',
        'HUME_CALLBACK_URL',
    ):
        os.environ.pop(secret_var, None)

    for proxy_var in (
        'HTTP_PROXY',
        'HTTPS_PROXY',
        'ALL_PROXY',
        'NO_PROXY',
        'http_proxy',
        'https_proxy',
        'all_proxy',
        'no_proxy',
    ):
        os.environ.pop(proxy_var, None)


def _install_import_paths() -> None:
    for path in (str(BACKEND_DIR), str(E2E_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)


def is_local_address(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode('idna')
    if not isinstance(host, str):
        return False
    normalized = host.strip().strip('[]').lower()
    if normalized in {'', 'localhost'}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _host_from_address(address: object) -> object:
    if isinstance(address, tuple) and address:
        return address[0]
    return None


@contextmanager
def record_and_block_outbound_network() -> Iterator[list[str]]:
    attempts: list[str] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname
    original_gethostbyname_ex = socket.gethostbyname_ex

    def record(kind: str, target: object) -> None:
        attempts.append(f'{kind}: {target!r}')

    def guarded_connect(sock: socket.socket, address: object):
        if sock.family != socket.AF_UNIX and not is_local_address(_host_from_address(address)):
            record('connect', address)
            raise OpenAPIContractError(f'blocked outbound network connection to {address!r}')
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: object):
        if sock.family != socket.AF_UNIX and not is_local_address(_host_from_address(address)):
            record('connect_ex', address)
            raise OpenAPIContractError(f'blocked outbound network connection to {address!r}')
        return original_connect_ex(sock, address)

    def guarded_create_connection(address: object, *args, **kwargs):
        if not is_local_address(_host_from_address(address)):
            record('create_connection', address)
            raise OpenAPIContractError(f'blocked outbound network connection to {address!r}')
        return original_create_connection(address, *args, **kwargs)

    def guarded_getaddrinfo(host: object, *args, **kwargs):
        if not is_local_address(host):
            record('getaddrinfo', host)
            raise OpenAPIContractError(f'blocked DNS resolution for {host!r}')
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_gethostbyname(host: object):
        if not is_local_address(host):
            record('gethostbyname', host)
            raise OpenAPIContractError(f'blocked DNS resolution for {host!r}')
        return original_gethostbyname(host)

    def guarded_gethostbyname_ex(host: object):
        if not is_local_address(host):
            record('gethostbyname_ex', host)
            raise OpenAPIContractError(f'blocked DNS resolution for {host!r}')
        return original_gethostbyname_ex(host)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    socket.getaddrinfo = guarded_getaddrinfo
    socket.gethostbyname = guarded_gethostbyname
    socket.gethostbyname_ex = guarded_gethostbyname_ex
    try:
        yield attempts
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo
        socket.gethostbyname = original_gethostbyname
        socket.gethostbyname_ex = original_gethostbyname_ex


def snapshot_side_effect_paths() -> dict[Path, tuple[bool, int | None, int | None]]:
    snapshot: dict[Path, tuple[bool, int | None, int | None]] = {}
    for path in SIDE_EFFECT_PATHS:
        if path.exists():
            stat = path.stat()
            snapshot[path] = (True, stat.st_mtime_ns, stat.st_size if path.is_file() else None)
        else:
            snapshot[path] = (False, None, None)
    return snapshot


def assert_no_side_effect_path_mutations(snapshot: dict[Path, tuple[bool, int | None, int | None]]) -> None:
    mutations = []
    for path, before in snapshot.items():
        if path.exists():
            stat = path.stat()
            after = (True, stat.st_mtime_ns, stat.st_size if path.is_file() else None)
        else:
            after = (False, None, None)
        if before != after:
            try:
                mutations.append(str(path.relative_to(ROOT_DIR)))
            except ValueError:
                mutations.append(str(path))
    if mutations:
        raise OpenAPIContractError('OpenAPI export mutated side-effect paths: ' + ', '.join(mutations))


def restore_restorable_side_effect_paths(snapshot: dict[Path, tuple[bool, int | None, int | None]]) -> None:
    for path, before in snapshot.items():
        existed_before = before[0]
        if existed_before or not path.exists():
            continue
        if path not in RESTORABLE_SIDE_EFFECT_PATHS:
            continue
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def assert_env_unchanged(expected_env: dict[str, str]) -> None:
    current_env = dict(os.environ)
    if current_env == expected_env:
        return

    added = sorted(set(current_env) - set(expected_env))
    removed = sorted(set(expected_env) - set(current_env))
    changed = sorted(key for key in set(current_env) & set(expected_env) if current_env[key] != expected_env[key])
    details = []
    if added:
        details.append('added=' + ','.join(added))
    if removed:
        details.append('removed=' + ','.join(removed))
    if changed:
        details.append('changed=' + ','.join(changed))
    raise OpenAPIContractError('OpenAPI export mutated environment: ' + '; '.join(details))


def install_hermetic_dependency_patches():
    import dotenv
    import google.auth
    import google.auth.credentials
    from fakes.firestore import get_mock_firestore, patch_google_firestore, setup_fake_firestore
    from fakes.redis import get_fake_redis, patch_redis_client, setup_fake_redis
    from fakes.storage import patch_google_storage, setup_fake_storage

    dotenv.load_dotenv = lambda *args, **kwargs: False
    # load_backend_env() reads .env files via dotenv_values and writes
    # os.environ directly, so a personal backend/.env would otherwise leak
    # into the export and trip assert_env_unchanged.
    dotenv.dotenv_values = lambda *args, **kwargs: {}
    google.auth.default = lambda *args, **kwargs: (
        google.auth.credentials.AnonymousCredentials(),
        'test-openapi-project',
    )

    fake_firestore = setup_fake_firestore()
    fake_redis = setup_fake_redis()
    setup_fake_storage()

    patch_google_firestore()
    patch_redis_client()
    patch_google_storage()

    import firebase_admin

    firebase_admin.initialize_app = lambda *args, **kwargs: None
    firebase_admin.get_app = lambda *args, **kwargs: object()

    return fake_firestore, fake_redis, get_mock_firestore, get_fake_redis


def relink_imported_service_singletons(fake_firestore, fake_redis, get_mock_firestore, get_fake_redis) -> None:
    import database._client as db_client
    import database.redis_db as redis_db

    old_db = db_client.db
    old_r = redis_db.r
    db_client.db = fake_firestore
    redis_db.r = fake_redis
    for module in list(sys.modules.values()):
        if module is None:
            continue
        for attr_name, attr_value in list(vars(module).items()):
            try:
                if attr_value is old_db:
                    setattr(module, attr_name, get_mock_firestore())
                elif attr_value is old_r:
                    setattr(module, attr_name, get_fake_redis())
            except Exception:
                continue


def generate_public_openapi() -> dict[str, Any]:
    return generate_openapi('public')


def generate_app_client_openapi() -> dict[str, Any]:
    return generate_openapi('app-client')


def generate_integration_public_openapi() -> dict[str, Any]:
    return generate_openapi('integration-public')


def generate_openapi(surface: str) -> dict[str, Any]:
    original_env = dict(os.environ)
    side_effect_snapshot = snapshot_side_effect_paths()
    configure_hermetic_environment()
    expected_fake_env = dict(os.environ)
    _install_import_paths()

    logging.disable(logging.CRITICAL)
    try:
        fake_firestore, fake_redis, get_mock_firestore, get_fake_redis = install_hermetic_dependency_patches()
        with record_and_block_outbound_network() as network_attempts:
            import main as backend_main

            relink_imported_service_singletons(fake_firestore, fake_redis, get_mock_firestore, get_fake_redis)
            schema = build_openapi(backend_main.app, surface)

            if network_attempts:
                raise OpenAPIContractError(
                    'OpenAPI export attempted outbound network during import/generation: ' + '; '.join(network_attempts)
                )

            assert_env_unchanged(expected_fake_env)
            return schema
    finally:
        logging.disable(logging.NOTSET)
        restore_restorable_side_effect_paths(side_effect_snapshot)
        os.environ.clear()
        os.environ.update(original_env)
        assert_no_side_effect_path_mutations(side_effect_snapshot)


def route_key(method: str, path: str) -> tuple[str, str]:
    return method.upper(), path


def iter_route_keys(routes: Iterable[Any]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted((route.methods or set()) & HTTP_METHODS):
            keys.append(route_key(method, route.path))
    return sorted(set(keys))


def is_public_contract_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in DOCUMENTED_PUBLIC_PREFIXES)


def is_app_client_contract_path(path: str) -> bool:
    for prefix in APP_CLIENT_PREFIXES:
        if prefix.endswith('/'):
            if path.startswith(prefix):
                return True
        elif path == prefix or path.startswith(f'{prefix}/'):
            return True
    return False


def is_integration_public_contract_path(path: str) -> bool:
    return path in INTEGRATION_PUBLIC_PATHS


def is_audited_public_path(path: str) -> bool:
    for prefix in AUDITED_PUBLIC_PREFIXES:
        if prefix.endswith('/'):
            if path.startswith(prefix):
                return True
        elif path == prefix or path.startswith(f'{prefix}/'):
            return True
    return False


def public_contract_routes(app) -> list[APIRoute]:
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and is_public_contract_path(route.path) and route.include_in_schema
    ]


def app_client_contract_routes(app) -> list[APIRoute]:
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and is_app_client_contract_path(route.path) and route.include_in_schema
    ]


def integration_public_contract_routes(app) -> list[APIRoute]:
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and is_integration_public_contract_path(route.path) and route.include_in_schema
    ]


def documented_route_keys(schema: dict[str, Any]) -> list[tuple[str, str]]:
    documented: list[tuple[str, str]] = []
    for path, operations in schema.get('paths', {}).items():
        for method in operations:
            method_upper = method.upper()
            if method_upper in HTTP_METHODS:
                documented.append(route_key(method_upper, path))
    return sorted(documented)


def _normalize_bearer_security(schema: dict[str, Any]) -> None:
    components = schema.setdefault('components', {})
    security_schemes = components.setdefault('securitySchemes', {})
    security_schemes.clear()
    security_schemes['firebaseBearer'] = FIREBASE_BEARER_AUTH_SCHEME
    security_schemes['developerApiKey'] = DEVELOPER_API_KEY_AUTH_SCHEME
    components.setdefault('schemas', {})['ErrorResponse'] = ERROR_RESPONSE_SCHEMA
    responses = components.setdefault('responses', {})
    for status_code, response in COMMON_RESPONSES.items():
        responses[f'Error{status_code}'] = {
            **response,
            'content': {
                'application/json': {
                    'schema': {'$ref': '#/components/schemas/ErrorResponse'},
                }
            },
        }
    schema.pop('security', None)

    for path, operations in schema.get('paths', {}).items():
        for method, operation in operations.items():
            if method.upper() in HTTP_METHODS:
                if path.startswith('/v1/dev/keys'):
                    operation['security'] = [{'firebaseBearer': []}]
                else:
                    operation['security'] = [{'developerApiKey': []}]
                operation.setdefault('responses', {})['401'] = {'$ref': '#/components/responses/Error401'}
                if operation['security'] == [{'developerApiKey': []}]:
                    operation['responses'].setdefault('403', {'$ref': '#/components/responses/Error403'})
                if '{' in path and method.upper() in {'GET', 'PATCH', 'DELETE'}:
                    operation['responses'].setdefault('404', {'$ref': '#/components/responses/Error404'})


def _normalize_app_client_security(schema: dict[str, Any]) -> None:
    components = schema.setdefault('components', {})
    security_schemes = components.setdefault('securitySchemes', {})
    security_schemes.clear()
    security_schemes['firebaseBearer'] = FIREBASE_BEARER_AUTH_SCHEME
    components.setdefault('schemas', {})['ErrorResponse'] = ERROR_RESPONSE_SCHEMA
    responses = components.setdefault('responses', {})
    for status_code, response in COMMON_RESPONSES.items():
        responses[f'Error{status_code}'] = {
            **response,
            'content': {
                'application/json': {
                    'schema': {'$ref': '#/components/schemas/ErrorResponse'},
                }
            },
        }
    schema.pop('security', None)

    for path, operations in schema.get('paths', {}).items():
        for method, operation in operations.items():
            if method.upper() in HTTP_METHODS:
                if path in APP_CLIENT_PUBLIC_PATHS:
                    operation['security'] = []
                else:
                    operation['security'] = [{'firebaseBearer': []}]
                    operation.setdefault('responses', {})['401'] = {'$ref': '#/components/responses/Error401'}
                if '{' in path and method.upper() in {'GET', 'PATCH', 'DELETE'}:
                    operation['responses'].setdefault('404', {'$ref': '#/components/responses/Error404'})


def _strip_authorization_header_params(operation: dict[str, Any]) -> None:
    """Drop raw Authorization header params in favor of securitySchemes.

    FastAPI emits optional header parameters for Authorization. Generators treat
    those as ordinary inputs and miss the bearer scheme. Prefer OpenAPI security.
    """
    params = operation.get('parameters')
    if not params:
        return
    filtered = [
        param
        for param in params
        if not (
            isinstance(param, dict)
            and param.get('in') == 'header'
            and str(param.get('name', '')).lower() == 'authorization'
        )
    ]
    if filtered:
        operation['parameters'] = filtered
    else:
        operation.pop('parameters', None)


def _normalize_integration_public_security(schema: dict[str, Any]) -> None:
    components = schema.setdefault('components', {})
    security_schemes = components.setdefault('securitySchemes', {})
    security_schemes.clear()
    security_schemes['integrationApiKey'] = INTEGRATION_API_KEY_AUTH_SCHEME
    components.setdefault('schemas', {})['ErrorResponse'] = ERROR_RESPONSE_SCHEMA
    responses = components.setdefault('responses', {})
    for status_code, response in COMMON_RESPONSES.items():
        responses[f'Error{status_code}'] = {
            **response,
            'content': {
                'application/json': {
                    'schema': {'$ref': '#/components/schemas/ErrorResponse'},
                }
            },
        }
    # Global default so generators wire bearer auth without per-op gymnastics.
    schema['security'] = [{'integrationApiKey': []}]

    for path, operations in schema.get('paths', {}).items():
        for method, operation in operations.items():
            if method.upper() in HTTP_METHODS:
                _strip_authorization_header_params(operation)
                operation['security'] = [{'integrationApiKey': []}]
                operation.setdefault('responses', {})['401'] = {'$ref': '#/components/responses/Error401'}
                operation['responses'].setdefault('403', {'$ref': '#/components/responses/Error403'})
                if '{' in path and method.upper() in {'GET', 'PATCH', 'DELETE'}:
                    operation['responses'].setdefault('404', {'$ref': '#/components/responses/Error404'})


def _rewrite_refs(value: Any, ref_map: dict[str, str]) -> None:
    if isinstance(value, dict):
        ref = value.get('$ref')
        if ref in ref_map:
            value['$ref'] = ref_map[ref]
        for child in value.values():
            _rewrite_refs(child, ref_map)
    elif isinstance(value, list):
        for child in value:
            _rewrite_refs(child, ref_map)


def _normalize_component_names(schema: dict[str, Any]) -> None:
    schemas = schema.get('components', {}).get('schemas', {})
    renamed: dict[str, Any] = {}
    ref_map: dict[str, str] = {}

    for name, component_schema in schemas.items():
        title = component_schema.get('title')
        new_name = title if isinstance(title, str) and title and title != name else name
        if (new_name in schemas and new_name != name) or new_name in renamed:
            new_name = name
        renamed[new_name] = component_schema
        if new_name != name:
            ref_map[f'#/components/schemas/{name}'] = f'#/components/schemas/{new_name}'

    if ref_map:
        schemas.clear()
        schemas.update(renamed)
        _rewrite_refs(schema, ref_map)


def build_openapi(app, surface: str) -> dict[str, Any]:
    if surface == 'public':
        routes = public_contract_routes(app)
        title = OPENAPI_TITLE
    elif surface == 'app-client':
        routes = app_client_contract_routes(app)
        title = APP_CLIENT_OPENAPI_TITLE
    elif surface == 'integration-public':
        routes = integration_public_contract_routes(app)
        title = INTEGRATION_PUBLIC_OPENAPI_TITLE
    else:
        raise OpenAPIContractError(f'unknown OpenAPI surface: {surface}')

    schema = get_openapi(
        title=title,
        version=OPENAPI_VERSION,
        description=OPENAPI_DESCRIPTION,
        routes=routes,
        tags=OPENAPI_TAGS,
        servers=OPENAPI_SERVERS,
        contact=OPENAPI_CONTACT,
        license_info=OPENAPI_LICENSE,
    )
    if surface == 'public':
        _normalize_bearer_security(schema)
    elif surface == 'app-client':
        _normalize_app_client_security(schema)
    elif surface == 'integration-public':
        _normalize_integration_public_security(schema)
    _normalize_component_names(schema)
    validate_contract(app, schema, surface)
    return schema


def build_public_openapi(app) -> dict[str, Any]:
    return build_openapi(app, 'public')


def assert_unique_operation_ids(schema: dict[str, Any]) -> None:
    operation_ids: dict[str, tuple[str, str]] = {}
    duplicates: list[str] = []
    missing: list[str] = []
    for path, operations in schema.get('paths', {}).items():
        for method, operation in operations.items():
            if method.upper() not in HTTP_METHODS:
                continue
            operation_id = operation.get('operationId')
            if not operation_id:
                missing.append(f'{method.upper()} {path}')
                continue
            if operation_id in operation_ids:
                previous_method, previous_path = operation_ids[operation_id]
                duplicates.append(f'{operation_id}: {previous_method} {previous_path} and {method.upper()} {path}')
            operation_ids[operation_id] = (method.upper(), path)
    if missing or duplicates:
        details = []
        if missing:
            details.append('missing operationId: ' + ', '.join(missing))
        if duplicates:
            details.append('duplicate operationId: ' + '; '.join(duplicates))
        raise OpenAPIContractError('\n'.join(details))


def assert_route_inventory(app, schema: dict[str, Any]) -> None:
    audited_routes = [
        route for route in app.routes if isinstance(route, APIRoute) and is_audited_public_path(route.path)
    ]
    expected = set(iter_route_keys(audited_routes))
    documented = set(documented_route_keys(schema))
    allowlisted = set(UNDOCUMENTED_PUBLIC_ROUTES)

    missing = sorted(expected - documented - allowlisted)
    extra = sorted(documented - expected)
    stale_allowlist = sorted(route for route in allowlisted if route not in set(iter_route_keys(app.routes)))

    if missing or extra or stale_allowlist:
        parts = []
        if missing:
            parts.append('public routes missing from OpenAPI: ' + ', '.join(f'{m} {p}' for m, p in missing))
        if extra:
            parts.append('OpenAPI routes not present in FastAPI app: ' + ', '.join(f'{m} {p}' for m, p in extra))
        if stale_allowlist:
            parts.append(
                'stale undocumented route allowlist entries: ' + ', '.join(f'{m} {p}' for m, p in stale_allowlist)
            )
        raise OpenAPIContractError('\n'.join(parts))


def validate_contract(app, schema: dict[str, Any], surface: str = 'public') -> None:
    if schema.get('openapi') != '3.1.0':
        raise OpenAPIContractError(f"expected OpenAPI 3.1.0, got {schema.get('openapi')!r}")
    assert_unique_operation_ids(schema)
    if surface == 'public':
        assert_route_inventory(app, schema)
        for path in schema.get('paths', {}):
            if not is_public_contract_path(path):
                raise OpenAPIContractError(f'non-public route leaked into public OpenAPI: {path}')
    elif surface == 'app-client':
        for path in schema.get('paths', {}):
            if not is_app_client_contract_path(path):
                raise OpenAPIContractError(f'non-app-client route leaked into app-client OpenAPI: {path}')
    elif surface == 'integration-public':
        documented = set(documented_route_keys(schema))
        expected = set(
            iter_route_keys(
                route
                for route in app.routes
                if isinstance(route, APIRoute) and is_integration_public_contract_path(route.path)
            )
        )
        missing = sorted(expected - documented)
        extra = sorted(documented - expected)
        if missing or extra:
            parts = []
            if missing:
                parts.append('integration routes missing from OpenAPI: ' + ', '.join(f'{m} {p}' for m, p in missing))
            if extra:
                parts.append(
                    'OpenAPI routes not present in integration surface: ' + ', '.join(f'{m} {p}' for m, p in extra)
                )
            raise OpenAPIContractError('\n'.join(parts))
        for path in schema.get('paths', {}):
            if not is_integration_public_contract_path(path):
                raise OpenAPIContractError(f'non-integration route leaked into integration OpenAPI: {path}')
    else:
        raise OpenAPIContractError(f'unknown OpenAPI surface: {surface}')


def stable_json(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def write_spec(path: Path, generated: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generated)


def check_spec(path: Path, generated: str) -> None:
    if not path.exists():
        raise OpenAPIContractError(f'{path} does not exist; run export_openapi.py --write {path}')
    current = path.read_text()
    if current != generated:
        raise OpenAPIContractError(f'{path} is stale; run backend/scripts/export_openapi.py --write {path}')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Export or verify an Omi OpenAPI contract.')
    parser.add_argument(
        '--surface',
        choices=('public', 'app-client', 'integration-public'),
        default='public',
        help='contract surface to export; defaults to public Developer API',
    )
    parser.add_argument(
        '--app-client',
        action='store_const',
        const='app-client',
        dest='surface',
        help='shortcut for --surface app-client',
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--write', nargs='?', const='', metavar='PATH', help='write generated spec')
    action.add_argument('--check', nargs='?', const='', metavar='PATH', help='check generated spec')
    action.add_argument('--print', action='store_true', help='print generated spec to stdout')
    return parser.parse_args()


def default_spec_path(surface: str) -> Path:
    if surface == 'public':
        return DEFAULT_SPEC_PATH
    if surface == 'app-client':
        return DEFAULT_APP_CLIENT_SPEC_PATH
    if surface == 'integration-public':
        return DEFAULT_INTEGRATION_PUBLIC_SPEC_PATH
    raise OpenAPIContractError(f'unknown OpenAPI surface: {surface}')


def resolve_spec_path(surface: str, raw_path: str) -> Path:
    if raw_path:
        return Path(raw_path)
    return default_spec_path(surface)


def main() -> int:
    args = parse_args()
    try:
        generated = stable_json(generate_openapi(args.surface))
        if args.print:
            sys.stdout.write(generated)
        elif args.write is not None:
            path = resolve_spec_path(args.surface, args.write)
            write_spec(path, generated)
            print(f'wrote {path}')
        elif args.check is not None:
            path = resolve_spec_path(args.surface, args.check)
            check_spec(path, generated)
            print(f'{path} is up to date')
        return 0
    except OpenAPIContractError as e:
        print(f'OpenAPI contract check failed: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
