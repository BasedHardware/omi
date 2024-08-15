from pydantic import BaseModel


class MemoryTimestampRange(BaseModel):
    start: int
    end: int


class ScreenPipeCreateMemory(BaseModel):
    request_id: str
    source: str
    text: str
    timestamp_range: MemoryTimestampRange


class EmptyResponse(BaseModel):
    pass
