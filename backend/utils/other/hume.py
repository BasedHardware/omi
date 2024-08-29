import os

import requests


class HumePredictionEmotionResponseModel:
    def __init__(
            self,
            name: str,
            score: float,
    ) -> None:
        self.name = name
        self.score = score

    @classmethod
    def from_dict(cls, data: dict) -> "HumePredictionEmotionResponseModel":
        model = cls(data["name"], data["score"])
        return model

    def to_dict(self):
        return {
            'name': self.name,
            'score': self.score,
        }

    @classmethod
    def to_multi_dict(cls, emotions: []):
        return [e.to_dict() for e in emotions]


class HumeJobModelPredictionResponseModel:
    def __init__(
            self,
            time,
            emotions: [HumePredictionEmotionResponseModel] = [],
    ) -> None:
        self.emotions = emotions
        self.time = time

    @classmethod
    def get_top_emotion_names(cls, emotions: [HumePredictionEmotionResponseModel] = [], k: int = 5,
                              peak_threshold: float = .7):
        emotions_dict = {}
        for emo in emotions:
            if emo.name not in emotions_dict:
                emotions_dict[emo.name] = emo.score
            else:
                emotions_dict[emo.name] = emotions_dict[emo.name] + emo.score

        n = len(emotions_dict)

        emotions_average = {}
        for emotion, score in emotions_dict.items():
            if score >= peak_threshold:
                emotions_average[emotion] = score / n

        ascend_sorted_emotion_average = sorted(emotions_average, key=emotions_average.get, reverse=True)
        k = min(k, len(ascend_sorted_emotion_average))
        return ascend_sorted_emotion_average[:k]

    @classmethod
    def from_dict(cls, data: dict) -> "HumeJobModelPredictionResponseModel":
        grouped_prediction_prediction = data
        model = cls((data["time"]["begin"], data["time"]["end"]))
        for emotion in grouped_prediction_prediction['emotions']:
            emo = HumePredictionEmotionResponseModel.from_dict(emotion)
            model.emotions.append(emo)

        return model

    @classmethod
    def from_multi_dict(cls, prediction_model: str, data: dict) -> "[HumeJobModelPredictionResponseModel]":
        model = []
        if "results" not in data or "predictions" not in data["results"]:
            return model

        for prediction in data["results"]["predictions"]:
            for grouped_prediction in prediction['models'][prediction_model]['grouped_predictions']:
                for grouped_prediction_prediction in grouped_prediction['predictions']:
                    model.append(cls.from_dict(grouped_prediction_prediction))

        return model


class HumeJobCallbackModel:
    def __init__(
            self,
            job_id,
            status,
            predictions: [HumeJobModelPredictionResponseModel] = [],
    ) -> None:
        self.job_id = job_id
        self.status = status
        self.predictions = predictions

    @classmethod
    def from_dict(cls, prediction_model: str, data: dict) -> "HumeJobCallbackModel":
        # predictions[0] -> results -> predictions
        predictions = []
        if "predictions" in data and len(data["predictions"]) > 0:
            predictions = HumeJobModelPredictionResponseModel.from_multi_dict(prediction_model, data["predictions"][0])

        model = cls(data["job_id"], data["status"], predictions)
        return model


class HumeJobResponseModel:
    def __init__(
            self,
            id,
    ) -> None:
        self.id = id

    @classmethod
    def from_dict(cls, data: dict) -> "HumeJobResponseModel":
        model = cls(data["job_id"])
        return model


class HumeClient:
    """
    Implementation of the Hume APIs.

    This abstract class provides a Python interface to all Hume APIs.
    """

    def __init__(
            self,
            api_key,
            callback_url,
    ) -> None:
        self.api_key = api_key
        self.callback_url = callback_url

    def request_user_expression_mersurement(self, urls: [str]):
        resp: requests.Response
        err = None

        # Model
        data = {
            "models": {
                "prosody": {
                    "granularity": "utterance"
                }
            },
            "urls": urls,
            "callback_url": self.callback_url,
        }
        try:
            resp = requests.post("https://api.hume.ai/v0/batch/jobs", json=data, headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json; charset=utf-8',
                'X-Hume-Api-Key': self.api_key,
            }, timeout=300, )
        except requests.exceptions.HTTPError:
            resp_text = f"{resp}"
            err = {
                "error": {
                    "status": resp.status_code,
                    "message": resp_text,
                },
            }
        except requests.exceptions.Timeout:
            err = {
                "error": {
                    "message": "Timeout",
                },
            }
        except requests.exceptions.TooManyRedirects:
            err = {
                "error": {
                    "message": "TooManyRedirects",
                },
            }
        except requests.exceptions.RequestException as e:
            err = {
                "error": {
                    "message": f"RequestException {e}",
                },
            }
        if err is None and resp.status_code != 200:
            resp_text = f"{resp}"
            err = {
                "error": {
                    "status": resp.status_code,
                    "message": resp_text,
                },
            }
        if err is not None:
            print(err)
            return err

        return {"result": HumeJobResponseModel.from_dict(resp.json())}


hume_client = HumeClient(
    api_key=os.getenv('HUME_API_KEY'),
    callback_url=os.getenv('HUME_CALLBACK_URL'),
)


def get_hume():
    return hume_client
