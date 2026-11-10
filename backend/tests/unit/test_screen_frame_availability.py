"""Storage and signing infrastructure must exist before frame adjudication."""

import pytest

from utils.screen_frames.availability import screen_frame_storage_ready


@pytest.fixture
def provisioned(monkeypatch):
    monkeypatch.setenv("BUCKET_SCREEN_FRAMES", "screen-frames")
    monkeypatch.setenv("SCREEN_FRAME_SIGNING_SECRET", "secret")
    monkeypatch.delenv("SCREEN_FRAME_KMS_KEY", raising=False)


def test_ready_when_bucket_and_signer_are_provisioned(provisioned):
    assert screen_frame_storage_ready() is True


def test_kms_key_satisfies_the_signer_requirement(provisioned, monkeypatch):
    monkeypatch.delenv("SCREEN_FRAME_SIGNING_SECRET", raising=False)
    monkeypatch.setenv("SCREEN_FRAME_KMS_KEY", "projects/p/locations/l/keyRings/r/cryptoKeys/k")
    assert screen_frame_storage_ready() is True


def test_disabled_when_bucket_missing(provisioned, monkeypatch):
    monkeypatch.delenv("BUCKET_SCREEN_FRAMES", raising=False)
    assert screen_frame_storage_ready() is False


def test_disabled_when_bucket_is_blank(provisioned, monkeypatch):
    monkeypatch.setenv("BUCKET_SCREEN_FRAMES", "   ")
    assert screen_frame_storage_ready() is False


def test_disabled_when_no_signer_configured(provisioned, monkeypatch):
    monkeypatch.delenv("SCREEN_FRAME_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("SCREEN_FRAME_KMS_KEY", raising=False)
    assert screen_frame_storage_ready() is False
