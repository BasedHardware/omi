import os

import requests

from models import ExternalIntegrationCreateConversation, Conversation

from .models import ZapierCreateConversation

# """
#    Models
# """


class ZapierDatabasePropertyModel:
    def __init__(
        self,
        id,
        name,
        property_type,
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
                properties.append(ZapierDatabasePropertyModel.from_dict(prop))
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

    def send_hook_conversation_created(self, target_url: str, conversation: ZapierCreateConversation):
        resp: requests.Response
        err = None
        try:
            resp = requests.post(
                target_url,
                json=conversation.model_dump(mode="json"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
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


class OmiClient:
    """
    Implementation of the Omi Core APIs.

    This abstract class provides a Python interface to all Omi Core APIs.
    """

    def __init__(
        self,
        base_url,
        zapier_app_id,
        zapier_app_sk,
    ) -> None:
        self.base_url = base_url
        self.zapier_app_id = zapier_app_id
        self.zapier_app_sk = zapier_app_sk
        pass

    def create_conversation(self, conversation: ExternalIntegrationCreateConversation, uid: str):
        resp: requests.Response
        err = None
        url = f"{self.base_url}/v2/integrations/{self.zapier_app_id}/user/conversations?uid={uid}"
        try:
            resp = requests.post(
                url,
                json=conversation.model_dump(mode="json"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.zapier_app_sk}",
                },
            )
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

    def get_latest_conversation(self, uid: str):
        resp: requests.Response
        err = None
        url = f"{self.base_url}/v2/integrations/{self.zapier_app_id}/conversations?uid={uid}&limit=1"
        try:
            resp = requests.get(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.zapier_app_sk}",
                },
            )
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
            latest_conversation_json = resp_json[0]
            return {"result": Conversation(**latest_conversation_json)}

        return {"result": None}


zap_client = ZapierClient()

omi_client = OmiClient(
    base_url=os.getenv("OMI_BASE_API_URL"),
    zapier_app_id=os.getenv("OMI_ZAPIER_APP_ID"),
    zapier_app_sk=os.getenv("OMI_ZAPIER_APP_SECRET"),
)


def get_zapier():
    return zap_client


def get_omi():
    return omi_client
