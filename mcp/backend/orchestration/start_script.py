# start_script.py
import os
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()

env_vars = {
    'GOOGLE_OAUTH_CLIENT_ID': os.getenv('GOOGLE_OAUTH_CLIENT_ID', ''),
    'GOOGLE_OAUTH_CLIENT_SECRET': os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', ''),
    'USER_GOOGLE_EMAIL': os.getenv('USER_GOOGLE_EMAIL', ''),
    'OAUTHLIB_INSECURE_TRANSPORT': '1',
     'PORT': '8001',  
    'HOST': '0.0.0.0' 
}

print("🚀 Starting Google Workspace MCP Server...")
for key, value in env_vars.items():
    print(f"  {key}: {'✓ Set' if value else '✗ Not Set'}")

cmd = [
    'uvx', '--python', '3.11',  # force uv to use Python 3.11 (matches workspace-mcp's env)
    'workspace-mcp',
    '--tools', 'gmail', 'calendar',
    '--transport', 'streamable-http'
]

try:
    process = subprocess.Popen(
        cmd,
        env={**os.environ, **env_vars},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    print(f"✅ MCP Server started (PID: {process.pid}) on port 8001")

    # Stream logs
    for line in process.stdout:
        print(f"[MCP] {line}", end="")

except FileNotFoundError:
    print("❌ 'uvx' not found. Is uv installed?")
except Exception as e:
    print(f"❌ Failed to start MCP server: {e}")