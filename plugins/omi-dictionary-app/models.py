"""Request, response and upstream dictionary data contracts."""

from pydantic import BaseModel, Field, field_validator


class WordRequest(BaseModel):
    word: str = Field(
        min_length=1, max_length=80, description="An English word or short phrase, such as 'serendipity'."
    )

    @field_validator("word")
    @classmethod
    def normalize_word(cls, value: str) -> str:
        word = " ".join(value.lower().split())
        if not any(char.isalpha() for char in word) or any(not (char.isalpha() or char in " '-’") for char in word):
            raise ValueError("Enter a word using letters, spaces, apostrophes or hyphens.")
        return word


class DefinitionRequest(WordRequest):
    max_definitions: int = Field(default=3, ge=1, le=5, description="Maximum number of meanings to return.")


class ChatToolResponse(BaseModel):
    result: str | None = None
    error: str | None = None


class License(BaseModel):
    name: str = ""
    url: str = ""


class Phonetic(BaseModel):
    text: str = ""
    audio: str = ""
    sourceUrl: str = ""
    license: License | None = None


class Definition(BaseModel):
    definition: str
    example: str = ""
    synonyms: list[str] = Field(default_factory=list)


class Meaning(BaseModel):
    partOfSpeech: str = ""
    definitions: list[Definition] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class Entry(BaseModel):
    word: str
    phonetic: str = ""
    phonetics: list[Phonetic] = Field(default_factory=list)
    meanings: list[Meaning] = Field(default_factory=list)
    license: License | None = None
    sourceUrls: list[str] = Field(default_factory=list)
