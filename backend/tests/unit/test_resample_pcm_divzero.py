"""Unit test for resample_pcm zero/invalid source_rate guard (routers/transcribe.py).

resample_pcm computes `ratio = target_rate / source_rate`. With source_rate == 0
(an attacker-controlled WS query param), this raised ZeroDivisionError -> the WS
handler crashed. The guard makes resample_pcm a no-op for a non-positive rate,
returning the input bytes unchanged.

Red (without the fix): ZeroDivisionError.
Green (with the fix): returns the input bytes unchanged.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# transcribe.py is VERY heavy: stub every heavy top-level import package it pulls.
_STUB = (
    'database',
    'utils',
    'models',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'lc3',
    'av',
    'numpy',
    'audioop',  # removed from stdlib in py3.13; transcribe.py imports it at top level
    'pydub',
    'redis',
    'langchain',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'httpx',
    'typesense',
    'pusher',
    'fastapi',
    'starlette',
    'websockets',
)


def _is_stubbed(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        return importlib.machinery.ModuleSpec(name, self, is_package=True) if _is_stubbed(name) else None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_f = _Finder()
_saved = {n: m for n, m in sys.modules.items() if _is_stubbed(n)}
for n in list(sys.modules):
    if _is_stubbed(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from routers import transcribe as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)


def test_resample_pcm_zero_source_rate_returns_input_unchanged():
    """source_rate == 0 must be a no-op (no ZeroDivisionError)."""
    pcm = b'\x00\x00\x00\x00'  # 4 zero bytes == 2 silent int16 samples
    result = mod.resample_pcm(pcm, 0, 16000)
    assert result == pcm


def test_resample_pcm_negative_target_rate_returns_input_unchanged():
    """target_rate <= 0 must also be a no-op."""
    pcm = b'\x01\x00\x02\x00'
    result = mod.resample_pcm(pcm, 16000, -1)
    assert result == pcm


def test_resample_pcm_equal_rates_still_passthrough():
    """Sanity: the pre-existing equal-rate fast path is unaffected."""
    pcm = b'\x05\x00\x06\x00'
    assert mod.resample_pcm(pcm, 16000, 16000) == pcm
