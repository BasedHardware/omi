"""
Spotify Integration App for Omi

This app provides Spotify integration through OAuth authentication
and chat tools for searching songs, managing playlists, and controlling playback.
"""
import os
import base64
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import (
    store_spotify_tokens,
    get_spotify_tokens,
    delete_spotify_tokens,
    is_token_expired,
    store_default_playlist,
    get_default_playlist,
    get_user_settings,
)
from models import (
    ChatToolResponse,
    SearchSongsRequest,
    AddToPlaylistRequest,
    CreatePlaylistRequest,
    GetPlaylistsRequest,
    PlaySongRequest,
    ControlPlaybackRequest,
    GetNowPlayingRequest,
    GetRecommendationsRequest,
    SpotifyTrack,
    SpotifyPlaylist,
)

load_dotenv()

# Spotify API Configuration
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID") or ""
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET") or ""
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/auth/spotify/callback")

def _require_spotify_credentials() -> None:
    """Refuse to run OAuth/token exchange without env-configured credentials."""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in the environment "
            "(no in-repo defaults)."
        )


# Spotify API endpoints
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

# Required Spotify scopes
SPOTIFY_SCOPES = [
    "user-read-private",
    "user-read-email",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-library-modify",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played",
]

app = FastAPI(
    title="Spotify Omi Integration",
    description="Spotify integration for Omi - Search songs, manage playlists, control playback",
    version="1.0.0"
)

# Mount static files and templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
if os.path.exists(templates_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(templates_dir, "static")), name="static")
templates = Jinja2Templates(directory=templates_dir)


# ============================================
# Helper Functions
# ============================================

def get_auth_header(access_token: str) -> Dict[str, str]:
    """Get authorization header for Spotify API requests."""
    return {"Authorization": f"Bearer {access_token}"}


def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh the Spotify access token."""
    _require_spotify_credentials()
    auth_header = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    
    response = requests.post(
        SPOTIFY_TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    
    if response.status_code == 200:
        return response.json()
    return None


def get_valid_access_token(uid: str) -> Optional[str]:
    """Get a valid access token, refreshing if necessary."""
    tokens = get_spotify_tokens(uid)
    if not tokens:
        return None
    
    if is_token_expired(uid):
        # Refresh the token
        new_tokens = refresh_access_token(tokens["refresh_token"])
        if new_tokens:
            expires_at = int(datetime.utcnow().timestamp()) + new_tokens.get("expires_in", 3600)
            store_spotify_tokens(
                uid,
                new_tokens["access_token"],
                new_tokens.get("refresh_token", tokens["refresh_token"]),
                expires_at
            )
            return new_tokens["access_token"]
        return None
    
    return tokens["access_token"]


def spotify_api_request(
    uid: str,
    method: str,
    endpoint: str,
    params: Optional[Dict] = None,
    json_data: Optional[Dict] = None
) -> Dict[str, Any]:
    """Make an authenticated request to Spotify API."""
    access_token = get_valid_access_token(uid)
    if not access_token:
        return {"error": "User not authenticated with Spotify"}
    
    url = f"{SPOTIFY_API_BASE}{endpoint}"
    headers = get_auth_header(access_token)
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=json_data, params=params)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=json_data, params=params)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, params=params)
        else:
            return {"error": f"Unsupported HTTP method: {method}"}
        
        if response.status_code == 204:
            return {"success": True}
        elif response.status_code >= 400:
            error_data = response.json() if response.content else {}
            return {"error": error_data.get("error", {}).get("message", f"API error: {response.status_code}")}
        
        return response.json() if response.content else {"success": True}
    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


def search_tracks(uid: str, query: str, limit: int = 5) -> List[SpotifyTrack]:
    """Search for tracks on Spotify."""
    result = spotify_api_request(
        uid, "GET", "/search",
        params={"q": query, "type": "track", "limit": limit}
    )
    
    if "error" in result:
        return []
    
    tracks = []
    for item in result.get("tracks", {}).get("items", []):
        tracks.append(SpotifyTrack(
            id=item["id"],
            name=item["name"],
            artists=[a["name"] for a in item["artists"]],
            album=item["album"]["name"],
            duration_ms=item["duration_ms"],
            uri=item["uri"],
            external_url=item.get("external_urls", {}).get("spotify"),
            preview_url=item.get("preview_url")
        ))
    return tracks


def playlist_owner_label(owner: Dict[str, Any]) -> str:
    """Spotify may omit owner display_name; SpotifyPlaylist.owner requires a string."""
    display_name = owner.get("display_name")
    if display_name is not None:
        return display_name
    return owner["id"]


def get_user_playlists(uid: str, limit: int = 20) -> List[SpotifyPlaylist]:
    """Get user's playlists."""
    result = spotify_api_request(
        uid, "GET", "/me/playlists",
        params={"limit": limit}
    )
    
    if "error" in result:
        return []
    
    playlists = []
    for item in result.get("items", []):
        playlists.append(SpotifyPlaylist(
            id=item["id"],
            name=item["name"],
            description=item.get("description", ""),
            owner=playlist_owner_label(item["owner"]),
            tracks_total=item["tracks"]["total"],
            public=item.get("public", False),
            uri=item["uri"],
            external_url=item.get("external_urls", {}).get("spotify")
        ))
    return playlists


