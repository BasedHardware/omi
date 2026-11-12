#!/usr/bin/env python3
"""Cause-chain composition grid for the contention classifier walk.

Every cell freezes one verdict of the persist boundary loss lanes over one
inventoried fault shape. Expected values are literals cross-verified at emit
time against an independent transcription of the lane doctrine; a failing
cell means the boundary verdict drifted from the documented family contract.

Failure-Class: FC-persist-contention-exhaustion-discards-completed-gpu-results
"""

import socket
import types

import google.api_core.exceptions as gax
from database.firestore_transaction_retry import FirestoreContentionExhausted
from google.api_core.exceptions import Aborted, InvalidArgument
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.source_audio import InvalidRetainedManifest, RetainedAudioInvalid
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from diarizer import batch_pipeline as bp


def _chain(outer, cause):
    outer.__cause__ = cause
    return outer


def _expired():
    return InvalidArgument('400 ' + _EXPIRED_MARKER.capitalize() + '.')


def _bver(value):
    return BatchValidationError(ValidationReason(value))


def _carrier(stamp):
    ns = types.SimpleNamespace(args=('carrier',))
    ns.retry_after = stamp
    return ns


def _stamperr(stamp):
    err = RuntimeError('carrier')
    err.retry_after = stamp
    return err


_EXPIRED_MARKER = 'the referenced transaction has expired or is no longer valid'
_SHAPE_BUILDERS = {
    'chain3_aborted_aborted_aborted': lambda: _chain(
        _chain(Aborted('conflict'), Aborted('conflict')), Aborted('conflict')
    ),
    'chain3_aborted_aborted_expired': lambda: _chain(_chain(Aborted('conflict'), Aborted('conflict')), _expired()),
    'chain3_aborted_aborted_invalid': lambda: _chain(
        _chain(Aborted('conflict'), Aborted('conflict')), InvalidArgument('transport')
    ),
    'chain3_aborted_aborted_timeout': lambda: _chain(
        _chain(Aborted('conflict'), Aborted('conflict')), TimeoutError('deadline')
    ),
    'chain3_aborted_aborted_value': lambda: _chain(
        _chain(Aborted('conflict'), Aborted('conflict')), ValueError('custody')
    ),
    'chain3_aborted_aborted_wrapper': lambda: _chain(
        _chain(Aborted('conflict'), Aborted('conflict')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_aborted_aborted_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_aborted_aborted_wrapper_expired': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_aborted_aborted_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_aborted_aborted_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_aborted_aborted_wrapper_value': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_aborted_expired_aborted': lambda: _chain(_chain(Aborted('conflict'), _expired()), Aborted('conflict')),
    'chain3_aborted_expired_expired': lambda: _chain(_chain(Aborted('conflict'), _expired()), _expired()),
    'chain3_aborted_expired_invalid': lambda: _chain(
        _chain(Aborted('conflict'), _expired()), InvalidArgument('transport')
    ),
    'chain3_aborted_expired_timeout': lambda: _chain(_chain(Aborted('conflict'), _expired()), TimeoutError('deadline')),
    'chain3_aborted_expired_value': lambda: _chain(_chain(Aborted('conflict'), _expired()), ValueError('custody')),
    'chain3_aborted_expired_wrapper': lambda: _chain(
        _chain(Aborted('conflict'), _expired()),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_aborted_expired_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_aborted_expired_wrapper_expired': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_aborted_expired_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_aborted_expired_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_aborted_expired_wrapper_value': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_aborted_invalid_aborted': lambda: _chain(
        _chain(Aborted('conflict'), InvalidArgument('transport')), Aborted('conflict')
    ),
    'chain3_aborted_invalid_expired': lambda: _chain(
        _chain(Aborted('conflict'), InvalidArgument('transport')), _expired()
    ),
    'chain3_aborted_invalid_invalid': lambda: _chain(
        _chain(Aborted('conflict'), InvalidArgument('transport')), InvalidArgument('transport')
    ),
    'chain3_aborted_invalid_timeout': lambda: _chain(
        _chain(Aborted('conflict'), InvalidArgument('transport')), TimeoutError('deadline')
    ),
    'chain3_aborted_invalid_value': lambda: _chain(
        _chain(Aborted('conflict'), InvalidArgument('transport')), ValueError('custody')
    ),
    'chain3_aborted_invalid_wrapper': lambda: _chain(
        _chain(Aborted('conflict'), InvalidArgument('transport')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_aborted_invalid_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_aborted_invalid_wrapper_expired': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_aborted_invalid_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_aborted_invalid_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_aborted_invalid_wrapper_value': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_aborted_timeout_aborted': lambda: _chain(
        _chain(Aborted('conflict'), TimeoutError('deadline')), Aborted('conflict')
    ),
    'chain3_aborted_timeout_expired': lambda: _chain(_chain(Aborted('conflict'), TimeoutError('deadline')), _expired()),
    'chain3_aborted_timeout_invalid': lambda: _chain(
        _chain(Aborted('conflict'), TimeoutError('deadline')), InvalidArgument('transport')
    ),
    'chain3_aborted_timeout_timeout': lambda: _chain(
        _chain(Aborted('conflict'), TimeoutError('deadline')), TimeoutError('deadline')
    ),
    'chain3_aborted_timeout_value': lambda: _chain(
        _chain(Aborted('conflict'), TimeoutError('deadline')), ValueError('custody')
    ),
    'chain3_aborted_timeout_wrapper': lambda: _chain(
        _chain(Aborted('conflict'), TimeoutError('deadline')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_aborted_timeout_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_aborted_timeout_wrapper_expired': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_aborted_timeout_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_aborted_timeout_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_aborted_timeout_wrapper_value': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_aborted_value_aborted': lambda: _chain(
        _chain(Aborted('conflict'), ValueError('custody')), Aborted('conflict')
    ),
    'chain3_aborted_value_expired': lambda: _chain(_chain(Aborted('conflict'), ValueError('custody')), _expired()),
    'chain3_aborted_value_invalid': lambda: _chain(
        _chain(Aborted('conflict'), ValueError('custody')), InvalidArgument('transport')
    ),
    'chain3_aborted_value_timeout': lambda: _chain(
        _chain(Aborted('conflict'), ValueError('custody')), TimeoutError('deadline')
    ),
    'chain3_aborted_value_value': lambda: _chain(
        _chain(Aborted('conflict'), ValueError('custody')), ValueError('custody')
    ),
    'chain3_aborted_value_wrapper': lambda: _chain(
        _chain(Aborted('conflict'), ValueError('custody')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_aborted_value_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_aborted_value_wrapper_expired': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_aborted_value_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_aborted_value_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_aborted_value_wrapper_value': lambda: _chain(
        _chain(
            _chain(Aborted('conflict'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_aborted_wrapper_aborted': lambda: _chain(
        _chain(
            Aborted('conflict'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        Aborted('conflict'),
    ),
    'chain3_aborted_wrapper_expired': lambda: _chain(
        _chain(
            Aborted('conflict'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        _expired(),
    ),
    'chain3_aborted_wrapper_invalid': lambda: _chain(
        _chain(
            Aborted('conflict'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        InvalidArgument('transport'),
    ),
    'chain3_aborted_wrapper_timeout': lambda: _chain(
        _chain(
            Aborted('conflict'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        TimeoutError('deadline'),
    ),
    'chain3_aborted_wrapper_value': lambda: _chain(
        _chain(
            Aborted('conflict'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        ValueError('custody'),
    ),
    'chain3_aborted_wrapper_wrapper': lambda: _chain(
        _chain(
            Aborted('conflict'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_expired_aborted_aborted': lambda: _chain(_chain(_expired(), Aborted('conflict')), Aborted('conflict')),
    'chain3_expired_aborted_expired': lambda: _chain(_chain(_expired(), Aborted('conflict')), _expired()),
    'chain3_expired_aborted_invalid': lambda: _chain(
        _chain(_expired(), Aborted('conflict')), InvalidArgument('transport')
    ),
    'chain3_expired_aborted_timeout': lambda: _chain(_chain(_expired(), Aborted('conflict')), TimeoutError('deadline')),
    'chain3_expired_aborted_value': lambda: _chain(_chain(_expired(), Aborted('conflict')), ValueError('custody')),
    'chain3_expired_aborted_wrapper': lambda: _chain(
        _chain(_expired(), Aborted('conflict')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_expired_aborted_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(_expired(), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_expired_aborted_wrapper_expired': lambda: _chain(
        _chain(
            _chain(_expired(), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_expired_aborted_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(_expired(), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_expired_aborted_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(_expired(), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_expired_aborted_wrapper_value': lambda: _chain(
        _chain(
            _chain(_expired(), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_expired_expired_aborted': lambda: _chain(_chain(_expired(), _expired()), Aborted('conflict')),
    'chain3_expired_expired_expired': lambda: _chain(_chain(_expired(), _expired()), _expired()),
    'chain3_expired_expired_invalid': lambda: _chain(_chain(_expired(), _expired()), InvalidArgument('transport')),
    'chain3_expired_expired_timeout': lambda: _chain(_chain(_expired(), _expired()), TimeoutError('deadline')),
    'chain3_expired_expired_value': lambda: _chain(_chain(_expired(), _expired()), ValueError('custody')),
    'chain3_expired_expired_wrapper': lambda: _chain(
        _chain(_expired(), _expired()),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_expired_expired_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(_expired(), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_expired_expired_wrapper_expired': lambda: _chain(
        _chain(
            _chain(_expired(), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_expired_expired_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(_expired(), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_expired_expired_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(_expired(), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_expired_expired_wrapper_value': lambda: _chain(
        _chain(
            _chain(_expired(), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_expired_invalid_aborted': lambda: _chain(
        _chain(_expired(), InvalidArgument('transport')), Aborted('conflict')
    ),
    'chain3_expired_invalid_expired': lambda: _chain(_chain(_expired(), InvalidArgument('transport')), _expired()),
    'chain3_expired_invalid_invalid': lambda: _chain(
        _chain(_expired(), InvalidArgument('transport')), InvalidArgument('transport')
    ),
    'chain3_expired_invalid_timeout': lambda: _chain(
        _chain(_expired(), InvalidArgument('transport')), TimeoutError('deadline')
    ),
    'chain3_expired_invalid_value': lambda: _chain(
        _chain(_expired(), InvalidArgument('transport')), ValueError('custody')
    ),
    'chain3_expired_invalid_wrapper': lambda: _chain(
        _chain(_expired(), InvalidArgument('transport')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_expired_invalid_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(_expired(), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_expired_invalid_wrapper_expired': lambda: _chain(
        _chain(
            _chain(_expired(), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_expired_invalid_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(_expired(), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_expired_invalid_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(_expired(), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_expired_invalid_wrapper_value': lambda: _chain(
        _chain(
            _chain(_expired(), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_expired_timeout_aborted': lambda: _chain(_chain(_expired(), TimeoutError('deadline')), Aborted('conflict')),
    'chain3_expired_timeout_expired': lambda: _chain(_chain(_expired(), TimeoutError('deadline')), _expired()),
    'chain3_expired_timeout_invalid': lambda: _chain(
        _chain(_expired(), TimeoutError('deadline')), InvalidArgument('transport')
    ),
    'chain3_expired_timeout_timeout': lambda: _chain(
        _chain(_expired(), TimeoutError('deadline')), TimeoutError('deadline')
    ),
    'chain3_expired_timeout_value': lambda: _chain(_chain(_expired(), TimeoutError('deadline')), ValueError('custody')),
    'chain3_expired_timeout_wrapper': lambda: _chain(
        _chain(_expired(), TimeoutError('deadline')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_expired_timeout_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(_expired(), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_expired_timeout_wrapper_expired': lambda: _chain(
        _chain(
            _chain(_expired(), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_expired_timeout_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(_expired(), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_expired_timeout_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(_expired(), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_expired_timeout_wrapper_value': lambda: _chain(
        _chain(
            _chain(_expired(), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_expired_value_aborted': lambda: _chain(_chain(_expired(), ValueError('custody')), Aborted('conflict')),
    'chain3_expired_value_expired': lambda: _chain(_chain(_expired(), ValueError('custody')), _expired()),
    'chain3_expired_value_invalid': lambda: _chain(
        _chain(_expired(), ValueError('custody')), InvalidArgument('transport')
    ),
    'chain3_expired_value_timeout': lambda: _chain(_chain(_expired(), ValueError('custody')), TimeoutError('deadline')),
    'chain3_expired_value_value': lambda: _chain(_chain(_expired(), ValueError('custody')), ValueError('custody')),
    'chain3_expired_value_wrapper': lambda: _chain(
        _chain(_expired(), ValueError('custody')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_expired_value_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(_expired(), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_expired_value_wrapper_expired': lambda: _chain(
        _chain(
            _chain(_expired(), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_expired_value_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(_expired(), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_expired_value_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(_expired(), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_expired_value_wrapper_value': lambda: _chain(
        _chain(
            _chain(_expired(), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_expired_wrapper_aborted': lambda: _chain(
        _chain(_expired(), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)),
        Aborted('conflict'),
    ),
    'chain3_expired_wrapper_expired': lambda: _chain(
        _chain(_expired(), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)),
        _expired(),
    ),
    'chain3_expired_wrapper_invalid': lambda: _chain(
        _chain(_expired(), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)),
        InvalidArgument('transport'),
    ),
    'chain3_expired_wrapper_timeout': lambda: _chain(
        _chain(_expired(), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)),
        TimeoutError('deadline'),
    ),
    'chain3_expired_wrapper_value': lambda: _chain(
        _chain(_expired(), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)),
        ValueError('custody'),
    ),
    'chain3_expired_wrapper_wrapper': lambda: _chain(
        _chain(_expired(), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_invalid_aborted_aborted': lambda: _chain(
        _chain(InvalidArgument('transport'), Aborted('conflict')), Aborted('conflict')
    ),
    'chain3_invalid_aborted_expired': lambda: _chain(
        _chain(InvalidArgument('transport'), Aborted('conflict')), _expired()
    ),
    'chain3_invalid_aborted_invalid': lambda: _chain(
        _chain(InvalidArgument('transport'), Aborted('conflict')), InvalidArgument('transport')
    ),
    'chain3_invalid_aborted_timeout': lambda: _chain(
        _chain(InvalidArgument('transport'), Aborted('conflict')), TimeoutError('deadline')
    ),
    'chain3_invalid_aborted_value': lambda: _chain(
        _chain(InvalidArgument('transport'), Aborted('conflict')), ValueError('custody')
    ),
    'chain3_invalid_aborted_wrapper': lambda: _chain(
        _chain(InvalidArgument('transport'), Aborted('conflict')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_invalid_aborted_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_invalid_aborted_wrapper_expired': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_invalid_aborted_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_invalid_aborted_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_invalid_aborted_wrapper_value': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_invalid_expired_aborted': lambda: _chain(
        _chain(InvalidArgument('transport'), _expired()), Aborted('conflict')
    ),
    'chain3_invalid_expired_expired': lambda: _chain(_chain(InvalidArgument('transport'), _expired()), _expired()),
    'chain3_invalid_expired_invalid': lambda: _chain(
        _chain(InvalidArgument('transport'), _expired()), InvalidArgument('transport')
    ),
    'chain3_invalid_expired_timeout': lambda: _chain(
        _chain(InvalidArgument('transport'), _expired()), TimeoutError('deadline')
    ),
    'chain3_invalid_expired_value': lambda: _chain(
        _chain(InvalidArgument('transport'), _expired()), ValueError('custody')
    ),
    'chain3_invalid_expired_wrapper': lambda: _chain(
        _chain(InvalidArgument('transport'), _expired()),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_invalid_expired_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_invalid_expired_wrapper_expired': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_invalid_expired_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_invalid_expired_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_invalid_expired_wrapper_value': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_invalid_invalid_aborted': lambda: _chain(
        _chain(InvalidArgument('transport'), InvalidArgument('transport')), Aborted('conflict')
    ),
    'chain3_invalid_invalid_expired': lambda: _chain(
        _chain(InvalidArgument('transport'), InvalidArgument('transport')), _expired()
    ),
    'chain3_invalid_invalid_invalid': lambda: _chain(
        _chain(InvalidArgument('transport'), InvalidArgument('transport')), InvalidArgument('transport')
    ),
    'chain3_invalid_invalid_timeout': lambda: _chain(
        _chain(InvalidArgument('transport'), InvalidArgument('transport')), TimeoutError('deadline')
    ),
    'chain3_invalid_invalid_value': lambda: _chain(
        _chain(InvalidArgument('transport'), InvalidArgument('transport')), ValueError('custody')
    ),
    'chain3_invalid_invalid_wrapper': lambda: _chain(
        _chain(InvalidArgument('transport'), InvalidArgument('transport')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_invalid_invalid_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_invalid_invalid_wrapper_expired': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_invalid_invalid_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_invalid_invalid_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_invalid_invalid_wrapper_value': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_invalid_timeout_aborted': lambda: _chain(
        _chain(InvalidArgument('transport'), TimeoutError('deadline')), Aborted('conflict')
    ),
    'chain3_invalid_timeout_expired': lambda: _chain(
        _chain(InvalidArgument('transport'), TimeoutError('deadline')), _expired()
    ),
    'chain3_invalid_timeout_invalid': lambda: _chain(
        _chain(InvalidArgument('transport'), TimeoutError('deadline')), InvalidArgument('transport')
    ),
    'chain3_invalid_timeout_timeout': lambda: _chain(
        _chain(InvalidArgument('transport'), TimeoutError('deadline')), TimeoutError('deadline')
    ),
    'chain3_invalid_timeout_value': lambda: _chain(
        _chain(InvalidArgument('transport'), TimeoutError('deadline')), ValueError('custody')
    ),
    'chain3_invalid_timeout_wrapper': lambda: _chain(
        _chain(InvalidArgument('transport'), TimeoutError('deadline')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_invalid_timeout_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_invalid_timeout_wrapper_expired': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_invalid_timeout_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_invalid_timeout_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_invalid_timeout_wrapper_value': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_invalid_value_aborted': lambda: _chain(
        _chain(InvalidArgument('transport'), ValueError('custody')), Aborted('conflict')
    ),
    'chain3_invalid_value_expired': lambda: _chain(
        _chain(InvalidArgument('transport'), ValueError('custody')), _expired()
    ),
    'chain3_invalid_value_invalid': lambda: _chain(
        _chain(InvalidArgument('transport'), ValueError('custody')), InvalidArgument('transport')
    ),
    'chain3_invalid_value_timeout': lambda: _chain(
        _chain(InvalidArgument('transport'), ValueError('custody')), TimeoutError('deadline')
    ),
    'chain3_invalid_value_value': lambda: _chain(
        _chain(InvalidArgument('transport'), ValueError('custody')), ValueError('custody')
    ),
    'chain3_invalid_value_wrapper': lambda: _chain(
        _chain(InvalidArgument('transport'), ValueError('custody')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_invalid_value_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_invalid_value_wrapper_expired': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_invalid_value_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_invalid_value_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_invalid_value_wrapper_value': lambda: _chain(
        _chain(
            _chain(InvalidArgument('transport'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_invalid_wrapper_aborted': lambda: _chain(
        _chain(
            InvalidArgument('transport'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain3_invalid_wrapper_expired': lambda: _chain(
        _chain(
            InvalidArgument('transport'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain3_invalid_wrapper_invalid': lambda: _chain(
        _chain(
            InvalidArgument('transport'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain3_invalid_wrapper_timeout': lambda: _chain(
        _chain(
            InvalidArgument('transport'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain3_invalid_wrapper_value': lambda: _chain(
        _chain(
            InvalidArgument('transport'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_invalid_wrapper_wrapper': lambda: _chain(
        _chain(
            InvalidArgument('transport'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_timeout_aborted_aborted': lambda: _chain(
        _chain(TimeoutError('deadline'), Aborted('conflict')), Aborted('conflict')
    ),
    'chain3_timeout_aborted_expired': lambda: _chain(_chain(TimeoutError('deadline'), Aborted('conflict')), _expired()),
    'chain3_timeout_aborted_invalid': lambda: _chain(
        _chain(TimeoutError('deadline'), Aborted('conflict')), InvalidArgument('transport')
    ),
    'chain3_timeout_aborted_timeout': lambda: _chain(
        _chain(TimeoutError('deadline'), Aborted('conflict')), TimeoutError('deadline')
    ),
    'chain3_timeout_aborted_value': lambda: _chain(
        _chain(TimeoutError('deadline'), Aborted('conflict')), ValueError('custody')
    ),
    'chain3_timeout_aborted_wrapper': lambda: _chain(
        _chain(TimeoutError('deadline'), Aborted('conflict')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_timeout_aborted_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_timeout_aborted_wrapper_expired': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_timeout_aborted_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_timeout_aborted_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_timeout_aborted_wrapper_value': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_timeout_expired_aborted': lambda: _chain(_chain(TimeoutError('deadline'), _expired()), Aborted('conflict')),
    'chain3_timeout_expired_expired': lambda: _chain(_chain(TimeoutError('deadline'), _expired()), _expired()),
    'chain3_timeout_expired_invalid': lambda: _chain(
        _chain(TimeoutError('deadline'), _expired()), InvalidArgument('transport')
    ),
    'chain3_timeout_expired_timeout': lambda: _chain(
        _chain(TimeoutError('deadline'), _expired()), TimeoutError('deadline')
    ),
    'chain3_timeout_expired_value': lambda: _chain(_chain(TimeoutError('deadline'), _expired()), ValueError('custody')),
    'chain3_timeout_expired_wrapper': lambda: _chain(
        _chain(TimeoutError('deadline'), _expired()),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_timeout_expired_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_timeout_expired_wrapper_expired': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_timeout_expired_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_timeout_expired_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_timeout_expired_wrapper_value': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_timeout_invalid_aborted': lambda: _chain(
        _chain(TimeoutError('deadline'), InvalidArgument('transport')), Aborted('conflict')
    ),
    'chain3_timeout_invalid_expired': lambda: _chain(
        _chain(TimeoutError('deadline'), InvalidArgument('transport')), _expired()
    ),
    'chain3_timeout_invalid_invalid': lambda: _chain(
        _chain(TimeoutError('deadline'), InvalidArgument('transport')), InvalidArgument('transport')
    ),
    'chain3_timeout_invalid_timeout': lambda: _chain(
        _chain(TimeoutError('deadline'), InvalidArgument('transport')), TimeoutError('deadline')
    ),
    'chain3_timeout_invalid_value': lambda: _chain(
        _chain(TimeoutError('deadline'), InvalidArgument('transport')), ValueError('custody')
    ),
    'chain3_timeout_invalid_wrapper': lambda: _chain(
        _chain(TimeoutError('deadline'), InvalidArgument('transport')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_timeout_invalid_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_timeout_invalid_wrapper_expired': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_timeout_invalid_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_timeout_invalid_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_timeout_invalid_wrapper_value': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_timeout_timeout_aborted': lambda: _chain(
        _chain(TimeoutError('deadline'), TimeoutError('deadline')), Aborted('conflict')
    ),
    'chain3_timeout_timeout_expired': lambda: _chain(
        _chain(TimeoutError('deadline'), TimeoutError('deadline')), _expired()
    ),
    'chain3_timeout_timeout_invalid': lambda: _chain(
        _chain(TimeoutError('deadline'), TimeoutError('deadline')), InvalidArgument('transport')
    ),
    'chain3_timeout_timeout_timeout': lambda: _chain(
        _chain(TimeoutError('deadline'), TimeoutError('deadline')), TimeoutError('deadline')
    ),
    'chain3_timeout_timeout_value': lambda: _chain(
        _chain(TimeoutError('deadline'), TimeoutError('deadline')), ValueError('custody')
    ),
    'chain3_timeout_timeout_wrapper': lambda: _chain(
        _chain(TimeoutError('deadline'), TimeoutError('deadline')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_timeout_timeout_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_timeout_timeout_wrapper_expired': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_timeout_timeout_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_timeout_timeout_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_timeout_timeout_wrapper_value': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_timeout_value_aborted': lambda: _chain(
        _chain(TimeoutError('deadline'), ValueError('custody')), Aborted('conflict')
    ),
    'chain3_timeout_value_expired': lambda: _chain(_chain(TimeoutError('deadline'), ValueError('custody')), _expired()),
    'chain3_timeout_value_invalid': lambda: _chain(
        _chain(TimeoutError('deadline'), ValueError('custody')), InvalidArgument('transport')
    ),
    'chain3_timeout_value_timeout': lambda: _chain(
        _chain(TimeoutError('deadline'), ValueError('custody')), TimeoutError('deadline')
    ),
    'chain3_timeout_value_value': lambda: _chain(
        _chain(TimeoutError('deadline'), ValueError('custody')), ValueError('custody')
    ),
    'chain3_timeout_value_wrapper': lambda: _chain(
        _chain(TimeoutError('deadline'), ValueError('custody')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_timeout_value_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_timeout_value_wrapper_expired': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_timeout_value_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_timeout_value_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_timeout_value_wrapper_value': lambda: _chain(
        _chain(
            _chain(TimeoutError('deadline'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_timeout_wrapper_aborted': lambda: _chain(
        _chain(
            TimeoutError('deadline'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain3_timeout_wrapper_expired': lambda: _chain(
        _chain(
            TimeoutError('deadline'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain3_timeout_wrapper_invalid': lambda: _chain(
        _chain(
            TimeoutError('deadline'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain3_timeout_wrapper_timeout': lambda: _chain(
        _chain(
            TimeoutError('deadline'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain3_timeout_wrapper_value': lambda: _chain(
        _chain(
            TimeoutError('deadline'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_timeout_wrapper_wrapper': lambda: _chain(
        _chain(
            TimeoutError('deadline'),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_value_aborted_aborted': lambda: _chain(
        _chain(ValueError('custody'), Aborted('conflict')), Aborted('conflict')
    ),
    'chain3_value_aborted_expired': lambda: _chain(_chain(ValueError('custody'), Aborted('conflict')), _expired()),
    'chain3_value_aborted_invalid': lambda: _chain(
        _chain(ValueError('custody'), Aborted('conflict')), InvalidArgument('transport')
    ),
    'chain3_value_aborted_timeout': lambda: _chain(
        _chain(ValueError('custody'), Aborted('conflict')), TimeoutError('deadline')
    ),
    'chain3_value_aborted_value': lambda: _chain(
        _chain(ValueError('custody'), Aborted('conflict')), ValueError('custody')
    ),
    'chain3_value_aborted_wrapper': lambda: _chain(
        _chain(ValueError('custody'), Aborted('conflict')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_value_aborted_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_value_aborted_wrapper_expired': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_value_aborted_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_value_aborted_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_value_aborted_wrapper_value': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), Aborted('conflict')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_value_expired_aborted': lambda: _chain(_chain(ValueError('custody'), _expired()), Aborted('conflict')),
    'chain3_value_expired_expired': lambda: _chain(_chain(ValueError('custody'), _expired()), _expired()),
    'chain3_value_expired_invalid': lambda: _chain(
        _chain(ValueError('custody'), _expired()), InvalidArgument('transport')
    ),
    'chain3_value_expired_timeout': lambda: _chain(_chain(ValueError('custody'), _expired()), TimeoutError('deadline')),
    'chain3_value_expired_value': lambda: _chain(_chain(ValueError('custody'), _expired()), ValueError('custody')),
    'chain3_value_expired_wrapper': lambda: _chain(
        _chain(ValueError('custody'), _expired()),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_value_expired_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_value_expired_wrapper_expired': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_value_expired_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_value_expired_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_value_expired_wrapper_value': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), _expired()),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_value_invalid_aborted': lambda: _chain(
        _chain(ValueError('custody'), InvalidArgument('transport')), Aborted('conflict')
    ),
    'chain3_value_invalid_expired': lambda: _chain(
        _chain(ValueError('custody'), InvalidArgument('transport')), _expired()
    ),
    'chain3_value_invalid_invalid': lambda: _chain(
        _chain(ValueError('custody'), InvalidArgument('transport')), InvalidArgument('transport')
    ),
    'chain3_value_invalid_timeout': lambda: _chain(
        _chain(ValueError('custody'), InvalidArgument('transport')), TimeoutError('deadline')
    ),
    'chain3_value_invalid_value': lambda: _chain(
        _chain(ValueError('custody'), InvalidArgument('transport')), ValueError('custody')
    ),
    'chain3_value_invalid_wrapper': lambda: _chain(
        _chain(ValueError('custody'), InvalidArgument('transport')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_value_invalid_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_value_invalid_wrapper_expired': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_value_invalid_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_value_invalid_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_value_invalid_wrapper_value': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), InvalidArgument('transport')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_value_timeout_aborted': lambda: _chain(
        _chain(ValueError('custody'), TimeoutError('deadline')), Aborted('conflict')
    ),
    'chain3_value_timeout_expired': lambda: _chain(_chain(ValueError('custody'), TimeoutError('deadline')), _expired()),
    'chain3_value_timeout_invalid': lambda: _chain(
        _chain(ValueError('custody'), TimeoutError('deadline')), InvalidArgument('transport')
    ),
    'chain3_value_timeout_timeout': lambda: _chain(
        _chain(ValueError('custody'), TimeoutError('deadline')), TimeoutError('deadline')
    ),
    'chain3_value_timeout_value': lambda: _chain(
        _chain(ValueError('custody'), TimeoutError('deadline')), ValueError('custody')
    ),
    'chain3_value_timeout_wrapper': lambda: _chain(
        _chain(ValueError('custody'), TimeoutError('deadline')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_value_timeout_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_value_timeout_wrapper_expired': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_value_timeout_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_value_timeout_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_value_timeout_wrapper_value': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), TimeoutError('deadline')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_value_value_aborted': lambda: _chain(
        _chain(ValueError('custody'), ValueError('custody')), Aborted('conflict')
    ),
    'chain3_value_value_expired': lambda: _chain(_chain(ValueError('custody'), ValueError('custody')), _expired()),
    'chain3_value_value_invalid': lambda: _chain(
        _chain(ValueError('custody'), ValueError('custody')), InvalidArgument('transport')
    ),
    'chain3_value_value_timeout': lambda: _chain(
        _chain(ValueError('custody'), ValueError('custody')), TimeoutError('deadline')
    ),
    'chain3_value_value_value': lambda: _chain(
        _chain(ValueError('custody'), ValueError('custody')), ValueError('custody')
    ),
    'chain3_value_value_wrapper': lambda: _chain(
        _chain(ValueError('custody'), ValueError('custody')),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain4_value_value_wrapper_aborted': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain4_value_value_wrapper_expired': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain4_value_value_wrapper_invalid': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain4_value_value_wrapper_timeout': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain4_value_value_wrapper_value': lambda: _chain(
        _chain(
            _chain(ValueError('custody'), ValueError('custody')),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_value_wrapper_aborted': lambda: _chain(
        _chain(
            ValueError('custody'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        Aborted('conflict'),
    ),
    'chain3_value_wrapper_expired': lambda: _chain(
        _chain(
            ValueError('custody'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        _expired(),
    ),
    'chain3_value_wrapper_invalid': lambda: _chain(
        _chain(
            ValueError('custody'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        InvalidArgument('transport'),
    ),
    'chain3_value_wrapper_timeout': lambda: _chain(
        _chain(
            ValueError('custody'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        TimeoutError('deadline'),
    ),
    'chain3_value_wrapper_value': lambda: _chain(
        _chain(
            ValueError('custody'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        ValueError('custody'),
    ),
    'chain3_value_wrapper_wrapper': lambda: _chain(
        _chain(
            ValueError('custody'), FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25)
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_wrapper_aborted_aborted': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), Aborted('conflict')
        ),
        Aborted('conflict'),
    ),
    'chain3_wrapper_aborted_expired': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), Aborted('conflict')
        ),
        _expired(),
    ),
    'chain3_wrapper_aborted_invalid': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), Aborted('conflict')
        ),
        InvalidArgument('transport'),
    ),
    'chain3_wrapper_aborted_timeout': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), Aborted('conflict')
        ),
        TimeoutError('deadline'),
    ),
    'chain3_wrapper_aborted_value': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), Aborted('conflict')
        ),
        ValueError('custody'),
    ),
    'chain3_wrapper_aborted_wrapper': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), Aborted('conflict')
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_wrapper_expired_aborted': lambda: _chain(
        _chain(FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), _expired()),
        Aborted('conflict'),
    ),
    'chain3_wrapper_expired_expired': lambda: _chain(
        _chain(FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), _expired()),
        _expired(),
    ),
    'chain3_wrapper_expired_invalid': lambda: _chain(
        _chain(FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), _expired()),
        InvalidArgument('transport'),
    ),
    'chain3_wrapper_expired_timeout': lambda: _chain(
        _chain(FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), _expired()),
        TimeoutError('deadline'),
    ),
    'chain3_wrapper_expired_value': lambda: _chain(
        _chain(FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), _expired()),
        ValueError('custody'),
    ),
    'chain3_wrapper_expired_wrapper': lambda: _chain(
        _chain(FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), _expired()),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_wrapper_invalid_aborted': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            InvalidArgument('transport'),
        ),
        Aborted('conflict'),
    ),
    'chain3_wrapper_invalid_expired': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            InvalidArgument('transport'),
        ),
        _expired(),
    ),
    'chain3_wrapper_invalid_invalid': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            InvalidArgument('transport'),
        ),
        InvalidArgument('transport'),
    ),
    'chain3_wrapper_invalid_timeout': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            InvalidArgument('transport'),
        ),
        TimeoutError('deadline'),
    ),
    'chain3_wrapper_invalid_value': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            InvalidArgument('transport'),
        ),
        ValueError('custody'),
    ),
    'chain3_wrapper_invalid_wrapper': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            InvalidArgument('transport'),
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_wrapper_timeout_aborted': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            TimeoutError('deadline'),
        ),
        Aborted('conflict'),
    ),
    'chain3_wrapper_timeout_expired': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            TimeoutError('deadline'),
        ),
        _expired(),
    ),
    'chain3_wrapper_timeout_invalid': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            TimeoutError('deadline'),
        ),
        InvalidArgument('transport'),
    ),
    'chain3_wrapper_timeout_timeout': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            TimeoutError('deadline'),
        ),
        TimeoutError('deadline'),
    ),
    'chain3_wrapper_timeout_value': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            TimeoutError('deadline'),
        ),
        ValueError('custody'),
    ),
    'chain3_wrapper_timeout_wrapper': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            TimeoutError('deadline'),
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_wrapper_value_aborted': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), ValueError('custody')
        ),
        Aborted('conflict'),
    ),
    'chain3_wrapper_value_expired': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), ValueError('custody')
        ),
        _expired(),
    ),
    'chain3_wrapper_value_invalid': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), ValueError('custody')
        ),
        InvalidArgument('transport'),
    ),
    'chain3_wrapper_value_timeout': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), ValueError('custody')
        ),
        TimeoutError('deadline'),
    ),
    'chain3_wrapper_value_value': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), ValueError('custody')
        ),
        ValueError('custody'),
    ),
    'chain3_wrapper_value_wrapper': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25), ValueError('custody')
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
    'chain3_wrapper_wrapper_aborted': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        Aborted('conflict'),
    ),
    'chain3_wrapper_wrapper_expired': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        _expired(),
    ),
    'chain3_wrapper_wrapper_invalid': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        InvalidArgument('transport'),
    ),
    'chain3_wrapper_wrapper_timeout': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        TimeoutError('deadline'),
    ),
    'chain3_wrapper_wrapper_value': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        ValueError('custody'),
    ),
    'chain3_wrapper_wrapper_wrapper': lambda: _chain(
        _chain(
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
            FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
        ),
        FirestoreContentionExhausted('chain', reason='attempts_exhausted', retry_after=1.25),
    ),
}


def test_chain_storm_00000():
    # chain3_aborted_aborted_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_aborted_aborted']()), 6) == 0.0


def test_chain_contention_00000():
    # chain3_aborted_aborted_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_aborted_aborted']()) is True


def test_chain_transport_00001():
    # chain3_aborted_aborted_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_aborted_aborted']()) is True


def test_chain_admitted_00002():
    # chain3_aborted_aborted_aborted
    error = _SHAPE_BUILDERS['chain3_aborted_aborted_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00003():
    # chain3_aborted_aborted_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_aborted_expired']()), 6) == 0.0


def test_chain_contention_00003():
    # chain3_aborted_aborted_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_aborted_expired']()) is True


def test_chain_transport_00004():
    # chain3_aborted_aborted_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_aborted_expired']()) is True


def test_chain_admitted_00005():
    # chain3_aborted_aborted_expired
    error = _SHAPE_BUILDERS['chain3_aborted_aborted_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00006():
    # chain3_aborted_aborted_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_aborted_invalid']()), 6) == 0.0


def test_chain_contention_00006():
    # chain3_aborted_aborted_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_aborted_invalid']()) is True


def test_chain_transport_00007():
    # chain3_aborted_aborted_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_aborted_invalid']()) is True


def test_chain_admitted_00008():
    # chain3_aborted_aborted_invalid
    error = _SHAPE_BUILDERS['chain3_aborted_aborted_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00009():
    # chain3_aborted_aborted_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_aborted_timeout']()), 6) == 0.0


def test_chain_contention_00009():
    # chain3_aborted_aborted_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_aborted_timeout']()) is True


def test_chain_transport_00010():
    # chain3_aborted_aborted_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_aborted_timeout']()) is True


def test_chain_admitted_00011():
    # chain3_aborted_aborted_timeout
    error = _SHAPE_BUILDERS['chain3_aborted_aborted_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00012():
    # chain3_aborted_aborted_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_aborted_value']()), 6) == 0.0


def test_chain_contention_00012():
    # chain3_aborted_aborted_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_aborted_value']()) is True


def test_chain_transport_00013():
    # chain3_aborted_aborted_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_aborted_value']()) is True


def test_chain_admitted_00014():
    # chain3_aborted_aborted_value
    error = _SHAPE_BUILDERS['chain3_aborted_aborted_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00015():
    # chain3_aborted_aborted_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_aborted_wrapper']()), 6) == 0.0


def test_chain_contention_00015():
    # chain3_aborted_aborted_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_aborted_wrapper']()) is True


def test_chain_transport_00016():
    # chain3_aborted_aborted_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_aborted_wrapper']()) is True


def test_chain_admitted_00017():
    # chain3_aborted_aborted_wrapper
    error = _SHAPE_BUILDERS['chain3_aborted_aborted_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00018():
    # chain4_aborted_aborted_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00018():
    # chain4_aborted_aborted_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_aborted']()) is True


def test_chain_transport_00019():
    # chain4_aborted_aborted_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_aborted']()) is True


def test_chain_admitted_00020():
    # chain4_aborted_aborted_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00021():
    # chain4_aborted_aborted_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00021():
    # chain4_aborted_aborted_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_expired']()) is True


def test_chain_transport_00022():
    # chain4_aborted_aborted_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_expired']()) is True


def test_chain_admitted_00023():
    # chain4_aborted_aborted_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00024():
    # chain4_aborted_aborted_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00024():
    # chain4_aborted_aborted_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_invalid']()) is True


def test_chain_transport_00025():
    # chain4_aborted_aborted_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_invalid']()) is True


def test_chain_admitted_00026():
    # chain4_aborted_aborted_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00027():
    # chain4_aborted_aborted_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00027():
    # chain4_aborted_aborted_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_timeout']()) is True


def test_chain_transport_00028():
    # chain4_aborted_aborted_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_timeout']()) is True


def test_chain_admitted_00029():
    # chain4_aborted_aborted_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00030():
    # chain4_aborted_aborted_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_value']()), 6) == 0.0


def test_chain_contention_00030():
    # chain4_aborted_aborted_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_value']()) is True


def test_chain_transport_00031():
    # chain4_aborted_aborted_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_value']()) is True


def test_chain_admitted_00032():
    # chain4_aborted_aborted_wrapper_value
    error = _SHAPE_BUILDERS['chain4_aborted_aborted_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00033():
    # chain3_aborted_expired_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_expired_aborted']()), 6) == 0.0


def test_chain_contention_00033():
    # chain3_aborted_expired_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_expired_aborted']()) is True


def test_chain_transport_00034():
    # chain3_aborted_expired_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_expired_aborted']()) is True


def test_chain_admitted_00035():
    # chain3_aborted_expired_aborted
    error = _SHAPE_BUILDERS['chain3_aborted_expired_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00036():
    # chain3_aborted_expired_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_expired_expired']()), 6) == 0.0


def test_chain_contention_00036():
    # chain3_aborted_expired_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_expired_expired']()) is True


def test_chain_transport_00037():
    # chain3_aborted_expired_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_expired_expired']()) is True


def test_chain_admitted_00038():
    # chain3_aborted_expired_expired
    error = _SHAPE_BUILDERS['chain3_aborted_expired_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00039():
    # chain3_aborted_expired_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_expired_invalid']()), 6) == 0.0


def test_chain_contention_00039():
    # chain3_aborted_expired_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_expired_invalid']()) is True


def test_chain_transport_00040():
    # chain3_aborted_expired_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_expired_invalid']()) is True


def test_chain_admitted_00041():
    # chain3_aborted_expired_invalid
    error = _SHAPE_BUILDERS['chain3_aborted_expired_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00042():
    # chain3_aborted_expired_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_expired_timeout']()), 6) == 0.0


def test_chain_contention_00042():
    # chain3_aborted_expired_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_expired_timeout']()) is True


def test_chain_transport_00043():
    # chain3_aborted_expired_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_expired_timeout']()) is True


def test_chain_admitted_00044():
    # chain3_aborted_expired_timeout
    error = _SHAPE_BUILDERS['chain3_aborted_expired_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00045():
    # chain3_aborted_expired_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_expired_value']()), 6) == 0.0


def test_chain_contention_00045():
    # chain3_aborted_expired_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_expired_value']()) is True


def test_chain_transport_00046():
    # chain3_aborted_expired_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_expired_value']()) is True


def test_chain_admitted_00047():
    # chain3_aborted_expired_value
    error = _SHAPE_BUILDERS['chain3_aborted_expired_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00048():
    # chain3_aborted_expired_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_expired_wrapper']()), 6) == 0.0


def test_chain_contention_00048():
    # chain3_aborted_expired_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_expired_wrapper']()) is True


def test_chain_transport_00049():
    # chain3_aborted_expired_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_expired_wrapper']()) is True


def test_chain_admitted_00050():
    # chain3_aborted_expired_wrapper
    error = _SHAPE_BUILDERS['chain3_aborted_expired_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00051():
    # chain4_aborted_expired_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00051():
    # chain4_aborted_expired_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_aborted']()) is True


def test_chain_transport_00052():
    # chain4_aborted_expired_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_aborted']()) is True


def test_chain_admitted_00053():
    # chain4_aborted_expired_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_aborted_expired_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00054():
    # chain4_aborted_expired_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00054():
    # chain4_aborted_expired_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_expired']()) is True


def test_chain_transport_00055():
    # chain4_aborted_expired_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_expired']()) is True


def test_chain_admitted_00056():
    # chain4_aborted_expired_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_aborted_expired_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00057():
    # chain4_aborted_expired_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00057():
    # chain4_aborted_expired_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_invalid']()) is True


def test_chain_transport_00058():
    # chain4_aborted_expired_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_invalid']()) is True


def test_chain_admitted_00059():
    # chain4_aborted_expired_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_aborted_expired_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00060():
    # chain4_aborted_expired_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00060():
    # chain4_aborted_expired_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_timeout']()) is True


def test_chain_transport_00061():
    # chain4_aborted_expired_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_timeout']()) is True


def test_chain_admitted_00062():
    # chain4_aborted_expired_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_aborted_expired_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00063():
    # chain4_aborted_expired_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_value']()), 6) == 0.0


def test_chain_contention_00063():
    # chain4_aborted_expired_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_value']()) is True


def test_chain_transport_00064():
    # chain4_aborted_expired_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_expired_wrapper_value']()) is True


def test_chain_admitted_00065():
    # chain4_aborted_expired_wrapper_value
    error = _SHAPE_BUILDERS['chain4_aborted_expired_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00066():
    # chain3_aborted_invalid_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_invalid_aborted']()), 6) == 0.0


def test_chain_contention_00066():
    # chain3_aborted_invalid_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_invalid_aborted']()) is True


def test_chain_transport_00067():
    # chain3_aborted_invalid_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_invalid_aborted']()) is True


def test_chain_admitted_00068():
    # chain3_aborted_invalid_aborted
    error = _SHAPE_BUILDERS['chain3_aborted_invalid_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00069():
    # chain3_aborted_invalid_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_invalid_expired']()), 6) == 0.0


def test_chain_contention_00069():
    # chain3_aborted_invalid_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_invalid_expired']()) is True


def test_chain_transport_00070():
    # chain3_aborted_invalid_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_invalid_expired']()) is True


def test_chain_admitted_00071():
    # chain3_aborted_invalid_expired
    error = _SHAPE_BUILDERS['chain3_aborted_invalid_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00072():
    # chain3_aborted_invalid_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_invalid_invalid']()), 6) == 0.0


def test_chain_contention_00072():
    # chain3_aborted_invalid_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_invalid_invalid']()) is True


def test_chain_transport_00073():
    # chain3_aborted_invalid_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_invalid_invalid']()) is True


def test_chain_admitted_00074():
    # chain3_aborted_invalid_invalid
    error = _SHAPE_BUILDERS['chain3_aborted_invalid_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00075():
    # chain3_aborted_invalid_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_invalid_timeout']()), 6) == 0.0


def test_chain_contention_00075():
    # chain3_aborted_invalid_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_invalid_timeout']()) is True


def test_chain_transport_00076():
    # chain3_aborted_invalid_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_invalid_timeout']()) is True


def test_chain_admitted_00077():
    # chain3_aborted_invalid_timeout
    error = _SHAPE_BUILDERS['chain3_aborted_invalid_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00078():
    # chain3_aborted_invalid_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_invalid_value']()), 6) == 0.0


def test_chain_contention_00078():
    # chain3_aborted_invalid_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_invalid_value']()) is True


def test_chain_transport_00079():
    # chain3_aborted_invalid_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_invalid_value']()) is True


def test_chain_admitted_00080():
    # chain3_aborted_invalid_value
    error = _SHAPE_BUILDERS['chain3_aborted_invalid_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00081():
    # chain3_aborted_invalid_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_invalid_wrapper']()), 6) == 0.0


def test_chain_contention_00081():
    # chain3_aborted_invalid_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_invalid_wrapper']()) is True


def test_chain_transport_00082():
    # chain3_aborted_invalid_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_invalid_wrapper']()) is True


def test_chain_admitted_00083():
    # chain3_aborted_invalid_wrapper
    error = _SHAPE_BUILDERS['chain3_aborted_invalid_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00084():
    # chain4_aborted_invalid_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00084():
    # chain4_aborted_invalid_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_aborted']()) is True


def test_chain_transport_00085():
    # chain4_aborted_invalid_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_aborted']()) is True


def test_chain_admitted_00086():
    # chain4_aborted_invalid_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00087():
    # chain4_aborted_invalid_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00087():
    # chain4_aborted_invalid_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_expired']()) is True


def test_chain_transport_00088():
    # chain4_aborted_invalid_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_expired']()) is True


def test_chain_admitted_00089():
    # chain4_aborted_invalid_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00090():
    # chain4_aborted_invalid_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00090():
    # chain4_aborted_invalid_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_invalid']()) is True


def test_chain_transport_00091():
    # chain4_aborted_invalid_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_invalid']()) is True


def test_chain_admitted_00092():
    # chain4_aborted_invalid_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00093():
    # chain4_aborted_invalid_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00093():
    # chain4_aborted_invalid_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_timeout']()) is True


def test_chain_transport_00094():
    # chain4_aborted_invalid_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_timeout']()) is True


def test_chain_admitted_00095():
    # chain4_aborted_invalid_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00096():
    # chain4_aborted_invalid_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_value']()), 6) == 0.0


def test_chain_contention_00096():
    # chain4_aborted_invalid_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_value']()) is True


def test_chain_transport_00097():
    # chain4_aborted_invalid_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_value']()) is True


def test_chain_admitted_00098():
    # chain4_aborted_invalid_wrapper_value
    error = _SHAPE_BUILDERS['chain4_aborted_invalid_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00099():
    # chain3_aborted_timeout_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_timeout_aborted']()), 6) == 0.0


def test_chain_contention_00099():
    # chain3_aborted_timeout_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_timeout_aborted']()) is True


def test_chain_transport_00100():
    # chain3_aborted_timeout_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_timeout_aborted']()) is True


def test_chain_admitted_00101():
    # chain3_aborted_timeout_aborted
    error = _SHAPE_BUILDERS['chain3_aborted_timeout_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00102():
    # chain3_aborted_timeout_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_timeout_expired']()), 6) == 0.0


def test_chain_contention_00102():
    # chain3_aborted_timeout_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_timeout_expired']()) is True


def test_chain_transport_00103():
    # chain3_aborted_timeout_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_timeout_expired']()) is True


def test_chain_admitted_00104():
    # chain3_aborted_timeout_expired
    error = _SHAPE_BUILDERS['chain3_aborted_timeout_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00105():
    # chain3_aborted_timeout_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_timeout_invalid']()), 6) == 0.0


def test_chain_contention_00105():
    # chain3_aborted_timeout_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_timeout_invalid']()) is True


def test_chain_transport_00106():
    # chain3_aborted_timeout_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_timeout_invalid']()) is True


def test_chain_admitted_00107():
    # chain3_aborted_timeout_invalid
    error = _SHAPE_BUILDERS['chain3_aborted_timeout_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00108():
    # chain3_aborted_timeout_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_timeout_timeout']()), 6) == 0.0


def test_chain_contention_00108():
    # chain3_aborted_timeout_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_timeout_timeout']()) is True


def test_chain_transport_00109():
    # chain3_aborted_timeout_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_timeout_timeout']()) is True


def test_chain_admitted_00110():
    # chain3_aborted_timeout_timeout
    error = _SHAPE_BUILDERS['chain3_aborted_timeout_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00111():
    # chain3_aborted_timeout_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_timeout_value']()), 6) == 0.0


def test_chain_contention_00111():
    # chain3_aborted_timeout_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_timeout_value']()) is True


def test_chain_transport_00112():
    # chain3_aborted_timeout_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_timeout_value']()) is True


def test_chain_admitted_00113():
    # chain3_aborted_timeout_value
    error = _SHAPE_BUILDERS['chain3_aborted_timeout_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00114():
    # chain3_aborted_timeout_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_timeout_wrapper']()), 6) == 0.0


def test_chain_contention_00114():
    # chain3_aborted_timeout_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_timeout_wrapper']()) is True


def test_chain_transport_00115():
    # chain3_aborted_timeout_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_timeout_wrapper']()) is True


def test_chain_admitted_00116():
    # chain3_aborted_timeout_wrapper
    error = _SHAPE_BUILDERS['chain3_aborted_timeout_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00117():
    # chain4_aborted_timeout_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00117():
    # chain4_aborted_timeout_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_aborted']()) is True


def test_chain_transport_00118():
    # chain4_aborted_timeout_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_aborted']()) is True


def test_chain_admitted_00119():
    # chain4_aborted_timeout_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00120():
    # chain4_aborted_timeout_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00120():
    # chain4_aborted_timeout_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_expired']()) is True


def test_chain_transport_00121():
    # chain4_aborted_timeout_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_expired']()) is True


def test_chain_admitted_00122():
    # chain4_aborted_timeout_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00123():
    # chain4_aborted_timeout_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00123():
    # chain4_aborted_timeout_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_invalid']()) is True


def test_chain_transport_00124():
    # chain4_aborted_timeout_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_invalid']()) is True


def test_chain_admitted_00125():
    # chain4_aborted_timeout_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00126():
    # chain4_aborted_timeout_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00126():
    # chain4_aborted_timeout_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_timeout']()) is True


def test_chain_transport_00127():
    # chain4_aborted_timeout_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_timeout']()) is True


def test_chain_admitted_00128():
    # chain4_aborted_timeout_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00129():
    # chain4_aborted_timeout_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_value']()), 6) == 0.0


def test_chain_contention_00129():
    # chain4_aborted_timeout_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_value']()) is True


def test_chain_transport_00130():
    # chain4_aborted_timeout_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_value']()) is True


def test_chain_admitted_00131():
    # chain4_aborted_timeout_wrapper_value
    error = _SHAPE_BUILDERS['chain4_aborted_timeout_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00132():
    # chain3_aborted_value_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_value_aborted']()), 6) == 0.0


def test_chain_contention_00132():
    # chain3_aborted_value_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_value_aborted']()) is True


def test_chain_transport_00133():
    # chain3_aborted_value_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_value_aborted']()) is True


def test_chain_admitted_00134():
    # chain3_aborted_value_aborted
    error = _SHAPE_BUILDERS['chain3_aborted_value_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00135():
    # chain3_aborted_value_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_value_expired']()), 6) == 0.0


def test_chain_contention_00135():
    # chain3_aborted_value_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_value_expired']()) is True


def test_chain_transport_00136():
    # chain3_aborted_value_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_value_expired']()) is True


def test_chain_admitted_00137():
    # chain3_aborted_value_expired
    error = _SHAPE_BUILDERS['chain3_aborted_value_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00138():
    # chain3_aborted_value_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_value_invalid']()), 6) == 0.0


def test_chain_contention_00138():
    # chain3_aborted_value_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_value_invalid']()) is True


def test_chain_transport_00139():
    # chain3_aborted_value_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_value_invalid']()) is True


def test_chain_admitted_00140():
    # chain3_aborted_value_invalid
    error = _SHAPE_BUILDERS['chain3_aborted_value_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00141():
    # chain3_aborted_value_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_value_timeout']()), 6) == 0.0


def test_chain_contention_00141():
    # chain3_aborted_value_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_value_timeout']()) is True


def test_chain_transport_00142():
    # chain3_aborted_value_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_value_timeout']()) is True


def test_chain_admitted_00143():
    # chain3_aborted_value_timeout
    error = _SHAPE_BUILDERS['chain3_aborted_value_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00144():
    # chain3_aborted_value_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_value_value']()), 6) == 0.0


def test_chain_contention_00144():
    # chain3_aborted_value_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_value_value']()) is True


def test_chain_transport_00145():
    # chain3_aborted_value_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_value_value']()) is True


def test_chain_admitted_00146():
    # chain3_aborted_value_value
    error = _SHAPE_BUILDERS['chain3_aborted_value_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00147():
    # chain3_aborted_value_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_value_wrapper']()), 6) == 0.0


def test_chain_contention_00147():
    # chain3_aborted_value_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_value_wrapper']()) is True


def test_chain_transport_00148():
    # chain3_aborted_value_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_value_wrapper']()) is True


def test_chain_admitted_00149():
    # chain3_aborted_value_wrapper
    error = _SHAPE_BUILDERS['chain3_aborted_value_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00150():
    # chain4_aborted_value_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00150():
    # chain4_aborted_value_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_aborted']()) is True


def test_chain_transport_00151():
    # chain4_aborted_value_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_aborted']()) is True


def test_chain_admitted_00152():
    # chain4_aborted_value_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_aborted_value_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00153():
    # chain4_aborted_value_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00153():
    # chain4_aborted_value_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_expired']()) is True


def test_chain_transport_00154():
    # chain4_aborted_value_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_expired']()) is True


def test_chain_admitted_00155():
    # chain4_aborted_value_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_aborted_value_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00156():
    # chain4_aborted_value_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00156():
    # chain4_aborted_value_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_invalid']()) is True


def test_chain_transport_00157():
    # chain4_aborted_value_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_invalid']()) is True


def test_chain_admitted_00158():
    # chain4_aborted_value_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_aborted_value_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00159():
    # chain4_aborted_value_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00159():
    # chain4_aborted_value_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_timeout']()) is True


def test_chain_transport_00160():
    # chain4_aborted_value_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_timeout']()) is True


def test_chain_admitted_00161():
    # chain4_aborted_value_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_aborted_value_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00162():
    # chain4_aborted_value_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_value']()), 6) == 0.0


def test_chain_contention_00162():
    # chain4_aborted_value_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_value']()) is True


def test_chain_transport_00163():
    # chain4_aborted_value_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_aborted_value_wrapper_value']()) is True


def test_chain_admitted_00164():
    # chain4_aborted_value_wrapper_value
    error = _SHAPE_BUILDERS['chain4_aborted_value_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00165():
    # chain3_aborted_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00165():
    # chain3_aborted_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_wrapper_aborted']()) is True


def test_chain_transport_00166():
    # chain3_aborted_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_wrapper_aborted']()) is True


def test_chain_admitted_00167():
    # chain3_aborted_wrapper_aborted
    error = _SHAPE_BUILDERS['chain3_aborted_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00168():
    # chain3_aborted_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00168():
    # chain3_aborted_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_wrapper_expired']()) is True


def test_chain_transport_00169():
    # chain3_aborted_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_wrapper_expired']()) is True


def test_chain_admitted_00170():
    # chain3_aborted_wrapper_expired
    error = _SHAPE_BUILDERS['chain3_aborted_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00171():
    # chain3_aborted_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00171():
    # chain3_aborted_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_wrapper_invalid']()) is True


def test_chain_transport_00172():
    # chain3_aborted_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_wrapper_invalid']()) is True


def test_chain_admitted_00173():
    # chain3_aborted_wrapper_invalid
    error = _SHAPE_BUILDERS['chain3_aborted_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00174():
    # chain3_aborted_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00174():
    # chain3_aborted_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_wrapper_timeout']()) is True


def test_chain_transport_00175():
    # chain3_aborted_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_wrapper_timeout']()) is True


def test_chain_admitted_00176():
    # chain3_aborted_wrapper_timeout
    error = _SHAPE_BUILDERS['chain3_aborted_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00177():
    # chain3_aborted_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_wrapper_value']()), 6) == 0.0


def test_chain_contention_00177():
    # chain3_aborted_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_wrapper_value']()) is True


def test_chain_transport_00178():
    # chain3_aborted_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_wrapper_value']()) is True


def test_chain_admitted_00179():
    # chain3_aborted_wrapper_value
    error = _SHAPE_BUILDERS['chain3_aborted_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00180():
    # chain3_aborted_wrapper_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_aborted_wrapper_wrapper']()), 6) == 0.0


def test_chain_contention_00180():
    # chain3_aborted_wrapper_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_aborted_wrapper_wrapper']()) is True


def test_chain_transport_00181():
    # chain3_aborted_wrapper_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_aborted_wrapper_wrapper']()) is True


def test_chain_admitted_00182():
    # chain3_aborted_wrapper_wrapper
    error = _SHAPE_BUILDERS['chain3_aborted_wrapper_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00183():
    # chain3_expired_aborted_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_aborted_aborted']()), 6) == 0.0


def test_chain_contention_00183():
    # chain3_expired_aborted_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_aborted_aborted']()) is True


def test_chain_transport_00184():
    # chain3_expired_aborted_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_aborted_aborted']()) is True


def test_chain_admitted_00185():
    # chain3_expired_aborted_aborted
    error = _SHAPE_BUILDERS['chain3_expired_aborted_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00186():
    # chain3_expired_aborted_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_aborted_expired']()), 6) == 0.0


def test_chain_contention_00186():
    # chain3_expired_aborted_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_aborted_expired']()) is True


def test_chain_transport_00187():
    # chain3_expired_aborted_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_aborted_expired']()) is True


def test_chain_admitted_00188():
    # chain3_expired_aborted_expired
    error = _SHAPE_BUILDERS['chain3_expired_aborted_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00189():
    # chain3_expired_aborted_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_aborted_invalid']()), 6) == 0.0


def test_chain_contention_00189():
    # chain3_expired_aborted_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_aborted_invalid']()) is True


def test_chain_transport_00190():
    # chain3_expired_aborted_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_aborted_invalid']()) is True


def test_chain_admitted_00191():
    # chain3_expired_aborted_invalid
    error = _SHAPE_BUILDERS['chain3_expired_aborted_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00192():
    # chain3_expired_aborted_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_aborted_timeout']()), 6) == 0.0


def test_chain_contention_00192():
    # chain3_expired_aborted_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_aborted_timeout']()) is True


def test_chain_transport_00193():
    # chain3_expired_aborted_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_aborted_timeout']()) is True


def test_chain_admitted_00194():
    # chain3_expired_aborted_timeout
    error = _SHAPE_BUILDERS['chain3_expired_aborted_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00195():
    # chain3_expired_aborted_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_aborted_value']()), 6) == 0.0


def test_chain_contention_00195():
    # chain3_expired_aborted_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_aborted_value']()) is True


def test_chain_transport_00196():
    # chain3_expired_aborted_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_aborted_value']()) is True


def test_chain_admitted_00197():
    # chain3_expired_aborted_value
    error = _SHAPE_BUILDERS['chain3_expired_aborted_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00198():
    # chain3_expired_aborted_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_aborted_wrapper']()), 6) == 0.0


def test_chain_contention_00198():
    # chain3_expired_aborted_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_aborted_wrapper']()) is True


def test_chain_transport_00199():
    # chain3_expired_aborted_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_aborted_wrapper']()) is True


def test_chain_admitted_00200():
    # chain3_expired_aborted_wrapper
    error = _SHAPE_BUILDERS['chain3_expired_aborted_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00201():
    # chain4_expired_aborted_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00201():
    # chain4_expired_aborted_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_aborted']()) is True


def test_chain_transport_00202():
    # chain4_expired_aborted_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_aborted']()) is True


def test_chain_admitted_00203():
    # chain4_expired_aborted_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_expired_aborted_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00204():
    # chain4_expired_aborted_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00204():
    # chain4_expired_aborted_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_expired']()) is True


def test_chain_transport_00205():
    # chain4_expired_aborted_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_expired']()) is True


def test_chain_admitted_00206():
    # chain4_expired_aborted_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_expired_aborted_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00207():
    # chain4_expired_aborted_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00207():
    # chain4_expired_aborted_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_invalid']()) is True


def test_chain_transport_00208():
    # chain4_expired_aborted_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_invalid']()) is True


def test_chain_admitted_00209():
    # chain4_expired_aborted_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_expired_aborted_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00210():
    # chain4_expired_aborted_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00210():
    # chain4_expired_aborted_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_timeout']()) is True


def test_chain_transport_00211():
    # chain4_expired_aborted_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_timeout']()) is True


def test_chain_admitted_00212():
    # chain4_expired_aborted_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_expired_aborted_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00213():
    # chain4_expired_aborted_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_value']()), 6) == 0.0


def test_chain_contention_00213():
    # chain4_expired_aborted_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_value']()) is True


def test_chain_transport_00214():
    # chain4_expired_aborted_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_aborted_wrapper_value']()) is True


def test_chain_admitted_00215():
    # chain4_expired_aborted_wrapper_value
    error = _SHAPE_BUILDERS['chain4_expired_aborted_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00216():
    # chain3_expired_expired_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_expired_aborted']()), 6) == 0.0


def test_chain_contention_00216():
    # chain3_expired_expired_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_expired_aborted']()) is True


def test_chain_transport_00217():
    # chain3_expired_expired_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_expired_aborted']()) is True


def test_chain_admitted_00218():
    # chain3_expired_expired_aborted
    error = _SHAPE_BUILDERS['chain3_expired_expired_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00219():
    # chain3_expired_expired_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_expired_expired']()), 6) == 0.0


def test_chain_contention_00219():
    # chain3_expired_expired_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_expired_expired']()) is True


def test_chain_transport_00220():
    # chain3_expired_expired_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_expired_expired']()) is True


def test_chain_admitted_00221():
    # chain3_expired_expired_expired
    error = _SHAPE_BUILDERS['chain3_expired_expired_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00222():
    # chain3_expired_expired_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_expired_invalid']()), 6) == 0.0


def test_chain_contention_00222():
    # chain3_expired_expired_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_expired_invalid']()) is True


def test_chain_transport_00223():
    # chain3_expired_expired_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_expired_invalid']()) is True


def test_chain_admitted_00224():
    # chain3_expired_expired_invalid
    error = _SHAPE_BUILDERS['chain3_expired_expired_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00225():
    # chain3_expired_expired_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_expired_timeout']()), 6) == 0.0


def test_chain_contention_00225():
    # chain3_expired_expired_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_expired_timeout']()) is True


def test_chain_transport_00226():
    # chain3_expired_expired_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_expired_timeout']()) is True


def test_chain_admitted_00227():
    # chain3_expired_expired_timeout
    error = _SHAPE_BUILDERS['chain3_expired_expired_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00228():
    # chain3_expired_expired_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_expired_value']()), 6) == 0.0


def test_chain_contention_00228():
    # chain3_expired_expired_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_expired_value']()) is True


def test_chain_transport_00229():
    # chain3_expired_expired_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_expired_value']()) is True


def test_chain_admitted_00230():
    # chain3_expired_expired_value
    error = _SHAPE_BUILDERS['chain3_expired_expired_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00231():
    # chain3_expired_expired_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_expired_wrapper']()), 6) == 0.0


def test_chain_contention_00231():
    # chain3_expired_expired_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_expired_wrapper']()) is True


def test_chain_transport_00232():
    # chain3_expired_expired_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_expired_wrapper']()) is True


def test_chain_admitted_00233():
    # chain3_expired_expired_wrapper
    error = _SHAPE_BUILDERS['chain3_expired_expired_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00234():
    # chain4_expired_expired_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00234():
    # chain4_expired_expired_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_aborted']()) is True


def test_chain_transport_00235():
    # chain4_expired_expired_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_aborted']()) is True


def test_chain_admitted_00236():
    # chain4_expired_expired_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_expired_expired_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00237():
    # chain4_expired_expired_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00237():
    # chain4_expired_expired_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_expired']()) is True


def test_chain_transport_00238():
    # chain4_expired_expired_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_expired']()) is True


def test_chain_admitted_00239():
    # chain4_expired_expired_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_expired_expired_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00240():
    # chain4_expired_expired_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00240():
    # chain4_expired_expired_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_invalid']()) is True


def test_chain_transport_00241():
    # chain4_expired_expired_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_invalid']()) is True


def test_chain_admitted_00242():
    # chain4_expired_expired_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_expired_expired_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00243():
    # chain4_expired_expired_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00243():
    # chain4_expired_expired_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_timeout']()) is True


def test_chain_transport_00244():
    # chain4_expired_expired_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_timeout']()) is True


def test_chain_admitted_00245():
    # chain4_expired_expired_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_expired_expired_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00246():
    # chain4_expired_expired_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_value']()), 6) == 0.0


def test_chain_contention_00246():
    # chain4_expired_expired_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_value']()) is True


def test_chain_transport_00247():
    # chain4_expired_expired_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_expired_wrapper_value']()) is True


def test_chain_admitted_00248():
    # chain4_expired_expired_wrapper_value
    error = _SHAPE_BUILDERS['chain4_expired_expired_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00249():
    # chain3_expired_invalid_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_invalid_aborted']()), 6) == 0.0


def test_chain_contention_00249():
    # chain3_expired_invalid_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_invalid_aborted']()) is True


def test_chain_transport_00250():
    # chain3_expired_invalid_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_invalid_aborted']()) is True


def test_chain_admitted_00251():
    # chain3_expired_invalid_aborted
    error = _SHAPE_BUILDERS['chain3_expired_invalid_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00252():
    # chain3_expired_invalid_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_invalid_expired']()), 6) == 0.0


def test_chain_contention_00252():
    # chain3_expired_invalid_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_invalid_expired']()) is True


def test_chain_transport_00253():
    # chain3_expired_invalid_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_invalid_expired']()) is True


def test_chain_admitted_00254():
    # chain3_expired_invalid_expired
    error = _SHAPE_BUILDERS['chain3_expired_invalid_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00255():
    # chain3_expired_invalid_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_invalid_invalid']()), 6) == 0.0


def test_chain_contention_00255():
    # chain3_expired_invalid_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_invalid_invalid']()) is True


def test_chain_transport_00256():
    # chain3_expired_invalid_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_invalid_invalid']()) is True


def test_chain_admitted_00257():
    # chain3_expired_invalid_invalid
    error = _SHAPE_BUILDERS['chain3_expired_invalid_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00258():
    # chain3_expired_invalid_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_invalid_timeout']()), 6) == 0.0


def test_chain_contention_00258():
    # chain3_expired_invalid_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_invalid_timeout']()) is True


def test_chain_transport_00259():
    # chain3_expired_invalid_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_invalid_timeout']()) is True


def test_chain_admitted_00260():
    # chain3_expired_invalid_timeout
    error = _SHAPE_BUILDERS['chain3_expired_invalid_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00261():
    # chain3_expired_invalid_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_invalid_value']()), 6) == 0.0


def test_chain_contention_00261():
    # chain3_expired_invalid_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_invalid_value']()) is True


def test_chain_transport_00262():
    # chain3_expired_invalid_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_invalid_value']()) is True


def test_chain_admitted_00263():
    # chain3_expired_invalid_value
    error = _SHAPE_BUILDERS['chain3_expired_invalid_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00264():
    # chain3_expired_invalid_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_invalid_wrapper']()), 6) == 0.0


def test_chain_contention_00264():
    # chain3_expired_invalid_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_invalid_wrapper']()) is True


def test_chain_transport_00265():
    # chain3_expired_invalid_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_invalid_wrapper']()) is True


def test_chain_admitted_00266():
    # chain3_expired_invalid_wrapper
    error = _SHAPE_BUILDERS['chain3_expired_invalid_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00267():
    # chain4_expired_invalid_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00267():
    # chain4_expired_invalid_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_aborted']()) is True


def test_chain_transport_00268():
    # chain4_expired_invalid_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_aborted']()) is True


def test_chain_admitted_00269():
    # chain4_expired_invalid_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_expired_invalid_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00270():
    # chain4_expired_invalid_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00270():
    # chain4_expired_invalid_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_expired']()) is True


def test_chain_transport_00271():
    # chain4_expired_invalid_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_expired']()) is True


def test_chain_admitted_00272():
    # chain4_expired_invalid_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_expired_invalid_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00273():
    # chain4_expired_invalid_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00273():
    # chain4_expired_invalid_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_invalid']()) is True


def test_chain_transport_00274():
    # chain4_expired_invalid_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_invalid']()) is True


def test_chain_admitted_00275():
    # chain4_expired_invalid_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_expired_invalid_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00276():
    # chain4_expired_invalid_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00276():
    # chain4_expired_invalid_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_timeout']()) is True


def test_chain_transport_00277():
    # chain4_expired_invalid_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_timeout']()) is True


def test_chain_admitted_00278():
    # chain4_expired_invalid_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_expired_invalid_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00279():
    # chain4_expired_invalid_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_value']()), 6) == 0.0


def test_chain_contention_00279():
    # chain4_expired_invalid_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_value']()) is True


def test_chain_transport_00280():
    # chain4_expired_invalid_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_invalid_wrapper_value']()) is True


def test_chain_admitted_00281():
    # chain4_expired_invalid_wrapper_value
    error = _SHAPE_BUILDERS['chain4_expired_invalid_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00282():
    # chain3_expired_timeout_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_timeout_aborted']()), 6) == 0.0


def test_chain_contention_00282():
    # chain3_expired_timeout_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_timeout_aborted']()) is True


def test_chain_transport_00283():
    # chain3_expired_timeout_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_timeout_aborted']()) is True


def test_chain_admitted_00284():
    # chain3_expired_timeout_aborted
    error = _SHAPE_BUILDERS['chain3_expired_timeout_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00285():
    # chain3_expired_timeout_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_timeout_expired']()), 6) == 0.0


def test_chain_contention_00285():
    # chain3_expired_timeout_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_timeout_expired']()) is True


def test_chain_transport_00286():
    # chain3_expired_timeout_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_timeout_expired']()) is True


def test_chain_admitted_00287():
    # chain3_expired_timeout_expired
    error = _SHAPE_BUILDERS['chain3_expired_timeout_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00288():
    # chain3_expired_timeout_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_timeout_invalid']()), 6) == 0.0


def test_chain_contention_00288():
    # chain3_expired_timeout_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_timeout_invalid']()) is True


def test_chain_transport_00289():
    # chain3_expired_timeout_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_timeout_invalid']()) is True


def test_chain_admitted_00290():
    # chain3_expired_timeout_invalid
    error = _SHAPE_BUILDERS['chain3_expired_timeout_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00291():
    # chain3_expired_timeout_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_timeout_timeout']()), 6) == 0.0


def test_chain_contention_00291():
    # chain3_expired_timeout_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_timeout_timeout']()) is True


def test_chain_transport_00292():
    # chain3_expired_timeout_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_timeout_timeout']()) is True


def test_chain_admitted_00293():
    # chain3_expired_timeout_timeout
    error = _SHAPE_BUILDERS['chain3_expired_timeout_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00294():
    # chain3_expired_timeout_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_timeout_value']()), 6) == 0.0


def test_chain_contention_00294():
    # chain3_expired_timeout_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_timeout_value']()) is True


def test_chain_transport_00295():
    # chain3_expired_timeout_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_timeout_value']()) is True


def test_chain_admitted_00296():
    # chain3_expired_timeout_value
    error = _SHAPE_BUILDERS['chain3_expired_timeout_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00297():
    # chain3_expired_timeout_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_timeout_wrapper']()), 6) == 0.0


def test_chain_contention_00297():
    # chain3_expired_timeout_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_timeout_wrapper']()) is True


def test_chain_transport_00298():
    # chain3_expired_timeout_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_timeout_wrapper']()) is True


def test_chain_admitted_00299():
    # chain3_expired_timeout_wrapper
    error = _SHAPE_BUILDERS['chain3_expired_timeout_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00300():
    # chain4_expired_timeout_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00300():
    # chain4_expired_timeout_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_aborted']()) is True


def test_chain_transport_00301():
    # chain4_expired_timeout_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_aborted']()) is True


def test_chain_admitted_00302():
    # chain4_expired_timeout_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_expired_timeout_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00303():
    # chain4_expired_timeout_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00303():
    # chain4_expired_timeout_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_expired']()) is True


def test_chain_transport_00304():
    # chain4_expired_timeout_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_expired']()) is True


def test_chain_admitted_00305():
    # chain4_expired_timeout_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_expired_timeout_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00306():
    # chain4_expired_timeout_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00306():
    # chain4_expired_timeout_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_invalid']()) is True


def test_chain_transport_00307():
    # chain4_expired_timeout_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_invalid']()) is True


def test_chain_admitted_00308():
    # chain4_expired_timeout_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_expired_timeout_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00309():
    # chain4_expired_timeout_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00309():
    # chain4_expired_timeout_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_timeout']()) is True


def test_chain_transport_00310():
    # chain4_expired_timeout_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_timeout']()) is True


def test_chain_admitted_00311():
    # chain4_expired_timeout_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_expired_timeout_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00312():
    # chain4_expired_timeout_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_value']()), 6) == 0.0


def test_chain_contention_00312():
    # chain4_expired_timeout_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_value']()) is True


def test_chain_transport_00313():
    # chain4_expired_timeout_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_timeout_wrapper_value']()) is True


def test_chain_admitted_00314():
    # chain4_expired_timeout_wrapper_value
    error = _SHAPE_BUILDERS['chain4_expired_timeout_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00315():
    # chain3_expired_value_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_value_aborted']()), 6) == 0.0


def test_chain_contention_00315():
    # chain3_expired_value_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_value_aborted']()) is True


def test_chain_transport_00316():
    # chain3_expired_value_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_value_aborted']()) is True


def test_chain_admitted_00317():
    # chain3_expired_value_aborted
    error = _SHAPE_BUILDERS['chain3_expired_value_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00318():
    # chain3_expired_value_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_value_expired']()), 6) == 0.0


def test_chain_contention_00318():
    # chain3_expired_value_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_value_expired']()) is True


def test_chain_transport_00319():
    # chain3_expired_value_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_value_expired']()) is True


def test_chain_admitted_00320():
    # chain3_expired_value_expired
    error = _SHAPE_BUILDERS['chain3_expired_value_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00321():
    # chain3_expired_value_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_value_invalid']()), 6) == 0.0


def test_chain_contention_00321():
    # chain3_expired_value_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_value_invalid']()) is True


def test_chain_transport_00322():
    # chain3_expired_value_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_value_invalid']()) is True


def test_chain_admitted_00323():
    # chain3_expired_value_invalid
    error = _SHAPE_BUILDERS['chain3_expired_value_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00324():
    # chain3_expired_value_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_value_timeout']()), 6) == 0.0


def test_chain_contention_00324():
    # chain3_expired_value_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_value_timeout']()) is True


def test_chain_transport_00325():
    # chain3_expired_value_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_value_timeout']()) is True


def test_chain_admitted_00326():
    # chain3_expired_value_timeout
    error = _SHAPE_BUILDERS['chain3_expired_value_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00327():
    # chain3_expired_value_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_value_value']()), 6) == 0.0


def test_chain_contention_00327():
    # chain3_expired_value_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_value_value']()) is True


def test_chain_transport_00328():
    # chain3_expired_value_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_value_value']()) is True


def test_chain_admitted_00329():
    # chain3_expired_value_value
    error = _SHAPE_BUILDERS['chain3_expired_value_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00330():
    # chain3_expired_value_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_value_wrapper']()), 6) == 0.0


def test_chain_contention_00330():
    # chain3_expired_value_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_value_wrapper']()) is True


def test_chain_transport_00331():
    # chain3_expired_value_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_value_wrapper']()) is True


def test_chain_admitted_00332():
    # chain3_expired_value_wrapper
    error = _SHAPE_BUILDERS['chain3_expired_value_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00333():
    # chain4_expired_value_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_value_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00333():
    # chain4_expired_value_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_value_wrapper_aborted']()) is True


def test_chain_transport_00334():
    # chain4_expired_value_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_value_wrapper_aborted']()) is True


def test_chain_admitted_00335():
    # chain4_expired_value_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_expired_value_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00336():
    # chain4_expired_value_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_value_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00336():
    # chain4_expired_value_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_value_wrapper_expired']()) is True


def test_chain_transport_00337():
    # chain4_expired_value_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_value_wrapper_expired']()) is True


def test_chain_admitted_00338():
    # chain4_expired_value_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_expired_value_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00339():
    # chain4_expired_value_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_value_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00339():
    # chain4_expired_value_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_value_wrapper_invalid']()) is True


def test_chain_transport_00340():
    # chain4_expired_value_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_value_wrapper_invalid']()) is True


def test_chain_admitted_00341():
    # chain4_expired_value_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_expired_value_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00342():
    # chain4_expired_value_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_value_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00342():
    # chain4_expired_value_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_value_wrapper_timeout']()) is True


def test_chain_transport_00343():
    # chain4_expired_value_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_value_wrapper_timeout']()) is True


def test_chain_admitted_00344():
    # chain4_expired_value_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_expired_value_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00345():
    # chain4_expired_value_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_expired_value_wrapper_value']()), 6) == 0.0


def test_chain_contention_00345():
    # chain4_expired_value_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_expired_value_wrapper_value']()) is True


def test_chain_transport_00346():
    # chain4_expired_value_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_expired_value_wrapper_value']()) is True


def test_chain_admitted_00347():
    # chain4_expired_value_wrapper_value
    error = _SHAPE_BUILDERS['chain4_expired_value_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00348():
    # chain3_expired_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00348():
    # chain3_expired_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_wrapper_aborted']()) is True


def test_chain_transport_00349():
    # chain3_expired_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_wrapper_aborted']()) is True


def test_chain_admitted_00350():
    # chain3_expired_wrapper_aborted
    error = _SHAPE_BUILDERS['chain3_expired_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00351():
    # chain3_expired_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00351():
    # chain3_expired_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_wrapper_expired']()) is True


def test_chain_transport_00352():
    # chain3_expired_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_wrapper_expired']()) is True


def test_chain_admitted_00353():
    # chain3_expired_wrapper_expired
    error = _SHAPE_BUILDERS['chain3_expired_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00354():
    # chain3_expired_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00354():
    # chain3_expired_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_wrapper_invalid']()) is True


def test_chain_transport_00355():
    # chain3_expired_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_wrapper_invalid']()) is True


def test_chain_admitted_00356():
    # chain3_expired_wrapper_invalid
    error = _SHAPE_BUILDERS['chain3_expired_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00357():
    # chain3_expired_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00357():
    # chain3_expired_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_wrapper_timeout']()) is True


def test_chain_transport_00358():
    # chain3_expired_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_wrapper_timeout']()) is True


def test_chain_admitted_00359():
    # chain3_expired_wrapper_timeout
    error = _SHAPE_BUILDERS['chain3_expired_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00360():
    # chain3_expired_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_wrapper_value']()), 6) == 0.0


def test_chain_contention_00360():
    # chain3_expired_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_wrapper_value']()) is True


def test_chain_transport_00361():
    # chain3_expired_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_wrapper_value']()) is True


def test_chain_admitted_00362():
    # chain3_expired_wrapper_value
    error = _SHAPE_BUILDERS['chain3_expired_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00363():
    # chain3_expired_wrapper_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_expired_wrapper_wrapper']()), 6) == 0.0


def test_chain_contention_00363():
    # chain3_expired_wrapper_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_expired_wrapper_wrapper']()) is True


def test_chain_transport_00364():
    # chain3_expired_wrapper_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_expired_wrapper_wrapper']()) is True


def test_chain_admitted_00365():
    # chain3_expired_wrapper_wrapper
    error = _SHAPE_BUILDERS['chain3_expired_wrapper_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00366():
    # chain3_invalid_aborted_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_aborted_aborted']()), 6) == 0.0


def test_chain_contention_00366():
    # chain3_invalid_aborted_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_aborted_aborted']()) is True


def test_chain_transport_00367():
    # chain3_invalid_aborted_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_aborted_aborted']()) is True


def test_chain_admitted_00368():
    # chain3_invalid_aborted_aborted
    error = _SHAPE_BUILDERS['chain3_invalid_aborted_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00369():
    # chain3_invalid_aborted_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_aborted_expired']()), 6) == 0.0


def test_chain_contention_00369():
    # chain3_invalid_aborted_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_aborted_expired']()) is True


def test_chain_transport_00370():
    # chain3_invalid_aborted_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_aborted_expired']()) is True


def test_chain_admitted_00371():
    # chain3_invalid_aborted_expired
    error = _SHAPE_BUILDERS['chain3_invalid_aborted_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00372():
    # chain3_invalid_aborted_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_aborted_invalid']()), 6) == 0.0


def test_chain_contention_00372():
    # chain3_invalid_aborted_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_aborted_invalid']()) is False


def test_chain_transport_00373():
    # chain3_invalid_aborted_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_aborted_invalid']()) is True


def test_chain_admitted_00374():
    # chain3_invalid_aborted_invalid
    error = _SHAPE_BUILDERS['chain3_invalid_aborted_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00375():
    # chain3_invalid_aborted_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_aborted_timeout']()), 6) == 0.0


def test_chain_contention_00375():
    # chain3_invalid_aborted_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_aborted_timeout']()) is False


def test_chain_transport_00376():
    # chain3_invalid_aborted_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_aborted_timeout']()) is True


def test_chain_admitted_00377():
    # chain3_invalid_aborted_timeout
    error = _SHAPE_BUILDERS['chain3_invalid_aborted_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00378():
    # chain3_invalid_aborted_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_aborted_value']()), 6) == 0.0


def test_chain_contention_00378():
    # chain3_invalid_aborted_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_aborted_value']()) is False


def test_chain_transport_00379():
    # chain3_invalid_aborted_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_aborted_value']()) is True


def test_chain_admitted_00380():
    # chain3_invalid_aborted_value
    error = _SHAPE_BUILDERS['chain3_invalid_aborted_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00381():
    # chain3_invalid_aborted_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_aborted_wrapper']()), 6) == 0.0


def test_chain_contention_00381():
    # chain3_invalid_aborted_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_aborted_wrapper']()) is False


def test_chain_transport_00382():
    # chain3_invalid_aborted_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_aborted_wrapper']()) is True


def test_chain_admitted_00383():
    # chain3_invalid_aborted_wrapper
    error = _SHAPE_BUILDERS['chain3_invalid_aborted_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00384():
    # chain4_invalid_aborted_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00384():
    # chain4_invalid_aborted_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_aborted']()) is True


def test_chain_transport_00385():
    # chain4_invalid_aborted_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_aborted']()) is True


def test_chain_admitted_00386():
    # chain4_invalid_aborted_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00387():
    # chain4_invalid_aborted_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00387():
    # chain4_invalid_aborted_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_expired']()) is True


def test_chain_transport_00388():
    # chain4_invalid_aborted_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_expired']()) is True


def test_chain_admitted_00389():
    # chain4_invalid_aborted_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00390():
    # chain4_invalid_aborted_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00390():
    # chain4_invalid_aborted_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_invalid']()) is False


def test_chain_transport_00391():
    # chain4_invalid_aborted_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_invalid']()) is True


def test_chain_admitted_00392():
    # chain4_invalid_aborted_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00393():
    # chain4_invalid_aborted_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00393():
    # chain4_invalid_aborted_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_timeout']()) is False


def test_chain_transport_00394():
    # chain4_invalid_aborted_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_timeout']()) is True


def test_chain_admitted_00395():
    # chain4_invalid_aborted_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00396():
    # chain4_invalid_aborted_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_value']()), 6) == 0.0


def test_chain_contention_00396():
    # chain4_invalid_aborted_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_value']()) is False


def test_chain_transport_00397():
    # chain4_invalid_aborted_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_value']()) is True


def test_chain_admitted_00398():
    # chain4_invalid_aborted_wrapper_value
    error = _SHAPE_BUILDERS['chain4_invalid_aborted_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00399():
    # chain3_invalid_expired_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_expired_aborted']()), 6) == 0.0


def test_chain_contention_00399():
    # chain3_invalid_expired_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_expired_aborted']()) is True


def test_chain_transport_00400():
    # chain3_invalid_expired_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_expired_aborted']()) is True


def test_chain_admitted_00401():
    # chain3_invalid_expired_aborted
    error = _SHAPE_BUILDERS['chain3_invalid_expired_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00402():
    # chain3_invalid_expired_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_expired_expired']()), 6) == 0.0


def test_chain_contention_00402():
    # chain3_invalid_expired_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_expired_expired']()) is True


def test_chain_transport_00403():
    # chain3_invalid_expired_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_expired_expired']()) is True


def test_chain_admitted_00404():
    # chain3_invalid_expired_expired
    error = _SHAPE_BUILDERS['chain3_invalid_expired_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00405():
    # chain3_invalid_expired_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_expired_invalid']()), 6) == 0.0


def test_chain_contention_00405():
    # chain3_invalid_expired_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_expired_invalid']()) is False


def test_chain_transport_00406():
    # chain3_invalid_expired_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_expired_invalid']()) is True


def test_chain_admitted_00407():
    # chain3_invalid_expired_invalid
    error = _SHAPE_BUILDERS['chain3_invalid_expired_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00408():
    # chain3_invalid_expired_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_expired_timeout']()), 6) == 0.0


def test_chain_contention_00408():
    # chain3_invalid_expired_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_expired_timeout']()) is False


def test_chain_transport_00409():
    # chain3_invalid_expired_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_expired_timeout']()) is True


def test_chain_admitted_00410():
    # chain3_invalid_expired_timeout
    error = _SHAPE_BUILDERS['chain3_invalid_expired_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00411():
    # chain3_invalid_expired_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_expired_value']()), 6) == 0.0


def test_chain_contention_00411():
    # chain3_invalid_expired_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_expired_value']()) is False


def test_chain_transport_00412():
    # chain3_invalid_expired_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_expired_value']()) is True


def test_chain_admitted_00413():
    # chain3_invalid_expired_value
    error = _SHAPE_BUILDERS['chain3_invalid_expired_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00414():
    # chain3_invalid_expired_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_expired_wrapper']()), 6) == 0.0


def test_chain_contention_00414():
    # chain3_invalid_expired_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_expired_wrapper']()) is False


def test_chain_transport_00415():
    # chain3_invalid_expired_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_expired_wrapper']()) is True


def test_chain_admitted_00416():
    # chain3_invalid_expired_wrapper
    error = _SHAPE_BUILDERS['chain3_invalid_expired_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00417():
    # chain4_invalid_expired_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00417():
    # chain4_invalid_expired_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_aborted']()) is True


def test_chain_transport_00418():
    # chain4_invalid_expired_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_aborted']()) is True


def test_chain_admitted_00419():
    # chain4_invalid_expired_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_invalid_expired_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00420():
    # chain4_invalid_expired_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00420():
    # chain4_invalid_expired_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_expired']()) is True


def test_chain_transport_00421():
    # chain4_invalid_expired_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_expired']()) is True


def test_chain_admitted_00422():
    # chain4_invalid_expired_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_invalid_expired_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00423():
    # chain4_invalid_expired_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00423():
    # chain4_invalid_expired_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_invalid']()) is False


def test_chain_transport_00424():
    # chain4_invalid_expired_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_invalid']()) is True


def test_chain_admitted_00425():
    # chain4_invalid_expired_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_invalid_expired_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00426():
    # chain4_invalid_expired_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00426():
    # chain4_invalid_expired_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_timeout']()) is False


def test_chain_transport_00427():
    # chain4_invalid_expired_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_timeout']()) is True


def test_chain_admitted_00428():
    # chain4_invalid_expired_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_invalid_expired_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00429():
    # chain4_invalid_expired_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_value']()), 6) == 0.0


def test_chain_contention_00429():
    # chain4_invalid_expired_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_value']()) is False


def test_chain_transport_00430():
    # chain4_invalid_expired_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_expired_wrapper_value']()) is True


def test_chain_admitted_00431():
    # chain4_invalid_expired_wrapper_value
    error = _SHAPE_BUILDERS['chain4_invalid_expired_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00432():
    # chain3_invalid_invalid_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_invalid_aborted']()), 6) == 0.0


def test_chain_contention_00432():
    # chain3_invalid_invalid_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_invalid_aborted']()) is True


def test_chain_transport_00433():
    # chain3_invalid_invalid_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_invalid_aborted']()) is True


def test_chain_admitted_00434():
    # chain3_invalid_invalid_aborted
    error = _SHAPE_BUILDERS['chain3_invalid_invalid_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00435():
    # chain3_invalid_invalid_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_invalid_expired']()), 6) == 0.0


def test_chain_contention_00435():
    # chain3_invalid_invalid_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_invalid_expired']()) is True


def test_chain_transport_00436():
    # chain3_invalid_invalid_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_invalid_expired']()) is True


def test_chain_admitted_00437():
    # chain3_invalid_invalid_expired
    error = _SHAPE_BUILDERS['chain3_invalid_invalid_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00438():
    # chain3_invalid_invalid_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_invalid_invalid']()), 6) == 0.0


def test_chain_contention_00438():
    # chain3_invalid_invalid_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_invalid_invalid']()) is False


def test_chain_transport_00439():
    # chain3_invalid_invalid_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_invalid_invalid']()) is True


def test_chain_admitted_00440():
    # chain3_invalid_invalid_invalid
    error = _SHAPE_BUILDERS['chain3_invalid_invalid_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00441():
    # chain3_invalid_invalid_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_invalid_timeout']()), 6) == 0.0


def test_chain_contention_00441():
    # chain3_invalid_invalid_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_invalid_timeout']()) is False


def test_chain_transport_00442():
    # chain3_invalid_invalid_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_invalid_timeout']()) is True


def test_chain_admitted_00443():
    # chain3_invalid_invalid_timeout
    error = _SHAPE_BUILDERS['chain3_invalid_invalid_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00444():
    # chain3_invalid_invalid_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_invalid_value']()), 6) == 0.0


def test_chain_contention_00444():
    # chain3_invalid_invalid_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_invalid_value']()) is False


def test_chain_transport_00445():
    # chain3_invalid_invalid_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_invalid_value']()) is True


def test_chain_admitted_00446():
    # chain3_invalid_invalid_value
    error = _SHAPE_BUILDERS['chain3_invalid_invalid_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00447():
    # chain3_invalid_invalid_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_invalid_wrapper']()), 6) == 0.0


def test_chain_contention_00447():
    # chain3_invalid_invalid_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_invalid_wrapper']()) is False


def test_chain_transport_00448():
    # chain3_invalid_invalid_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_invalid_wrapper']()) is True


def test_chain_admitted_00449():
    # chain3_invalid_invalid_wrapper
    error = _SHAPE_BUILDERS['chain3_invalid_invalid_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00450():
    # chain4_invalid_invalid_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00450():
    # chain4_invalid_invalid_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_aborted']()) is True


def test_chain_transport_00451():
    # chain4_invalid_invalid_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_aborted']()) is True


def test_chain_admitted_00452():
    # chain4_invalid_invalid_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00453():
    # chain4_invalid_invalid_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00453():
    # chain4_invalid_invalid_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_expired']()) is True


def test_chain_transport_00454():
    # chain4_invalid_invalid_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_expired']()) is True


def test_chain_admitted_00455():
    # chain4_invalid_invalid_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00456():
    # chain4_invalid_invalid_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00456():
    # chain4_invalid_invalid_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_invalid']()) is False


def test_chain_transport_00457():
    # chain4_invalid_invalid_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_invalid']()) is True


def test_chain_admitted_00458():
    # chain4_invalid_invalid_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00459():
    # chain4_invalid_invalid_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00459():
    # chain4_invalid_invalid_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_timeout']()) is False


def test_chain_transport_00460():
    # chain4_invalid_invalid_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_timeout']()) is True


def test_chain_admitted_00461():
    # chain4_invalid_invalid_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00462():
    # chain4_invalid_invalid_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_value']()), 6) == 0.0


def test_chain_contention_00462():
    # chain4_invalid_invalid_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_value']()) is False


def test_chain_transport_00463():
    # chain4_invalid_invalid_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_value']()) is True


def test_chain_admitted_00464():
    # chain4_invalid_invalid_wrapper_value
    error = _SHAPE_BUILDERS['chain4_invalid_invalid_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00465():
    # chain3_invalid_timeout_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_timeout_aborted']()), 6) == 0.0


def test_chain_contention_00465():
    # chain3_invalid_timeout_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_timeout_aborted']()) is True


def test_chain_transport_00466():
    # chain3_invalid_timeout_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_timeout_aborted']()) is True


def test_chain_admitted_00467():
    # chain3_invalid_timeout_aborted
    error = _SHAPE_BUILDERS['chain3_invalid_timeout_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00468():
    # chain3_invalid_timeout_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_timeout_expired']()), 6) == 0.0


def test_chain_contention_00468():
    # chain3_invalid_timeout_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_timeout_expired']()) is True


def test_chain_transport_00469():
    # chain3_invalid_timeout_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_timeout_expired']()) is True


def test_chain_admitted_00470():
    # chain3_invalid_timeout_expired
    error = _SHAPE_BUILDERS['chain3_invalid_timeout_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00471():
    # chain3_invalid_timeout_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_timeout_invalid']()), 6) == 0.0


def test_chain_contention_00471():
    # chain3_invalid_timeout_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_timeout_invalid']()) is False


def test_chain_transport_00472():
    # chain3_invalid_timeout_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_timeout_invalid']()) is True


def test_chain_admitted_00473():
    # chain3_invalid_timeout_invalid
    error = _SHAPE_BUILDERS['chain3_invalid_timeout_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00474():
    # chain3_invalid_timeout_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_timeout_timeout']()), 6) == 0.0


def test_chain_contention_00474():
    # chain3_invalid_timeout_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_timeout_timeout']()) is False


def test_chain_transport_00475():
    # chain3_invalid_timeout_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_timeout_timeout']()) is True


def test_chain_admitted_00476():
    # chain3_invalid_timeout_timeout
    error = _SHAPE_BUILDERS['chain3_invalid_timeout_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00477():
    # chain3_invalid_timeout_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_timeout_value']()), 6) == 0.0


def test_chain_contention_00477():
    # chain3_invalid_timeout_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_timeout_value']()) is False


def test_chain_transport_00478():
    # chain3_invalid_timeout_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_timeout_value']()) is True


def test_chain_admitted_00479():
    # chain3_invalid_timeout_value
    error = _SHAPE_BUILDERS['chain3_invalid_timeout_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00480():
    # chain3_invalid_timeout_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_timeout_wrapper']()), 6) == 0.0


def test_chain_contention_00480():
    # chain3_invalid_timeout_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_timeout_wrapper']()) is False


def test_chain_transport_00481():
    # chain3_invalid_timeout_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_timeout_wrapper']()) is True


def test_chain_admitted_00482():
    # chain3_invalid_timeout_wrapper
    error = _SHAPE_BUILDERS['chain3_invalid_timeout_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00483():
    # chain4_invalid_timeout_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00483():
    # chain4_invalid_timeout_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_aborted']()) is True


def test_chain_transport_00484():
    # chain4_invalid_timeout_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_aborted']()) is True


def test_chain_admitted_00485():
    # chain4_invalid_timeout_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00486():
    # chain4_invalid_timeout_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00486():
    # chain4_invalid_timeout_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_expired']()) is True


def test_chain_transport_00487():
    # chain4_invalid_timeout_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_expired']()) is True


def test_chain_admitted_00488():
    # chain4_invalid_timeout_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00489():
    # chain4_invalid_timeout_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00489():
    # chain4_invalid_timeout_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_invalid']()) is False


def test_chain_transport_00490():
    # chain4_invalid_timeout_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_invalid']()) is True


def test_chain_admitted_00491():
    # chain4_invalid_timeout_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00492():
    # chain4_invalid_timeout_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00492():
    # chain4_invalid_timeout_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_timeout']()) is False


def test_chain_transport_00493():
    # chain4_invalid_timeout_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_timeout']()) is True


def test_chain_admitted_00494():
    # chain4_invalid_timeout_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00495():
    # chain4_invalid_timeout_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_value']()), 6) == 0.0


def test_chain_contention_00495():
    # chain4_invalid_timeout_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_value']()) is False


def test_chain_transport_00496():
    # chain4_invalid_timeout_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_value']()) is True


def test_chain_admitted_00497():
    # chain4_invalid_timeout_wrapper_value
    error = _SHAPE_BUILDERS['chain4_invalid_timeout_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00498():
    # chain3_invalid_value_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_value_aborted']()), 6) == 0.0


def test_chain_contention_00498():
    # chain3_invalid_value_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_value_aborted']()) is True


def test_chain_transport_00499():
    # chain3_invalid_value_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_value_aborted']()) is True


def test_chain_admitted_00500():
    # chain3_invalid_value_aborted
    error = _SHAPE_BUILDERS['chain3_invalid_value_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00501():
    # chain3_invalid_value_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_value_expired']()), 6) == 0.0


def test_chain_contention_00501():
    # chain3_invalid_value_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_value_expired']()) is True


def test_chain_transport_00502():
    # chain3_invalid_value_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_value_expired']()) is True


def test_chain_admitted_00503():
    # chain3_invalid_value_expired
    error = _SHAPE_BUILDERS['chain3_invalid_value_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00504():
    # chain3_invalid_value_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_value_invalid']()), 6) == 0.0


def test_chain_contention_00504():
    # chain3_invalid_value_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_value_invalid']()) is False


def test_chain_transport_00505():
    # chain3_invalid_value_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_value_invalid']()) is True


def test_chain_admitted_00506():
    # chain3_invalid_value_invalid
    error = _SHAPE_BUILDERS['chain3_invalid_value_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00507():
    # chain3_invalid_value_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_value_timeout']()), 6) == 0.0


def test_chain_contention_00507():
    # chain3_invalid_value_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_value_timeout']()) is False


def test_chain_transport_00508():
    # chain3_invalid_value_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_value_timeout']()) is True


def test_chain_admitted_00509():
    # chain3_invalid_value_timeout
    error = _SHAPE_BUILDERS['chain3_invalid_value_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00510():
    # chain3_invalid_value_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_value_value']()), 6) == 0.0


def test_chain_contention_00510():
    # chain3_invalid_value_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_value_value']()) is False


def test_chain_transport_00511():
    # chain3_invalid_value_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_value_value']()) is True


def test_chain_admitted_00512():
    # chain3_invalid_value_value
    error = _SHAPE_BUILDERS['chain3_invalid_value_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00513():
    # chain3_invalid_value_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_value_wrapper']()), 6) == 0.0


def test_chain_contention_00513():
    # chain3_invalid_value_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_value_wrapper']()) is False


def test_chain_transport_00514():
    # chain3_invalid_value_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_value_wrapper']()) is True


def test_chain_admitted_00515():
    # chain3_invalid_value_wrapper
    error = _SHAPE_BUILDERS['chain3_invalid_value_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00516():
    # chain4_invalid_value_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00516():
    # chain4_invalid_value_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_aborted']()) is True


def test_chain_transport_00517():
    # chain4_invalid_value_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_aborted']()) is True


def test_chain_admitted_00518():
    # chain4_invalid_value_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_invalid_value_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00519():
    # chain4_invalid_value_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00519():
    # chain4_invalid_value_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_expired']()) is True


def test_chain_transport_00520():
    # chain4_invalid_value_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_expired']()) is True


def test_chain_admitted_00521():
    # chain4_invalid_value_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_invalid_value_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00522():
    # chain4_invalid_value_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00522():
    # chain4_invalid_value_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_invalid']()) is False


def test_chain_transport_00523():
    # chain4_invalid_value_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_invalid']()) is True


def test_chain_admitted_00524():
    # chain4_invalid_value_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_invalid_value_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00525():
    # chain4_invalid_value_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00525():
    # chain4_invalid_value_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_timeout']()) is False


def test_chain_transport_00526():
    # chain4_invalid_value_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_timeout']()) is True


def test_chain_admitted_00527():
    # chain4_invalid_value_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_invalid_value_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00528():
    # chain4_invalid_value_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_value']()), 6) == 0.0


def test_chain_contention_00528():
    # chain4_invalid_value_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_value']()) is False


def test_chain_transport_00529():
    # chain4_invalid_value_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_invalid_value_wrapper_value']()) is True


def test_chain_admitted_00530():
    # chain4_invalid_value_wrapper_value
    error = _SHAPE_BUILDERS['chain4_invalid_value_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00531():
    # chain3_invalid_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00531():
    # chain3_invalid_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_wrapper_aborted']()) is True


def test_chain_transport_00532():
    # chain3_invalid_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_wrapper_aborted']()) is True


def test_chain_admitted_00533():
    # chain3_invalid_wrapper_aborted
    error = _SHAPE_BUILDERS['chain3_invalid_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00534():
    # chain3_invalid_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00534():
    # chain3_invalid_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_wrapper_expired']()) is True


def test_chain_transport_00535():
    # chain3_invalid_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_wrapper_expired']()) is True


def test_chain_admitted_00536():
    # chain3_invalid_wrapper_expired
    error = _SHAPE_BUILDERS['chain3_invalid_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00537():
    # chain3_invalid_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00537():
    # chain3_invalid_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_wrapper_invalid']()) is False


def test_chain_transport_00538():
    # chain3_invalid_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_wrapper_invalid']()) is True


def test_chain_admitted_00539():
    # chain3_invalid_wrapper_invalid
    error = _SHAPE_BUILDERS['chain3_invalid_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00540():
    # chain3_invalid_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00540():
    # chain3_invalid_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_wrapper_timeout']()) is False


def test_chain_transport_00541():
    # chain3_invalid_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_wrapper_timeout']()) is True


def test_chain_admitted_00542():
    # chain3_invalid_wrapper_timeout
    error = _SHAPE_BUILDERS['chain3_invalid_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00543():
    # chain3_invalid_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_wrapper_value']()), 6) == 0.0


def test_chain_contention_00543():
    # chain3_invalid_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_wrapper_value']()) is False


def test_chain_transport_00544():
    # chain3_invalid_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_wrapper_value']()) is True


def test_chain_admitted_00545():
    # chain3_invalid_wrapper_value
    error = _SHAPE_BUILDERS['chain3_invalid_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00546():
    # chain3_invalid_wrapper_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_invalid_wrapper_wrapper']()), 6) == 0.0


def test_chain_contention_00546():
    # chain3_invalid_wrapper_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_invalid_wrapper_wrapper']()) is False


def test_chain_transport_00547():
    # chain3_invalid_wrapper_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_invalid_wrapper_wrapper']()) is True


def test_chain_admitted_00548():
    # chain3_invalid_wrapper_wrapper
    error = _SHAPE_BUILDERS['chain3_invalid_wrapper_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00549():
    # chain3_timeout_aborted_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_aborted_aborted']()), 6) == 0.0


def test_chain_contention_00549():
    # chain3_timeout_aborted_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_aborted_aborted']()) is True


def test_chain_transport_00550():
    # chain3_timeout_aborted_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_aborted_aborted']()) is True


def test_chain_admitted_00551():
    # chain3_timeout_aborted_aborted
    error = _SHAPE_BUILDERS['chain3_timeout_aborted_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00552():
    # chain3_timeout_aborted_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_aborted_expired']()), 6) == 0.0


def test_chain_contention_00552():
    # chain3_timeout_aborted_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_aborted_expired']()) is True


def test_chain_transport_00553():
    # chain3_timeout_aborted_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_aborted_expired']()) is True


def test_chain_admitted_00554():
    # chain3_timeout_aborted_expired
    error = _SHAPE_BUILDERS['chain3_timeout_aborted_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00555():
    # chain3_timeout_aborted_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_aborted_invalid']()), 6) == 0.0


def test_chain_contention_00555():
    # chain3_timeout_aborted_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_aborted_invalid']()) is False


def test_chain_transport_00556():
    # chain3_timeout_aborted_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_aborted_invalid']()) is True


def test_chain_admitted_00557():
    # chain3_timeout_aborted_invalid
    error = _SHAPE_BUILDERS['chain3_timeout_aborted_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00558():
    # chain3_timeout_aborted_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_aborted_timeout']()), 6) == 0.0


def test_chain_contention_00558():
    # chain3_timeout_aborted_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_aborted_timeout']()) is False


def test_chain_transport_00559():
    # chain3_timeout_aborted_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_aborted_timeout']()) is True


def test_chain_admitted_00560():
    # chain3_timeout_aborted_timeout
    error = _SHAPE_BUILDERS['chain3_timeout_aborted_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00561():
    # chain3_timeout_aborted_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_aborted_value']()), 6) == 0.0


def test_chain_contention_00561():
    # chain3_timeout_aborted_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_aborted_value']()) is False


def test_chain_transport_00562():
    # chain3_timeout_aborted_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_aborted_value']()) is True


def test_chain_admitted_00563():
    # chain3_timeout_aborted_value
    error = _SHAPE_BUILDERS['chain3_timeout_aborted_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00564():
    # chain3_timeout_aborted_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_aborted_wrapper']()), 6) == 0.0


def test_chain_contention_00564():
    # chain3_timeout_aborted_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_aborted_wrapper']()) is False


def test_chain_transport_00565():
    # chain3_timeout_aborted_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_aborted_wrapper']()) is True


def test_chain_admitted_00566():
    # chain3_timeout_aborted_wrapper
    error = _SHAPE_BUILDERS['chain3_timeout_aborted_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00567():
    # chain4_timeout_aborted_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00567():
    # chain4_timeout_aborted_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_aborted']()) is True


def test_chain_transport_00568():
    # chain4_timeout_aborted_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_aborted']()) is True


def test_chain_admitted_00569():
    # chain4_timeout_aborted_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00570():
    # chain4_timeout_aborted_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00570():
    # chain4_timeout_aborted_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_expired']()) is True


def test_chain_transport_00571():
    # chain4_timeout_aborted_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_expired']()) is True


def test_chain_admitted_00572():
    # chain4_timeout_aborted_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00573():
    # chain4_timeout_aborted_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00573():
    # chain4_timeout_aborted_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_invalid']()) is False


def test_chain_transport_00574():
    # chain4_timeout_aborted_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_invalid']()) is True


def test_chain_admitted_00575():
    # chain4_timeout_aborted_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00576():
    # chain4_timeout_aborted_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00576():
    # chain4_timeout_aborted_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_timeout']()) is False


def test_chain_transport_00577():
    # chain4_timeout_aborted_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_timeout']()) is True


def test_chain_admitted_00578():
    # chain4_timeout_aborted_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00579():
    # chain4_timeout_aborted_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_value']()), 6) == 0.0


def test_chain_contention_00579():
    # chain4_timeout_aborted_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_value']()) is False


def test_chain_transport_00580():
    # chain4_timeout_aborted_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_value']()) is True


def test_chain_admitted_00581():
    # chain4_timeout_aborted_wrapper_value
    error = _SHAPE_BUILDERS['chain4_timeout_aborted_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00582():
    # chain3_timeout_expired_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_expired_aborted']()), 6) == 0.0


def test_chain_contention_00582():
    # chain3_timeout_expired_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_expired_aborted']()) is True


def test_chain_transport_00583():
    # chain3_timeout_expired_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_expired_aborted']()) is True


def test_chain_admitted_00584():
    # chain3_timeout_expired_aborted
    error = _SHAPE_BUILDERS['chain3_timeout_expired_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00585():
    # chain3_timeout_expired_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_expired_expired']()), 6) == 0.0


def test_chain_contention_00585():
    # chain3_timeout_expired_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_expired_expired']()) is True


def test_chain_transport_00586():
    # chain3_timeout_expired_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_expired_expired']()) is True


def test_chain_admitted_00587():
    # chain3_timeout_expired_expired
    error = _SHAPE_BUILDERS['chain3_timeout_expired_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00588():
    # chain3_timeout_expired_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_expired_invalid']()), 6) == 0.0


def test_chain_contention_00588():
    # chain3_timeout_expired_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_expired_invalid']()) is False


def test_chain_transport_00589():
    # chain3_timeout_expired_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_expired_invalid']()) is True


def test_chain_admitted_00590():
    # chain3_timeout_expired_invalid
    error = _SHAPE_BUILDERS['chain3_timeout_expired_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00591():
    # chain3_timeout_expired_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_expired_timeout']()), 6) == 0.0


def test_chain_contention_00591():
    # chain3_timeout_expired_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_expired_timeout']()) is False


def test_chain_transport_00592():
    # chain3_timeout_expired_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_expired_timeout']()) is True


def test_chain_admitted_00593():
    # chain3_timeout_expired_timeout
    error = _SHAPE_BUILDERS['chain3_timeout_expired_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00594():
    # chain3_timeout_expired_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_expired_value']()), 6) == 0.0


def test_chain_contention_00594():
    # chain3_timeout_expired_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_expired_value']()) is False


def test_chain_transport_00595():
    # chain3_timeout_expired_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_expired_value']()) is True


def test_chain_admitted_00596():
    # chain3_timeout_expired_value
    error = _SHAPE_BUILDERS['chain3_timeout_expired_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00597():
    # chain3_timeout_expired_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_expired_wrapper']()), 6) == 0.0


def test_chain_contention_00597():
    # chain3_timeout_expired_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_expired_wrapper']()) is False


def test_chain_transport_00598():
    # chain3_timeout_expired_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_expired_wrapper']()) is True


def test_chain_admitted_00599():
    # chain3_timeout_expired_wrapper
    error = _SHAPE_BUILDERS['chain3_timeout_expired_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00600():
    # chain4_timeout_expired_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00600():
    # chain4_timeout_expired_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_aborted']()) is True


def test_chain_transport_00601():
    # chain4_timeout_expired_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_aborted']()) is True


def test_chain_admitted_00602():
    # chain4_timeout_expired_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_timeout_expired_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00603():
    # chain4_timeout_expired_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00603():
    # chain4_timeout_expired_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_expired']()) is True


def test_chain_transport_00604():
    # chain4_timeout_expired_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_expired']()) is True


def test_chain_admitted_00605():
    # chain4_timeout_expired_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_timeout_expired_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00606():
    # chain4_timeout_expired_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00606():
    # chain4_timeout_expired_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_invalid']()) is False


def test_chain_transport_00607():
    # chain4_timeout_expired_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_invalid']()) is True


def test_chain_admitted_00608():
    # chain4_timeout_expired_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_timeout_expired_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00609():
    # chain4_timeout_expired_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00609():
    # chain4_timeout_expired_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_timeout']()) is False


def test_chain_transport_00610():
    # chain4_timeout_expired_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_timeout']()) is True


def test_chain_admitted_00611():
    # chain4_timeout_expired_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_timeout_expired_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00612():
    # chain4_timeout_expired_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_value']()), 6) == 0.0


def test_chain_contention_00612():
    # chain4_timeout_expired_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_value']()) is False


def test_chain_transport_00613():
    # chain4_timeout_expired_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_expired_wrapper_value']()) is True


def test_chain_admitted_00614():
    # chain4_timeout_expired_wrapper_value
    error = _SHAPE_BUILDERS['chain4_timeout_expired_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00615():
    # chain3_timeout_invalid_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_invalid_aborted']()), 6) == 0.0


def test_chain_contention_00615():
    # chain3_timeout_invalid_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_invalid_aborted']()) is True


def test_chain_transport_00616():
    # chain3_timeout_invalid_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_invalid_aborted']()) is True


def test_chain_admitted_00617():
    # chain3_timeout_invalid_aborted
    error = _SHAPE_BUILDERS['chain3_timeout_invalid_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00618():
    # chain3_timeout_invalid_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_invalid_expired']()), 6) == 0.0


def test_chain_contention_00618():
    # chain3_timeout_invalid_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_invalid_expired']()) is True


def test_chain_transport_00619():
    # chain3_timeout_invalid_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_invalid_expired']()) is True


def test_chain_admitted_00620():
    # chain3_timeout_invalid_expired
    error = _SHAPE_BUILDERS['chain3_timeout_invalid_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00621():
    # chain3_timeout_invalid_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_invalid_invalid']()), 6) == 0.0


def test_chain_contention_00621():
    # chain3_timeout_invalid_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_invalid_invalid']()) is False


def test_chain_transport_00622():
    # chain3_timeout_invalid_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_invalid_invalid']()) is True


def test_chain_admitted_00623():
    # chain3_timeout_invalid_invalid
    error = _SHAPE_BUILDERS['chain3_timeout_invalid_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00624():
    # chain3_timeout_invalid_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_invalid_timeout']()), 6) == 0.0


def test_chain_contention_00624():
    # chain3_timeout_invalid_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_invalid_timeout']()) is False


def test_chain_transport_00625():
    # chain3_timeout_invalid_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_invalid_timeout']()) is True


def test_chain_admitted_00626():
    # chain3_timeout_invalid_timeout
    error = _SHAPE_BUILDERS['chain3_timeout_invalid_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00627():
    # chain3_timeout_invalid_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_invalid_value']()), 6) == 0.0


def test_chain_contention_00627():
    # chain3_timeout_invalid_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_invalid_value']()) is False


def test_chain_transport_00628():
    # chain3_timeout_invalid_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_invalid_value']()) is True


def test_chain_admitted_00629():
    # chain3_timeout_invalid_value
    error = _SHAPE_BUILDERS['chain3_timeout_invalid_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00630():
    # chain3_timeout_invalid_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_invalid_wrapper']()), 6) == 0.0


def test_chain_contention_00630():
    # chain3_timeout_invalid_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_invalid_wrapper']()) is False


def test_chain_transport_00631():
    # chain3_timeout_invalid_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_invalid_wrapper']()) is True


def test_chain_admitted_00632():
    # chain3_timeout_invalid_wrapper
    error = _SHAPE_BUILDERS['chain3_timeout_invalid_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00633():
    # chain4_timeout_invalid_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00633():
    # chain4_timeout_invalid_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_aborted']()) is True


def test_chain_transport_00634():
    # chain4_timeout_invalid_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_aborted']()) is True


def test_chain_admitted_00635():
    # chain4_timeout_invalid_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00636():
    # chain4_timeout_invalid_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00636():
    # chain4_timeout_invalid_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_expired']()) is True


def test_chain_transport_00637():
    # chain4_timeout_invalid_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_expired']()) is True


def test_chain_admitted_00638():
    # chain4_timeout_invalid_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00639():
    # chain4_timeout_invalid_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00639():
    # chain4_timeout_invalid_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_invalid']()) is False


def test_chain_transport_00640():
    # chain4_timeout_invalid_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_invalid']()) is True


def test_chain_admitted_00641():
    # chain4_timeout_invalid_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00642():
    # chain4_timeout_invalid_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00642():
    # chain4_timeout_invalid_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_timeout']()) is False


def test_chain_transport_00643():
    # chain4_timeout_invalid_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_timeout']()) is True


def test_chain_admitted_00644():
    # chain4_timeout_invalid_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00645():
    # chain4_timeout_invalid_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_value']()), 6) == 0.0


def test_chain_contention_00645():
    # chain4_timeout_invalid_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_value']()) is False


def test_chain_transport_00646():
    # chain4_timeout_invalid_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_value']()) is True


def test_chain_admitted_00647():
    # chain4_timeout_invalid_wrapper_value
    error = _SHAPE_BUILDERS['chain4_timeout_invalid_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00648():
    # chain3_timeout_timeout_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_timeout_aborted']()), 6) == 0.0


def test_chain_contention_00648():
    # chain3_timeout_timeout_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_timeout_aborted']()) is True


def test_chain_transport_00649():
    # chain3_timeout_timeout_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_timeout_aborted']()) is True


def test_chain_admitted_00650():
    # chain3_timeout_timeout_aborted
    error = _SHAPE_BUILDERS['chain3_timeout_timeout_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00651():
    # chain3_timeout_timeout_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_timeout_expired']()), 6) == 0.0


def test_chain_contention_00651():
    # chain3_timeout_timeout_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_timeout_expired']()) is True


def test_chain_transport_00652():
    # chain3_timeout_timeout_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_timeout_expired']()) is True


def test_chain_admitted_00653():
    # chain3_timeout_timeout_expired
    error = _SHAPE_BUILDERS['chain3_timeout_timeout_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00654():
    # chain3_timeout_timeout_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_timeout_invalid']()), 6) == 0.0


def test_chain_contention_00654():
    # chain3_timeout_timeout_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_timeout_invalid']()) is False


def test_chain_transport_00655():
    # chain3_timeout_timeout_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_timeout_invalid']()) is True


def test_chain_admitted_00656():
    # chain3_timeout_timeout_invalid
    error = _SHAPE_BUILDERS['chain3_timeout_timeout_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00657():
    # chain3_timeout_timeout_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_timeout_timeout']()), 6) == 0.0


def test_chain_contention_00657():
    # chain3_timeout_timeout_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_timeout_timeout']()) is False


def test_chain_transport_00658():
    # chain3_timeout_timeout_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_timeout_timeout']()) is True


def test_chain_admitted_00659():
    # chain3_timeout_timeout_timeout
    error = _SHAPE_BUILDERS['chain3_timeout_timeout_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00660():
    # chain3_timeout_timeout_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_timeout_value']()), 6) == 0.0


def test_chain_contention_00660():
    # chain3_timeout_timeout_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_timeout_value']()) is False


def test_chain_transport_00661():
    # chain3_timeout_timeout_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_timeout_value']()) is True


def test_chain_admitted_00662():
    # chain3_timeout_timeout_value
    error = _SHAPE_BUILDERS['chain3_timeout_timeout_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00663():
    # chain3_timeout_timeout_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_timeout_wrapper']()), 6) == 0.0


def test_chain_contention_00663():
    # chain3_timeout_timeout_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_timeout_wrapper']()) is False


def test_chain_transport_00664():
    # chain3_timeout_timeout_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_timeout_wrapper']()) is True


def test_chain_admitted_00665():
    # chain3_timeout_timeout_wrapper
    error = _SHAPE_BUILDERS['chain3_timeout_timeout_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00666():
    # chain4_timeout_timeout_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00666():
    # chain4_timeout_timeout_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_aborted']()) is True


def test_chain_transport_00667():
    # chain4_timeout_timeout_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_aborted']()) is True


def test_chain_admitted_00668():
    # chain4_timeout_timeout_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00669():
    # chain4_timeout_timeout_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00669():
    # chain4_timeout_timeout_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_expired']()) is True


def test_chain_transport_00670():
    # chain4_timeout_timeout_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_expired']()) is True


def test_chain_admitted_00671():
    # chain4_timeout_timeout_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00672():
    # chain4_timeout_timeout_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00672():
    # chain4_timeout_timeout_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_invalid']()) is False


def test_chain_transport_00673():
    # chain4_timeout_timeout_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_invalid']()) is True


def test_chain_admitted_00674():
    # chain4_timeout_timeout_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00675():
    # chain4_timeout_timeout_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00675():
    # chain4_timeout_timeout_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_timeout']()) is False


def test_chain_transport_00676():
    # chain4_timeout_timeout_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_timeout']()) is True


def test_chain_admitted_00677():
    # chain4_timeout_timeout_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00678():
    # chain4_timeout_timeout_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_value']()), 6) == 0.0


def test_chain_contention_00678():
    # chain4_timeout_timeout_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_value']()) is False


def test_chain_transport_00679():
    # chain4_timeout_timeout_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_value']()) is True


def test_chain_admitted_00680():
    # chain4_timeout_timeout_wrapper_value
    error = _SHAPE_BUILDERS['chain4_timeout_timeout_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00681():
    # chain3_timeout_value_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_value_aborted']()), 6) == 0.0


def test_chain_contention_00681():
    # chain3_timeout_value_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_value_aborted']()) is True


def test_chain_transport_00682():
    # chain3_timeout_value_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_value_aborted']()) is True


def test_chain_admitted_00683():
    # chain3_timeout_value_aborted
    error = _SHAPE_BUILDERS['chain3_timeout_value_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00684():
    # chain3_timeout_value_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_value_expired']()), 6) == 0.0


def test_chain_contention_00684():
    # chain3_timeout_value_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_value_expired']()) is True


def test_chain_transport_00685():
    # chain3_timeout_value_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_value_expired']()) is True


def test_chain_admitted_00686():
    # chain3_timeout_value_expired
    error = _SHAPE_BUILDERS['chain3_timeout_value_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00687():
    # chain3_timeout_value_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_value_invalid']()), 6) == 0.0


def test_chain_contention_00687():
    # chain3_timeout_value_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_value_invalid']()) is False


def test_chain_transport_00688():
    # chain3_timeout_value_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_value_invalid']()) is True


def test_chain_admitted_00689():
    # chain3_timeout_value_invalid
    error = _SHAPE_BUILDERS['chain3_timeout_value_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00690():
    # chain3_timeout_value_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_value_timeout']()), 6) == 0.0


def test_chain_contention_00690():
    # chain3_timeout_value_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_value_timeout']()) is False


def test_chain_transport_00691():
    # chain3_timeout_value_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_value_timeout']()) is True


def test_chain_admitted_00692():
    # chain3_timeout_value_timeout
    error = _SHAPE_BUILDERS['chain3_timeout_value_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00693():
    # chain3_timeout_value_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_value_value']()), 6) == 0.0


def test_chain_contention_00693():
    # chain3_timeout_value_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_value_value']()) is False


def test_chain_transport_00694():
    # chain3_timeout_value_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_value_value']()) is True


def test_chain_admitted_00695():
    # chain3_timeout_value_value
    error = _SHAPE_BUILDERS['chain3_timeout_value_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00696():
    # chain3_timeout_value_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_value_wrapper']()), 6) == 0.0


def test_chain_contention_00696():
    # chain3_timeout_value_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_value_wrapper']()) is False


def test_chain_transport_00697():
    # chain3_timeout_value_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_value_wrapper']()) is True


def test_chain_admitted_00698():
    # chain3_timeout_value_wrapper
    error = _SHAPE_BUILDERS['chain3_timeout_value_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00699():
    # chain4_timeout_value_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00699():
    # chain4_timeout_value_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_aborted']()) is True


def test_chain_transport_00700():
    # chain4_timeout_value_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_aborted']()) is True


def test_chain_admitted_00701():
    # chain4_timeout_value_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_timeout_value_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00702():
    # chain4_timeout_value_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00702():
    # chain4_timeout_value_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_expired']()) is True


def test_chain_transport_00703():
    # chain4_timeout_value_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_expired']()) is True


def test_chain_admitted_00704():
    # chain4_timeout_value_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_timeout_value_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00705():
    # chain4_timeout_value_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00705():
    # chain4_timeout_value_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_invalid']()) is False


def test_chain_transport_00706():
    # chain4_timeout_value_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_invalid']()) is True


def test_chain_admitted_00707():
    # chain4_timeout_value_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_timeout_value_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00708():
    # chain4_timeout_value_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00708():
    # chain4_timeout_value_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_timeout']()) is False


def test_chain_transport_00709():
    # chain4_timeout_value_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_timeout']()) is True


def test_chain_admitted_00710():
    # chain4_timeout_value_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_timeout_value_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00711():
    # chain4_timeout_value_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_value']()), 6) == 0.0


def test_chain_contention_00711():
    # chain4_timeout_value_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_value']()) is False


def test_chain_transport_00712():
    # chain4_timeout_value_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_timeout_value_wrapper_value']()) is True


def test_chain_admitted_00713():
    # chain4_timeout_value_wrapper_value
    error = _SHAPE_BUILDERS['chain4_timeout_value_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00714():
    # chain3_timeout_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00714():
    # chain3_timeout_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_wrapper_aborted']()) is True


def test_chain_transport_00715():
    # chain3_timeout_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_wrapper_aborted']()) is True


def test_chain_admitted_00716():
    # chain3_timeout_wrapper_aborted
    error = _SHAPE_BUILDERS['chain3_timeout_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00717():
    # chain3_timeout_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00717():
    # chain3_timeout_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_wrapper_expired']()) is True


def test_chain_transport_00718():
    # chain3_timeout_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_wrapper_expired']()) is True


def test_chain_admitted_00719():
    # chain3_timeout_wrapper_expired
    error = _SHAPE_BUILDERS['chain3_timeout_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00720():
    # chain3_timeout_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00720():
    # chain3_timeout_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_wrapper_invalid']()) is False


def test_chain_transport_00721():
    # chain3_timeout_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_wrapper_invalid']()) is True


def test_chain_admitted_00722():
    # chain3_timeout_wrapper_invalid
    error = _SHAPE_BUILDERS['chain3_timeout_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00723():
    # chain3_timeout_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00723():
    # chain3_timeout_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_wrapper_timeout']()) is False


def test_chain_transport_00724():
    # chain3_timeout_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_wrapper_timeout']()) is True


def test_chain_admitted_00725():
    # chain3_timeout_wrapper_timeout
    error = _SHAPE_BUILDERS['chain3_timeout_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00726():
    # chain3_timeout_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_wrapper_value']()), 6) == 0.0


def test_chain_contention_00726():
    # chain3_timeout_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_wrapper_value']()) is False


def test_chain_transport_00727():
    # chain3_timeout_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_wrapper_value']()) is True


def test_chain_admitted_00728():
    # chain3_timeout_wrapper_value
    error = _SHAPE_BUILDERS['chain3_timeout_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00729():
    # chain3_timeout_wrapper_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_timeout_wrapper_wrapper']()), 6) == 0.0


def test_chain_contention_00729():
    # chain3_timeout_wrapper_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_timeout_wrapper_wrapper']()) is False


def test_chain_transport_00730():
    # chain3_timeout_wrapper_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_timeout_wrapper_wrapper']()) is True


def test_chain_admitted_00731():
    # chain3_timeout_wrapper_wrapper
    error = _SHAPE_BUILDERS['chain3_timeout_wrapper_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00732():
    # chain3_value_aborted_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_aborted_aborted']()), 6) == 0.0


def test_chain_contention_00732():
    # chain3_value_aborted_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_aborted_aborted']()) is True


def test_chain_transport_00733():
    # chain3_value_aborted_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_aborted_aborted']()) is False


def test_chain_admitted_00734():
    # chain3_value_aborted_aborted
    error = _SHAPE_BUILDERS['chain3_value_aborted_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00735():
    # chain3_value_aborted_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_aborted_expired']()), 6) == 0.0


def test_chain_contention_00735():
    # chain3_value_aborted_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_aborted_expired']()) is True


def test_chain_transport_00736():
    # chain3_value_aborted_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_aborted_expired']()) is False


def test_chain_admitted_00737():
    # chain3_value_aborted_expired
    error = _SHAPE_BUILDERS['chain3_value_aborted_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00738():
    # chain3_value_aborted_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_aborted_invalid']()), 6) == 0.0


def test_chain_contention_00738():
    # chain3_value_aborted_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_aborted_invalid']()) is False


def test_chain_transport_00739():
    # chain3_value_aborted_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_aborted_invalid']()) is False


def test_chain_admitted_00740():
    # chain3_value_aborted_invalid
    error = _SHAPE_BUILDERS['chain3_value_aborted_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00741():
    # chain3_value_aborted_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_aborted_timeout']()), 6) == 0.0


def test_chain_contention_00741():
    # chain3_value_aborted_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_aborted_timeout']()) is False


def test_chain_transport_00742():
    # chain3_value_aborted_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_aborted_timeout']()) is False


def test_chain_admitted_00743():
    # chain3_value_aborted_timeout
    error = _SHAPE_BUILDERS['chain3_value_aborted_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00744():
    # chain3_value_aborted_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_aborted_value']()), 6) == 0.0


def test_chain_contention_00744():
    # chain3_value_aborted_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_aborted_value']()) is False


def test_chain_transport_00745():
    # chain3_value_aborted_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_aborted_value']()) is False


def test_chain_admitted_00746():
    # chain3_value_aborted_value
    error = _SHAPE_BUILDERS['chain3_value_aborted_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00747():
    # chain3_value_aborted_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_aborted_wrapper']()), 6) == 0.0


def test_chain_contention_00747():
    # chain3_value_aborted_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_aborted_wrapper']()) is False


def test_chain_transport_00748():
    # chain3_value_aborted_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_aborted_wrapper']()) is False


def test_chain_admitted_00749():
    # chain3_value_aborted_wrapper
    error = _SHAPE_BUILDERS['chain3_value_aborted_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00750():
    # chain4_value_aborted_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00750():
    # chain4_value_aborted_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_aborted']()) is True


def test_chain_transport_00751():
    # chain4_value_aborted_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_aborted']()) is False


def test_chain_admitted_00752():
    # chain4_value_aborted_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_value_aborted_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00753():
    # chain4_value_aborted_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00753():
    # chain4_value_aborted_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_expired']()) is True


def test_chain_transport_00754():
    # chain4_value_aborted_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_expired']()) is False


def test_chain_admitted_00755():
    # chain4_value_aborted_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_value_aborted_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00756():
    # chain4_value_aborted_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00756():
    # chain4_value_aborted_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_invalid']()) is False


def test_chain_transport_00757():
    # chain4_value_aborted_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_invalid']()) is False


def test_chain_admitted_00758():
    # chain4_value_aborted_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_value_aborted_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00759():
    # chain4_value_aborted_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00759():
    # chain4_value_aborted_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_timeout']()) is False


def test_chain_transport_00760():
    # chain4_value_aborted_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_timeout']()) is False


def test_chain_admitted_00761():
    # chain4_value_aborted_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_value_aborted_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00762():
    # chain4_value_aborted_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_value']()), 6) == 0.0


def test_chain_contention_00762():
    # chain4_value_aborted_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_value']()) is False


def test_chain_transport_00763():
    # chain4_value_aborted_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_aborted_wrapper_value']()) is False


def test_chain_admitted_00764():
    # chain4_value_aborted_wrapper_value
    error = _SHAPE_BUILDERS['chain4_value_aborted_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00765():
    # chain3_value_expired_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_expired_aborted']()), 6) == 0.0


def test_chain_contention_00765():
    # chain3_value_expired_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_expired_aborted']()) is True


def test_chain_transport_00766():
    # chain3_value_expired_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_expired_aborted']()) is False


def test_chain_admitted_00767():
    # chain3_value_expired_aborted
    error = _SHAPE_BUILDERS['chain3_value_expired_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00768():
    # chain3_value_expired_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_expired_expired']()), 6) == 0.0


def test_chain_contention_00768():
    # chain3_value_expired_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_expired_expired']()) is True


def test_chain_transport_00769():
    # chain3_value_expired_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_expired_expired']()) is False


def test_chain_admitted_00770():
    # chain3_value_expired_expired
    error = _SHAPE_BUILDERS['chain3_value_expired_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00771():
    # chain3_value_expired_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_expired_invalid']()), 6) == 0.0


def test_chain_contention_00771():
    # chain3_value_expired_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_expired_invalid']()) is False


def test_chain_transport_00772():
    # chain3_value_expired_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_expired_invalid']()) is False


def test_chain_admitted_00773():
    # chain3_value_expired_invalid
    error = _SHAPE_BUILDERS['chain3_value_expired_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00774():
    # chain3_value_expired_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_expired_timeout']()), 6) == 0.0


def test_chain_contention_00774():
    # chain3_value_expired_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_expired_timeout']()) is False


def test_chain_transport_00775():
    # chain3_value_expired_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_expired_timeout']()) is False


def test_chain_admitted_00776():
    # chain3_value_expired_timeout
    error = _SHAPE_BUILDERS['chain3_value_expired_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00777():
    # chain3_value_expired_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_expired_value']()), 6) == 0.0


def test_chain_contention_00777():
    # chain3_value_expired_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_expired_value']()) is False


def test_chain_transport_00778():
    # chain3_value_expired_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_expired_value']()) is False


def test_chain_admitted_00779():
    # chain3_value_expired_value
    error = _SHAPE_BUILDERS['chain3_value_expired_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00780():
    # chain3_value_expired_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_expired_wrapper']()), 6) == 0.0


def test_chain_contention_00780():
    # chain3_value_expired_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_expired_wrapper']()) is False


def test_chain_transport_00781():
    # chain3_value_expired_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_expired_wrapper']()) is False


def test_chain_admitted_00782():
    # chain3_value_expired_wrapper
    error = _SHAPE_BUILDERS['chain3_value_expired_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00783():
    # chain4_value_expired_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_expired_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00783():
    # chain4_value_expired_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_expired_wrapper_aborted']()) is True


def test_chain_transport_00784():
    # chain4_value_expired_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_expired_wrapper_aborted']()) is False


def test_chain_admitted_00785():
    # chain4_value_expired_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_value_expired_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00786():
    # chain4_value_expired_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_expired_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00786():
    # chain4_value_expired_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_expired_wrapper_expired']()) is True


def test_chain_transport_00787():
    # chain4_value_expired_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_expired_wrapper_expired']()) is False


def test_chain_admitted_00788():
    # chain4_value_expired_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_value_expired_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00789():
    # chain4_value_expired_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_expired_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00789():
    # chain4_value_expired_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_expired_wrapper_invalid']()) is False


def test_chain_transport_00790():
    # chain4_value_expired_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_expired_wrapper_invalid']()) is False


def test_chain_admitted_00791():
    # chain4_value_expired_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_value_expired_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00792():
    # chain4_value_expired_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_expired_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00792():
    # chain4_value_expired_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_expired_wrapper_timeout']()) is False


def test_chain_transport_00793():
    # chain4_value_expired_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_expired_wrapper_timeout']()) is False


def test_chain_admitted_00794():
    # chain4_value_expired_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_value_expired_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00795():
    # chain4_value_expired_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_expired_wrapper_value']()), 6) == 0.0


def test_chain_contention_00795():
    # chain4_value_expired_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_expired_wrapper_value']()) is False


def test_chain_transport_00796():
    # chain4_value_expired_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_expired_wrapper_value']()) is False


def test_chain_admitted_00797():
    # chain4_value_expired_wrapper_value
    error = _SHAPE_BUILDERS['chain4_value_expired_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00798():
    # chain3_value_invalid_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_invalid_aborted']()), 6) == 0.0


def test_chain_contention_00798():
    # chain3_value_invalid_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_invalid_aborted']()) is True


def test_chain_transport_00799():
    # chain3_value_invalid_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_invalid_aborted']()) is False


def test_chain_admitted_00800():
    # chain3_value_invalid_aborted
    error = _SHAPE_BUILDERS['chain3_value_invalid_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00801():
    # chain3_value_invalid_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_invalid_expired']()), 6) == 0.0


def test_chain_contention_00801():
    # chain3_value_invalid_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_invalid_expired']()) is True


def test_chain_transport_00802():
    # chain3_value_invalid_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_invalid_expired']()) is False


def test_chain_admitted_00803():
    # chain3_value_invalid_expired
    error = _SHAPE_BUILDERS['chain3_value_invalid_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00804():
    # chain3_value_invalid_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_invalid_invalid']()), 6) == 0.0


def test_chain_contention_00804():
    # chain3_value_invalid_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_invalid_invalid']()) is False


def test_chain_transport_00805():
    # chain3_value_invalid_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_invalid_invalid']()) is False


def test_chain_admitted_00806():
    # chain3_value_invalid_invalid
    error = _SHAPE_BUILDERS['chain3_value_invalid_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00807():
    # chain3_value_invalid_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_invalid_timeout']()), 6) == 0.0


def test_chain_contention_00807():
    # chain3_value_invalid_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_invalid_timeout']()) is False


def test_chain_transport_00808():
    # chain3_value_invalid_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_invalid_timeout']()) is False


def test_chain_admitted_00809():
    # chain3_value_invalid_timeout
    error = _SHAPE_BUILDERS['chain3_value_invalid_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00810():
    # chain3_value_invalid_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_invalid_value']()), 6) == 0.0


def test_chain_contention_00810():
    # chain3_value_invalid_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_invalid_value']()) is False


def test_chain_transport_00811():
    # chain3_value_invalid_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_invalid_value']()) is False


def test_chain_admitted_00812():
    # chain3_value_invalid_value
    error = _SHAPE_BUILDERS['chain3_value_invalid_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00813():
    # chain3_value_invalid_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_invalid_wrapper']()), 6) == 0.0


def test_chain_contention_00813():
    # chain3_value_invalid_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_invalid_wrapper']()) is False


def test_chain_transport_00814():
    # chain3_value_invalid_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_invalid_wrapper']()) is False


def test_chain_admitted_00815():
    # chain3_value_invalid_wrapper
    error = _SHAPE_BUILDERS['chain3_value_invalid_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00816():
    # chain4_value_invalid_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00816():
    # chain4_value_invalid_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_aborted']()) is True


def test_chain_transport_00817():
    # chain4_value_invalid_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_aborted']()) is False


def test_chain_admitted_00818():
    # chain4_value_invalid_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_value_invalid_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00819():
    # chain4_value_invalid_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00819():
    # chain4_value_invalid_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_expired']()) is True


def test_chain_transport_00820():
    # chain4_value_invalid_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_expired']()) is False


def test_chain_admitted_00821():
    # chain4_value_invalid_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_value_invalid_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00822():
    # chain4_value_invalid_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00822():
    # chain4_value_invalid_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_invalid']()) is False


def test_chain_transport_00823():
    # chain4_value_invalid_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_invalid']()) is False


def test_chain_admitted_00824():
    # chain4_value_invalid_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_value_invalid_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00825():
    # chain4_value_invalid_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00825():
    # chain4_value_invalid_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_timeout']()) is False


def test_chain_transport_00826():
    # chain4_value_invalid_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_timeout']()) is False


def test_chain_admitted_00827():
    # chain4_value_invalid_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_value_invalid_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00828():
    # chain4_value_invalid_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_value']()), 6) == 0.0


def test_chain_contention_00828():
    # chain4_value_invalid_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_value']()) is False


def test_chain_transport_00829():
    # chain4_value_invalid_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_invalid_wrapper_value']()) is False


def test_chain_admitted_00830():
    # chain4_value_invalid_wrapper_value
    error = _SHAPE_BUILDERS['chain4_value_invalid_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00831():
    # chain3_value_timeout_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_timeout_aborted']()), 6) == 0.0


def test_chain_contention_00831():
    # chain3_value_timeout_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_timeout_aborted']()) is True


def test_chain_transport_00832():
    # chain3_value_timeout_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_timeout_aborted']()) is False


def test_chain_admitted_00833():
    # chain3_value_timeout_aborted
    error = _SHAPE_BUILDERS['chain3_value_timeout_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00834():
    # chain3_value_timeout_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_timeout_expired']()), 6) == 0.0


def test_chain_contention_00834():
    # chain3_value_timeout_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_timeout_expired']()) is True


def test_chain_transport_00835():
    # chain3_value_timeout_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_timeout_expired']()) is False


def test_chain_admitted_00836():
    # chain3_value_timeout_expired
    error = _SHAPE_BUILDERS['chain3_value_timeout_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00837():
    # chain3_value_timeout_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_timeout_invalid']()), 6) == 0.0


def test_chain_contention_00837():
    # chain3_value_timeout_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_timeout_invalid']()) is False


def test_chain_transport_00838():
    # chain3_value_timeout_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_timeout_invalid']()) is False


def test_chain_admitted_00839():
    # chain3_value_timeout_invalid
    error = _SHAPE_BUILDERS['chain3_value_timeout_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00840():
    # chain3_value_timeout_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_timeout_timeout']()), 6) == 0.0


def test_chain_contention_00840():
    # chain3_value_timeout_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_timeout_timeout']()) is False


def test_chain_transport_00841():
    # chain3_value_timeout_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_timeout_timeout']()) is False


def test_chain_admitted_00842():
    # chain3_value_timeout_timeout
    error = _SHAPE_BUILDERS['chain3_value_timeout_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00843():
    # chain3_value_timeout_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_timeout_value']()), 6) == 0.0


def test_chain_contention_00843():
    # chain3_value_timeout_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_timeout_value']()) is False


def test_chain_transport_00844():
    # chain3_value_timeout_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_timeout_value']()) is False


def test_chain_admitted_00845():
    # chain3_value_timeout_value
    error = _SHAPE_BUILDERS['chain3_value_timeout_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00846():
    # chain3_value_timeout_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_timeout_wrapper']()), 6) == 0.0


def test_chain_contention_00846():
    # chain3_value_timeout_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_timeout_wrapper']()) is False


def test_chain_transport_00847():
    # chain3_value_timeout_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_timeout_wrapper']()) is False


def test_chain_admitted_00848():
    # chain3_value_timeout_wrapper
    error = _SHAPE_BUILDERS['chain3_value_timeout_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00849():
    # chain4_value_timeout_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00849():
    # chain4_value_timeout_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_aborted']()) is True


def test_chain_transport_00850():
    # chain4_value_timeout_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_aborted']()) is False


def test_chain_admitted_00851():
    # chain4_value_timeout_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_value_timeout_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00852():
    # chain4_value_timeout_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00852():
    # chain4_value_timeout_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_expired']()) is True


def test_chain_transport_00853():
    # chain4_value_timeout_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_expired']()) is False


def test_chain_admitted_00854():
    # chain4_value_timeout_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_value_timeout_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00855():
    # chain4_value_timeout_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00855():
    # chain4_value_timeout_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_invalid']()) is False


def test_chain_transport_00856():
    # chain4_value_timeout_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_invalid']()) is False


def test_chain_admitted_00857():
    # chain4_value_timeout_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_value_timeout_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00858():
    # chain4_value_timeout_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00858():
    # chain4_value_timeout_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_timeout']()) is False


def test_chain_transport_00859():
    # chain4_value_timeout_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_timeout']()) is False


def test_chain_admitted_00860():
    # chain4_value_timeout_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_value_timeout_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00861():
    # chain4_value_timeout_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_value']()), 6) == 0.0


def test_chain_contention_00861():
    # chain4_value_timeout_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_value']()) is False


def test_chain_transport_00862():
    # chain4_value_timeout_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_timeout_wrapper_value']()) is False


def test_chain_admitted_00863():
    # chain4_value_timeout_wrapper_value
    error = _SHAPE_BUILDERS['chain4_value_timeout_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00864():
    # chain3_value_value_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_value_aborted']()), 6) == 0.0


def test_chain_contention_00864():
    # chain3_value_value_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_value_aborted']()) is True


def test_chain_transport_00865():
    # chain3_value_value_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_value_aborted']()) is False


def test_chain_admitted_00866():
    # chain3_value_value_aborted
    error = _SHAPE_BUILDERS['chain3_value_value_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00867():
    # chain3_value_value_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_value_expired']()), 6) == 0.0


def test_chain_contention_00867():
    # chain3_value_value_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_value_expired']()) is True


def test_chain_transport_00868():
    # chain3_value_value_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_value_expired']()) is False


def test_chain_admitted_00869():
    # chain3_value_value_expired
    error = _SHAPE_BUILDERS['chain3_value_value_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00870():
    # chain3_value_value_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_value_invalid']()), 6) == 0.0


def test_chain_contention_00870():
    # chain3_value_value_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_value_invalid']()) is False


def test_chain_transport_00871():
    # chain3_value_value_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_value_invalid']()) is False


def test_chain_admitted_00872():
    # chain3_value_value_invalid
    error = _SHAPE_BUILDERS['chain3_value_value_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00873():
    # chain3_value_value_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_value_timeout']()), 6) == 0.0


def test_chain_contention_00873():
    # chain3_value_value_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_value_timeout']()) is False


def test_chain_transport_00874():
    # chain3_value_value_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_value_timeout']()) is False


def test_chain_admitted_00875():
    # chain3_value_value_timeout
    error = _SHAPE_BUILDERS['chain3_value_value_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00876():
    # chain3_value_value_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_value_value']()), 6) == 0.0


def test_chain_contention_00876():
    # chain3_value_value_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_value_value']()) is False


def test_chain_transport_00877():
    # chain3_value_value_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_value_value']()) is False


def test_chain_admitted_00878():
    # chain3_value_value_value
    error = _SHAPE_BUILDERS['chain3_value_value_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00879():
    # chain3_value_value_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_value_wrapper']()), 6) == 0.0


def test_chain_contention_00879():
    # chain3_value_value_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_value_wrapper']()) is False


def test_chain_transport_00880():
    # chain3_value_value_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_value_wrapper']()) is False


def test_chain_admitted_00881():
    # chain3_value_value_wrapper
    error = _SHAPE_BUILDERS['chain3_value_value_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00882():
    # chain4_value_value_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_value_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00882():
    # chain4_value_value_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_value_wrapper_aborted']()) is True


def test_chain_transport_00883():
    # chain4_value_value_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_value_wrapper_aborted']()) is False


def test_chain_admitted_00884():
    # chain4_value_value_wrapper_aborted
    error = _SHAPE_BUILDERS['chain4_value_value_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00885():
    # chain4_value_value_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_value_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00885():
    # chain4_value_value_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_value_wrapper_expired']()) is True


def test_chain_transport_00886():
    # chain4_value_value_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_value_wrapper_expired']()) is False


def test_chain_admitted_00887():
    # chain4_value_value_wrapper_expired
    error = _SHAPE_BUILDERS['chain4_value_value_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00888():
    # chain4_value_value_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_value_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00888():
    # chain4_value_value_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_value_wrapper_invalid']()) is False


def test_chain_transport_00889():
    # chain4_value_value_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_value_wrapper_invalid']()) is False


def test_chain_admitted_00890():
    # chain4_value_value_wrapper_invalid
    error = _SHAPE_BUILDERS['chain4_value_value_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00891():
    # chain4_value_value_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_value_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00891():
    # chain4_value_value_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_value_wrapper_timeout']()) is False


def test_chain_transport_00892():
    # chain4_value_value_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_value_wrapper_timeout']()) is False


def test_chain_admitted_00893():
    # chain4_value_value_wrapper_timeout
    error = _SHAPE_BUILDERS['chain4_value_value_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00894():
    # chain4_value_value_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain4_value_value_wrapper_value']()), 6) == 0.0


def test_chain_contention_00894():
    # chain4_value_value_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain4_value_value_wrapper_value']()) is False


def test_chain_transport_00895():
    # chain4_value_value_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain4_value_value_wrapper_value']()) is False


def test_chain_admitted_00896():
    # chain4_value_value_wrapper_value
    error = _SHAPE_BUILDERS['chain4_value_value_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00897():
    # chain3_value_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_wrapper_aborted']()), 6) == 0.0


def test_chain_contention_00897():
    # chain3_value_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_wrapper_aborted']()) is True


def test_chain_transport_00898():
    # chain3_value_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_wrapper_aborted']()) is False


def test_chain_admitted_00899():
    # chain3_value_wrapper_aborted
    error = _SHAPE_BUILDERS['chain3_value_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00900():
    # chain3_value_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_wrapper_expired']()), 6) == 0.0


def test_chain_contention_00900():
    # chain3_value_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_wrapper_expired']()) is True


def test_chain_transport_00901():
    # chain3_value_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_wrapper_expired']()) is False


def test_chain_admitted_00902():
    # chain3_value_wrapper_expired
    error = _SHAPE_BUILDERS['chain3_value_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00903():
    # chain3_value_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_wrapper_invalid']()), 6) == 0.0


def test_chain_contention_00903():
    # chain3_value_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_wrapper_invalid']()) is False


def test_chain_transport_00904():
    # chain3_value_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_wrapper_invalid']()) is False


def test_chain_admitted_00905():
    # chain3_value_wrapper_invalid
    error = _SHAPE_BUILDERS['chain3_value_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00906():
    # chain3_value_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_wrapper_timeout']()), 6) == 0.0


def test_chain_contention_00906():
    # chain3_value_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_wrapper_timeout']()) is False


def test_chain_transport_00907():
    # chain3_value_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_wrapper_timeout']()) is False


def test_chain_admitted_00908():
    # chain3_value_wrapper_timeout
    error = _SHAPE_BUILDERS['chain3_value_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00909():
    # chain3_value_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_wrapper_value']()), 6) == 0.0


def test_chain_contention_00909():
    # chain3_value_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_wrapper_value']()) is False


def test_chain_transport_00910():
    # chain3_value_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_wrapper_value']()) is False


def test_chain_admitted_00911():
    # chain3_value_wrapper_value
    error = _SHAPE_BUILDERS['chain3_value_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00912():
    # chain3_value_wrapper_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_value_wrapper_wrapper']()), 6) == 0.0


def test_chain_contention_00912():
    # chain3_value_wrapper_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_value_wrapper_wrapper']()) is False


def test_chain_transport_00913():
    # chain3_value_wrapper_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_value_wrapper_wrapper']()) is False


def test_chain_admitted_00914():
    # chain3_value_wrapper_wrapper
    error = _SHAPE_BUILDERS['chain3_value_wrapper_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is False


def test_chain_storm_00915():
    # chain3_wrapper_aborted_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_aborted_aborted']()), 6) == 1.25


def test_chain_contention_00915():
    # chain3_wrapper_aborted_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_aborted_aborted']()) is True


def test_chain_transport_00916():
    # chain3_wrapper_aborted_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_aborted_aborted']()) is False


def test_chain_admitted_00917():
    # chain3_wrapper_aborted_aborted
    error = _SHAPE_BUILDERS['chain3_wrapper_aborted_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00918():
    # chain3_wrapper_aborted_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_aborted_expired']()), 6) == 1.25


def test_chain_contention_00918():
    # chain3_wrapper_aborted_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_aborted_expired']()) is True


def test_chain_transport_00919():
    # chain3_wrapper_aborted_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_aborted_expired']()) is False


def test_chain_admitted_00920():
    # chain3_wrapper_aborted_expired
    error = _SHAPE_BUILDERS['chain3_wrapper_aborted_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00921():
    # chain3_wrapper_aborted_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_aborted_invalid']()), 6) == 1.25


def test_chain_contention_00921():
    # chain3_wrapper_aborted_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_aborted_invalid']()) is True


def test_chain_transport_00922():
    # chain3_wrapper_aborted_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_aborted_invalid']()) is False


def test_chain_admitted_00923():
    # chain3_wrapper_aborted_invalid
    error = _SHAPE_BUILDERS['chain3_wrapper_aborted_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00924():
    # chain3_wrapper_aborted_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_aborted_timeout']()), 6) == 1.25


def test_chain_contention_00924():
    # chain3_wrapper_aborted_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_aborted_timeout']()) is True


def test_chain_transport_00925():
    # chain3_wrapper_aborted_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_aborted_timeout']()) is False


def test_chain_admitted_00926():
    # chain3_wrapper_aborted_timeout
    error = _SHAPE_BUILDERS['chain3_wrapper_aborted_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00927():
    # chain3_wrapper_aborted_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_aborted_value']()), 6) == 1.25


def test_chain_contention_00927():
    # chain3_wrapper_aborted_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_aborted_value']()) is True


def test_chain_transport_00928():
    # chain3_wrapper_aborted_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_aborted_value']()) is False


def test_chain_admitted_00929():
    # chain3_wrapper_aborted_value
    error = _SHAPE_BUILDERS['chain3_wrapper_aborted_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00930():
    # chain3_wrapper_aborted_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_aborted_wrapper']()), 6) == 1.25


def test_chain_contention_00930():
    # chain3_wrapper_aborted_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_aborted_wrapper']()) is True


def test_chain_transport_00931():
    # chain3_wrapper_aborted_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_aborted_wrapper']()) is False


def test_chain_admitted_00932():
    # chain3_wrapper_aborted_wrapper
    error = _SHAPE_BUILDERS['chain3_wrapper_aborted_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00933():
    # chain3_wrapper_expired_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_expired_aborted']()), 6) == 1.25


def test_chain_contention_00933():
    # chain3_wrapper_expired_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_expired_aborted']()) is True


def test_chain_transport_00934():
    # chain3_wrapper_expired_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_expired_aborted']()) is False


def test_chain_admitted_00935():
    # chain3_wrapper_expired_aborted
    error = _SHAPE_BUILDERS['chain3_wrapper_expired_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00936():
    # chain3_wrapper_expired_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_expired_expired']()), 6) == 1.25


def test_chain_contention_00936():
    # chain3_wrapper_expired_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_expired_expired']()) is True


def test_chain_transport_00937():
    # chain3_wrapper_expired_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_expired_expired']()) is False


def test_chain_admitted_00938():
    # chain3_wrapper_expired_expired
    error = _SHAPE_BUILDERS['chain3_wrapper_expired_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00939():
    # chain3_wrapper_expired_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_expired_invalid']()), 6) == 1.25


def test_chain_contention_00939():
    # chain3_wrapper_expired_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_expired_invalid']()) is True


def test_chain_transport_00940():
    # chain3_wrapper_expired_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_expired_invalid']()) is False


def test_chain_admitted_00941():
    # chain3_wrapper_expired_invalid
    error = _SHAPE_BUILDERS['chain3_wrapper_expired_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00942():
    # chain3_wrapper_expired_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_expired_timeout']()), 6) == 1.25


def test_chain_contention_00942():
    # chain3_wrapper_expired_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_expired_timeout']()) is True


def test_chain_transport_00943():
    # chain3_wrapper_expired_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_expired_timeout']()) is False


def test_chain_admitted_00944():
    # chain3_wrapper_expired_timeout
    error = _SHAPE_BUILDERS['chain3_wrapper_expired_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00945():
    # chain3_wrapper_expired_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_expired_value']()), 6) == 1.25


def test_chain_contention_00945():
    # chain3_wrapper_expired_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_expired_value']()) is True


def test_chain_transport_00946():
    # chain3_wrapper_expired_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_expired_value']()) is False


def test_chain_admitted_00947():
    # chain3_wrapper_expired_value
    error = _SHAPE_BUILDERS['chain3_wrapper_expired_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00948():
    # chain3_wrapper_expired_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_expired_wrapper']()), 6) == 1.25


def test_chain_contention_00948():
    # chain3_wrapper_expired_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_expired_wrapper']()) is True


def test_chain_transport_00949():
    # chain3_wrapper_expired_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_expired_wrapper']()) is False


def test_chain_admitted_00950():
    # chain3_wrapper_expired_wrapper
    error = _SHAPE_BUILDERS['chain3_wrapper_expired_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00951():
    # chain3_wrapper_invalid_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_invalid_aborted']()), 6) == 1.25


def test_chain_contention_00951():
    # chain3_wrapper_invalid_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_invalid_aborted']()) is True


def test_chain_transport_00952():
    # chain3_wrapper_invalid_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_invalid_aborted']()) is False


def test_chain_admitted_00953():
    # chain3_wrapper_invalid_aborted
    error = _SHAPE_BUILDERS['chain3_wrapper_invalid_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00954():
    # chain3_wrapper_invalid_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_invalid_expired']()), 6) == 1.25


def test_chain_contention_00954():
    # chain3_wrapper_invalid_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_invalid_expired']()) is True


def test_chain_transport_00955():
    # chain3_wrapper_invalid_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_invalid_expired']()) is False


def test_chain_admitted_00956():
    # chain3_wrapper_invalid_expired
    error = _SHAPE_BUILDERS['chain3_wrapper_invalid_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00957():
    # chain3_wrapper_invalid_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_invalid_invalid']()), 6) == 1.25


def test_chain_contention_00957():
    # chain3_wrapper_invalid_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_invalid_invalid']()) is True


def test_chain_transport_00958():
    # chain3_wrapper_invalid_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_invalid_invalid']()) is False


def test_chain_admitted_00959():
    # chain3_wrapper_invalid_invalid
    error = _SHAPE_BUILDERS['chain3_wrapper_invalid_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00960():
    # chain3_wrapper_invalid_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_invalid_timeout']()), 6) == 1.25


def test_chain_contention_00960():
    # chain3_wrapper_invalid_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_invalid_timeout']()) is True


def test_chain_transport_00961():
    # chain3_wrapper_invalid_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_invalid_timeout']()) is False


def test_chain_admitted_00962():
    # chain3_wrapper_invalid_timeout
    error = _SHAPE_BUILDERS['chain3_wrapper_invalid_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00963():
    # chain3_wrapper_invalid_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_invalid_value']()), 6) == 1.25


def test_chain_contention_00963():
    # chain3_wrapper_invalid_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_invalid_value']()) is True


def test_chain_transport_00964():
    # chain3_wrapper_invalid_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_invalid_value']()) is False


def test_chain_admitted_00965():
    # chain3_wrapper_invalid_value
    error = _SHAPE_BUILDERS['chain3_wrapper_invalid_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00966():
    # chain3_wrapper_invalid_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_invalid_wrapper']()), 6) == 1.25


def test_chain_contention_00966():
    # chain3_wrapper_invalid_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_invalid_wrapper']()) is True


def test_chain_transport_00967():
    # chain3_wrapper_invalid_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_invalid_wrapper']()) is False


def test_chain_admitted_00968():
    # chain3_wrapper_invalid_wrapper
    error = _SHAPE_BUILDERS['chain3_wrapper_invalid_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00969():
    # chain3_wrapper_timeout_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_timeout_aborted']()), 6) == 1.25


def test_chain_contention_00969():
    # chain3_wrapper_timeout_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_timeout_aborted']()) is True


def test_chain_transport_00970():
    # chain3_wrapper_timeout_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_timeout_aborted']()) is False


def test_chain_admitted_00971():
    # chain3_wrapper_timeout_aborted
    error = _SHAPE_BUILDERS['chain3_wrapper_timeout_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00972():
    # chain3_wrapper_timeout_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_timeout_expired']()), 6) == 1.25


def test_chain_contention_00972():
    # chain3_wrapper_timeout_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_timeout_expired']()) is True


def test_chain_transport_00973():
    # chain3_wrapper_timeout_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_timeout_expired']()) is False


def test_chain_admitted_00974():
    # chain3_wrapper_timeout_expired
    error = _SHAPE_BUILDERS['chain3_wrapper_timeout_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00975():
    # chain3_wrapper_timeout_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_timeout_invalid']()), 6) == 1.25


def test_chain_contention_00975():
    # chain3_wrapper_timeout_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_timeout_invalid']()) is True


def test_chain_transport_00976():
    # chain3_wrapper_timeout_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_timeout_invalid']()) is False


def test_chain_admitted_00977():
    # chain3_wrapper_timeout_invalid
    error = _SHAPE_BUILDERS['chain3_wrapper_timeout_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00978():
    # chain3_wrapper_timeout_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_timeout_timeout']()), 6) == 1.25


def test_chain_contention_00978():
    # chain3_wrapper_timeout_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_timeout_timeout']()) is True


def test_chain_transport_00979():
    # chain3_wrapper_timeout_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_timeout_timeout']()) is False


def test_chain_admitted_00980():
    # chain3_wrapper_timeout_timeout
    error = _SHAPE_BUILDERS['chain3_wrapper_timeout_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00981():
    # chain3_wrapper_timeout_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_timeout_value']()), 6) == 1.25


def test_chain_contention_00981():
    # chain3_wrapper_timeout_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_timeout_value']()) is True


def test_chain_transport_00982():
    # chain3_wrapper_timeout_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_timeout_value']()) is False


def test_chain_admitted_00983():
    # chain3_wrapper_timeout_value
    error = _SHAPE_BUILDERS['chain3_wrapper_timeout_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00984():
    # chain3_wrapper_timeout_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_timeout_wrapper']()), 6) == 1.25


def test_chain_contention_00984():
    # chain3_wrapper_timeout_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_timeout_wrapper']()) is True


def test_chain_transport_00985():
    # chain3_wrapper_timeout_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_timeout_wrapper']()) is False


def test_chain_admitted_00986():
    # chain3_wrapper_timeout_wrapper
    error = _SHAPE_BUILDERS['chain3_wrapper_timeout_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00987():
    # chain3_wrapper_value_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_value_aborted']()), 6) == 1.25


def test_chain_contention_00987():
    # chain3_wrapper_value_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_value_aborted']()) is True


def test_chain_transport_00988():
    # chain3_wrapper_value_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_value_aborted']()) is False


def test_chain_admitted_00989():
    # chain3_wrapper_value_aborted
    error = _SHAPE_BUILDERS['chain3_wrapper_value_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00990():
    # chain3_wrapper_value_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_value_expired']()), 6) == 1.25


def test_chain_contention_00990():
    # chain3_wrapper_value_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_value_expired']()) is True


def test_chain_transport_00991():
    # chain3_wrapper_value_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_value_expired']()) is False


def test_chain_admitted_00992():
    # chain3_wrapper_value_expired
    error = _SHAPE_BUILDERS['chain3_wrapper_value_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00993():
    # chain3_wrapper_value_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_value_invalid']()), 6) == 1.25


def test_chain_contention_00993():
    # chain3_wrapper_value_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_value_invalid']()) is True


def test_chain_transport_00994():
    # chain3_wrapper_value_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_value_invalid']()) is False


def test_chain_admitted_00995():
    # chain3_wrapper_value_invalid
    error = _SHAPE_BUILDERS['chain3_wrapper_value_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00996():
    # chain3_wrapper_value_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_value_timeout']()), 6) == 1.25


def test_chain_contention_00996():
    # chain3_wrapper_value_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_value_timeout']()) is True


def test_chain_transport_00997():
    # chain3_wrapper_value_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_value_timeout']()) is False


def test_chain_admitted_00998():
    # chain3_wrapper_value_timeout
    error = _SHAPE_BUILDERS['chain3_wrapper_value_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_00999():
    # chain3_wrapper_value_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_value_value']()), 6) == 1.25


def test_chain_contention_00999():
    # chain3_wrapper_value_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_value_value']()) is True


def test_chain_transport_01000():
    # chain3_wrapper_value_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_value_value']()) is False


def test_chain_admitted_01001():
    # chain3_wrapper_value_value
    error = _SHAPE_BUILDERS['chain3_wrapper_value_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_01002():
    # chain3_wrapper_value_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_value_wrapper']()), 6) == 1.25


def test_chain_contention_01002():
    # chain3_wrapper_value_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_value_wrapper']()) is True


def test_chain_transport_01003():
    # chain3_wrapper_value_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_value_wrapper']()) is False


def test_chain_admitted_01004():
    # chain3_wrapper_value_wrapper
    error = _SHAPE_BUILDERS['chain3_wrapper_value_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_01005():
    # chain3_wrapper_wrapper_aborted
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_wrapper_aborted']()), 6) == 1.25


def test_chain_contention_01005():
    # chain3_wrapper_wrapper_aborted
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_wrapper_aborted']()) is True


def test_chain_transport_01006():
    # chain3_wrapper_wrapper_aborted
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_wrapper_aborted']()) is False


def test_chain_admitted_01007():
    # chain3_wrapper_wrapper_aborted
    error = _SHAPE_BUILDERS['chain3_wrapper_wrapper_aborted']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_01008():
    # chain3_wrapper_wrapper_expired
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_wrapper_expired']()), 6) == 1.25


def test_chain_contention_01008():
    # chain3_wrapper_wrapper_expired
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_wrapper_expired']()) is True


def test_chain_transport_01009():
    # chain3_wrapper_wrapper_expired
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_wrapper_expired']()) is False


def test_chain_admitted_01010():
    # chain3_wrapper_wrapper_expired
    error = _SHAPE_BUILDERS['chain3_wrapper_wrapper_expired']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_01011():
    # chain3_wrapper_wrapper_invalid
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_wrapper_invalid']()), 6) == 1.25


def test_chain_contention_01011():
    # chain3_wrapper_wrapper_invalid
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_wrapper_invalid']()) is True


def test_chain_transport_01012():
    # chain3_wrapper_wrapper_invalid
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_wrapper_invalid']()) is False


def test_chain_admitted_01013():
    # chain3_wrapper_wrapper_invalid
    error = _SHAPE_BUILDERS['chain3_wrapper_wrapper_invalid']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_01014():
    # chain3_wrapper_wrapper_timeout
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_wrapper_timeout']()), 6) == 1.25


def test_chain_contention_01014():
    # chain3_wrapper_wrapper_timeout
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_wrapper_timeout']()) is True


def test_chain_transport_01015():
    # chain3_wrapper_wrapper_timeout
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_wrapper_timeout']()) is False


def test_chain_admitted_01016():
    # chain3_wrapper_wrapper_timeout
    error = _SHAPE_BUILDERS['chain3_wrapper_wrapper_timeout']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_01017():
    # chain3_wrapper_wrapper_value
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_wrapper_value']()), 6) == 1.25


def test_chain_contention_01017():
    # chain3_wrapper_wrapper_value
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_wrapper_value']()) is True


def test_chain_transport_01018():
    # chain3_wrapper_wrapper_value
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_wrapper_value']()) is False


def test_chain_admitted_01019():
    # chain3_wrapper_wrapper_value
    error = _SHAPE_BUILDERS['chain3_wrapper_wrapper_value']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True


def test_chain_storm_01020():
    # chain3_wrapper_wrapper_wrapper
    assert round(bp.persist_restrike_storm_after(_SHAPE_BUILDERS['chain3_wrapper_wrapper_wrapper']()), 6) == 1.25


def test_chain_contention_01020():
    # chain3_wrapper_wrapper_wrapper
    assert bp.persist_loss_is_contention(_SHAPE_BUILDERS['chain3_wrapper_wrapper_wrapper']()) is True


def test_chain_transport_01021():
    # chain3_wrapper_wrapper_wrapper
    assert bp.persist_loss_is_restrikeable(_SHAPE_BUILDERS['chain3_wrapper_wrapper_wrapper']()) is False


def test_chain_admitted_01022():
    # chain3_wrapper_wrapper_wrapper
    error = _SHAPE_BUILDERS['chain3_wrapper_wrapper_wrapper']()
    assert (bp.persist_loss_is_restrikeable(error) or bp.persist_loss_is_contention(error)) is True
