from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


def _render_mcp_template() -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return env.get_template("mcp_oauth_authorize.html").render(
        permissions=[
            "Read your Omi memories",
            "Create, update, and delete your Omi action items",
        ],
        oauth_params={
            "response_type": "code",
            "client_id": "test-client",
            "redirect_uri": "https://chatgpt.com/connector/oauth/test",
            "resource": "https://api.omi.me/v1/mcp/sse",
            "scope": "memories.read action_items.write",
            "state": "state",
            "code_challenge": "challenge",
            "code_challenge_method": "S256",
        },
        firebase_config={
            "apiKey": "test-api-key",
            "authDomain": "test.firebaseapp.com",
            "projectId": "test-project",
        },
    )


def test_mcp_oauth_template_uses_deterministic_email_password_sign_in():
    html = _render_mcp_template()

    assert 'id="email-sign-in-form"' in html
    assert 'id="email-input"' in html
    assert 'id="password-input"' in html
    assert "signInWithEmailAndPassword" in html


def test_mcp_oauth_template_does_not_offer_firebaseui_email_signup_flow():
    html = _render_mcp_template()

    assert "firebase.auth.EmailAuthProvider.PROVIDER_ID" not in html
    assert "Create account" not in html


def test_mcp_oauth_template_still_renders_permissions_and_social_sign_in():
    html = _render_mcp_template()

    assert "Read your Omi memories" in html
    assert "Create, update, and delete your Omi action items" in html
    assert "firebase.auth.GoogleAuthProvider.PROVIDER_ID" in html
    assert "firebaseui-auth-container" in html
