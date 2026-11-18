"""Where the lab's local peers live. Defaults follow ``make dev-up`` (scripts/dev-harness).

Every value comes from an environment variable so private paths and ports never
enter Git. Only loopback hosts are accepted for the local peers; approved STT
endpoints (DESIGN L9) are the only non-loopback names and must be listed
explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from testing.pipeline_lab.stack import LAB_UID

LOOPBACK = frozenset({'127.0.0.1', 'localhost', '::1'})

# Shared with lane core (llm_proxy/). Named here so both lanes read one variable.
LLM_PROXY_URL_ENV = 'OMI_PIPELINE_LAB_LLM_PROXY_URL'
LAB_ROOT_ENV = 'OMI_PIPELINE_LAB_ROOT'
DEFAULT_LAB_ROOT = '/Volumes/Ephemeral/pipeline-lab'
STT_ALLOWLIST_ENV = 'OMI_PIPELINE_LAB_STT_ENDPOINTS'


# Same local bucket names as dev-up (scripts/dev-harness/dev_harness/config.py).
LOCAL_STORAGE_BUCKET_ENV = {
    'BUCKET_SPEECH_PROFILES': 'speech-profiles',
    'BUCKET_POSTPROCESSING': 'postprocessing',
    'BUCKET_PRIVATE_CLOUD_SYNC': 'omi-private-cloud-sync',
    'BUCKET_TEMPORAL_SYNC_LOCAL': 'sync-temporal',
    'BUCKET_MEMORIES_RECORDINGS': 'memories-recordings',
    'BUCKET_PLUGINS_LOGOS': 'plugins-logos',
    'BUCKET_APP_THUMBNAILS': 'app-thumbnails',
    'BUCKET_CHAT_FILES': 'chat-files',
    'BUCKET_DESKTOP_UPDATES': 'desktop-updates',
    'BUCKET_SCREEN_FRAMES': 'screen-frames',
}


class StackConfigError(ValueError):
    """A configured peer is not a permitted local endpoint."""


def _host_port(value: str, *, name: str) -> tuple[str, int]:
    host, sep, port = value.strip().rpartition(':')
    host = host.strip('[]')
    if not sep or not port.isdigit() or not 0 < int(port) < 65536:
        raise StackConfigError(f'{name} must be host:port')
    if host not in LOOPBACK:
        raise StackConfigError(f'{name} must be a loopback address')
    return host, int(port)


def _url_host_port(url: str, *, name: str) -> tuple[str, int]:
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise StackConfigError(f'{name} must be an http(s) URL')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    if parts.hostname not in LOOPBACK:
        raise StackConfigError(f'{name} must be a loopback URL')
    return parts.hostname, port


def _stt_endpoints(raw: str) -> tuple[tuple[str, int], ...]:
    endpoints = []
    for item in raw.split(','):
        item = item.strip()
        if not item:
            continue
        host, sep, port = item.rpartition(':')
        if not sep or not port.isdigit() or not host or '/' in host:
            raise StackConfigError(f'{STT_ALLOWLIST_ENV} entries must be host:port')
        endpoints.append((host.lower(), int(port)))
    return tuple(endpoints)


@dataclass(frozen=True)
class LabStackConfig:
    firestore: tuple[str, int] = ('127.0.0.1', 8085)
    auth: tuple[str, int] = ('127.0.0.1', 9099)
    redis: tuple[str, int] = ('127.0.0.1', 6380)
    typesense: tuple[str, int] = ('127.0.0.1', 8108)
    typesense_api_key: str = 'local-typesense-api-key-not-real'
    project_id: str = 'demo-omi-local'
    llm_proxy_url: str = 'http://127.0.0.1:9180'
    lab_root: Path = Path(DEFAULT_LAB_ROOT)
    uid: str = LAB_UID
    stt_endpoints: tuple[tuple[str, int], ...] = ()
    extra_loopback_ports: tuple[int, ...] = field(default=())

    @property
    def storage_root(self) -> Path:
        return self.lab_root / 'stack' / 'storage'

    @property
    def firestore_host(self) -> str:
        return f'{self.firestore[0]}:{self.firestore[1]}'

    @property
    def auth_host(self) -> str:
        return f'{self.auth[0]}:{self.auth[1]}'

    def loopback_ports(self) -> frozenset[int]:
        """Every local peer the lab may reach (DESIGN L9)."""
        proxy = _url_host_port(self.llm_proxy_url, name=LLM_PROXY_URL_ENV)
        return frozenset(
            {self.firestore[1], self.auth[1], self.redis[1], self.typesense[1], proxy[1], *self.extra_loopback_ports}
        )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> 'LabStackConfig':
        env = os.environ if environ is None else environ
        defaults = cls()

        def pick(name: str, fallback: tuple[str, int]) -> tuple[str, int]:
            raw = env.get(name, '').strip()
            return _host_port(raw, name=name) if raw else fallback

        proxy_url = env.get(LLM_PROXY_URL_ENV, '').strip() or defaults.llm_proxy_url
        _url_host_port(proxy_url, name=LLM_PROXY_URL_ENV)
        redis_host = env.get('OMI_PIPELINE_LAB_REDIS', '').strip()
        typesense = env.get('OMI_PIPELINE_LAB_TYPESENSE', '').strip()
        return cls(
            firestore=pick('FIRESTORE_EMULATOR_HOST', defaults.firestore),
            auth=pick('FIREBASE_AUTH_EMULATOR_HOST', defaults.auth),
            redis=_host_port(redis_host, name='OMI_PIPELINE_LAB_REDIS') if redis_host else defaults.redis,
            typesense=_host_port(typesense, name='OMI_PIPELINE_LAB_TYPESENSE') if typesense else defaults.typesense,
            typesense_api_key=env.get('OMI_PIPELINE_LAB_TYPESENSE_API_KEY', '') or defaults.typesense_api_key,
            project_id=env.get('OMI_PIPELINE_LAB_PROJECT_ID', '') or defaults.project_id,
            llm_proxy_url=proxy_url,
            lab_root=Path(env.get(LAB_ROOT_ENV, '') or DEFAULT_LAB_ROOT).expanduser(),
            stt_endpoints=_stt_endpoints(env.get(STT_ALLOWLIST_ENV, '')),
        )

    def product_env(self) -> dict[str, str]:
        """Process env the product reads, mirroring dev-up's ``_harness_service_extra``.

        Feature env (modes, flags) is not here; it comes from the run overlay.
        """
        if not self.project_id.startswith('demo-'):
            # Firebase only treats demo-* projects as emulator-only; refuse anything else.
            raise StackConfigError('lab project id must be a demo-* emulator project')
        return {
            'FIRESTORE_EMULATOR_HOST': self.firestore_host,
            'FIREBASE_AUTH_EMULATOR_HOST': self.auth_host,
            'FIREBASE_AUTH_PROJECT_ID': self.project_id,
            'FIREBASE_PROJECT_ID': self.project_id,
            'GOOGLE_CLOUD_PROJECT': self.project_id,
            'REDIS_DB_HOST': self.redis[0],
            'REDIS_DB_PORT': str(self.redis[1]),
            'REDIS_DB_PASSWORD': '',
            'TYPESENSE_HOST': self.typesense[0],
            'TYPESENSE_HOST_PORT': str(self.typesense[1]),
            'TYPESENSE_API_KEY': self.typesense_api_key,
            'TYPESENSE_PROTOCOL': 'http',
            'OMI_LOCAL_STORAGE_ROOT': str(self.storage_root),
            'OMI_ENV_STAGE': 'local',
            'ENVIRONMENT': 'pipeline-lab',
            # Same dev-only secret family as dev-up; never a production key.
            'ENCRYPTION_SECRET': 'omi_pipeline_lab_32_byte_local_secret_not_prod',  # pragma: allowlist secret
            'OMI_LLM_GATEWAY_URL': self.llm_proxy_url,
            'OMI_LLM_GATEWAY_FEATURE_MODE': 'gateway',
            'OMI_LLM_GATEWAY_SERVICE_TOKEN': 'pipeline-lab-local-token-not-real',  # pragma: allowlist secret
            # Provider keys are placeholders: every LLM call must go through the proxy.
            'OPENAI_API_KEY': 'pipeline-lab-placeholder-not-a-key',  # pragma: allowlist secret
            # Analytics drop at the source (product_telemetry reads these at call time).
            'POSTHOG_PRODUCT_CAPTURE_TOKEN': '',
            'POSTHOG_PROJECT_API_KEY': '',
            'POSTHOG_BILLING_API_KEY': '',
            'POSTHOG_EVENTS_API_KEY': '',
            'POSTHOG_HOST': 'http://127.0.0.1:9',
            'PINECONE_API_KEY': '',
            'PINECONE_INDEX_NAME': 'pipeline-lab-local',
            **LOCAL_STORAGE_BUCKET_ENV,
        }
