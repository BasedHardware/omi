import os
import requests

class HumeJobCallbackModel:
    def __init__(
            self,
            job_id,
            status,
            predictions,
    ) -> None:
        self.job_id = job_id
        self.status = status
        self.predictions = predictions

    @classmethod
    def from_dict(cls, data: dict) -> "HumeJobCallbackModel":
        # predictions[0] -> results -> predictions
        predictions = []
        if "predictions" in data and len(data["predictions"]) > 0:
            prediction_data = data["predictions"][0]["results"]["predictions"]
            predictions = HumeJobLanguageModelPredictionResponseModel.from_multi_dict(prediction_data)

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

    @classmethod
    def from_multi_dict(cls, data: dict) -> "HumePredictionEmotionResponseModel":
        model = []
        for item in data:
            model.append(cls.from_dict(item))

        return model


class HumeJobLanguageModelPredictionResponseModel:
    def __init__(
            self,
            emotions=[],
    ) -> None:
        self.emotions = emotions

    @classmethod
    def from_dict(cls, data: dict) -> "HumeJobLanguageModelPredictionResponseModel":
        # Validate model
        # models -> language -> grouped_predictions
        if "models" not in data or "language" not in data["models"] or "grouped_predictions" not in data["models"]["language"]:
            print("Data is in valid")
            return None

        # grouped_predictions -> predictions -> emotions
        grouped_predictions = data["models"]["language"]["grouped_predictions"]
        if len(grouped_predictions) == 0 or "predictions" not in grouped_predictions[0] or len(grouped_predictions[0]["predictions"]) == 0 or "emotions" not in grouped_predictions[0]["predictions"][0]:
            return cls()

        emotions = HumePredictionEmotionResponseModel.from_multi_dict(grouped_predictions[0]["predictions"][0]["emotions"])

        model = cls(emotions)

        return model

    @ classmethod
    def from_multi_dict(cls, data: dict) -> "HumeJobLanguageModelPredictionResponseModel":
        predictions = []

        for item in data:
            predictions.append(cls.from_dict(item))

        return predictions

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

    def request_user_expression_mersurement(self, transcript: str):
        resp: requests.Response
        err = None

        # Model
        data = {
            "models": {
                "language": {
                    "granularity": "conversational_turn"
                }
            },
            "text": [transcript],
            "callback_url": self.callback_url,
        }
        try:
            resp = requests.post("https://api.hume.ai/v0/batch/jobs", json=data, headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json; charset=utf-8',
                'X-Hume-Api-Key': self.api_key,
            }, timeout=300,)
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
