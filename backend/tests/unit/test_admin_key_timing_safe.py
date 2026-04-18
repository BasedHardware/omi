"""Verify the new require_admin_key dependency uses constant-time comparison
and refuses to authorize when ADMIN_KEY is unconfigured (empty-match bug).
"""

from __future__ import annotations

import os
import time
from unittest import mock

import pytest
from fastapi import HTTPException

from utils.other import endpoints


def test_refuses_when_admin_key_unset():
    """Previous per-router pattern `if secret != os.getenv('ADMIN_KEY')` would
    pass when BOTH were empty strings. require_admin_key returns 503 instead.
    """
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop('ADMIN_KEY', None)
        with pytest.raises(HTTPException) as ei:
            endpoints.require_admin_key(secret_key='')
        assert ei.value.status_code == 503


def test_rejects_empty_secret_with_configured_key():
    with mock.patch.dict(os.environ, {'ADMIN_KEY': 'real'}, clear=False):
        with pytest.raises(HTTPException) as ei:
            endpoints.require_admin_key(secret_key='')
        assert ei.value.status_code == 403


def test_rejects_wrong_secret():
    with mock.patch.dict(os.environ, {'ADMIN_KEY': 'real'}, clear=False):
        with pytest.raises(HTTPException) as ei:
            endpoints.require_admin_key(secret_key='wrong')
        assert ei.value.status_code == 403


def test_accepts_correct_secret():
    with mock.patch.dict(os.environ, {'ADMIN_KEY': 'real'}, clear=False):
        # Should not raise
        endpoints.require_admin_key(secret_key='real')


def test_timing_comparison_similar_duration():
    """Smoke-test the constant-time property: comparison time with a
    matching-prefix wrong key should be indistinguishable from a fully-
    mismatched key. Not a strict timing oracle test — just a smoke check
    that hmac.compare_digest is being used (early-exit on '!=' would
    produce ~10x runtime differences on long strings).
    """
    secret = 'a' * 1000
    matching_prefix = 'a' * 999 + 'b'  # differs only at last char
    fully_wrong = 'z' * 1000

    with mock.patch.dict(os.environ, {'ADMIN_KEY': secret}, clear=False):
        # Warm up
        for _ in range(100):
            try:
                endpoints.require_admin_key(secret_key=matching_prefix)
            except HTTPException:
                pass

        t1 = time.perf_counter()
        for _ in range(10_000):
            try:
                endpoints.require_admin_key(secret_key=matching_prefix)
            except HTTPException:
                pass
        matching_time = time.perf_counter() - t1

        t2 = time.perf_counter()
        for _ in range(10_000):
            try:
                endpoints.require_admin_key(secret_key=fully_wrong)
            except HTTPException:
                pass
        wrong_time = time.perf_counter() - t2

        # With constant-time compare, ratio should be close to 1.0.
        # A string-`!=` compare would show ~100x difference on 1000-char
        # inputs. Allow generous slack for CPU jitter in CI.
        ratio = matching_time / wrong_time
        assert 0.3 < ratio < 3.0, f"timing ratio {ratio:.2f} suggests short-circuit compare"
