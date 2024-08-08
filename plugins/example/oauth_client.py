import os
import base64
import requests

# """
#    Models
# """


class NotionDatabasePropertyModel:
    def __init__(
        self,
        id, name, propertyType,
    ) -> None:
        self.id = id
        self.name = name
        self.propertyType = propertyType
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
            for property in data["properties"].values():
                properties.append(
                    NotionDatabasePropertyModel.from_dict(property))
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
        oAuthClientId="",
        oAuthClientSecret="",
        oAuthRedirectUri="",
        authUrl="",
    ) -> None:
        self.oAuthClientId = oAuthClientId
        self.oAuthClientSecret = oAuthClientSecret
        self.oAuthRedirectUri = oAuthRedirectUri
        self.authUrl = authUrl
        pass

    def getOAuthUrl(self, uid: str):
        # Should use encryption on state (with some salt) to prevent attacks
        state = uid
        return f"{self.authUrl}&state={state}"

    def getDatabase(self, database_id: str, access_token: str):
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

    def getAccessToken(self, code: str):
        client_id = self.oAuthClientId
        client_secret = self.oAuthClientSecret
        redirect_uri = self.oAuthRedirectUri

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

    def getDatabasesEditedTimeDesc(self, access_token: str):
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
    oAuthClientId=os.getenv('NOTION_OAUTH_CLIENT_ID'),
    oAuthClientSecret=os.getenv('NOTION_OAUTH_CLIENT_SECRET'),
    oAuthRedirectUri=os.getenv('NOTION_OAUTH_REDIRECT_URI'),
    authUrl=os.getenv('NOTION_AUTH_URL'),
)


def getNotion():
    return client
