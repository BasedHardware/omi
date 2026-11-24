"""Refuse ambient cloud authority before constructing any simulator client."""

from collections.abc import Mapping
import ipaddress
import os
from pathlib import Path


class HermeticRefusal(RuntimeError):
    """The simulator cannot establish local-only authority."""


def preflight(isolated_root: Path, *, environ: Mapping[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    root = isolated_root.resolve()
    if not env.get('GOOGLE_CLOUD_PROJECT', '').startswith('demo-'):
        raise HermeticRefusal('a demo-* project is required')
    endpoint = env.get('FIRESTORE_EMULATOR_HOST', '')
    try:
        host, port = endpoint.rsplit(':', 1)
        host = host.removeprefix('[').removesuffix(']')
        if host != 'localhost' and not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        if not 1 <= int(port) <= 65535:
            raise ValueError
    except ValueError:
        raise HermeticRefusal('a loopback Firestore emulator is required') from None
    for key in ('GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON', 'FIREBASE_AUTH_CREDENTIALS_PATH'):
        if env.get(key):
            raise HermeticRefusal('ambient credentials are forbidden')
    for key, value in env.items():
        if not key.startswith('CLOUDSDK_'):
            continue
        if key != 'CLOUDSDK_CONFIG' or not value or not Path(value).resolve().is_relative_to(root):
            raise HermeticRefusal('ambient Cloud SDK configuration is forbidden')
    for key in ('GCLOUD_PROJECT', 'FIREBASE_PROJECT_ID', 'CLOUD_ML_PROJECT_ID'):
        if env.get(key) and not env[key].startswith('demo-'):
            raise HermeticRefusal('ambient cloud project is forbidden')
    home = Path(env.get('HOME', str(Path.home())))
    config = Path(env.get('XDG_CONFIG_HOME', str(home / '.config')))
    candidates = {
        home / '.config/gcloud/application_default_credentials.json',
        config / 'gcloud/application_default_credentials.json',
    }
    if env.get('CLOUDSDK_CONFIG'):
        candidates.add(Path(env['CLOUDSDK_CONFIG']) / 'application_default_credentials.json')
    if any(path.exists() for path in candidates):
        raise HermeticRefusal('reachable application default credentials are forbidden')
