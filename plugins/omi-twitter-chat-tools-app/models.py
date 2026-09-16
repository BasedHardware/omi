"""Pydantic models for Twitter Omi Integration."""
from typing import Optional
from pydantic import BaseModel, Field


class ChatToolResponse(BaseModel):
    """Response model for chat tool endpoints."""
    result: Optional[str] = None
    error: Optional[str] = None


class PostTweetRequest(BaseModel):
    """Request model for post_tweet."""
    uid: str = Field(..., description="User ID")
    text: str = Field(..., description="Tweet text")
    reply_to: Optional[str] = Field(None, description="Tweet ID to reply to")


class GetTimelineRequest(BaseModel):
    """Request model for get_timeline."""
    uid: str = Field(..., description="User ID")
    max_results: Optional[int] = Field(10, description="Max results (1-100)")


class GetMyTweetsRequest(BaseModel):
    """Request model for get_my_tweets."""
    uid: str = Field(..., description="User ID")
    max_results: Optional[int] = Field(10, description="Max results (5-100)")


class GetMentionsRequest(BaseModel):
    """Request model for get_mentions."""
    uid: str = Field(..., description="User ID")
    max_results: Optional[int] = Field(10, description="Max results (5-100)")


class SearchTweetsRequest(BaseModel):
    """Request model for search_tweets."""
    uid: str = Field(..., description="User ID")
    query: str = Field(..., description="Search query")
    max_results: Optional[int] = Field(10, description="Max results (10-100)")


class LikeTweetRequest(BaseModel):
    """Request model for like_tweet."""
    uid: str = Field(..., description="User ID")
    tweet_id: str = Field(..., description="Tweet ID to like")


class UnlikeTweetRequest(BaseModel):
    """Request model for unlike_tweet."""
    uid: str = Field(..., description="User ID")
    tweet_id: str = Field(..., description="Tweet ID to unlike")


class RetweetRequest(BaseModel):
    """Request model for retweet."""
    uid: str = Field(..., description="User ID")
    tweet_id: str = Field(..., description="Tweet ID to retweet")


class DeleteTweetRequest(BaseModel):
    """Request model for delete_tweet."""
    uid: str = Field(..., description="User ID")
    tweet_id: str = Field(..., description="Tweet ID to delete")


class GetUserProfileRequest(BaseModel):
    """Request model for get_user_profile."""
    uid: str = Field(..., description="User ID")
    username: Optional[str] = Field(None, description="Twitter username (without @)")
