```python
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

class Announcement(BaseModel):
    id: str = Field(..., description="The id of the announcement")
    created_at: datetime = Field(
        None, description="The datetime when the announcement was created"
    )
    expires_at: datetime = Field(
        None, description="The datetime when the announcement expires"
    )
    content: Optional[str] = Field(None, description="The content of the announcement")
    active: Optional[bool] = Field(None, description="Whether the announcement is active")
    device_models: Optional[list[str]] = Field(
        None, description="List of device models targeted by the announcement"
    )
    show_once: bool = Field(None, description="Whether the announcement should be shown once")

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_dict(cls, data: dict) -> "Announcement":
        data = {
            key: value
            for key, value in data.items()
            if key in cls.__fields__
        }
        return super().from_dict(data)

def _doc_to_announcement(doc) -> Announcement:
    data = dict(doc)
    id = data.pop("id", None)
    if not id:
        id = doc.id
    data["id"] = str(id)
    return Announcement.from_dict(data)
```

```python
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

class Announcement(BaseModel):
    id: str = Field(..., description="The id of the announcement")
    created_at: datetime = Field(
        None, description="The datetime when the announcement was created"
    )
    expires_at: datetime = Field(
        None, description="The datetime when the announcement expires"
    )
    content: Optional[str] = Field(None, description="The content of the announcement")
    active: Optional[bool] = Field(None, description="Whether the announcement is active")
    device_models: Optional[list[str]] = Field(
        None, description="List of device models targeted by the announcement"
    )
    show_once: bool = Field(None, description="Whether the announcement should be shown once")

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_dict(cls, data: dict) -> "Announcement":
        data = {
            key: value
            for key, value in data.items()
            if key in cls.__fields__
        }
        return super().from_dict(data)

def _doc_to_announcement(doc) -> Announcement:
    data = dict(doc)
    id = data.pop("id", None)
    if not id:
        id = doc.id
    data["id"] = str(id)
    return Announcement.from_dict(data)
```

```python
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

class Announcement(BaseModel):
    id: str = Field(..., description="The id of the announcement")
    created_at: datetime = Field(
        None, description="The datetime when the announcement was created"
    )
    expires_at: datetime = Field(
        None, description="The datetime when the announcement expires"
    )
    content: Optional[str] = Field(None, description="The content of the announcement")
    active: Optional[bool] = Field(None, description="Whether the announcement is active")
    device_models: Optional[list[str]] = Field(
        None, description="List of device models targeted by the announcement"
    )
    show_once: bool = Field(None, description="Whether the announcement should be shown once")

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_dict(cls, data: dict) -> "Announcement":
        data = {
            key: value
            for key, value in data.items()
            if key in cls.__fields__
        }
        return super().from_dict(data)

def _doc_to_announcement(doc) -> Announcement:
    data = dict(doc)
    id = data.pop("id", None)
    if not id:
        id = doc.id
    data["id"] = str(id)
    return Announcement.from_dict(data)
```