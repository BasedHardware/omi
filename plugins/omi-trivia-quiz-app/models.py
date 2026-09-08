"""Pydantic models for Omi Open Trivia & Quiz Integration App."""

from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class GetTriviaQuestionRequest(BaseModel):
    """Request model for retrieving a trivia question."""

    category: Optional[str] = Field(
        default=None,
        description="Optional category name or keyword (e.g. 'Science', 'History', 'Computers', 'Film', 'Geography').",
    )
    difficulty: Optional[Literal["easy", "medium", "hard"]] = Field(
        default=None,
        description="Optional difficulty level ('easy', 'medium', or 'hard').",
    )
    question_type: Optional[Literal["multiple", "boolean"]] = Field(
        default=None,
        description="Optional question type ('multiple' for multiple choice, 'boolean' for True/False).",
    )


class QuickTrueFalseQuizRequest(BaseModel):
    """Request model for a quick True/False voice challenge."""

    category: Optional[str] = Field(
        default=None,
        description="Optional category keyword (e.g. 'Science', 'Animals', 'Geography', 'History').",
    )
    difficulty: Optional[Literal["easy", "medium", "hard"]] = Field(
        default=None,
        description="Optional difficulty level ('easy', 'medium', or 'hard').",
    )


class ListCategoriesRequest(BaseModel):
    """Request model for listing all available trivia categories."""

    pass
