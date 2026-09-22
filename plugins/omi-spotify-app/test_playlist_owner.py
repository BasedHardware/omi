"""Offline coverage for Spotify's nullable owner.display_name contract.

Stdlib only so `.github/checks-manifest.yaml` can run without plugin deps.
Drives the production GET / setup handler through FastAPI stubs — do not
re-implement `playlist_owner_label` here.
"""
import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playlist_owner import (
    playlist_from_spotify_item,
    playlist_owner_label,
    playlists_from_spotify_page,
)


def playlist(display_name):
    return {
        "id": "fixture-playlist",
        "name": "Fixture Favorites",
        "owner": {"id": "fixture-owner", "display_name": display_name},
        "tracks": {"total": 3},
        "public": False,
        "uri": "spotify:playlist:fixture-playlist",
        "external_urls": {"spotify": "https://open.spotify.com/playlist/fixture-playlist"},
    }


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


class PlaylistParseTests(unittest.TestCase):
    def test_null_display_name_parses_as_owner_id(self):
        raw = playlist(None)
        self.assertIsNone(raw["owner"]["display_name"])
        parsed = playlist_from_spotify_item(raw)
        self.assertIsInstance(parsed["owner"], str)
        self.assertEqual(parsed["owner"], "fixture-owner")
        self.assertEqual(parsed["id"], "fixture-playlist")
        self.assertEqual(parsed["name"], "Fixture Favorites")
        self.assertEqual(parsed["tracks_total"], 3)

    def test_display_name_parse_is_preserved(self):
        parsed = playlist_from_spotify_item(playlist("Fixture Owner"))
        self.assertEqual(parsed["owner"], "Fixture Owner")

    def test_empty_display_name_parse_is_preserved(self):
        parsed = playlist_from_spotify_item(playlist(""))
        self.assertEqual(parsed["owner"], "")

    def test_setup_dropdown_keeps_playlist_when_owner_name_is_null(self):
        playlists = playlists_from_spotify_page({"items": [playlist(None)]})
        self.assertEqual(len(playlists), 1)
        self.assertEqual(playlists[0]["id"], "fixture-playlist")
        self.assertEqual(playlists[0]["name"], "Fixture Favorites")
        self.assertEqual(playlists[0]["owner"], "fixture-owner")


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class HTMLResponse:
    def __init__(self, content="", status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


def _module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def _load_setup_app():
    stubs = {
        "fastapi": _module("fastapi", FastAPI=Framework),
        "fastapi.responses": _module("fastapi.responses", HTMLResponse=HTMLResponse),
    }
    spec = importlib.util.spec_from_file_location(
        "omi_spotify_setup_under_test", Path(__file__).with_name("main.py")
    )
    loaded = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(loaded)
    return loaded


class SetupRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _load_setup_app()

    def test_get_user_playlists_uses_owner_label_for_null_display_name(self):
        with patch.object(
            self.main, "spotify_api_request", return_value={"items": [playlist(None)]}
        ):
            result = self.main.get_user_playlists("fixture-user")
        self.assertEqual(result[0]["owner"], "fixture-owner")
        self.assertEqual(result[0]["id"], "fixture-playlist")

    def test_setup_renders_playlist_with_null_owner_name(self):
        def spotify_response(uid, method, endpoint, **kwargs):
            self.assertEqual(endpoint, "/me/playlists")
            return {"items": [playlist(None)]}

        with (
            patch.object(self.main, "get_spotify_tokens", return_value={"access_token": "unused-fixture"}),
            patch.object(self.main, "spotify_api_request", side_effect=spotify_response),
        ):
            response = asyncio.run(self.main.home(uid="fixture-user"))
        self.assertEqual(response.status_code, 200)
        self.assertIn('value="fixture-playlist"', response.content)
        self.assertIn("Fixture Favorites", response.content)

    def test_setup_missing_uid_does_not_list_playlists(self):
        response = asyncio.run(self.main.home(uid=None))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Missing user ID", response.content)
        self.assertNotIn('value="fixture-playlist"', response.content)


if __name__ == "__main__":
    unittest.main()
