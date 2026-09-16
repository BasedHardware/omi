"""Offline coverage for Spotify's nullable owner.display_name contract."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

PLUGIN_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN_ROOT))

import main  # noqa: E402


def playlist(display_name):
    return {
        "id": "fixture-playlist",
        "name": "Fixture Favorites",
        "owner": {"id": "fixture-owner", "display_name": display_name},
        "tracks": {"total": 3},
        "public": False,
        "uri": "spotify:playlist:fixture-playlist",
    }


class PlaylistOwnerTests(unittest.TestCase):
    def test_null_display_name_uses_owner_id(self):
        with patch.object(main, "spotify_api_request", return_value={"items": [playlist(None)]}):
            result = main.get_user_playlists("fixture-user")
        self.assertEqual(result[0].owner, "fixture-owner")

    def test_display_name_is_preserved(self):
        with patch.object(main, "spotify_api_request", return_value={"items": [playlist("Fixture Owner")]}):
            result = main.get_user_playlists("fixture-user")
        self.assertEqual(result[0].owner, "Fixture Owner")

    def test_empty_display_name_is_preserved(self):
        with patch.object(main, "spotify_api_request", return_value={"items": [playlist("")]}):
            result = main.get_user_playlists("fixture-user")
        self.assertEqual(result[0].owner, "")

    def test_setup_renders_playlist_with_null_owner_name(self):
        def spotify_response(uid, method, endpoint, **kwargs):
            if endpoint == "/me":
                return {"id": "fixture-user", "display_name": "Fixture User", "images": []}
            self.assertEqual(endpoint, "/me/playlists")
            return {"items": [playlist(None)]}

        with (
            patch.object(main, "get_spotify_tokens", return_value={"access_token": "unused-fixture"}),
            patch.object(main, "get_default_playlist", return_value=None),
            patch.object(main, "spotify_api_request", side_effect=spotify_response),
            patch("requests.sessions.Session.request", side_effect=AssertionError("Network forbidden")),
            TestClient(main.app, raise_server_exceptions=False) as client,
        ):
            response = client.get("/", params={"uid": "fixture-user"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('value="fixture-playlist"', response.text)
        self.assertIn("Fixture Favorites", response.text)


if __name__ == "__main__":
    unittest.main()