def find_playlist_by_name(uid: str, name: str) -> Optional[SpotifyPlaylist]:
    """Find a playlist by name (case-insensitive partial match)."""
    playlists = get_user_playlists(uid, limit=50)
    name_lower = name.lower()
    
    # First try exact match
    for playlist in playlists:
        if playlist.name.lower() == name_lower:
            return playlist
    
    # Then try partial match
    for playlist in playlists:
        if name_lower in playlist.name.lower():
            return playlist
    
    return None


# ============================================
# OAuth Endpoints
# ============================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, uid: Optional[str] = None):
    """Home page / App settings page."""
    if not uid:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Missing user ID"
        })
    
    tokens = get_spotify_tokens(uid)
    authenticated = tokens is not None
    
    # Get user profile if authenticated
    user_profile = None
    playlists = []
    default_playlist = None
    
    if authenticated:
        profile_result = spotify_api_request(uid, "GET", "/me")
        if "error" not in profile_result:
            user_profile = profile_result
        
        playlists = get_user_playlists(uid, limit=50)
        default_playlist = get_default_playlist(uid)
    
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "uid": uid,
        "authenticated": authenticated,
        "user_profile": user_profile,
        "playlists": playlists,
        "default_playlist": default_playlist,
        "oauth_url": f"/auth/spotify?uid={uid}"
    })


@app.get("/auth/spotify")
async def spotify_auth(uid: str):
    """Initiate Spotify OAuth flow."""
    _require_spotify_credentials()
    if not uid:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": " ".join(SPOTIFY_SCOPES),
        "state": uid,
        "show_dialog": "true"
    }
    
    auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/auth/spotify/callback", response_class=HTMLResponse)
