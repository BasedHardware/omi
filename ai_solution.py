```python
from fastapi import FastAPI, status
from fastapi.responses import HTMLResponse
from typing import Optional
import html
from urllib.parse import quote

app = FastAPI()

def get_css():
    return """
    <style>
        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .error-box {
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 5px;
            margin: 20px 0;
        }
        .error-box h2 {
            color: #333;
            margin-bottom: 10px;
        }
        .error-box p {
            color: #666;
            margin-bottom: 15px;
        }
        .btn {
            display: inline-block;
            padding: 8px 16px;
            background-color: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            margin-top: 10px;
        }
        .btn-primary {
            background-color: #007bff;
        }
    </style>
    """

@app.get("/auth/notion/callback")
def notion_callback(error: Optional[str] = None, state: Optional[str] = None):
    if error:
        return HTMLResponse(
            content=f"""
<html>
<head><style>{html.escape(get_css())}</style></head>
<body>
<div class="container">
    <div class="error-box">
        <h2>Authorization Failed</h2>
        <p>{html.escape(error)}</p>
    </div>
</div>
</body>
</html>
""",
            status_code=400
        )
    else:
        token_data = {"workspace_name": "Notion Workspace"}  # Simplified for example
        workspace_name = html.escape(token_data.get("workspace_name", "Notion Workspace"))
        uid = state
        return HTMLResponse(
            content=f"""
<html>
<head><style>{html.escape(get_css())}</style></head>
<body>
<div class="container">
    <p>Connected to: {workspace_name}</p>
    <a href="/?uid={quote(uid, safe='')}" class="btn btn-primary btn-block">
        Continue to Settings
    </a>
</div>
</body>
</html>
""",
            status_code=200
        )

@app.get("/auth/notion/disconnect")
def disconnect():
    return HTMLResponse(
        content=f"""
<html>
<head><style>{html.escape(get_css())}</style></head>
<body>
<div class="container">
    <p>Disconnected from Notion.</p>
    <a href="/" class="btn btn-primary btn-block">
        Return Home
    </a>
</div>
</body>
</html>
""",
        status_code=200
    )
```

```