"""Offline, allowlisted runtime settings rendered by the selected product tree."""

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ALLOWLIST = ('FSR_*', 'FIRESTORE_READ_*', '*_PERCENT', '*_TTL_SECONDS', '*_ENABLED')
# A broad rollout prefix must never admit a connection/identity/credential setting.
PROTECTED = re.compile(
    r'(^|_)(SECRET|SECRETS|TOKEN|PASSWORD|CREDENTIALS?|AUTH|API_KEY|PRIVATE_KEY|PROJECT|PROJECT_ID|'
    r'ENDPOINT|URL|URI|HOST|HOSTNAME|PORT|EMULATOR|SOCKET|BUCKET|DATABASE|PATH|FILE|KEY|SERVICE_ACCOUNT|IDENTITY|ADDRESS|CONNECTION|DSN)(_|$)'
)
SENSITIVE_CATEGORIES = {
    'secret',
    'secrets',
    'credential',
    'credentials',
    'service_auth',
    'auth',
    'identity',
    'runtime_identity',
    'service_discovery',
}


@dataclass(frozen=True)
class RuntimeEnv:
    service: str
    env: str
    values: dict[str, str] = field(repr=False)
    dropped_count: int

    def report(self):
        return dict(
            service=self.service, env=self.env, applied_keys=sorted(self.values), dropped_count=self.dropped_count
        )

    def apply(self, settings):
        # Equal bindings preserve the hermetic setting; any differing binding refuses.
        if any(name in settings and settings[name] != value for name, value in self.values.items()):
            raise ValueError('runtime env conflicts with hermetic replay settings')
        settings.update(self.values)


def allowed(name):
    return bool(
        re.fullmatch(r'[A-Z][A-Z0-9_]*', name)
        and any(fnmatchcase(name, pattern) for pattern in ALLOWLIST)
        and not PROTECTED.search(name)
    )


def literal_entry(entry):
    return (
        isinstance(entry, dict)
        and set(entry) <= {'value', 'category', 'name', 'provisional'}
        and str(entry.get('category', '')).lower() not in SENSITIVE_CATEGORIES
        and 'secret' not in str(entry.get('category', '')).lower()
        and type(entry.get('value')) in (str, int, float, bool)
    )


def select_entries(service, env, entries):
    """Entries use Cloud Run's descriptor shape; never resolve any indirect source."""
    values, dropped = {}, 0
    for name, entry in entries:
        if not allowed(name) or not literal_entry(entry):
            dropped += 1
            continue
        if name in values:
            raise ValueError('duplicate runtime env key')
        values[name] = str(entry['value'])
    return RuntimeEnv(service, env, values, dropped)


def indirect_chart_names(paths):
    """Conservative deny union, not a values merge; Helm owns final values.

    Templates can discard secret/category metadata while emitting a literal.
    Preserve those denials from every input, including privateEnv replacements.
    """
    import yaml

    names = set()
    for path in paths:
        if path.is_file():
            values = yaml.safe_load(path.read_text()) or {}
            names.update(values.get('privateEnv') or {})
            names.update(entry['name'] for entry in values.get('env', []) if not literal_entry(entry))
    return names


def parse_selector(selector):
    parts = selector.split(':')
    if (
        len(parts) > 2
        or not re.fullmatch(r'[a-z][a-z0-9-]*', parts[0])
        or (len(parts) == 2 and parts[1] not in ('prod', 'dev'))
    ):
        raise ValueError('runtime env requires service[:prod|dev]')
    return parts[0], parts[1] if len(parts) == 2 else 'prod'


def load_runtime_env(selector, *, backend=None):
    if selector is None:
        return None
    service, env = parse_selector(selector)
    backend = backend or Path(__file__).resolve().parents[2]
    # Rendering runs in a separate, credential-free process. Its imports and
    # composition defaults belong entirely to this side's archived product tree.
    result = subprocess.run(
        [sys.executable, '-I', str(Path(__file__).resolve()), str(backend), service, env],
        env={name: os.environ[name] for name in ('PATH', 'TMPDIR', 'SYSTEMROOT') if name in os.environ},
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise ValueError('runtime env render failed (unknown service or invalid configuration)')
    payload = json.loads(result.stdout)
    return RuntimeEnv(service, env, payload['values'], payload['dropped_count'])


def render(backend, service, env):
    sys.path.insert(0, str(backend))
    from deploy.compose_runtime_env import compose_environment

    config = compose_environment(env)
    services = config.get('cloud_run', {}).get('services', {})
    if service in services:
        selected = services[service]
        # Secret bindings win even if a malformed config also declares a
        # literal with the same name. Never fall back to that literal.
        entries = {**selected.get('env', {}), **{name: {'secret': True} for name in selected.get('secrets', {})}}
        return select_entries(service, env, entries.items())

    # Reuse the drift checker's exact Helm invocation, workload registry and
    # container selection. Helm owns all values/template merge semantics.
    from scripts import check_cloud_run_env_drift as drift
    import yaml

    if service not in drift.GKE_WORKLOADS:
        raise ValueError('unknown runtime env service')
    rendered = []

    def capture(*args, **kwargs):
        result = subprocess.run(*args, **kwargs)
        rendered.extend(yaml.safe_load_all(result.stdout))
        return result

    drift.expected_gke_env_from_helm(service, env=env, root=backend.parent, runner=capture)
    spec = drift.GKE_WORKLOADS[service]
    deployment = next(
        doc
        for doc in rendered
        if isinstance(doc, dict)
        and doc.get('kind') == 'Deployment'
        and doc.get('metadata', {}).get('name') == spec.deployment.format(env=env)
    )
    container = drift._application_container(
        deployment['spec']['template']['spec']['containers'], scope='replay runtime env', name=spec.container
    )
    indirect = indirect_chart_names(
        (backend.parent / spec.chart / 'values.yaml', backend.parent / spec.values_file.format(env=env))
    )
    entries = [
        (entry['name'], {'secret': True} if entry['name'] in indirect else entry) for entry in container.get('env', [])
    ]
    # envFrom is indirect and unresolved offline; count each dropped source.
    entries.extend(('', {}) for _ in container.get('envFrom', []))
    return select_entries(service, env, entries)


if __name__ == '__main__':
    try:
        runtime = render(Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3])
        print(json.dumps(dict(values=runtime.values, dropped_count=runtime.dropped_count)))
    except Exception:
        # Neither composition errors nor Helm stderr may disclose rejected values.
        sys.exit(2)
