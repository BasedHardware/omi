import os
import requests

from models import WorkflowCreateMemory, Memory
from .models import ZapierCreateMemory


# """
#    Models
# """


class ZapierDatabasePropertyModel:
    def __init__(
            self,
            id, name, property_type,
    ) -> None:
        self.id = id
        self.name = name
        self.property_type = property_type
        pass

    @classmethod
    def from_dict(cls, data: dict) -> "ZapierDatabasePropertyModel":
        model = cls(data["id"], data["name"], data["type"])
        return model


class ZapierDatabaseModel:
    def __init__(
            self,
    ) -> None:
        self.id = ""
        self.properties = []
        pass

    @classmethod
    def from_dict(cls, data: dict) -> "ZapierDatabaseModel":
        model = cls()
        model.id = data["id"]

        # properties
        properties: [ZapierDatabasePropertyModel] = []
        if data["properties"] is not None:
            for prop in data["properties"].values():
                properties.append(
                    ZapierDatabasePropertyModel.from_dict(prop))
        model.properties = properties

        return model

    @classmethod
    def multi_from_dict(cls, data: dict) -> "[ZapierDatabaseModel]":
        model = []
        for item in data:
            model.append(ZapierDatabaseModel.from_dict(item))

        return model


class ZapierOAuthModel:
    def __init__(
            self,
    ) -> None:
        self.access_token = ""
        pass

    @classmethod
    def from_dict(cls, data: dict) -> "ZapierDatabaseModel":
        model = cls()
        model.access_token = data["access_token"]
        return model


# """
#    Client
# """

class ZapierClient:
    """
    Implementation of the Zapier APIs.

    This abstract class provides a Python interface to all Zapier APIs.
    """

    def __init__(
            self,
    ) -> None:
        pass

    def send_hook_memory_created(self, target_url: str, memory: ZapierCreateMemory):
        resp: requests.Response
        err = None
        try:
            resp = requests.post(target_url, json=memory.model_dump(mode="json"), headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            })
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

        print(resp)

        return {"result": "{}"}


class FriendClient:
    """
    Implementation of the Friend Core APIs.

    This abstract class provides a Python interface to all Friend Core APIs.
    """

    def __init__(
            self,
            base_url,
            workflow_api_key,
    ) -> None:
        self.base_url = base_url
        self.workflow_api_key = workflow_api_key
        pass

    def create_memory(self, memory: WorkflowCreateMemory, uid: str):
        resp: requests.Response
        err = None
        url = f"{self.base_url}/v1/integrations/workflow/memories?uid={uid}"
        try:
            resp = requests.post(url, json=memory.model_dump(mode="json"), headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'api-key': self.workflow_api_key,
            })
        except requests.exceptions.HTTPError:
            resp_text = f"{resp.text()}"
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

        print(resp)

        return {"result": "{}"}

    def get_latest_memory(self, uid: str):
        resp: requests.Response
        err = None
        url = f"{self.base_url}/v1/integrations/workflow/memories?uid={uid}&limit=1"
        try:
            resp = requests.get(url, headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'api-key': self.workflow_api_key,
            })
        except requests.exceptions.HTTPError:
            resp_text = f"{resp.text()}"
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

        print(resp)

        # view
        resp_json = resp.json()
        if len(resp_json) > 0:
            latest_memory_json = resp_json[0]
            return {"result": Memory(**latest_memory_json)}

        return {"result": None}


zap_client = ZapierClient()

friend_client = FriendClient(
    base_url=os.getenv('FRIEND_API_URL'),
    workflow_api_key=os.getenv('WORKFLOW_API_KEY'),
)


def get_zapier():
    return zap_client


def get_friend():
    return friend_client
