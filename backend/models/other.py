from pydantic import BaseModel


class SaveFcmTokenRequest(BaseModel):
    fcm_token: str
    time_zone: str
