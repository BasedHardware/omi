from pydantic import BaseModel


class SaveFcmTokenRequest(BaseModel):
    token: str
    time_zone: str
