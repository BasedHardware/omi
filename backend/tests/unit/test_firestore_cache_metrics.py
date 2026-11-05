import math
from unittest.mock import MagicMock, patch
import pytest

from database import firestore_cache_metrics as fcm


def test_record_request_normal():
    with patch.object(fcm.FIRESTORE_CACHE_REQUESTS, 'labels') as mock_labels:
        mock_counter = MagicMock()
        mock_labels.return_value = mock_counter
        
        fcm.record_request('user_profile', 'hit')
        mock_labels.assert_called_once_with(namespace='user_profile', result='hit')
        mock_counter.inc.assert_called_once_with()


def test_record_request_invalid_inputs_does_not_raise():
    # record_request should safely degrade and not crash caller if prometheus fails or invalid args passed
    with patch.object(fcm.FIRESTORE_CACHE_REQUESTS, 'labels', side_effect=Exception('Prometheus client error')):
        # Should not raise exception
        fcm.record_request('user_profile', 'hit')


def test_observe_fetch_normal():
    with patch.object(fcm.FIRESTORE_CACHE_FETCH_SECONDS, 'labels') as mock_labels:
        mock_hist = MagicMock()
        mock_labels.return_value = mock_hist
        
        fcm.observe_fetch('user_profile', 0.125)
        mock_labels.assert_called_once_with(namespace='user_profile')
        mock_hist.observe.assert_called_once_with(0.125)


def test_observe_fetch_negative_or_nan_safely_handled():
    # If seconds is negative, NaN, or Prometheus raises, observe_fetch must not crash the caller
    with patch.object(fcm.FIRESTORE_CACHE_FETCH_SECONDS, 'labels') as mock_labels:
        mock_hist = MagicMock()
        mock_labels.return_value = mock_hist
        
        # Test negative value
        fcm.observe_fetch('user_profile', -0.5)
        # Should clamp or observe safely without throwing
        
        # Test NaN or Inf
        fcm.observe_fetch('user_profile', float('nan'))
        fcm.observe_fetch('user_profile', float('inf'))


def test_observe_fetch_exception_suppressed():
    with patch.object(fcm.FIRESTORE_CACHE_FETCH_SECONDS, 'labels', side_effect=RuntimeError('Metrics registry broken')):
        fcm.observe_fetch('user_profile', 1.0)


def test_observe_payload_normal():
    with patch.object(fcm.FIRESTORE_CACHE_PAYLOAD_BYTES, 'labels') as mock_labels:
        mock_hist = MagicMock()
        mock_labels.return_value = mock_hist
        
        fcm.observe_payload('user_profile', 2048)
        mock_labels.assert_called_once_with(namespace='user_profile')
        mock_hist.observe.assert_called_once_with(2048)


def test_observe_payload_negative_or_invalid_handled():
    with patch.object(fcm.FIRESTORE_CACHE_PAYLOAD_BYTES, 'labels', side_effect=ValueError('Invalid value')):
        fcm.observe_payload('user_profile', -10)
