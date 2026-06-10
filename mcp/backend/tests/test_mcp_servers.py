"""
Test script to verify Google servers and RAG server work standalone before connecting to client
Run this first to diagnose issues with Gmail, Drive, Calendar, and RAG servers

UPDATED FOR NEW FOLDER STRUCTURE:
backend/
├── mcp_servers/
│   ├── gmail_server.py
│   ├── drive_server.py
│   ├── rag_server.py
│   └── calendar_server.py
├── credentials/
│   ├── credentials.json
│   └── token.json
└── scripts/
    └── test_servers.py (this file)
"""

import sys
import os
import subprocess
from pathlib import Path

def test_server_import(server_path, server_name, credentials_dir, needs_credentials=True):
    """Test if a server file exists and can be imported"""
    print(f"\n{'='*60}")
    print(f"Testing {server_name}")
    print('='*60)
    
    # Check if file exists
    if not os.path.exists(server_path):
        print(f"❌ File not found: {server_path}")
        return False
    
    print(f"✓ File exists: {server_path}")
    
    # Check credentials only for Google servers
    if needs_credentials:
        credentials_path = credentials_dir / "credentials.json"
        token_path = credentials_dir / "token.json"
        
        if not credentials_path.exists():
            print(f"❌ Missing credentials.json at: {credentials_path}")
            print(f"   You need to download OAuth credentials from Google Cloud Console")
            print(f"   and place it in: {credentials_dir}")
            return False
        else:
            print(f"✓ credentials.json found at: {credentials_path}")
        
        if not token_path.exists():
            print(f"⚠️  Missing token.json at: {token_path}")
            print(f"   You need to run the authentication script first")
            print(f"   Run: python backend/scripts/generate_all_tokens.py")
            return False
        else:
            print(f"✓ token.json found at: {token_path}")
    else:
        print(f"ℹ️  {server_name} does not require Google credentials")
    
    # Try to run the server briefly to check for syntax errors
    print(f"\n🔍 Testing if {server_name} can start...")
    try:
        # Start the server process from backend directory
        backend_dir = Path(server_path).parent.parent
        
        # Use sys.executable to ensure we use the same Python interpreter
        python_executable = sys.executable
        print(f"   Using Python: {python_executable}")
        
        process = subprocess.Popen(
            [python_executable, str(server_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            cwd=str(backend_dir)  # Run from backend dir so relative paths work
        )
        
        # Give it a moment to start or fail
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            # If it times out, that's actually good - it means it's running
            process.kill()
            stdout, stderr = process.communicate()
            print(f"✅ {server_name} started successfully (process running)")
            return True
        
        # If it exited immediately, check for errors
        if process.returncode != 0:
            print(f"❌ {server_name} exited with error code {process.returncode}")
            if stderr:
                print(f"   Error output:\n{stderr.decode()}")
            return False
        else:
            print(f"✅ {server_name} can run")
            return True
            
    except Exception as e:
        print(f"❌ Error testing {server_name}: {e}")
        return False

def main():
    print("="*60)
    print("MCP Servers - Diagnostic Test")
    print("="*60)
    
    # Get paths dynamically from this script's location
    # This file is in: backend/scripts/test_servers.py
    script_dir = Path(__file__).resolve().parent
    backend_dir = script_dir.parent
    mcp_servers_dir = backend_dir / "mcp_servers"
    credentials_dir = backend_dir / "credentials"
    
    print(f"\n📁 Detected paths:")
    print(f"   Backend: {backend_dir}")
    print(f"   MCP Servers: {mcp_servers_dir}")
    print(f"   Credentials: {credentials_dir}")
    
    # Define server paths and whether they need Google credentials
    servers = {
        "Gmail": {
            "path": mcp_servers_dir / "gmail_server.py",
            "needs_credentials": True
        },
        "Drive": {
            "path": mcp_servers_dir / "google_drive_server.py",
            "needs_credentials": True
        },
        "Calendar": {
            "path": mcp_servers_dir / "google_calendar_server.py",
            "needs_credentials": True
        },
        "RAG": {
            "path": mcp_servers_dir / "rag_server.py",
            "needs_credentials": False
        }
    }
    
    # Check if directories exist
    if not mcp_servers_dir.exists():
        print(f"\n❌ ERROR: MCP servers directory not found at {mcp_servers_dir}")
        print("   Make sure you're running this from backend/scripts/")
        return
    
    if not credentials_dir.exists():
        print(f"\n⚠️  Credentials directory not found at {credentials_dir}")
        print(f"   Creating it now...")
        credentials_dir.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created {credentials_dir}")
        print(f"   Please place your credentials.json there (needed for Google servers)")
    
    results = {}
    for name, config in servers.items():
        results[name] = test_server_import(
            str(config["path"]), 
            name, 
            credentials_dir,
            needs_credentials=config["needs_credentials"]
        )
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 All servers are ready!")
        print("\nNext steps:")
        print("1. Run your client to connect all servers")
        print("2. Start building your FastAPI backend (backend/api/main.py)")
    else:
        print("\n⚠️  Some servers have issues. Fix them before proceeding.")
        print("\nCommon fixes:")
        print("\nFor Google servers (Gmail, Drive, Calendar):")
        print("  1. Place credentials.json in: backend/credentials/")
        print("  2. Run: python backend/scripts/generate_all_tokens.py")
        print("  3. Install required packages:")
        print("     pip install google-auth google-auth-oauthlib google-api-python-client")
        print("\nFor RAG server:")
        print("  1. Install required packages:")
        print("     pip install sentence-transformers chromadb")
        print("\nFor all servers:")
        print("  1. Install MCP: pip install mcp")
        print("  2. Check that all server files are in backend/mcp_servers/")

if __name__ == "__main__":
    main()