async def spotify_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Spotify OAuth callback."""
    if error:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": f"Authorization failed: {error}"
        })
    
    if not code or not state:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Invalid callback parameters"
        })
    
    uid = state
    
    # Exchange code for tokens
    _require_spotify_credentials()
    auth_header = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    
    response = requests.post(
        SPOTIFY_TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
        },
    )
    
    if response.status_code != 200:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Failed to exchange authorization code"
        })
    
    token_data = response.json()
    expires_at = int(datetime.utcnow().timestamp()) + token_data.get("expires_in", 3600)
    
    store_spotify_tokens(
        uid,
        token_data["access_token"],
        token_data["refresh_token"],
        expires_at
    )
    
    # Redirect to home with uid
    return RedirectResponse(url=f"/?uid={uid}")


@app.get("/setup/spotify", tags=["setup"])
async def check_setup(uid: str):
    """Check if the user has completed Spotify setup (used by Omi)."""
    tokens = get_spotify_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.post("/settings/default-playlist")
async def set_default_playlist(uid: str, playlist_id: str, playlist_name: str):
    """Set the default playlist for a user."""
    store_default_playlist(uid, playlist_id, playlist_name)
    return {"success": True, "message": f"Default playlist set to: {playlist_name}"}


@app.get("/disconnect")
async def disconnect_spotify(uid: str):
    """Disconnect Spotify account."""
    delete_spotify_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


# ============================================
# Chat Tool Endpoints
# ============================================

@app.post("/tools/search_songs", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_search_songs(request: Request):
    """
    Search for songs on Spotify.
    Chat tool for Omi - searches Spotify and returns matching tracks.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        query = body.get("query", "")
        limit = body.get("limit", 5)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not query:
            return ChatToolResponse(error="Search query is required")
        
        # Check authentication
        if not get_spotify_tokens(uid):
            return ChatToolResponse(error="Please connect your Spotify account first in the app settings.")
        
        tracks = search_tracks(uid, query, limit)
        
        if not tracks:
            return ChatToolResponse(result=f"No songs found for '{query}'")
        
        # Format results
        results = []
        for i, track in enumerate(tracks, 1):
            artists = ", ".join(track.artists)
            duration = f"{track.duration_ms // 60000}:{(track.duration_ms % 60000) // 1000:02d}"
            results.append(f"{i}. **{track.name}** by {artists} ({duration}) - Album: {track.album}")
        
        return ChatToolResponse(result=f"🎵 Found {len(tracks)} songs:\n\n" + "\n".join(results))
    
    except Exception as e:
        return ChatToolResponse(error=f"Search failed: {str(e)}")


