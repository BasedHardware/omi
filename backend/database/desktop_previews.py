"""Immutable registry for externally installable desktop preview builds.

Preview records intentionally do not share the stable/beta manifest or channel
collections. A preview is identified by its safe branch-derived slug and the
exact source commit SHA that produced the immutable artifact.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any, cast
from urllib.parse import urlparse

from google.cloud.firestore import transactional

from database._client import get_firestore_client

PREVIEW_MANIFESTS_COLLECTION = "desktop_preview_manifests"
PREVIEW_POINTERS_COLLECTION = "desktop_preview_pointers"
PREVIEW_BUCKET_HOST = "storage.googleapis.com"
PREVIEW_BUCKET_NAME = "omi_macos_updates"

PREVIEW_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
BUNDLE_ID_RE = re.compile(r"^com\.omi\.preview\.[a-z0-9-]{1,63}$")
URL_SCHEME_RE = re.compile(r"^omi-preview-[a-z0-9-]{1,63}$")
MAX_NOTES_LENGTH = 2_000


def _required_string(data: dict[str, Any], key: str, *, max_length: int = 512) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{key} is too long")
    return normalized


def _optional_string(data: dict[str, Any], key: str, *, max_length: int = 512) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{key} is too long")
    return normalized or None


def _slug(value: str) -> str:
    if not PREVIEW_SLUG_RE.fullmatch(value):
        raise ValueError("slug must use lowercase letters, digits, and path-safe hyphens")
    return value


def _source_sha(value: str) -> str:
    if not SHA40_RE.fullmatch(value):
        raise ValueError("source_sha must be a full 40-character commit SHA")
    return value.lower()


def _sha256(value: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise ValueError("dmg_sha256 must be a SHA-256 digest")
    return value.lower()


def _timestamp(data: dict[str, Any], key: str) -> str:
    value = _required_string(data, key, max_length=64)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO-8601 timestamp") from exc
    return value


def _https_url(data: dict[str, Any], key: str, *, required: bool) -> str | None:
    value = _required_string(data, key, max_length=2_048) if required else _optional_string(data, key, max_length=2_048)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{key} must be an https URL")
    return value


def _preview_dmg_url(data: dict[str, Any], *, slug: str, source_sha: str) -> str:
    value = _https_url(data, "dmg_url", required=True)
    assert value is not None
    parsed = urlparse(value)
    expected_path = f"/{PREVIEW_BUCKET_NAME}/previews/{slug}/{source_sha}/Omi-Preview.dmg"
    if (
        parsed.netloc != PREVIEW_BUCKET_HOST
        or parsed.path != expected_path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("dmg_url must be the canonical immutable preview artifact URL")
    return value


def _manifest_id(slug: str, source_sha: str) -> str:
    return f"{slug}:{source_sha}"


def preview_identity(slug: str) -> str:
    """Derive the stable app identity that lets each preview branch coexist."""
    return f"p{hashlib.sha256(slug.encode('utf-8')).hexdigest()[:10]}"


def _generation(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("pointer generation must be a non-negative integer")


def normalize_preview_manifest(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and narrow a preview's immutable artifact metadata."""
    slug = _slug(_required_string(data, "slug", max_length=63))
    source_sha = _source_sha(_required_string(data, "source_sha", max_length=40))
    app_name = _required_string(data, "app_name", max_length=128)
    if not app_name.startswith("Omi Preview"):
        raise ValueError("app_name must identify this as an Omi Preview build")
    bundle_id = _required_string(data, "bundle_id", max_length=96)
    preview_id = preview_identity(slug)
    if not BUNDLE_ID_RE.fullmatch(bundle_id) or bundle_id != f"com.omi.preview.{preview_id}":
        raise ValueError("bundle_id must match the slug-derived com.omi.preview.<id> identity")
    url_scheme = _required_string(data, "url_scheme", max_length=96)
    if not URL_SCHEME_RE.fullmatch(url_scheme) or url_scheme != f"omi-preview-{preview_id}":
        raise ValueError("url_scheme must match the slug-derived omi-preview-<id> identity")

    notarization = _required_string(data, "notarization", max_length=32).lower()
    if notarization != "stapled":
        raise ValueError("notarization must be stapled")

    return {
        "slug": slug,
        "source_sha": source_sha,
        "dmg_url": _preview_dmg_url(data, slug=slug, source_sha=source_sha),
        "dmg_sha256": _sha256(_required_string(data, "dmg_sha256", max_length=64)),
        "app_name": app_name,
        "bundle_id": bundle_id,
        "url_scheme": url_scheme,
        "built_at": _timestamp(data, "built_at"),
        "signer": _required_string(data, "signer", max_length=512),
        "notarization": notarization,
        "notes": _optional_string(data, "notes", max_length=MAX_NOTES_LENGTH),
        "backend_url": _https_url(data, "backend_url", required=False),
    }


