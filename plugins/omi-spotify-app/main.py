"""Minimal Spotify setup surface for #6792.

GET / is the default-playlist dropdown. Playlist records are built with
playlist_owner_label so a null Spotify owner.display_name cannot 500 the
page.

This is not the full OAuth/chat-tool app. Production traffic is still
served from BasedHardware/omi-spotify-integration — apply the same
owner-label call at its get_user_playlists construction site.
"""

import html
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from playlist_owner import playlists_from_spotify_page

app = FastAPI(title="Spotify Omi setup")


def get_spotify_tokens(uid: str) -> Optional[Dict[str, Any]]:
    """Token seam. Hosts that persist OAuth tokens replace or patch this."""
    return None


def spotify_api_request(
    uid: str,
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Spotify API seam used by the setup playlist list.

    Errors stay generic — never interpolate exception text into the page.
    """
    tokens = get_spotify_tokens(uid)
    if not tokens or not tokens.get("access_token"):
        return {"error": "User not authenticated with Spotify"}
    try:
        import requests
    except ImportError:
        return {"error": "Spotify request failed"}
    try:
        response = requests.request(
            method,
            f"https://api.spotify.com/v1{endpoint}",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            params=params,
            timeout=15,
        )
    except Exception:
        return {"error": "Spotify request failed"}
    if response.status_code >= 400:
        return {"error": "Spotify request failed"}
    if not response.content:
        return {"success": True}
    try:
        return response.json()
    except ValueError:
        return {"error": "Spotify request failed"}


def get_user_playlists(uid: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Crash site for #6792: parse /me/playlists into dropdown records."""
    result = spotify_api_request(uid, "GET", "/me/playlists", params={"limit": limit})
    if "error" in result:
        return []
    return playlists_from_spotify_page(result)


def _option(playlist: Dict[str, Any]) -> str:
    playlist_id = html.escape(str(playlist["id"]))
    name = html.escape(str(playlist["name"]))
    tracks = playlist["tracks_total"]
    return f'<option value="{playlist_id}">{name} ({tracks} tracks)</option>'


def render_setup_page(
    *,
    uid: str,
    playlists: List[Dict[str, Any]],
    authenticated: bool,
    error: Optional[str] = None,
) -> str:
    error_html = f"<p>{html.escape(error)}</p>" if error else ""
    if not authenticated:
        return (
            "<!DOCTYPE html><html><head><title>Spotify for Omi</title></head>"
            f"<body>{error_html}<p>Connect Spotify to choose a default playlist.</p>"
            "</body></html>"
        )
    options = ['<option value="">Select a default playlist...</option>']
    options.extend(_option(playlist) for playlist in playlists)
    uid_attr = html.escape(uid)
    return (
        "<!DOCTYPE html><html><head><title>Spotify for Omi</title></head><body>"
        f"{error_html}<label for=\"playlist-select\">Default playlist</label>"
        f'<select id="playlist-select" data-uid="{uid_attr}">{"".join(options)}</select>'
        "</body></html>"
    )


@app.get("/")
async def home(uid: Optional[str] = None) -> HTMLResponse:
    """App settings page: default-playlist dropdown after OAuth."""
    if not uid:
        return HTMLResponse(
            content=render_setup_page(
                uid="",
                playlists=[],
                authenticated=False,
                error="Missing user ID",
            )
        )
    tokens = get_spotify_tokens(uid)
    authenticated = tokens is not None
    playlists = get_user_playlists(uid, limit=50) if authenticated else []
    return HTMLResponse(
        content=render_setup_page(uid=uid, playlists=playlists, authenticated=authenticated)
    )
