import pytest
from fastapi.testclient import TestClient
import html
from urllib.parse import quote
from main import app, oauth_states
from simple_storage import SimpleUserStorage
import main

client = TestClient(app)

def test_unauth_uid_breakout():
    """Verify uid is URL encoded in the unauthenticated flow to prevent attribute breakout."""
    uid = '"><script>alert(1)</script>'
    response = client.get(f"/?uid={uid}")
    assert response.status_code == 200
    assert f'uid={quote(uid, safe="")}' in response.text
    assert '"><script>' not in response.text

def test_channel_xss(monkeypatch):
    """Verify channel names and IDs are HTML escaped."""
    def mock_get_user(uid):
        return {
            "access_token": "fake",
            "team_name": "Test Team",
            "available_channels": [
                {"id": "C123\">", "name": "</option><script>alert(1)</script>"}
            ]
        }
    monkeypatch.setattr(SimpleUserStorage, "get_user", mock_get_user)
    response = client.get("/?uid=test")
    assert response.status_code == 200
    assert '&lt;/option&gt;&lt;script&gt;alert(1)&lt;/script&gt;' in response.text
    assert 'C123&quot;&gt;' in response.text
    assert '</option><script>' not in response.text

def test_team_name_xss(monkeypatch):
    """Verify team name is HTML escaped in the settings page."""
    def mock_get_user(uid):
        return {
            "access_token": "fake",
            "team_name": "<script>alert('team')</script>",
            "available_channels": []
        }
    monkeypatch.setattr(SimpleUserStorage, "get_user", mock_get_user)
    response = client.get("/?uid=test")
    assert response.status_code == 200
    assert '&lt;script&gt;alert(&#x27;team&#x27;)&lt;/script&gt;' in response.text
    assert '<script>alert' not in response.text

def test_auth_callback_success_xss(monkeypatch):
    """Verify team name and uid are safely encoded in the OAuth callback success page."""
    uid = "\"><script>alert('uid')</script>"
    oauth_states["fake_state"] = uid
    
    class FakeSlackClient:
        def exchange_code_for_token(self, code, redirect_uri):
            return {"access_token": "token", "team_id": "T1", "team_name": "<img src=x onerror=alert(1)>"}
        def list_channels(self, token):
            return []
            
    monkeypatch.setattr(main, "slack_client", FakeSlackClient())
    monkeypatch.setattr(SimpleUserStorage, "save_user", lambda **kwargs: None)
    
    response = client.get("/auth/callback?code=fake_code&state=fake_state")
    assert response.status_code == 200
    assert '&lt;img src=x onerror=alert(1)&gt;' in response.text
    assert f'uid={quote(uid, safe="")}' in response.text
    assert '<img src=x' not in response.text

def test_auth_callback_failure_xss(monkeypatch):
    """Verify error messages and uid are safely encoded in the OAuth callback failure page."""
    uid = "\"><script>alert(1)</script>"
    oauth_states["err_state"] = uid
    
    class FailingSlackClient:
        def exchange_code_for_token(self, code, redirect_uri):
            raise Exception("<script>alert('error')</script>")
            
    monkeypatch.setattr(main, "slack_client", FailingSlackClient())
    response = client.get("/auth/callback?code=fake_code&state=err_state")
    assert response.status_code == 500
    assert f'uid={quote(uid, safe="")}' in response.text
    assert '<script>alert' not in response.text

def test_normal_input(monkeypatch):
    """Verify normal inputs render cleanly without over-escaping where not needed."""
    def mock_get_user(uid):
        return {
            "access_token": "fake",
            "team_name": "Normal Team",
            "available_channels": [
                {"id": "C123", "name": "general"}
            ]
        }
    monkeypatch.setattr(SimpleUserStorage, "get_user", mock_get_user)
    response = client.get("/?uid=normal_user_123")
    assert response.status_code == 200
    assert 'Normal Team' in response.text
    assert 'general' in response.text
    assert 'value="C123"' in response.text

def test_js_uid_encoding():
    """Verify Javascript fetch templates use encodeURIComponent for uid."""
    with open("main.py", "r") as f:
        content = f.read()
    assert 'encodeURIComponent(uid)' in content or "encodeURIComponent(document.getElementById('uid').value)" in content
