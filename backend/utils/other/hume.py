import os
from typing import Any, Dict, List, Optional, Tuple, cast

import httpx
import logging

logger = logging.getLogger(__name__)


class HumePredictionEmotionResponseModel:
    def __init__(
        self,
        name: str,
        score: float,
    ) -> None:
        self.name = name
        self.score = score

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumePredictionEmotionResponseModel":
        # Default to safe values for a malformed entry: a missing/invalid score must stay numeric so
        # downstream math in get_top_emotion_names (sum and threshold comparison) does not hit None.
        score = data.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            score = 0.0
        model = cls(data.get("name") or "", score)
        return model

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'score': self.score,
        }

    @classmethod
    def to_multi_dict(cls, emotions: List["HumePredictionEmotionResponseModel"]) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in emotions]


class HumeJobModelPredictionResponseModel:
    def __init__(
        self,
        time: Tuple[float, float],
        emotions: Optional[List[HumePredictionEmotionResponseModel]] = None,
    ) -> None:
        # Use a fresh list per instance, never a shared mutable default. from_dict appends to
        # self.emotions, so a shared default would leak emotions across parsed callbacks.
        self.emotions = emotions if emotions is not None else []
        self.time = time

    @classmethod
    def get_top_emotion_names(
        cls,
        emotions: Optional[List[HumePredictionEmotionResponseModel]] = None,
        k: int = 5,
        peak_threshold: float = 0.7,
    ) -> List[str]:
        emotions_dict: Dict[str, float] = {}
        for emo in emotions or []:
            if emo.name not in emotions_dict:
                emotions_dict[emo.name] = emo.score
            else:
                emotions_dict[emo.name] = emotions_dict[emo.name] + emo.score

        n = len(emotions_dict)

        emotions_average: Dict[str, float] = {}
        for emotion, score in emotions_dict.items():
            if score >= peak_threshold:
                emotions_average[emotion] = score / n

        ascend_sorted_emotion_average = sorted(emotions_average, key=lambda name: emotions_average[name], reverse=True)
        k = min(k, len(ascend_sorted_emotion_average))
        return ascend_sorted_emotion_average[:k]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumeJobModelPredictionResponseModel":
        grouped_prediction_prediction = data
        raw_time = data.get("time")
        time_data: Dict[str, Any] = cast(Dict[str, Any], raw_time) if isinstance(raw_time, dict) else {}
        # Keep the interval numeric so downstream consumers comparing begin/end never hit None.
        begin = time_data.get("begin")
        end = time_data.get("end")
        if not isinstance(begin, (int, float)) or isinstance(begin, bool):
            begin = 0.0
        if not isinstance(end, (int, float)) or isinstance(end, bool):
            end = 0.0
        model = cls((begin, end))
        raw_emotions = grouped_prediction_prediction.get('emotions')
        emotions_list: List[Dict[str, Any]] = (
            cast(List[Dict[str, Any]], raw_emotions) if isinstance(raw_emotions, list) else []
        )
        for emotion in emotions_list:
            emo = HumePredictionEmotionResponseModel.from_dict(emotion)
            model.emotions.append(emo)

        return model

    @classmethod
    def from_multi_dict(
        cls, prediction_model: str, data: Dict[str, Any]
    ) -> List["HumeJobModelPredictionResponseModel"]:
        model: List[HumeJobModelPredictionResponseModel] = []
        if "results" not in data or "predictions" not in data["results"]:
            return model

        for prediction in data["results"]["predictions"]:
            # A failed or partial Hume job can omit the requested model, grouped_predictions, or the
            # inner predictions list; guard the nested lookups so one malformed prediction yields no
            # emotions instead of a KeyError that 500s the whole callback (mirrors the .get(...) style
            # used elsewhere in this module).
            grouped_predictions = prediction.get('models', {}).get(prediction_model, {}).get('grouped_predictions', [])
            for grouped_prediction in grouped_predictions:
                for grouped_prediction_prediction in grouped_prediction.get('predictions', []):
                    model.append(cls.from_dict(grouped_prediction_prediction))

        return model


class HumeJobCallbackModel:
    def __init__(
        self,
        job_id: Optional[str],
        status: Optional[str],
        predictions: Optional[List[HumeJobModelPredictionResponseModel]] = None,
    ) -> None:
        self.job_id = job_id
        self.status = status
        self.predictions = predictions if predictions is not None else []

    @classmethod
    def from_dict(cls, prediction_model: str, data: Dict[str, Any]) -> "HumeJobCallbackModel":
        # predictions[0] -> results -> predictions
        predictions: List[HumeJobModelPredictionResponseModel] = []
        if "predictions" in data and len(data["predictions"]) > 0:
            predictions = HumeJobModelPredictionResponseModel.from_multi_dict(prediction_model, data["predictions"][0])

        model = cls(data.get("job_id"), data.get("status"), predictions)
        return model


class HumeJobResponseModel:
    def __init__(
        self,
        id: Optional[str],
    ) -> None:
        self.id = id

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumeJobResponseModel":
        # Read job_id defensively: this runs on the success (HTTP 200) path from resp.json(),
        # and a response missing job_id must not raise KeyError out of the caller while every
        # error status is already turned into an error dict. id is Optional[str].
        model = cls(data.get("job_id"))
        return model


class HumeClient:
    """
    Implementation of the Hume APIs.

    This abstract class provides a Python interface to all Hume APIs.
    """

    def __init__(
        self,
        api_key: Optional[str],
        callback_url: Optional[str],
    ) -> None:
        self.api_key = api_key
        self.callback_url = callback_url

    def request_user_expression_mersurement(self, urls: List[str]) -> Dict[str, Any]:
        err: Optional[Dict[str, Any]] = None
        resp: Optional[httpx.Response] = None

        # Model
        data = {
            "models": {"prosody": {"granularity": "utterance"}},
            "urls": urls,
            "callback_url": self.callback_url,
        }
        try:
            resp = httpx.post(
                "https://api.hume.ai/v0/batch/jobs",
                json=data,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json; charset=utf-8',
                    'X-Hume-Api-Key': self.api_key if self.api_key is not None else '',
                },
                timeout=300.0,
                follow_redirects=True,
            )
        except httpx.TimeoutException:
            err = {
                "error": {
                    "message": "Timeout",
                },
            }
        except httpx.TooManyRedirects:
            err = {
                "error": {
                    "message": "TooManyRedirects",
                },
            }
        except httpx.RequestError as e:
            err = {
                "error": {
                    "message": f"RequestError {e}",
                },
            }
        if err is None and resp is not None and resp.status_code != 200:
            resp_text = f"{resp}"
            err = {
                "error": {
                    "status": resp.status_code,
                    "message": resp_text,
                },
            }
        if err is not None:
            logger.error(err)
            return err

        assert resp is not None  # err is None implies the try-block assigned resp
        return {"result": HumeJobResponseModel.from_dict(resp.json())}


hume_client = HumeClient(
    api_key=os.getenv('HUME_API_KEY'),
    callback_url=os.getenv('HUME_CALLBACK_URL'),
)


def get_hume() -> HumeClient:
    return hume_client
