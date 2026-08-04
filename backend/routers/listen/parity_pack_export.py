"""Fail-open durable export of dev-only parity-pack cassettes to GCS.

Local emptyDir capture remains the source of truth inside the pod. This module
best-effort mirrors `cassettes/*.json` to a private development bucket so
operators can download packs for offline replay after the pod is gone.

Export never raises into the listen path. GCS outages only log + optional
fallback telemetry.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from .parity_telemetry import record_parity_capture_event

logger = logging.getLogger(__name__)

_DEFAULT_EXPORT_INTERVAL_SECONDS = 3600
_reconcile_lock = threading.Lock()
_reconcile_started = False


def _parse_gcs_uri(uri: str) -> tuple[str, str] | None:
    value = (uri or "").strip()
    if not value:
        return None
    if value.startswith("gs://"):
        parsed = urlparse(value)
        bucket = parsed.netloc.strip()
        prefix = parsed.path.lstrip("/")
        if not bucket:
            return None
        return bucket, prefix.rstrip("/")
    return None


def resolve_export_target(environ: Mapping[str, str] | None = None) -> tuple[str, str] | None:
    """Return (bucket, object_prefix) when durable export is configured."""
    env = os.environ if environ is None else environ
    uri = (env.get("OMI_PARITY_PACK_GCS_URI") or "").strip()
    parsed = _parse_gcs_uri(uri)
    if parsed is not None:
        return parsed
    bucket = (env.get("OMI_PARITY_PACK_GCS_BUCKET") or "").strip()
    if not bucket:
        return None
    prefix = (env.get("OMI_PARITY_PACK_GCS_PREFIX") or "parity-pack/v0").strip().strip("/")
    return bucket, prefix


def _object_name(prefix: str, local_path: Path, root: Path) -> str:
    try:
        rel = local_path.resolve().relative_to(root.resolve())
    except ValueError:
        rel = Path("cassettes") / local_path.name
    rel_s = rel.as_posix().lstrip("/")
    if not prefix:
        return rel_s
    return f"{prefix.rstrip('/')}/{rel_s}"


_client = None
_client_lock = threading.Lock()


def _storage_client():
    """Lazy GCS client using the same credential sources as backend storage."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        from google.cloud import storage
        from google.oauth2 import service_account
        import json

        if os.environ.get("SERVICE_ACCOUNT_JSON"):
            info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
            credentials = service_account.Credentials.from_service_account_info(info)
            _client = storage.Client(credentials=credentials)
        else:
            project = (os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("FIREBASE_PROJECT_ID") or "").strip()
            _client = storage.Client(project=project) if project else storage.Client()
        return _client


def _record_export_failure(*, reason: str) -> None:
    try:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component="other",
            from_mode="parity_pack_gcs_export",
            to_mode="local_only",
            reason="other" if reason not in {"auth", "timeout", "other"} else reason,
            outcome="degraded",
        )
    except Exception:
        # Telemetry must never block listen.
        pass


def export_cassette_file(local_path: Path, *, environ: Mapping[str, str] | None = None) -> bool:
    """Upload one local cassette JSON. Returns True on success. Fail-open."""
    env = os.environ if environ is None else environ
    target = resolve_export_target(env)
    if target is None:
        record_parity_capture_event('export', 'skipped', 'target_unconfigured', environ=env)
        return False
    root_value = (env.get("OMI_PARITY_PACK_ROOT") or "").strip()
    if not root_value:
        record_parity_capture_event('export', 'skipped', 'root_unconfigured', environ=env)
        return False
    root = Path(root_value)
    path = Path(local_path)
    if not path.is_file():
        record_parity_capture_event('export', 'failed', 'local_file_missing', environ=env)
        return False
    bucket_name, prefix = target
    object_name = _object_name(prefix, path, root)
    record_parity_capture_event('export', 'attempted', 'configured', environ=env)
    try:
        client = _storage_client()
        blob = client.bucket(bucket_name).blob(object_name)
        blob.upload_from_filename(str(path), content_type="application/json")
        record_parity_capture_event('export', 'succeeded', 'none', environ=env)
        return True
    except Exception:
        logger.warning("Parity pack cassette export failed reason_class=upload_error")
        record_parity_capture_event('export', 'failed', 'upload_error', environ=env)
        _record_export_failure(reason="other")
        return False


def reconcile_local_cassettes(*, environ: Mapping[str, str] | None = None) -> int:
    """Best-effort upload of every local cassette under ROOT/cassettes."""
    env = os.environ if environ is None else environ
    if resolve_export_target(env) is None:
        return 0
    root_value = (env.get("OMI_PARITY_PACK_ROOT") or "").strip()
    if not root_value:
        return 0
    cassettes = Path(root_value) / "cassettes"
    if not cassettes.is_dir():
        return 0
    uploaded = 0
    for path in sorted(cassettes.glob("*.json")):
        if export_cassette_file(path, environ=env):
            uploaded += 1
    return uploaded


def _export_interval_seconds(environ: Mapping[str, str]) -> int:
    raw = (environ.get("OMI_PARITY_PACK_EXPORT_INTERVAL_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_EXPORT_INTERVAL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_EXPORT_INTERVAL_SECONDS
    return max(60, value)


def ensure_reconcile_loop(*, environ: Mapping[str, str] | None = None) -> None:
    """Start a single daemon thread that periodically re-exports local cassettes."""
    global _reconcile_started
    env = dict(os.environ if environ is None else environ)
    if resolve_export_target(env) is None:
        return
    with _reconcile_lock:
        if _reconcile_started:
            return
        _reconcile_started = True

    interval = _export_interval_seconds(env)

    def _loop() -> None:
        while True:
            try:
                time.sleep(interval)
                reconcile_local_cassettes(environ=env)
            except Exception as error:
                logger.warning(
                    "Parity pack cassette reconcile loop error error_type=%s",
                    type(error).__name__,
                )

    thread = threading.Thread(
        target=_loop,
        name="omi-parity-pack-export-reconcile",
        daemon=True,
    )
    thread.start()
