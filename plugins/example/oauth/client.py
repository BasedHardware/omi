import base64
import os

import requests


# """
#    Models
# """


class NotionDatabasePropertyModel:
    def __init__(
            self,
            id, name, property_type,
    ) -> None:
        self.id = id
        self.name = name
        self.property_type = property_type
        pass

    @classmethod
    def from_dict(cls, data: dict) -> "NotionDatabasePropertyModel":
        model = cls(data["id"], data["name"], data["type"])
        return model


class NotionDatabaseModel:
    def __init__(
            self,
    ) -> None:
        self.id = ""
        self.properties = []
        pass

    @classmethod
    def from_dict(cls, data: dict) -> "NotionDatabaseModel":
        model = cls()
        model.id = data["id"]

        # properties
        properties: [NotionDatabasePropertyModel] = []
        if data["properties"] is not None:
            for prop in data["properties"].values():
                properties.append(
                    NotionDatabasePropertyModel.from_dict(prop))
        model.properties = properties

        return model

    @classmethod
    def multi_from_dict(cls, data: dict) -> "[NotionDatabaseModel]":
        model = []
        for item in data:
            model.append(NotionDatabaseModel.from_dict(item))

        return model


class NotionOAuthModel:
    def __init__(
            self,
    ) -> None:
        self.access_token = ""
        pass

    @classmethod
    def from_dict(cls, data: dict) -> "NotionDatabaseModel":
        model = cls()
        model.access_token = data["access_token"]
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

    def get_database(self, database_id: str, access_token: str):
        resp: requests.Response
        resp = requests.get(f'https://api.notion.com/v1/databases/{database_id}', headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Notion-Version': '2022-06-28'
        })
        if resp.status_code != 200:
            resp_json = resp.json()
            print(f"Error: HTTP_{resp.status_code} {resp_json}")
            return {
                "error": {
                    "status": resp.status_code,
                    "code": resp_json["code"] if "code" in resp_json else "",
                    "message": resp_json["message"] if "message" in resp_json else "",
                },
            }

        print(resp.json())

        return {"result": NotionDatabaseModel.from_dict(resp.json())}

    def get_access_token(self, code: str):
        client_id = self.oauth_client_id
        client_secret = self.oauth_client_secret
        redirect_uri = self.oauth_redirect_uri

        # encode in base 64
        encoded = base64.b64encode(
            f"{client_id}:{client_secret}".encode()).decode()

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        resp = requests.post("https://api.notion.com/v1/oauth/token", headers={
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            'Notion-Version': '2022-06-28'
        }, json=data)
        if resp.status_code != 200:
            resp_json = resp.json()
            print(f"Error: HTTP_{resp.status_code} {resp_json}")
            return {
                "error": {
                    "status": resp.status_code,
                    "code": resp_json["code"] if "code" in resp_json else "",
                    "message": resp_json["message"] if "message" in resp_json else "",
                },
            }

        print(resp.json())

        return {"result": NotionOAuthModel.from_dict(resp.json())}

    def get_databases_edited_time_desc(self, access_token: str):
        data = {
            "filter": {
                "value": "database",
                "property": "object"
            },
            "sort": {
                "direction": "descending",
                "timestamp": "last_edited_time"
            }
        }
        resp = requests.post("https://api.notion.com/v1/search", headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Notion-Version': '2022-06-28'
        }, json=data)
        if resp.status_code != 200:
            resp_json = resp.json()
            print(f"Error: HTTP_{resp.status_code} {resp_json}")
            return {
                "error": {
                    "status": resp.status_code,
                    "code": resp_json["code"] if "code" in resp_json else "",
                    "message": resp_json["message"] if "message" in resp_json else "",
                },
            }

        print(resp.json())

        return {"result": NotionDatabaseModel.multi_from_dict(resp.json()["results"])}


client = NotionClient(
    oauth_client_id=os.getenv('NOTION_OAUTH_CLIENT_ID'),
    oauth_client_secret=os.getenv('NOTION_OAUTH_CLIENT_SECRET'),
    oauth_redirect_uri=os.getenv('NOTION_OAUTH_REDIRECT_URI'),
    auth_url=os.getenv('NOTION_AUTH_URL'),
)


def get_notion():
    return client
