import base64
import os
from typing import Any, List

import requests

DEFAULT_TIMEOUT = 10.0


def _safe_json(resp: requests.Response) -> dict:
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data
        return {"data": data}
    except Exception:
        return {"message": "Non-JSON response"}


# """
#    Models
# """


class NotionDatabasePropertyModel:
    def __init__(
        self,
        id: str = "",
        name: str = "",
        property_type: str = "",
    ) -> None:
        self.id = id
        self.name = name
        self.property_type = property_type

    @classmethod
    def from_dict(cls, data: dict) -> "NotionDatabasePropertyModel":
        if not isinstance(data, dict):
            return cls("", "", "")
        return cls(
            id=str(data.get("id", "") or ""),
            name=str(data.get("name", "") or ""),
            property_type=str(data.get("type", "") or ""),
        )


class NotionDatabaseModel:
    def __init__(
        self,
    ) -> None:
        self.id = ""
        self.properties = []

    @classmethod
    def from_dict(cls, data: dict) -> "NotionDatabaseModel":
        model = cls()
        if not isinstance(data, dict):
            return model
        model.id = str(data.get("id", "") or "")

        # properties
        properties: List[NotionDatabasePropertyModel] = []
        raw_properties = data.get("properties")
        if isinstance(raw_properties, dict):
            for prop in raw_properties.values():
                if isinstance(prop, dict):
                    properties.append(NotionDatabasePropertyModel.from_dict(prop))
        model.properties = properties

        return model

    @classmethod
    def multi_from_dict(cls, data: Any) -> List["NotionDatabaseModel"]:
        model = []
        if not isinstance(data, list):
            return model
        for item in data:
            if isinstance(item, dict):
                model.append(NotionDatabaseModel.from_dict(item))

        return model


class NotionOAuthModel:
    def __init__(
        self,
    ) -> None:
        self.access_token = ""

    @classmethod
    def from_dict(cls, data: dict) -> "NotionOAuthModel":
        model = cls()
        if isinstance(data, dict):
            model.access_token = str(data.get("access_token", "") or "")
        return model


# """
#    Client
# """


class NotionClient:
    """
    Implementation of the Notion APIs.

    This abstract class provides a Python interface to all Notion APIs.
    """

    def __init__(
        self,
        oauth_client_id="",
        oauth_client_secret="",
        oauth_redirect_uri="",
        auth_url="",
    ) -> None:
        self.oauth_client_id = oauth_client_id
        self.oauth_client_secret = oauth_client_secret
        self.oauth_redirect_uri = oauth_redirect_uri
        self.auth_url = auth_url

    def get_oauth_url(self, uid: str):
        # Should use encryption on state (with some salt) to prevent attacks
        state = uid
        return f"{self.auth_url}&state={state}"

    def get_database(self, database_id: str, access_token: str, timeout: float = DEFAULT_TIMEOUT):
        resp: requests.Response
        try:
            resp = requests.get(
                f'https://api.notion.com/v1/databases/{database_id}',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Notion-Version': '2022-06-28',
                },
                timeout=timeout,
            )
        except requests.RequestException as e:
            err_code = type(e).__name__
            return {
                "error": {
                    "status": 500,
                    "code": err_code,
                    "message": f"Request failed: {err_code}",
                },
            }

        if resp.status_code != 200:
            resp_json = _safe_json(resp)
            print(f"Error: HTTP_{resp.status_code}")
            return {
                "error": {
                    "status": resp.status_code,
                    "code": resp_json.get("code", "") if isinstance(resp_json, dict) else "",
                    "message": resp_json.get("message", "") if isinstance(resp_json, dict) else "",
                },
            }

        return {"result": NotionDatabaseModel.from_dict(_safe_json(resp))}

    def get_access_token(self, code: str, timeout: float = DEFAULT_TIMEOUT):
        client_id = self.oauth_client_id
        client_secret = self.oauth_client_secret
        redirect_uri = self.oauth_redirect_uri

        # encode in base 64
        encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        try:
            resp = requests.post(
                "https://api.notion.com/v1/oauth/token",
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    'Notion-Version': '2022-06-28',
                },
                json=data,
                timeout=timeout,
            )
        except requests.RequestException as e:
            err_code = type(e).__name__
            return {
                "error": {
                    "status": 500,
                    "code": err_code,
                    "message": f"Request failed: {err_code}",
                },
            }

        if resp.status_code != 200:
            resp_json = _safe_json(resp)
            print(f"Error: HTTP_{resp.status_code}")
            return {
                "error": {
                    "status": resp.status_code,
                    "code": resp_json.get("code", "") if isinstance(resp_json, dict) else "",
                    "message": resp_json.get("message", "") if isinstance(resp_json, dict) else "",
                },
            }

        return {"result": NotionOAuthModel.from_dict(_safe_json(resp))}

    def get_databases_edited_time_desc(self, access_token: str, timeout: float = DEFAULT_TIMEOUT):
        data = {
            "filter": {"value": "database", "property": "object"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        }
        try:
            resp = requests.post(
                "https://api.notion.com/v1/search",
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Notion-Version': '2022-06-28',
                },
                json=data,
                timeout=timeout,
            )
        except requests.RequestException as e:
            err_code = type(e).__name__
            return {
                "error": {
                    "status": 500,
                    "code": err_code,
                    "message": f"Request failed: {err_code}",
                },
            }

        if resp.status_code != 200:
            resp_json = _safe_json(resp)
            print(f"Error: HTTP_{resp.status_code}")
            return {
                "error": {
                    "status": resp.status_code,
                    "code": resp_json.get("code", "") if isinstance(resp_json, dict) else "",
                    "message": resp_json.get("message", "") if isinstance(resp_json, dict) else "",
                },
            }

        resp_json = _safe_json(resp)
        results = resp_json.get("results", []) if isinstance(resp_json, dict) else []
        return {"result": NotionDatabaseModel.multi_from_dict(results)}


client = NotionClient(
    oauth_client_id=os.getenv('NOTION_OAUTH_CLIENT_ID'),
    oauth_client_secret=os.getenv('NOTION_OAUTH_CLIENT_SECRET'),
    oauth_redirect_uri=os.getenv('NOTION_OAUTH_REDIRECT_URI'),
    auth_url=os.getenv('NOTION_AUTH_URL'),
)


def get_notion():
    return client
