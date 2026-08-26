"""The egress gate is three independent conditions; each one alone must fail closed."""

import pytest

from utils.screen_frames.availability import screen_frame_egress_enabled


@pytest.fixture
def provisioned(monkeypatch):
    monkeypatch.setenv("SCREEN_FRAME_EGRESS_ENABLED", "true")
    monkeypatch.setenv("BUCKET_SCREEN_FRAMES", "screen-frames")
    monkeypatch.setenv("SCREEN_FRAME_SIGNING_SECRET", "secret")
    monkeypatch.delenv("SCREEN_FRAME_KMS_KEY", raising=False)


def test_enabled_when_fully_provisioned(provisioned):
    assert screen_frame_egress_enabled() is True


def test_kms_key_satisfies_the_signer_requirement(provisioned, monkeypatch):
    monkeypatch.delenv("SCREEN_FRAME_SIGNING_SECRET", raising=False)
    monkeypatch.setenv("SCREEN_FRAME_KMS_KEY", "projects/p/locations/l/keyRings/r/cryptoKeys/k")
    assert screen_frame_egress_enabled() is True


def test_disabled_when_flag_absent(provisioned, monkeypatch):
    monkeypatch.delenv("SCREEN_FRAME_EGRESS_ENABLED", raising=False)
    assert screen_frame_egress_enabled() is False


@pytest.mark.parametrize("value", ["false", "1", "yes", "on", "", "  "])
def test_truthy_lookalikes_do_not_enable_it(provisioned, monkeypatch, value):
    """ "1"/"yes"/"on" read as on to a human but are not this flag's vocabulary. A
    privacy-relevant egress path should not switch on because someone reached for a
    different truthiness convention."""
    monkeypatch.setenv("SCREEN_FRAME_EGRESS_ENABLED", value)
    assert screen_frame_egress_enabled() is False


@pytest.mark.parametrize("value", ["true", "True", "TRUE", " true "])
def test_the_word_true_enables_it_however_it_is_cased(provisioned, monkeypatch, value):
    """The opposite footgun matters too: a flag that stays silently off because the
    operator wrote "True" costs an hour of debugging and teaches nothing."""
    monkeypatch.setenv("SCREEN_FRAME_EGRESS_ENABLED", value)
    assert screen_frame_egress_enabled() is True


def test_disabled_when_bucket_missing(provisioned, monkeypatch):
    monkeypatch.delenv("BUCKET_SCREEN_FRAMES", raising=False)
    assert screen_frame_egress_enabled() is False


def test_disabled_when_bucket_is_blank(provisioned, monkeypatch):
    monkeypatch.setenv("BUCKET_SCREEN_FRAMES", "   ")
    assert screen_frame_egress_enabled() is False


def test_disabled_when_no_signer_configured(provisioned, monkeypatch):
    monkeypatch.delenv("SCREEN_FRAME_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("SCREEN_FRAME_KMS_KEY", raising=False)
    assert screen_frame_egress_enabled() is False
