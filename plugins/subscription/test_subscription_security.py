from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from plugins.subscription.main import router, _sanitize_uid


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_sanitize_uid_valid():
    assert _sanitize_uid("user_12345") == "user_12345"
    assert _sanitize_uid("usr-abc-DEF_99") == "usr-abc-DEF_99"
    assert _sanitize_uid("a" * 128) == "a" * 128


def test_sanitize_uid_invalid_and_injection():
    assert _sanitize_uid("';alert(1);//") == ""
    assert _sanitize_uid("<script>alert(1)</script>") == ""
    assert _sanitize_uid('admin" OR "1"="1') == ""
    assert _sanitize_uid("user`id`") == ""
    assert _sanitize_uid("   ") == ""
    assert _sanitize_uid(None) == ""
    assert _sanitize_uid("a" * 129) == ""


def test_subscription_page_sanitizes_xss_payload(client):
    xss_payload = "';alert(document.domain);//"
    response = client.get(f"/subscription/?uid={xss_payload}")
    assert response.status_code == 200
    # Payload must NOT be reflected inside the body or script block
    assert "';alert(document.domain);//" not in response.text
    assert "<script>alert" not in response.text


def test_subscription_page_renders_clean_uid(client):
    clean_uid = "valid_contributor_123"
    response = client.get(f"/subscription/?uid={clean_uid}")
    assert response.status_code == 200
    assert 'data-uid="valid_contributor_123"' in response.text
    # Script block must not contain raw unescaped interpolation
    assert "'{{ uid }}'" not in response.text
