"""
Pydantic models for the Spotify Omi plugin.
"""
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class SpotifyTrack(BaseModel):
    """Spotify track information."""
    id: str
    name: str
    artists: List[str]
    album: str
    duration_ms: int
    uri: str
    external_url: Optional[str] = None
    preview_url: Optional[str] = None


class SpotifyPlaylist(BaseModel):
    """Spotify playlist information."""
    id: str
    name: str
    description: Optional[str] = ""
    owner: str
    tracks_total: int
    public: bool
    uri: str
    external_url: Optional[str] = None


class SpotifyArtist(BaseModel):
    """Spotify artist information."""
    id: str
    name: str
    genres: List[str] = []
    popularity: int = 0
    uri: str
    external_url: Optional[str] = None


class SpotifyAlbum(BaseModel):
    """Spotify album information."""
    id: str
    name: str
    artists: List[str]
    release_date: str
    total_tracks: int
    uri: str
    external_url: Optional[str] = None


class NowPlaying(BaseModel):
    """Currently playing track information."""
    is_playing: bool
    track: Optional[SpotifyTrack] = None
    progress_ms: int = 0
    device_name: Optional[str] = None


# Omi Chat Tool Models
class ChatToolRequest(BaseModel):
    """Base request model for Omi chat tools."""
    uid: str
    app_id: str
    tool_name: str


class SearchSongsRequest(ChatToolRequest):
    """Request model for searching songs."""
    query: str
    limit: int = 5


class AddToPlaylistRequest(ChatToolRequest):
    """Request model for adding song to playlist."""
    song_name: str
    artist_name: Optional[str] = None
    playlist_name: Optional[str] = None
    playlist_id: Optional[str] = None


class CreatePlaylistRequest(ChatToolRequest):
    """Request model for creating a playlist."""
    name: str
    description: Optional[str] = ""
    public: bool = False


class GetPlaylistsRequest(ChatToolRequest):
    """Request model for getting user playlists."""
    limit: int = 10


class PlaySongRequest(ChatToolRequest):
    """Request model for playing a song."""
    song_name: str
    artist_name: Optional[str] = None


class ControlPlaybackRequest(ChatToolRequest):
    """Request model for playback control."""
    action: str  # play, pause, next, previous


class GetNowPlayingRequest(ChatToolRequest):
    """Request model for getting currently playing track."""
    pass


class GetRecommendationsRequest(ChatToolRequest):
    """Request model for getting recommendations."""
    seed_tracks: Optional[List[str]] = None
    seed_artists: Optional[List[str]] = None
    seed_genres: Optional[List[str]] = None
    limit: int = 5


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: Optional[str] = None
    error: Optional[str] = None


# Omi Conversation Models (for future memory/webhook integrations)
class TranscriptSegment(BaseModel):
    """Transcript segment from Omi conversation."""
    text: str
    speaker: Optional[str] = "SPEAKER_00"
    is_user: bool
    start: float
    end: float


class Structured(BaseModel):
    """Structured conversation data."""
    title: str
    overview: str
    emoji: str = ""
    category: str = "other"


class Conversation(BaseModel):
    """Omi conversation model."""
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = []
    structured: Structured
    discarded: bool


class EndpointResponse(BaseModel):
    """Standard endpoint response for Omi webhooks."""
    message: str = Field(description="A short message to be sent as notification to the user, if needed.", default="")

