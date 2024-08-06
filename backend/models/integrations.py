from pydantic import BaseModel


class ScreenPipeCreateMemory(BaseModel):
    memory_source: str
    memory_text: str
