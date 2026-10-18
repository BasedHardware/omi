import pytest
import os
from fastapi import HTTPException
from plugins.iq_rating.iq_auth import verify_iq_auth


def test_fail_closed_when_secret_unset(monkeypatch):
    monkeypatch.delenv("IQ_RATING_SECRET", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        verify_iq_auth(authorization="Bearer test")
    assert exc_info.value.status_code == 503


def test_missing_token_raises_401(monkeypatch):
    monkeypatch.setenv("IQ_RATING_SECRET", "supersecret123")
    with pytest.raises(HTTPException) as exc_info:
        verify_iq_auth(authorization=None, iq_rating_token=None)
    assert exc_info.value.status_code == 401


def test_invalid_token_raises_401(monkeypatch):
    monkeypatch.setenv("IQ_RATING_SECRET", "supersecret123")
    with pytest.raises(HTTPException) as exc_info:
        verify_iq_auth(authorization="Bearer wrongtoken")
    assert exc_info.value.status_code == 401


def test_valid_bearer_token(monkeypatch):
    monkeypatch.setenv("IQ_RATING_SECRET", "supersecret123")
    assert verify_iq_auth(authorization="Bearer supersecret123") is True


def test_valid_query_param_token(monkeypatch):
    monkeypatch.setenv("IQ_RATING_SECRET", "supersecret123")
    assert verify_iq_auth(iq_rating_token="supersecret123") is True
