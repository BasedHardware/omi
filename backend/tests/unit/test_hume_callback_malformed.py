"""HumeJobCallbackModel.from_dict and friends must tolerate a malformed external Hume callback.

POST /v1/agents/hume/callback parses the external Hume payload via from_dict, which used data['job_id'],
data['status'], data['time']['begin'] and data['name']/['score'] via direct subscript, so a malformed
callback raised KeyError -> HTTP 500. The parsers now use .get() and keep score and the time interval
numeric so downstream math (get_top_emotion_names, interval comparisons) does not later hit None.
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
    assert m.name == ''
    assert m.score == 0.0  # missing score must stay numeric, not None


def test_emotion_from_dict_non_numeric_score_defaults_zero():
    m = HumePredictionEmotionResponseModel.from_dict({'name': 'joy', 'score': 'not-a-number'})
    assert m.score == 0.0


def test_top_emotion_names_handles_missing_scores():
    # A malformed payload with emotions missing scores must not crash the downstream math.
    emotions = [
        HumePredictionEmotionResponseModel.from_dict({'name': 'joy'}),
        HumePredictionEmotionResponseModel.from_dict({'name': 'anger', 'score': 0.9}),
    ]
    result = HumeJobModelPredictionResponseModel.get_top_emotion_names(emotions, k=2, peak_threshold=0.7)
    assert result == ['anger']


def test_prediction_from_dict_missing_time_and_emotions_no_raise():
    m = HumeJobModelPredictionResponseModel.from_dict({})
    assert m is not None
    assert m.time == (0.0, 0.0)  # missing time interval stays numeric
    m2 = HumeJobModelPredictionResponseModel.from_dict({'time': {}, 'emotions': []})
    assert m2.emotions == []


def test_prediction_emotions_not_shared_between_instances():
    # __init__ must not use a shared mutable default list: from_dict appends to self.emotions, so a
    # shared default would leak emotions from one parsed callback into the next.
    a = HumeJobModelPredictionResponseModel.from_dict({'emotions': [{'name': 'joy', 'score': 0.5}]})
    b = HumeJobModelPredictionResponseModel.from_dict({'emotions': [{'name': 'anger', 'score': 0.9}]})
    assert [e.name for e in a.emotions] == ['joy']
    assert [e.name for e in b.emotions] == ['anger']


def test_callback_from_dict_missing_job_id_and_status_no_raise():
    m = HumeJobCallbackModel.from_dict('prosody', {})
    assert m.job_id is None
    assert m.status is None


def test_valid_callback_parsed():
    m = HumeJobCallbackModel.from_dict('prosody', {'job_id': 'j1', 'status': 'COMPLETED'})
    assert m.job_id == 'j1'
    assert m.status == 'COMPLETED'
