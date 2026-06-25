from typing import Any, Iterable

from pydantic import BaseModel, Field


class ConversationMetadataKeys:
    UID = 'uid'
    MEMORY_ID = 'memory_id'
    CREATED_AT = 'created_at'
    PEOPLE = 'people'
    TOPICS = 'topics'
    ENTITIES = 'entities'
    DATES = 'dates'


class ConversationMetadata(BaseModel):
    people: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)

    def to_vector_metadata(self) -> dict[str, list[str]]:
        return {
            ConversationMetadataKeys.PEOPLE: self.people,
            ConversationMetadataKeys.TOPICS: self.topics,
            ConversationMetadataKeys.ENTITIES: self.entities,
            ConversationMetadataKeys.DATES: self.dates,
        }


def metadata_list(metadata: dict[str, Any], key: str) -> list[str]:
    value = metadata.get(key, [])
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def normalize_metadata_values(values: Iterable[str]) -> list[str]:
    return [value for value in values if value]
