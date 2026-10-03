```python
from fastapi import Request, status
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException
from contextlib import contextmanager
from typing import Generator
from pydantic import BaseModel
from datetime import datetime
from urllib.parse import quote
from jinja2 import Template

def html_escape(s: str) -> str:
    return html.escape(s)

def quote_url_param(s: str) -> str:
    return quote(s, safe='')

@contextmanager
def handle_auth_error() -> Generator:
    try:
        yield
    except Exception as e:
        error = str(e)
        return HTMLResponse(
            content=f"Authentication error: {html_escape(error)}", 
            status_code=500
        )

class OmiWhoopAppMain:
    def __init__(self, request: Request):
        self.request = request
        self.uid = self.request.url.query.get("uid", "")

    async def root(self):
        auth_url = f"/auth/whoop?uid={quote_url_param(self.uid)}"
        return Template("""
            <h1>Welcome to the Whoop App</h1>
            {{ if not connected: }}
                <p>Not connected.</p>
                <a href="{{ safe_auth_url }}">Connect with Whoop.</a>
            {{ else: }}
                <p>Connected!</p>
                <a href="{{ safe_disconnect_url }}">Disconnect</a>
            {{ endif }}
        """).render(
            connected=False,
            safe_auth_url=quote_url_param(f"/auth/whoop?uid={self.uid}"),
            safe_disconnect_url=quote_url_param(f"/auth/whoop Disconnect?uid={self.uid}")
        )

    async def callback(self):
        error = self.request.url.query.get("error", "")
        if error:
            safe_error = html_escape(error)
            return HTMLResponse(
                content=f"""
                    <html>
                    <head><title>Whoop Auth Error</title></head>
                    <body>
                        <p>{safe_error}</p>
                        <a href="/">Back</a>
                    </body>
                    </html>
                """
            )
        else:
            uid = self.request.url.query.get("uid", "")
            return RedirectResponse(url=f"/?uid={quote_url_param(uid)}")

    async def disconnect(self):
        uid = self.request.url.query.get("uid", "")
        return RedirectResponse(url=f"/?uid={quote_url_param(uid)}")

def test_connect_page_encoding():
    from .main import OmiWhoopAppMain, html_escape, quote_url_param
    from fastapi.testclient import TestClient
    from fastapi import Request
    client = TestClient(app)
    with handle_auth_error():
        response = client.get("/")
    assert "Connected" not in response.text
    response = client.get("/?connected=False")
    assert "Not connected." in response.text
    assert 'safe_auth_url' in response.text
    assert 'safe_disconnect_url' in response.text

def test_callback_error():
    from .main import OmiWhoopAppMain, html_escape, quote_url_param
    from fastapi.testclient import TestClient
    from fastapi import Request
    client = TestClient(app)
    response = client.get("/auth/whoop/callback?error=<script>alert</script>")
    assert "Authentication error: &lt;script&gt;alert&lt;/script&gt;" in response.text

def test_callback_success():
    from .main import OmiWhoopAppMain, html_escape, quote_url_param
    from fastapi.testclient import TestClient
    from fastapi import Request
    client = TestClient(app)
    response = client.get("/auth/whoop/callback")
    assert "Connected!" in response.text

def test_uid_quoting():
    from .main import OmiWhoopAppMain, html_escape, quote_url_param
    from fastapi.testclient import TestClient
    from fastapi import Request
    client = TestClient(app)
    response = client.get("/auth/whoop")
    assert "%3F" in response.url
```