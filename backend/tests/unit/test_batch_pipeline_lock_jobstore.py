"""The batch-pipeline-worker image can import the job-store Postgres driver.

The A2 shadow seam (``diarizer.batch_pipeline_runtime`` -> ``database.batch_pipeline_shadow_hook`` /
``database.jobstore``) reaches ``psycopg`` through function-local imports. The image's build-time
dependency probe (``runtime_image_contracts.py smoke``) walks that closure, so a lock without the
driver fails the image build, and a worker started with ``BATCH_JOBSTORE_MODE=shadow`` refuses
(``driver_missing``). PR CI does not build this image, so pin the lock contract here.
"""

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_DIR / 'scripts' / 'runtime_image_contracts.py'
BATCH_REQUIREMENTS = BACKEND_DIR / 'diarizer' / 'requirements-batch-pipeline.txt'
BATCH_LOCK = BACKEND_DIR / 'diarizer' / 'pylock.batch-pipeline.toml'


def _requirement_pin(text: str, package: str) -> str:
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if line.startswith(package) and '==' in line:
            return line
    raise AssertionError(f'{package} pin missing from requirements')


@pytest.fixture(scope='module')
def batch_worker_dependency_modules() -> tuple[str, ...]:
    """Walked once per file (an AST closure walk over the worker's source tree)."""
    spec = importlib.util.spec_from_file_location('runtime_image_contracts_for_jobstore_lock', SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    contract = next(c for c in module.load_contracts() if c.name == 'batch-pipeline-worker')
    assert contract.dependency_probe_smoke
    return module.third_party_dependency_modules(contract)


def test_batch_worker_image_closure_reaches_the_postgres_driver(batch_worker_dependency_modules):
    modules = batch_worker_dependency_modules
    assert 'psycopg' in modules
    assert 'google.auth.transport.requests' in modules  # Cloud SQL IAM token for the shadow connection


def test_batch_pipeline_lock_carries_the_backend_psycopg_pin():
    backend_pin = _requirement_pin((BACKEND_DIR / 'requirements.txt').read_text(encoding='utf-8'), 'psycopg[binary]')
    assert _requirement_pin(BATCH_REQUIREMENTS.read_text(encoding='utf-8'), 'psycopg[binary]') == backend_pin
    version = backend_pin.split('==', 1)[1]
    packages = {p['name']: p['version'] for p in tomllib.loads(BATCH_LOCK.read_text(encoding='utf-8'))['packages']}
    # psycopg-binary ships libpq inside the wheel; the slim image has no system libpq.
    assert packages.get('psycopg') == version
    assert packages.get('psycopg-binary') == version
    for distribution in ('google-auth', 'requests'):
        assert distribution in packages