def _build_preview_pointer(
    current: dict[str, Any],
    manifest: dict[str, Any],
    *,
    expected_generation: int | None,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    current_generation = _generation(current.get("generation", 0))
    if expected_generation is not None and expected_generation != current_generation:
        raise ValueError(f"generation mismatch: expected {expected_generation}, current {current_generation}")
    if current.get("source_sha") == manifest["source_sha"]:
        return current
    return {
        "slug": manifest["slug"],
        "source_sha": manifest["source_sha"],
        "generation": current_generation + 1,
        "updated_at": updated_at or datetime.now(timezone.utc),
    }


def _build_preview_delisting(current: dict[str, Any], *, slug: str, expected_generation: int) -> dict[str, Any]:
    """Validate a compare-and-delete request for one mutable preview pointer."""
    source_sha = current.get("source_sha")
    if current.get("slug") != slug or not isinstance(source_sha, str):
        raise ValueError("preview pointer is malformed")
    _source_sha(source_sha)
    current_generation = _generation(current.get("generation", 0))
    if expected_generation != current_generation:
        raise ValueError(f"generation mismatch: expected {expected_generation}, current {current_generation}")
    return {"slug": slug, "deleted": True, "generation": current_generation}


@transactional
def _publish_preview_transaction(
    transaction: Any,
    manifest_ref: Any,
    pointer_ref: Any,
    *,
    manifest: dict[str, Any],
    expected_generation: int | None,
) -> dict[str, Any]:
    manifest_snapshot = manifest_ref.get(transaction=transaction)
    if getattr(manifest_snapshot, "exists", False):
        raw_existing: object = manifest_snapshot.to_dict()
        existing_data = cast(dict[str, Any], raw_existing) if isinstance(raw_existing, dict) else {}
        existing = normalize_preview_manifest(existing_data)
        if existing != manifest:
            raise ValueError("preview artifact already exists with different immutable metadata")
    else:
        transaction.create(manifest_ref, {**manifest, "created_at": datetime.now(timezone.utc)})

    pointer_snapshot = pointer_ref.get(transaction=transaction)
    raw_current: object = pointer_snapshot.to_dict() if getattr(pointer_snapshot, "exists", False) else {}
    current = cast(dict[str, Any], raw_current) if isinstance(raw_current, dict) else {}
    pointer = _build_preview_pointer(current, manifest, expected_generation=expected_generation)
    if pointer is not current:
        transaction.set(pointer_ref, pointer)
    return {"manifest": manifest, "pointer": pointer}


def publish_preview(
    data: dict[str, Any],
    *,
    expected_generation: int | None = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Atomically register an immutable preview and advance only its slug pointer."""
    if expected_generation is not None and (isinstance(expected_generation, bool) or expected_generation < 0):
        raise ValueError("expected_generation must be a non-negative integer")
    manifest = normalize_preview_manifest(data)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    manifest_ref = client.collection(PREVIEW_MANIFESTS_COLLECTION).document(
        _manifest_id(manifest["slug"], manifest["source_sha"])
    )
    pointer_ref = client.collection(PREVIEW_POINTERS_COLLECTION).document(manifest["slug"])
    transaction = client.transaction()
    return _publish_preview_transaction(
        transaction,
        manifest_ref,
        pointer_ref,
        manifest=manifest,
        expected_generation=expected_generation,
    )


@transactional
def _delist_preview_transaction(
    transaction: Any,
    pointer_ref: Any,
    *,
    slug: str,
    expected_generation: int,
) -> dict[str, Any]:
    pointer_snapshot = pointer_ref.get(transaction=transaction)
    if not getattr(pointer_snapshot, "exists", False):
        return {"slug": slug, "deleted": False, "generation": None}
    raw_current: object = pointer_snapshot.to_dict()
    current = cast(dict[str, Any], raw_current) if isinstance(raw_current, dict) else {}
    result = _build_preview_delisting(current, slug=slug, expected_generation=expected_generation)
    transaction.delete(pointer_ref)
    return result


def delist_preview(
    slug: str,
    *,
    expected_generation: int,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Atomically delist one mutable preview pointer, retaining immutable artifacts."""
    normalized_slug = _slug(slug.strip())
    if isinstance(expected_generation, bool) or expected_generation < 0:
        raise ValueError("expected_generation must be a non-negative integer")
    client = firestore_client if firestore_client is not None else get_firestore_client()
    pointer_ref = client.collection(PREVIEW_POINTERS_COLLECTION).document(normalized_slug)
    transaction = client.transaction()
    return _delist_preview_transaction(
        transaction,
        pointer_ref,
        slug=normalized_slug,
        expected_generation=expected_generation,
    )


def _get_manifest(slug: str, source_sha: str, *, firestore_client: Any) -> dict[str, Any] | None:
    snapshot = firestore_client.collection(PREVIEW_MANIFESTS_COLLECTION).document(_manifest_id(slug, source_sha)).get()
    if not getattr(snapshot, "exists", False):
        return None
    raw_manifest: object = snapshot.to_dict()
    manifest_data = cast(dict[str, Any], raw_manifest) if isinstance(raw_manifest, dict) else {}
    manifest = normalize_preview_manifest(manifest_data)
    if manifest["slug"] != slug or manifest["source_sha"] != source_sha:
        raise ValueError("preview manifest identity does not match its registry key")
    return manifest


def get_preview_manifest(slug: str, source_sha: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """Resolve one immutable preview artifact by its slug and full source SHA."""
    normalized_slug = _slug(slug.strip())
    normalized_sha = _source_sha(source_sha.strip())
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _get_manifest(normalized_slug, normalized_sha, firestore_client=client)


def get_current_preview(slug: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """Resolve a slug's current pointer and its immutable preview artifact."""
    normalized_slug = _slug(slug.strip())
    client = firestore_client if firestore_client is not None else get_firestore_client()
    pointer_snapshot = client.collection(PREVIEW_POINTERS_COLLECTION).document(normalized_slug).get()
    if not getattr(pointer_snapshot, "exists", False):
        return None
    raw_pointer: object = pointer_snapshot.to_dict()
    pointer_data = cast(dict[str, Any], raw_pointer) if isinstance(raw_pointer, dict) else {}
    source_sha_raw = pointer_data.get("source_sha")
    if pointer_data.get("slug") != normalized_slug or not isinstance(source_sha_raw, str):
        raise ValueError("preview pointer is malformed")
    source_sha = _source_sha(source_sha_raw)
    manifest = _get_manifest(normalized_slug, source_sha, firestore_client=client)
    if manifest is None:
        raise ValueError("preview pointer references a missing manifest")
    return {
        "pointer": {
            "slug": normalized_slug,
            "source_sha": source_sha,
            "generation": _generation(pointer_data.get("generation", 0)),
            "updated_at": pointer_data.get("updated_at"),
        },
        "manifest": manifest,
    }
