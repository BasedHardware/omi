"""
backend/start_mcp.py

Starts the Google Workspace MCP server in EXTERNAL_OAUTH21_PROVIDER mode.

In this mode:
  - The MCP server does NOT manage its own OAuth flow or credential files.
  - It expects every tool call to include: Authorization: Bearer <google_access_token>
  - Your orchestrator fetches the user's Google token from Supabase (via
    auth.google_oauth.get_valid_google_token) and injects it into each MCP request.
  - No ~/.google_workspace_mcp/credentials/ files are created.
"""

import os
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

required = ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"]
for key in required:
    if not os.getenv(key):
        raise SystemExit(f"❌ Missing required env var: {key}")

env_vars = {
    # Google OAuth app credentials (still needed by the MCP server
    # to validate bearer tokens via Google's tokeninfo API)
    "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
    "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),

    # Enable OAuth 2.1 mode — required for EXTERNAL_OAUTH21_PROVIDER
    "MCP_ENABLE_OAUTH21": "true",

    # External provider mode: MCP server expects Bearer tokens from your app,
    # does not run its own OAuth flow, writes no credential files.
    "EXTERNAL_OAUTH21_PROVIDER": "true",

    # Stateless: no in-memory session store, each request is self-contained
    "WORKSPACE_MCP_STATELESS_MODE": "true",

    # Allow HTTP callback for local development
    "OAUTHLIB_INSECURE_TRANSPORT": "1",

    # Port the MCP server listens on (your orchestrator connects to this)
    "WORKSPACE_MCP_PORT": os.getenv("MCP_SERVER_PORT", "8001"),
}

print("🚀 Starting Google Workspace MCP Server (External OAuth mode)...")
print("   Mode: EXTERNAL_OAUTH21_PROVIDER + STATELESS")
print("   Port:", env_vars["WORKSPACE_MCP_PORT"])
print()
print("Environment:")
for key, value in env_vars.items():
    safe = "✓ Set" if value and value not in ("true", "1") else value
    print(f"  {key}: {safe}")

import sys, os

venv_scripts = os.path.dirname(sys.executable)  # .venv\Scripts\
cmd = [
    "uvx", "workspace-mcp",
    "--tools", "gmail", "calendar",
    "--transport", "streamable-http",
    # "--port", env_vars["WORKSPACE_MCP_PORT"],
]
subprocess.run(cmd, env={**os.environ, **env_vars})
