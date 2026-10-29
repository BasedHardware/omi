import asyncio
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from fastapi.responses import HTMLResponse
import httpx
from main import app

client = TestClient(app)

def test_shopify_callback_perf_async():
    with patch('httpx.AsyncClient.post') as mock_post, \
         patch('httpx.AsyncClient.get') as mock_get, \
         patch('main.verify_shopify_hmac') as mock_verify, \
         patch('main._oauth_state_uid') as mock_uid, \
         patch('main.store_shopify_tokens') as mock_store, \
         patch('main.store_default_store') as mock_store_default, \
         patch('main.templates.TemplateResponse') as mock_template:

        mock_verify.return_value = True
        mock_uid.return_value = "test_uid"

        post_response = MagicMock()
        post_response.status_code = 200
        post_response.json.return_value = {"access_token": "test_token", "scope": "test_scope"}

        async def slow_post(*args, **kwargs):
            await asyncio.sleep(0.5)
            return post_response
        mock_post.side_effect = slow_post

        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {"shop": {"name": "Test Shop"}}

        async def slow_get(*args, **kwargs):
            await asyncio.sleep(0.5)
            return get_response
        mock_get.side_effect = slow_get

        mock_template.return_value = HTMLResponse(content="<html></html>")

        start = time.time()
        response = client.get("/auth/shopify/callback?code=test_code&state=test_state&shop=test_shop&hmac=test_hmac")
        end = time.time()

        assert response.status_code == 200
        assert end - start < 1.5
