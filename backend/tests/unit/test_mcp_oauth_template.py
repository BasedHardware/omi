from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


def _render_mcp_template() -> str:
    return _render_mcp_template_for_client("ChatGPT")


def _render_mcp_template_for_client(client_name: str) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return env.get_template("mcp_oauth_authorize.html").render(
        client_name=client_name,
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


def _render_oauth_authenticate_template() -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return env.get_template("oauth_authenticate.html").render(
        app_name="Test App",
        app_image=None,
        app_id="test-app",
        state="state",
        firebase_api_key="test-api-key",
        firebase_auth_domain="test.firebaseapp.com",
        firebase_project_id="test-project",
        permissions=[
            {"text": "Read your memories"},
        ],
    )


def test_mcp_oauth_template_uses_deterministic_email_password_sign_in():
    html = _render_mcp_template()

    assert 'id="email-sign-in-form"' in html
    assert 'id="email-input"' in html
    assert 'id="password-input"' in html
    assert "signInWithEmailAndPassword" in html
    assert "finishSignIn(result.user, true)" in html


def test_mcp_oauth_template_does_not_offer_firebaseui_email_signup_flow():
    html = _render_mcp_template()

    assert "firebase.auth.EmailAuthProvider.PROVIDER_ID" not in html
    assert "Create account" not in html


def test_mcp_oauth_social_sign_in_requires_explicit_consent_after_login():
    html = _render_mcp_template()

    assert 'id="consent-retry"' in html
    assert "finishSignIn(authResult.user, false)" in html
    assert "showConsentRetry()" in html


def test_mcp_oauth_template_still_renders_permissions_and_social_sign_in():
    html = _render_mcp_template()

    assert "Read your Omi memories" in html
    assert "Create, update, and delete your Omi action items" in html
    assert "firebase.auth.GoogleAuthProvider.PROVIDER_ID" in html
    assert "firebaseui-auth-container" in html


def test_mcp_oauth_template_places_email_sign_in_below_social_options():
    html = _render_mcp_template()

    assert "or sign in with email" in html
    assert html.index('id="firebaseui-auth-container"') < html.index('id="email-sign-in-form"')


def test_mcp_oauth_template_uses_client_display_name():
    html = _render_mcp_template_for_client("Claude")

    assert "Connect Claude" in html
    assert "Claude will be able to" in html
    assert "<strong>Claude</strong>" in html
    assert "ChatGPT will be able to" not in html


def test_mcp_oauth_template_escapes_client_display_name():
    html = _render_mcp_template_for_client("<script>alert(1)</script>")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_app_oauth_template_uses_deterministic_email_password_sign_in():
    html = _render_oauth_authenticate_template()

    assert 'id="email-sign-in-form"' in html
    assert 'id="email-input"' in html
    assert 'id="password-input"' in html
    assert "signInWithEmailAndPassword" in html
    assert "firebase.auth.EmailAuthProvider.PROVIDER_ID" not in html
    assert "Create account" not in html


def test_app_oauth_template_terms_and_privacy_links_are_distinct():
    html = _render_oauth_authenticate_template()

    assert 'href="https://www.omi.me/pages/terms-of-service">Terms of Service</a>' in html
    assert 'href="https://www.omi.me/pages/privacy">Privacy Policy</a>' in html
