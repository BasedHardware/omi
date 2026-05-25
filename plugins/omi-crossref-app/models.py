from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    message: str
