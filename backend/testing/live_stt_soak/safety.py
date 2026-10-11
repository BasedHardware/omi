"""Fail closed before importing the listen runtime or opening a client socket."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from urllib.parse import urlsplit

DEV_CONTEXT = 'gke_based-hardware-dev_us-central1_dev-omi-gke'
PROJECT = 'demo-omi-stt-soak'
NAMESPACE = 'dev-stt-soak'
FORBIDDEN = (
    'SERVICE_ACCOUNT_JSON',
    'GOOGLE_APPLICATION_CREDENTIALS',
    'FIREBASE_AUTH_CREDENTIALS_PATH',
    'OMI_CUSTOMER_DATA_PROJECT',
    'OMI_FIRESTORE_DATA_PLANE_PROJECT',
    'REDIS_DB_PASSWORD',
)


def validate_environment(env: Mapping[str, str]) -> None:
    required = {
        'OMI_STT_SOAK_ISOLATED': '1',
        'OMI_HARNESS_INSTANCE': 'live-stt-soak',
        'FIRESTORE_EMULATOR_HOST': '127.0.0.1:8085',
        'REDIS_DB_HOST': '127.0.0.1',
        'REDIS_DB_PORT': '6379',
        'GOOGLE_CLOUD_PROJECT': PROJECT,
        'FIREBASE_PROJECT_ID': PROJECT,
        'OMI_JIT_QA_LOCAL_STACK': '1',
    }
    if any(env.get(key) != value for key, value in required.items()) or any(env.get(key) for key in FORBIDDEN):
        raise ValueError('soak requires local emulators, demo project, no customer credentials and no shared Redis')
    if env.get('OMI_STT_SOAK_MODE') not in ('fake', 'paid'):
        raise ValueError('soak mode must be fake or paid')


def validate_target(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('only an explicit loopback port-forward to the isolated dev workload is accepted')
    if not parsed.port or parsed.path not in ('', '/'):
        raise ValueError('target must be http://127.0.0.1:PORT')


def session_uid(index: int) -> str:
    # E2E fresh_uid convention: UUIDs, seeded only in the private emulator.
    # Ordinary release probes use utils.release_probe.RELEASE_PROBE_UID; its
    # single UID cannot support simultaneous sockets under the listen lock.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'omi-live-stt-soak/{index}'))
