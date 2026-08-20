import json
import os
import tempfile
from pathlib import Path

RUNTIME_GOOGLE_CREDENTIALS_PATH = Path('/tmp/omi-google-credentials.json')


def prepare_google_credentials() -> None:
    service_account_json = os.environ.get('SERVICE_ACCOUNT_JSON', '').strip()
    if service_account_json:
        _write_credentials_file(service_account_json)
        return

    credentials = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '').strip()
    if not credentials:
        return

    if credentials.startswith('{'):
        _write_credentials_file(credentials)
        return

    credentials_path = Path(credentials)
    if not credentials_path.exists():
        raise RuntimeError(f'GOOGLE_APPLICATION_CREDENTIALS points to missing file: {credentials_path}')


def _write_credentials_file(raw_credentials: str) -> None:
    try:
        service_account_info = json.loads(raw_credentials)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Google service account credentials are not valid JSON') from exc

    fchmod = getattr(os, 'fchmod', None)
    if not callable(fchmod):
        raise RuntimeError('Google service account credentials require owner-only file permissions')

    RUNTIME_GOOGLE_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        dir=RUNTIME_GOOGLE_CREDENTIALS_PATH.parent,
        prefix=f'.{RUNTIME_GOOGLE_CREDENTIALS_PATH.name}.',
        text=True,
    )
    try:
        fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            fd = -1
            json.dump(service_account_info, handle)
        os.replace(temp_path, RUNTIME_GOOGLE_CREDENTIALS_PATH)
    except Exception:
        if fd >= 0:
            os.close(fd)
        Path(temp_path).unlink(missing_ok=True)
        raise
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(RUNTIME_GOOGLE_CREDENTIALS_PATH)
