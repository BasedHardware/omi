To address the issues, here's the revised code:

```python
# backend/routers/x_connector.py
from backend.utils.x_connector import (
    build_authorize_url,
    is_safe_redirect_url,
    get DEFAULT_DEEP_LINK from settings,
)
from django.utils.html import escape

def x_oauth_url():
    from backend.models import User
    user = User(request.user.id)
    redirect_url = request.GET.get('redirect', '')
    if not is_safe_redirect_url(redirect_url):
        redirect_url = DEFAULT_DEEP_LINK
    redirect_url = escape(redirect_url, quote=True)
    redirect_html = f'<meta http-equiv="refresh" content="0;url={redirect_url}">'
    redirect_html += f'<script>setTimeout(function(){{window.location.href="{escape(redirect_url.replace("'", "\\'"))}";}},150);</script>'
    return {'redirect_html': redirect_html}

# backend/utils/x_connector.py
import json
from django.utils.html import escape

def build_authorize_url(redirect_url, user_id, state):
    redirect_url = escape(redirect_url, quote=True)
    state = f"{user_id}\x01{state}"
    return f"{OAUTH_BASE_URL}?redirect_url={redirect_url}&state={state}"

def consume_oauth_state(request):
    state = request.GET.get('state', '')
    if not state:
        return None
    parts = state.split('\x01')
    if len(parts) != 3:
        return None
    return parts
```

```python
# backend/routers/x_connector.py
from backend.utils.x_connector import build_authorize_url, is_safe_redirect_url, get DEFAULT_DEEP_LINK from settings

def x_oauth_url():
    try:
        from backend.models import User
        user = User(request.user.id)
        redirect_url = request.GET.get('redirect', '')
        if not is_safe_redirect_url(redirect_url):
            redirect_url = DEFAULT_DEEP_LINK
        redirect_url = escape(redirect_url, quote=True)
        redirect_html = f'<meta http-equiv="refresh" content="0;url={redirect_url}">'
        redirect_html += f'<script>setTimeout(function(){{window.location.href="{json.dumps(redirect_url).replace('</', r'<\/')}"},150);</script>'
        return {'redirect_html': redirect_html}
    except Exception as e:
        logger.info(f'Error in x_oauth_url: {str(e).replace("\n", " ")}')

# backend/utils/x_connector.py
import json
from django.utils.html import escape

def build_authorize_url(redirect_url, user_id, state):
    redirect_url = escape(redirect_url, quote=True)
    state = f"{user_id}\x01{state}"
    return f"{OAUTH_BASE_URL}?redirect_url={redirect_url}&state={state}"

def consume_oauth_state(request):
    state = request.GET.get('state', '')
    if not state:
        return None
    parts = state.split('\x01')
    if len(parts) != 3:
        return None
    return parts
```