"""Offline coverage for Spotify's nullable owner.display_name contract.

Stdlib only so `.github/checks-manifest.yaml` can run without plugin deps.
Imports the production helper — do not re-implement `playlist_owner_label` here.
"""
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
