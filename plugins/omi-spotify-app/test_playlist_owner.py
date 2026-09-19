"""Offline coverage for Spotify's nullable owner.display_name contract.

Stdlib-only label tests so `.github/checks-manifest.yaml` can run without
installing plugin deps. Integration tests run when FastAPI/plugin deps exist.
Keep `playlist_owner_label` in sync with main.py.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def playlist_owner_label(owner):
    """Spotify may omit owner display_name; SpotifyPlaylist.owner requires a string."""
    display_name = owner.get("display_name")
    if display_name is not None:
        return display_name
    return owner["id"]


class PlaylistOwnerLabelTests(unittest.TestCase):
    def test_null_display_name_uses_owner_id(self):
        self.assertEqual(
            playlist_owner_label({"id": "fixture-owner", "display_name": None}),
            "fixture-owner",
        )

    def test_display_name_is_preserved(self):
        self.assertEqual(
            playlist_owner_label({"id": "fixture-owner", "display_name": "Fixture Owner"}),
            "Fixture Owner",
        )

    def test_empty_display_name_is_preserved(self):
        self.assertEqual(
            playlist_owner_label({"id": "fixture-owner", "display_name": ""}),
            "",
        )


try:
    from fastapi.testclient import TestClient

    PLUGIN_ROOT = Path(__file__).resolve().parent
    sys.path.insert(0, str(PLUGIN_ROOT))
    import main  # noqa: E402

    HAS_PLUGIN_DEPS = True
except Exception:
    TestClient = None  # type: ignore
    main = None  # type: ignore
    HAS_PLUGIN_DEPS = False


def playlist(display_name):
    return {
        "id": "fixture-playlist",
        "name": "Fixture Favorites",
        "owner": {"id": "fixture-owner", "display_name": display_name},
        "tracks": {"total": 3},
        "public": False,
        "uri": "spotify:playlist:fixture-playlist",
    }


@unittest.skipUnless(HAS_PLUGIN_DEPS, "omi-spotify-app deps not installed")
class PlaylistOwnerIntegrationTests(unittest.TestCase):
    def test_null_display_name_uses_owner_id_via_main(self):
        with patch.object(main, "spotify_api_request", return_value={"items": [playlist(None)]}):
            result = main.get_user_playlists("fixture-user")
        self.assertEqual(result[0].owner, "fixture-owner")

    def test_display_name_is_preserved_via_main(self):
        with patch.object(
            main, "spotify_api_request", return_value={"items": [playlist("Fixture Owner")]}
        ):
            result = main.get_user_playlists("fixture-user")
        self.assertEqual(result[0].owner, "Fixture Owner")

    def test_empty_display_name_is_preserved_via_main(self):
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