@app.post("/tools/add_to_playlist", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_add_to_playlist(request: Request):
    """
    Add a song to a Spotify playlist.
    Chat tool for Omi - searches for the song and adds it to the specified playlist.
    """
    try:
        body = await request.json()
        print(f"🎵 ADD TO PLAYLIST - Received request: {body}")
        uid = body.get("uid")
        song_name = body.get("song_name", "")
        artist_name = body.get("artist_name", "")
        playlist_name = body.get("playlist_name")
        playlist_id = body.get("playlist_id")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not song_name:
            return ChatToolResponse(error="Song name is required")
        
        # Check authentication
        if not get_spotify_tokens(uid):
            return ChatToolResponse(error="Please connect your Spotify account first in the app settings.")
        
        # Build search query
        search_query = song_name
        if artist_name:
            search_query = f"{song_name} artist:{artist_name}"
        
        # Search for the song
        tracks = search_tracks(uid, search_query, limit=1)
        
        if not tracks:
            return ChatToolResponse(error=f"Could not find song: {song_name}")
        
        track = tracks[0]
        
        # Determine which playlist to use
        target_playlist = None
        
        if playlist_id:
            # Use provided playlist ID
            target_playlist = SpotifyPlaylist(
                id=playlist_id,
                name=playlist_name or "Unknown",
                owner="",
                tracks_total=0,
                public=False,
                uri=f"spotify:playlist:{playlist_id}"
            )
        elif playlist_name:
            # Find playlist by name
            target_playlist = find_playlist_by_name(uid, playlist_name)
            if not target_playlist:
                return ChatToolResponse(error=f"Could not find playlist: {playlist_name}")
        else:
            # Use default playlist
            default = get_default_playlist(uid)
            if default:
                target_playlist = SpotifyPlaylist(
                    id=default["id"],
                    name=default["name"],
                    owner="",
                    tracks_total=0,
                    public=False,
                    uri=f"spotify:playlist:{default['id']}"
                )
            else:
                return ChatToolResponse(error="No playlist specified and no default playlist set. Please specify a playlist name or set a default in app settings.")
        
        # Add track to playlist
        print(f"🎵 Adding track {track.uri} to playlist {target_playlist.id} ({target_playlist.name})")
        result = spotify_api_request(
            uid, "POST",
            f"/playlists/{target_playlist.id}/tracks",
            json_data={"uris": [track.uri]}
        )
        print(f"🎵 Spotify API response: {result}")
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to add song: {result['error']}")
        
        artists = ", ".join(track.artists)
        print(f"🎵 SUCCESS: Added {track.name} by {artists} to {target_playlist.name}")
        return ChatToolResponse(
            result=f"✅ Added **{track.name}** by {artists} to playlist **{target_playlist.name}**!"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to add song: {str(e)}")


@app.post("/tools/create_playlist", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_create_playlist(request: Request):
    """
    Create a new Spotify playlist.
    Chat tool for Omi - creates a new playlist with the specified name.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        name = body.get("name", "")
        description = body.get("description", "Created with Omi")
        public = body.get("public", False)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not name:
            return ChatToolResponse(error="Playlist name is required")
        
        # Check authentication
        if not get_spotify_tokens(uid):
            return ChatToolResponse(error="Please connect your Spotify account first in the app settings.")
        
        # Get user ID
        profile = spotify_api_request(uid, "GET", "/me")
        if "error" in profile:
            return ChatToolResponse(error="Failed to get user profile")
        
        spotify_user_id = profile["id"]
        
        # Create playlist
        result = spotify_api_request(
            uid, "POST",
            f"/users/{spotify_user_id}/playlists",
            json_data={
                "name": name,
                "description": description,
                "public": public
            }
        )
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to create playlist: {result['error']}")
        
        playlist_url = result.get("external_urls", {}).get("spotify", "")
        return ChatToolResponse(
            result=f"✅ Created playlist **{name}**!\n\nOpen in Spotify: {playlist_url}"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to create playlist: {str(e)}")


@app.post("/tools/get_playlists", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_playlists(request: Request):
    """
    Get user's Spotify playlists.
    Chat tool for Omi - retrieves the user's playlists.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        limit = body.get("limit", 10)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_spotify_tokens(uid):
            return ChatToolResponse(error="Please connect your Spotify account first in the app settings.")
        
        playlists = get_user_playlists(uid, limit)
        
        if not playlists:
            return ChatToolResponse(result="You don't have any playlists yet.")
        
        # Format results
        results = []
        for i, playlist in enumerate(playlists, 1):
            visibility = "🌐" if playlist.public else "🔒"
            results.append(f"{i}. {visibility} **{playlist.name}** ({playlist.tracks_total} tracks)")
        
        return ChatToolResponse(result=f"📋 Your playlists:\n\n" + "\n".join(results))
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get playlists: {str(e)}")


@app.post("/tools/get_now_playing", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_now_playing(request: Request):
    """
    Get currently playing track on Spotify.
    Chat tool for Omi - shows what's currently playing.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_spotify_tokens(uid):
            return ChatToolResponse(error="Please connect your Spotify account first in the app settings.")
        
        result = spotify_api_request(uid, "GET", "/me/player/currently-playing")
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get playback: {result['error']}")
        
        if not result or not result.get("item"):
            return ChatToolResponse(result="🔇 Nothing is currently playing on Spotify.")
        
        track = result["item"]
        is_playing = result.get("is_playing", False)
        progress_ms = result.get("progress_ms", 0)
        
        artists = ", ".join([a["name"] for a in track["artists"]])
        duration_ms = track["duration_ms"]
        
        progress = f"{progress_ms // 60000}:{(progress_ms % 60000) // 1000:02d}"
        duration = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}"
        
        status = "▶️ Playing" if is_playing else "⏸️ Paused"
        
        return ChatToolResponse(
            result=f"{status}: **{track['name']}** by {artists}\n"
                   f"Album: {track['album']['name']}\n"
                   f"Progress: {progress} / {duration}"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get current playback: {str(e)}")


@app.post("/tools/control_playback", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_control_playback(request: Request):
    """
    Control Spotify playback (play, pause, next, previous).
    Chat tool for Omi - controls music playback.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        action = body.get("action", "").lower()
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if action not in ["play", "pause", "next", "previous", "skip"]:
            return ChatToolResponse(error="Invalid action. Use: play, pause, next, previous")
        
        # Check authentication
        if not get_spotify_tokens(uid):
            return ChatToolResponse(error="Please connect your Spotify account first in the app settings.")
        
        # Map action to endpoint
        endpoint_map = {
            "play": ("/me/player/play", "PUT"),
            "pause": ("/me/player/pause", "PUT"),
            "next": ("/me/player/next", "POST"),
            "skip": ("/me/player/next", "POST"),
            "previous": ("/me/player/previous", "POST"),
        }
        
        endpoint, method = endpoint_map[action]
        result = spotify_api_request(uid, method, endpoint)
        
        if "error" in result:
            if "No active device" in str(result.get("error", "")):
                return ChatToolResponse(error="No active Spotify device found. Please open Spotify on one of your devices first.")
            return ChatToolResponse(error=f"Playback control failed: {result['error']}")
        
        action_messages = {
            "play": "▶️ Resumed playback",
            "pause": "⏸️ Paused playback",
            "next": "⏭️ Skipped to next track",
            "skip": "⏭️ Skipped to next track",
            "previous": "⏮️ Went to previous track",
        }
        
        return ChatToolResponse(result=action_messages[action])
    
    except Exception as e:
        return ChatToolResponse(error=f"Playback control failed: {str(e)}")


@app.post("/tools/play_song", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_play_song(request: Request):
    """
    Search and play a specific song on Spotify.
    Chat tool for Omi - finds and plays a song.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        song_name = body.get("song_name", "")
        artist_name = body.get("artist_name", "")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not song_name:
            return ChatToolResponse(error="Song name is required")
        
        # Check authentication
        if not get_spotify_tokens(uid):
            return ChatToolResponse(error="Please connect your Spotify account first in the app settings.")
        
        # Build search query
        search_query = song_name
        if artist_name:
            search_query = f"{song_name} artist:{artist_name}"
        
        # Search for the song
        tracks = search_tracks(uid, search_query, limit=1)
        
        if not tracks:
            return ChatToolResponse(error=f"Could not find song: {song_name}")
        
        track = tracks[0]
        
        # Play the track
        result = spotify_api_request(
            uid, "PUT", "/me/player/play",
            json_data={"uris": [track.uri]}
        )
        
        if "error" in result:
            if "No active device" in str(result.get("error", "")):
                return ChatToolResponse(
                    error="No active Spotify device found. Please open Spotify on one of your devices first."
                )
            return ChatToolResponse(error=f"Failed to play: {result['error']}")
        
        artists = ", ".join(track.artists)
        return ChatToolResponse(
            result=f"▶️ Now playing: **{track.name}** by {artists}"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to play song: {str(e)}")


@app.post("/tools/get_recommendations", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_recommendations(request: Request):
    """
    Get song recommendations from Spotify.
    Chat tool for Omi - gets personalized recommendations.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        seed_tracks = body.get("seed_tracks", [])
        seed_artists = body.get("seed_artists", [])
        seed_genres = body.get("seed_genres", [])
        limit = body.get("limit", 5)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_spotify_tokens(uid):
            return ChatToolResponse(error="Please connect your Spotify account first in the app settings.")
        
        # If no seeds provided, get from recently played
        if not seed_tracks and not seed_artists and not seed_genres:
            recent = spotify_api_request(uid, "GET", "/me/player/recently-played", params={"limit": 5})
            if "error" not in recent and recent.get("items"):
                seed_tracks = [item["track"]["id"] for item in recent["items"][:5]]
        
        params = {"limit": limit}
        if seed_tracks:
            params["seed_tracks"] = ",".join(seed_tracks[:5])
        if seed_artists:
            params["seed_artists"] = ",".join(seed_artists[:5])
        if seed_genres:
            params["seed_genres"] = ",".join(seed_genres[:5])
        
        result = spotify_api_request(uid, "GET", "/recommendations", params=params)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get recommendations: {result['error']}")
        
        tracks = result.get("tracks", [])
        if not tracks:
            return ChatToolResponse(result="No recommendations found.")
        
        # Format results
        results = []
        for i, track in enumerate(tracks, 1):
            artists = ", ".join([a["name"] for a in track["artists"]])
            results.append(f"{i}. **{track['name']}** by {artists}")
        
        return ChatToolResponse(result=f"🎧 Recommended songs for you:\n\n" + "\n".join(results))
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get recommendations: {str(e)}")


# ============================================
# Omi Chat Tools Manifest
# ============================================

@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    """
    Omi Chat Tools Manifest endpoint.
    
    This endpoint returns the chat tools definitions that Omi will fetch
    when the app is created or updated in the Omi App Store.
    """
    return {
        "tools": [
            {
                "name": "search_songs",
                "description": "Search for songs on Spotify. Use this when the user wants to find songs, look up music, or search for tracks by name, artist, or album.",
                "endpoint": "/tools/search_songs",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query - song name, artist name, or album name"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 5)"
                        }
                    },
                    "required": ["query"]
                },
                "auth_required": True,
                "status_message": "Searching Spotify..."
            },
            {
                "name": "add_to_playlist",
                "description": "Add a song to a Spotify playlist. Use this when the user wants to add a song or track to one of their playlists.",
                "endpoint": "/tools/add_to_playlist",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "song_name": {
                            "type": "string",
                            "description": "Name of the song to add"
                        },
                        "artist_name": {
                            "type": "string",
                            "description": "Artist name (helps find the exact song)"
                        },
                        "playlist_name": {
                            "type": "string",
                            "description": "Name of the playlist to add to (uses default if not specified)"
                        }
                    },
                    "required": ["song_name"]
                },
                "auth_required": True,
                "status_message": "Adding to playlist..."
            },
            {
                "name": "create_playlist",
                "description": "Create a new Spotify playlist. Use this when the user wants to create or make a new playlist.",
                "endpoint": "/tools/create_playlist",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the new playlist"
                        },
                        "description": {
                            "type": "string",
                            "description": "Description for the playlist"
                        },
                        "public": {
                            "type": "boolean",
                            "description": "Whether the playlist should be public (default: false)"
                        }
                    },
                    "required": ["name"]
                },
                "auth_required": True,
                "status_message": "Creating playlist..."
            },
            {
                "name": "get_playlists",
                "description": "Get the user's Spotify playlists. Use this when the user wants to see their playlists or check what playlists they have.",
                "endpoint": "/tools/get_playlists",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of playlists to return (default: 10)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your playlists..."
            },
            {
                "name": "get_now_playing",
                "description": "Get the currently playing track on Spotify. Use this when the user asks what's playing or wants to know the current track.",
                "endpoint": "/tools/get_now_playing",
                "method": "POST",
                "parameters": {
                    "properties": {},
                    "required": []
                },
                "auth_required": True,
                "status_message": "Checking what's playing..."
            },
            {
                "name": "control_playback",
                "description": "Control Spotify playback - play, pause, skip to next, or go to previous track. Use this when the user wants to control their music.",
                "endpoint": "/tools/control_playback",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Playback action: 'play', 'pause', 'next', 'skip', or 'previous'"
                        }
                    },
                    "required": ["action"]
                },
                "auth_required": True,
                "status_message": "Controlling playback..."
            },
            {
                "name": "play_song",
                "description": "Search for and play a specific song on Spotify. Use this when the user wants to play a particular song.",
                "endpoint": "/tools/play_song",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "song_name": {
                            "type": "string",
                            "description": "Name of the song to play"
                        },
                        "artist_name": {
                            "type": "string",
                            "description": "Artist name (helps find the exact song)"
                        }
                    },
                    "required": ["song_name"]
                },
                "auth_required": True,
                "status_message": "Playing song..."
            },
            {
                "name": "get_recommendations",
                "description": "Get personalized song recommendations from Spotify. Use this when the user wants music suggestions or to discover new songs.",
                "endpoint": "/tools/get_recommendations",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of recommendations to return (default: 5)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting recommendations..."
            }
        ]
    }


# ============================================
# Health Check
# ============================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "spotify-omi-integration"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

