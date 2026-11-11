import os

import requests

from typing import Any

from models import ExternalIntegrationCreateConversation, Conversation

# Fallback to direct package import when running outside parent package context (e.g. test harness)
try:
    from .models import ZapierCreateConversation
except (ImportError, ValueError):
    from zapier.models import ZapierCreateConversation

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

    @classmethod
    def from_dict(cls, data: dict) -> "ZapierDatabasePropertyModel":
        if not isinstance(data, dict):
            return cls("", "", "")
        return cls(data.get("id", ""), data.get("name", ""), data.get("type", ""))


class ZapierDatabaseModel:
    def __init__(
        self,
    ) -> None:
        self.id = ""
        self.properties = []

    @classmethod
    def from_dict(cls, data: dict) -> "ZapierDatabaseModel":
        model = cls()
        if not isinstance(data, dict):
            return model
        model.id = data.get("id", "")

        # properties
        properties: list[ZapierDatabasePropertyModel] = []
        raw_props = data.get("properties")
        if isinstance(raw_props, dict):
            for prop in raw_props.values():
                if isinstance(prop, dict):
                    properties.append(ZapierDatabasePropertyModel.from_dict(prop))
        elif isinstance(raw_props, list):
            for prop in raw_props:
                if isinstance(prop, dict):
                    properties.append(ZapierDatabasePropertyModel.from_dict(prop))
        model.properties = properties

        return model

    @classmethod
    def multi_from_dict(cls, data: Any) -> list["ZapierDatabaseModel"]:
        model = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    model.append(ZapierDatabaseModel.from_dict(item))
        elif isinstance(data, dict):
            model.append(ZapierDatabaseModel.from_dict(data))

        return model


class ZapierOAuthModel:
    def __init__(
        self,
    ) -> None:
        self.access_token = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ZapierOAuthModel":
        model = cls()
        if isinstance(data, dict):
            model.access_token = data.get("access_token", "")
        return model


# """
#    Client
# """

DEFAULT_TIMEOUT = 10.0


class ZapierClient:
    """
    Implementation of the Zapier APIs.

    This abstract class provides a Python interface to all Zapier APIs.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.timeout = timeout

    def send_hook_conversation_created(self, target_url: str, conversation: ZapierCreateConversation):
        resp: requests.Response | None = None
        err = None
        try:
            payload = (
                conversation.model_dump(mode="json")
                if hasattr(conversation, "model_dump")
                else conversation.dict()
                if hasattr(conversation, "dict")
                else conversation
            )
            resp = requests.post(
                target_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
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
                    "message": f"RequestException {type(e).__name__}",
                },
            }

        if err is None and resp is not None and not (200 <= resp.status_code < 300):
            resp_text = getattr(resp, "text", "") or f"{resp}"
            err = {
                "error": {
                    "status": resp.status_code,
                    "message": resp_text,
                },
            }

        if err is not None:
            print(err)
            return err

        return {"result": "{}"}


class OmiClient:
    """
    Implementation of the Omi Core APIs.

    This abstract class provides a Python interface to all Omi Core APIs.
    """

    def __init__(
        self,
        base_url: str | None = None,
        zapier_app_id: str | None = None,
        zapier_app_sk: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.zapier_app_id = zapier_app_id or ""
        self.zapier_app_sk = zapier_app_sk or ""
        self.timeout = timeout

    def create_conversation(self, conversation: ExternalIntegrationCreateConversation, uid: str):
        resp: requests.Response | None = None
        err = None
        url = f"{self.base_url}/v2/integrations/{self.zapier_app_id}/user/conversations?uid={uid}"
        try:
            payload = (
                conversation.model_dump(mode="json")
                if hasattr(conversation, "model_dump")
                else conversation.dict()
                if hasattr(conversation, "dict")
                else conversation
            )
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.zapier_app_sk}",
                },
                timeout=self.timeout,
            )
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
                    "message": f"RequestException {type(e).__name__}",
                },
            }

        if err is None and resp is not None and not (200 <= resp.status_code < 300):
            resp_text = getattr(resp, "text", "") or f"HTTP_{resp.status_code}"
            err = {
                "error": {
                    "status": resp.status_code,
                    "message": resp_text,
                },
            }

        if err is not None:
            print(err)
            return err

        return {"result": "{}"}

    def get_latest_conversation(self, uid: str):
        resp: requests.Response | None = None
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
                timeout=self.timeout,
            )
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
                    "message": f"RequestException {type(e).__name__}",
                },
            }

        if err is None and resp is not None and not (200 <= resp.status_code < 300):
            resp_text = getattr(resp, "text", "") or f"HTTP_{resp.status_code}"
            err = {
                "error": {
                    "status": resp.status_code,
                    "message": resp_text,
                },
            }

        if err is not None:
            print(err)
            return err

        if resp is None:
            return {"result": None}

        # view
        try:
            resp_json = resp.json()
        except Exception:
            return {"result": None}

        if isinstance(resp_json, list) and len(resp_json) > 0:
            latest_conversation_json = resp_json[0]
            if isinstance(latest_conversation_json, dict):
                try:
                    return {"result": Conversation(**latest_conversation_json)}
                except Exception:
                    return {"result": None}
        elif isinstance(resp_json, dict):
            items = resp_json.get("conversations") or resp_json.get("items")
            if isinstance(items, list) and len(items) > 0:
                first = items[0]
                if isinstance(first, dict):
                    try:
                        return {"result": Conversation(**first)}
                    except Exception:
                        return {"result": None}
            elif "id" in resp_json or "created_at" in resp_json:
                try:
                    return {"result": Conversation(**resp_json)}
                except Exception:
                    return {"result": None}

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
