"""HumeJobCallbackModel.from_dict and friends must tolerate a malformed external Hume callback.

POST /v1/agents/hume/callback parses the external Hume payload via from_dict, which used data['job_id'],
data['status'], data['time']['begin'] and data['name']/['score'] via direct subscript, so a malformed
callback raised KeyError -> HTTP 500. The parsers now use .get().
"""

import os

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from utils.other.hume import (  # noqa: E402
    HumeJobCallbackModel,
    HumeJobModelPredictionResponseModel,
    HumePredictionEmotionResponseModel,
)


def test_emotion_from_dict_missing_fields_no_raise():
    m = HumePredictionEmotionResponseModel.from_dict({})
    assert m.name is None
    assert m.score is None


def test_prediction_from_dict_missing_time_and_emotions_no_raise():
    m = HumeJobModelPredictionResponseModel.from_dict({})
    assert m is not None
    m2 = HumeJobModelPredictionResponseModel.from_dict({'time': {}, 'emotions': []})
    assert m2.emotions == []


def test_callback_from_dict_missing_job_id_and_status_no_raise():
    m = HumeJobCallbackModel.from_dict('prosody', {})
    assert m.job_id is None
    assert m.status is None


def test_valid_callback_parsed():
    m = HumeJobCallbackModel.from_dict('prosody', {'job_id': 'j1', 'status': 'COMPLETED'})
    assert m.job_id == 'j1'
    assert m.status == 'COMPLETED'
