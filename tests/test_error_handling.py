import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Import the routes
from plugins.omi_dropbox_app.src.routes.auth import authDropbox, authDropboxCallback
from plugins.omi_dropbox_app.src.routes.tools import searchFiles, listFolder, readFile
from plugins.omi_dropbox_app.src.routes.audio import audioEndpoint

app = FastAPI()
app.get("/auth/dropbox")(authDropbox)
app.get("/auth/dropbox/callback")(authDropboxCallback)
app.post("/tools/search")(searchFiles)
app.post("/tools/list")(listFolder)
app.post("/tools/read")(readFile)
app.post("/audio")(audioEndpoint)

client = TestClient(app)

class TestErrorHandling(unittest.TestCase):
    @patch('plugins.omi_dropbox_app.src.routes.auth.authDropbox', side_effect=Exception('Auth fail'))
    def test_auth_error(self, mock_auth):
        response = client.get("/auth/dropbox")
        self.assertEqual(response.status_code, 500)
        self.assertIn('unexpected error', response.text)

    @patch('plugins.omi_dropbox_app.src.routes.tools.searchFiles', side_effect=Exception('Search fail'))
    def test_search_error(self, mock_search):
        response = client.post("/tools/search", json={"query": "x"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "An error occurred while searching files."})

    @patch('plugins.omi_dropbox_app.src.routes.audio.audioEndpoint', side_effect=Exception('Audio fail'))
    def test_audio_error(self, mock_audio):
        response = client.post("/audio", json={})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"message": "An error occurred while processing audio."})

if __name__ == "__main__":
    unittest.main()
