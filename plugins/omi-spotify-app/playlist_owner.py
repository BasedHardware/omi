"""Null-safe Spotify playlist owner labels for #6792.

Spotify's playlist payload allows `owner.display_name` to be null. The
setup route used to assign that value to a required string field, so
validation raised and `/` returned HTTP 500 — the default-playlist
dropdown looked empty.

`main.get_user_playlists` is the in-repo call site. Production traffic is
still served from BasedHardware/omi-spotify-integration; apply the same
`playlist_owner_label` call at its playlist-construction site.
"""

from typing import Any, Dict, List, Mapping


def playlist_owner_label(owner: Mapping[str, Any]) -> str:
    """Spotify may omit owner display_name; playlist owner requires a string."""
    display_name = owner.get("display_name")
    if display_name is not None:
        return display_name
    return owner["id"]


def playlist_from_spotify_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    """Parse one Spotify playlist item the way the setup route used to.

    A null `owner.display_name` must become a string (the owner id) so the
    required-string owner field never sees None.
    """
    owner_label = playlist_owner_label(item["owner"])
    if not isinstance(owner_label, str):
        raise TypeError("playlist owner must be a string")
    return {
        "id": item["id"],
        "name": item["name"],
        "description": item.get("description", ""),
        "owner": owner_label,
        "tracks_total": item["tracks"]["total"],
        "public": item.get("public", False),
        "uri": item["uri"],
        "external_url": item.get("external_urls", {}).get("spotify"),
    }


def playlists_from_spotify_page(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Parse a `/me/playlists` page into setup-dropdown playlist records."""
    return [playlist_from_spotify_item(item) for item in payload.get("items", [])]
