"""GCS client construction, plus the filesystem storage adapter used only by the owned local dev harness."""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import quote

from google.cloud import storage
from google.cloud.exceptions import NotFound
from google.oauth2 import service_account

LOCAL_STORAGE_ROOT_ENV = 'OMI_LOCAL_STORAGE_ROOT'
LOCAL_STORAGE_BASE_URL_ENV = 'OMI_LOCAL_STORAGE_BASE_URL'
HARNESS_STATE_ROOT_ENV = 'OMI_HARNESS_STATE_ROOT'


def _contained_path(root: Path, value: str, *, label: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    if candidate == root or root not in candidate.parents:
        raise RuntimeError(f'{label} must be a child of {root}')
    return candidate


def local_storage_root_from_env() -> Path | None:
    """Return the validated harness storage root, or ``None`` when disabled."""

    raw_root = os.environ.get(LOCAL_STORAGE_ROOT_ENV, '').strip()
    if not raw_root:
        return None

    raw_state_root = os.environ.get(HARNESS_STATE_ROOT_ENV, '').strip()
    if not raw_state_root:
        raise RuntimeError(f'{LOCAL_STORAGE_ROOT_ENV} requires {HARNESS_STATE_ROOT_ENV}')

    project_id = (os.environ.get('FIREBASE_PROJECT_ID') or '').strip()
    if not project_id.startswith('demo-') or not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        raise RuntimeError(f'{LOCAL_STORAGE_ROOT_ENV} is allowed only with the owned local emulator harness')

    state_root = Path(raw_state_root).expanduser().resolve()
    return _contained_path(state_root, raw_root, label=LOCAL_STORAGE_ROOT_ENV)


def _safe_relative_path(value: str, *, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {'', '.', '..'} for part in path.parts):
        raise ValueError(f'Unsafe local storage {label}: {value!r}')
    return path


class LocalBlob:
    def __init__(self, bucket: 'LocalBucket', name: str):
        self.bucket = bucket
        self.name = _safe_relative_path(name, label='blob name').as_posix()
        self.metadata = None
        self.cache_control = None
        self.content_type = None

    @property
    def path(self) -> Path:
        return self.bucket.path.joinpath(*PurePosixPath(self.name).parts)

    @property
    def size(self) -> int | None:
        return self.path.stat().st_size if self.path.is_file() else None

    @property
    def public_url(self) -> str:
        return self.generate_signed_url()

    def exists(self, *_args, **_kwargs) -> bool:
        return self.path.is_file()

    def reload(self, *_args, **_kwargs) -> None:
        if not self.exists():
            raise NotFound(f'Local storage blob not found: {self.bucket.name}/{self.name}')

    def upload_from_filename(self, filename: str, *_args, **_kwargs) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(filename, self.path)

    def download_to_filename(self, filename: str, *_args, **_kwargs) -> None:
        if not self.exists():
            raise NotFound(f'Local storage blob not found: {self.bucket.name}/{self.name}')
        destination = Path(filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path, destination)

    def upload_from_string(self, data: bytes | str, content_type: str | None = None, *_args, **_kwargs) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.content_type = content_type
        self.path.write_bytes(data.encode() if isinstance(data, str) else data)

    def download_as_bytes(self, *_args, **_kwargs) -> bytes:
        if not self.exists():
            raise NotFound(f'Local storage blob not found: {self.bucket.name}/{self.name}')
        return self.path.read_bytes()

    def delete(self, *_args, **_kwargs) -> None:
        if not self.exists():
            raise NotFound(f'Local storage blob not found: {self.bucket.name}/{self.name}')
        self.path.unlink()

    def open(self, mode: str = 'rb', *_args, **_kwargs):
        if mode not in {'rb', 'wb'}:
            raise ValueError(f'Unsupported local storage blob mode: {mode}')
        if 'w' in mode:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.exists():
            raise NotFound(f'Local storage blob not found: {self.bucket.name}/{self.name}')
        return self.path.open(mode)

    def generate_signed_url(self, *_args, **_kwargs) -> str:
        base_url = os.environ.get(LOCAL_STORAGE_BASE_URL_ENV, '').strip().rstrip('/')
        if not base_url:
            raise RuntimeError(f'{LOCAL_STORAGE_BASE_URL_ENV} is required for local storage URLs')
        bucket = quote(self.bucket.name, safe='')
        name = quote(self.name, safe='/')
        return f'{base_url}/{bucket}/{name}'

    def make_public(self, *_args, **_kwargs) -> None:
        return None

    def patch(self, *_args, **_kwargs) -> None:
        return None


class LocalBucket:
    def __init__(self, root: Path, name: str):
        self.root = root
        self.name = _safe_relative_path(name, label='bucket name').as_posix()
        if '/' in self.name:
            raise ValueError(f'Unsafe local storage bucket name: {name!r}')
        self.path.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self.root / self.name

    def blob(self, name: str) -> LocalBlob:
        return LocalBlob(self, name)

    def list_blobs(self, prefix: str = '', *_args, **_kwargs) -> Iterable[LocalBlob]:
        if prefix:
            _safe_relative_path(prefix.rstrip('/'), label='blob prefix')
        if not self.path.exists():
            return []
        return [
            LocalBlob(self, path.relative_to(self.path).as_posix())
            for path in sorted(self.path.rglob('*'))
            if path.is_file() and path.relative_to(self.path).as_posix().startswith(prefix)
        ]

    def copy_blob(self, blob: LocalBlob, destination_bucket: 'LocalBucket', new_name: str) -> LocalBlob:
        destination = destination_bucket.blob(new_name)
        destination.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(blob.path, destination.path)
        return destination


class LocalStorageClient:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> 'LocalStorageClient | None':
        root = local_storage_root_from_env()
        return cls(root) if root is not None else None

    def bucket(self, name: str) -> LocalBucket:
        return LocalBucket(self.root, name)

    def get_bucket(self, name: str) -> LocalBucket:
        return self.bucket(name)


def storage_client_project() -> str:
    """Project for a keyless GCS client: the customer-data pin, then the host project."""
    return (
        os.environ.get('OMI_CUSTOMER_DATA_PROJECT')
        or os.environ.get('GOOGLE_CLOUD_PROJECT')
        or os.environ.get('FIREBASE_PROJECT_ID')
        or ''
    ).strip()


def create_storage_client():
    local_client = LocalStorageClient.from_env()
    if local_client is not None:
        return local_client
    if os.environ.get('SERVICE_ACCOUNT_JSON'):
        service_account_info = json.loads(os.environ['SERVICE_ACCOUNT_JSON'])
        credentials = service_account.Credentials.from_service_account_info(service_account_info)  # type: ignore[reportUnknownMemberType]  # google.oauth2 partial stubs
        return storage.Client(credentials=credentials)
    project = storage_client_project()
    return storage.Client(project=project) if project else storage.Client()


_signing_token_lock = threading.Lock()

# IAM ``signBlob`` accepts only a token carrying the cloud-platform (or iam)
# scope. The storage client's own credentials are scoped to the devstorage
# scopes, and the Cloud Run metadata server honours that request, so reusing
# the client's token fails with ACCESS_TOKEN_SCOPE_INSUFFICIENT (measured on
# Cloud Run 2026-09-24; every keyless signed URL failed). Signing therefore uses
# a cloud-platform-scoped copy of the same identity.
_IAM_SIGNING_SCOPES = ('https://www.googleapis.com/auth/cloud-platform',)
_signing_credentials_by_source: dict[int, tuple[Any, Any]] = {}


def _iam_signing_credentials(credentials: Any) -> Any:
    """The same identity as ``credentials`` with a scope IAM ``signBlob`` accepts."""
    from google.auth import credentials as google_auth_credentials

    if not isinstance(credentials, google_auth_credentials.Scoped):
        return credentials
    cached = _signing_credentials_by_source.get(id(credentials))
    if cached is not None and cached[0] is credentials:
        return cached[1]
    scoped = credentials.with_scopes(list(_IAM_SIGNING_SCOPES))
    _signing_credentials_by_source[id(credentials)] = (credentials, scoped)
    return scoped


def iam_signing_kwargs(client: Any) -> dict[str, str]:
    """Signer arguments that let ``Blob.generate_signed_url`` work on a keyless identity.

    A JSON key signs V4 URLs locally. An attached Cloud Run service account or a
    GKE Workload Identity holds only an access token, and ``generate_signed_url``
    raises unless it is handed ``service_account_email`` + ``access_token``, in
    which case it signs through IAM ``signBlob`` (the identity needs
    ``iam.serviceAccounts.signBlob`` on itself, and the token needs the
    cloud-platform scope, which the storage client's own token lacks). Returns
    ``{}`` whenever the credentials can already sign, or are not real Google
    credentials (local harness, test fakes), so the key path and fakes are
    unchanged.
    """
    credentials = getattr(client, '_credentials', None)
    from google.auth import credentials as google_auth_credentials

    if not isinstance(credentials, google_auth_credentials.Credentials):
        return {}
    if isinstance(credentials, google_auth_credentials.Signing):
        return {}
    from google.auth.transport import requests as google_auth_requests

    with _signing_token_lock:
        signing_credentials = _iam_signing_credentials(credentials)
        if not signing_credentials.valid:
            signing_credentials.refresh(google_auth_requests.Request())
        token = signing_credentials.token
    email = getattr(signing_credentials, 'service_account_email', None)
    if not token or not isinstance(email, str) or '@' not in email:
        return {}
    return {'service_account_email': email, 'access_token': token}


def local_public_url(bucket_name: str | None, blob_name: str) -> str | None:
    if not bucket_name:
        return None
    client = LocalStorageClient.from_env()
    return client.bucket(bucket_name).blob(blob_name).public_url if client is not None else None
