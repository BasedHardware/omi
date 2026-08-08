import pytest

import database.desktop_previews as previews_db
from database.desktop_previews import (
    PREVIEW_MANIFESTS_COLLECTION,
    PREVIEW_POINTERS_COLLECTION,
    _build_preview_delisting,
    _build_preview_pointer,
    delist_preview,
    get_current_preview,
    get_preview_manifest,
    normalize_preview_manifest,
    preview_identity,
)
from tests.store_fakes import FakeDocumentStore

SLUG = "new-onboarding"
SOURCE_SHA = "a" * 40


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(previews_db, "_store", lambda: fake)
    return fake


def _manifest(**overrides):
    data = {
        "slug": SLUG,
        "source_sha": SOURCE_SHA,
        "dmg_url": f"https://storage.googleapis.com/omi_macos_updates/previews/{SLUG}/{SOURCE_SHA}/Omi-Preview.dmg",
        "dmg_sha256": "b" * 64,
        "app_name": "Omi Preview – new-onboarding",
        "bundle_id": f"com.omi.preview.{preview_identity(SLUG)}",
        "url_scheme": f"omi-preview-{preview_identity(SLUG)}",
        "built_at": "2026-07-15T12:00:00Z",
        "signer": "Developer ID Application: Omi, Inc.",
        "notarization": "stapled",
        "notes": "Try the redesigned onboarding.",
        "backend_url": "https://api.omi.me",
    }
    data.update(overrides)
    return data


def _pointer_path(slug=SLUG):
    return f"{PREVIEW_POINTERS_COLLECTION}/{slug}"


def _manifest_path(slug=SLUG, source_sha=SOURCE_SHA):
    return f"{PREVIEW_MANIFESTS_COLLECTION}/{slug}:{source_sha}"


class TestPreviewManifestNormalization:
    def test_slug_derives_a_stable_concurrent_preview_identity(self):
        assert preview_identity(SLUG) == "p04a26d265d"

    def test_accepts_complete_preview_manifest(self):
        manifest = normalize_preview_manifest(_manifest())

        assert manifest["slug"] == SLUG
        assert manifest["source_sha"] == SOURCE_SHA
        assert manifest["notarization"] == "stapled"

    @pytest.mark.parametrize("slug", ["../preview", "preview/foo", "UPPERCASE", "contains space", "-leading"])
    def test_rejects_non_path_safe_slug(self, slug):
        with pytest.raises(ValueError, match="slug"):
            normalize_preview_manifest(_manifest(slug=slug))

    def test_requires_exact_immutable_preview_artifact_url(self):
        with pytest.raises(ValueError, match="canonical immutable"):
            normalize_preview_manifest(
                _manifest(
                    dmg_url=f"https://storage.googleapis.com/omi_macos_updates/previews/{SLUG}/latest/Omi-Preview.dmg"
                )
            )

    def test_requires_preview_identity_and_stapling(self):
        with pytest.raises(ValueError, match="app_name"):
            normalize_preview_manifest(_manifest(app_name="Omi"))
        with pytest.raises(ValueError, match="bundle_id"):
            normalize_preview_manifest(_manifest(bundle_id="com.omi.computer-macos"))
        with pytest.raises(ValueError, match="url_scheme"):
            normalize_preview_manifest(_manifest(url_scheme="omi-preview-pwrong"))
        with pytest.raises(ValueError, match="notarization"):
            normalize_preview_manifest(_manifest(notarization="submitted"))


class TestPreviewPointers:
    def test_new_manifest_advances_only_its_slug_pointer(self):
        pointer = _build_preview_pointer({}, normalize_preview_manifest(_manifest()), expected_generation=0)

        assert pointer["slug"] == SLUG
        assert pointer["source_sha"] == SOURCE_SHA
        assert pointer["generation"] == 1

    def test_compare_and_set_rejects_stale_pointer_update(self):
        newer_sha = "c" * 40
        current = {"slug": SLUG, "source_sha": newer_sha, "generation": 4}

        with pytest.raises(ValueError, match="generation mismatch"):
            _build_preview_pointer(current, normalize_preview_manifest(_manifest()), expected_generation=3)

    def test_delisting_requires_the_current_generation_and_preserves_the_manifest(self):
        current = {"slug": SLUG, "source_sha": SOURCE_SHA, "generation": 4}

        result = _build_preview_delisting(current, slug=SLUG, expected_generation=4)

        assert result == {"slug": SLUG, "deleted": True, "generation": 4}
        assert current["source_sha"] == SOURCE_SHA
        with pytest.raises(ValueError, match="generation mismatch"):
            _build_preview_delisting(current, slug=SLUG, expected_generation=3)

    def test_delisting_transaction_deletes_only_the_pointer(self, store):
        store.set(_pointer_path(), {"slug": SLUG, "source_sha": SOURCE_SHA, "generation": 4})
        store.set(_manifest_path(), normalize_preview_manifest(_manifest()))

        result = delist_preview(SLUG, expected_generation=4)

        assert result == {"slug": SLUG, "deleted": True, "generation": 4}
        # Only the mutable pointer is removed; the immutable artifact is retained.
        assert _pointer_path() not in store._docs
        assert _manifest_path() in store._docs

    def test_delisting_an_absent_pointer_is_idempotent(self, store):
        result = delist_preview(SLUG, expected_generation=4)

        assert result == {"slug": SLUG, "deleted": False, "generation": None}


class TestPreviewLookup:
    def test_resolves_immutable_manifest_from_preview_only_collection(self, store):
        store.set(_manifest_path(), _manifest())

        result = get_preview_manifest(SLUG, SOURCE_SHA)

        assert result is not None
        assert result["dmg_url"].endswith("/Omi-Preview.dmg")

    def test_current_pointer_resolves_its_immutable_manifest(self, store):
        store.set(_pointer_path(), {"slug": SLUG, "source_sha": SOURCE_SHA, "generation": 2})
        store.set(_manifest_path(), _manifest())

        result = get_current_preview(SLUG)

        assert result is not None
        assert result["pointer"]["generation"] == 2
        assert result["manifest"]["source_sha"] == SOURCE_SHA
