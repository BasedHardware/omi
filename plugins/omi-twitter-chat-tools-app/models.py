"""Pydantic models for Twitter Omi Integration."""
from typing import Optional
from pydantic import BaseModel, field_validator


class ChatToolResponse(BaseModel):
    """Response model for chat tool endpoints."""
    result: Optional[str] = None
    error: Optional[str] = None


class BaseToolRequest(BaseModel):
    """Base tool request containing uid."""
    uid: Optional[str] = None


class PostTweetRequest(BaseToolRequest):
    """Request model for posting a tweet."""
    text: Optional[str] = None
    reply_to: Optional[str] = None

    @field_validator("text")
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
        return v

    @field_validator("reply_to")
    @classmethod
    def sanitize_reply_to(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = str(v).strip().lstrip("#")
        return v or None


class PaginationToolRequest(BaseToolRequest):
    """Request model for endpoints taking max_results/count."""
    max_results: Optional[int] = None
    count: Optional[int] = None


class GetTimelineRequest(PaginationToolRequest):
    pass


class GetMyTweetsRequest(PaginationToolRequest):
    pass


class GetMentionsRequest(PaginationToolRequest):
    pass


class SearchTweetsRequest(PaginationToolRequest):
    """Request model for searching tweets."""
    query: Optional[str] = None

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
        return v


class TweetActionRequest(BaseToolRequest):
    """Request model for actions taking tweet_id (like, retweet, delete)."""
    tweet_id: Optional[str] = None

    @field_validator("tweet_id")
    @classmethod
    def sanitize_tweet_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = str(v).strip().lstrip("#")
        return v or None


class LikeTweetRequest(TweetActionRequest):
    pass


class UnlikeTweetRequest(TweetActionRequest):
    pass


class RetweetRequest(TweetActionRequest):
    pass


class DeleteTweetRequest(TweetActionRequest):
    pass


class GetUserProfileRequest(BaseToolRequest):
    """Request model for user profile lookup."""
    username: Optional[str] = None

    @field_validator("username")
    @classmethod
    def sanitize_username(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            # Strip whitespace, strip leading @, strip URL prefix if any
            v = v.strip()
            if v.startswith("http://") or v.startswith("https://"):
                v = v.rstrip("/").split("/")[-1]
            v = v.lstrip("@").strip()
        return v or None
