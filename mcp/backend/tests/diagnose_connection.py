"""
Diagnose MCP server connection issues
Tests each server individually to find which one is failing

Place in: backend/scripts/diagnose_mcp_connection.py
Run: python backend/scripts/diagnose_mcp_connection.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager

@asynccontextmanager
async def test_server_connection(server_name: str, server_params: StdioServerParameters):
    """Test if a single MCP server can be connected to"""
    print(f"\n{'='*60}")
    print(f"Testing {server_name}")
    print('='*60)
    print(f"Command: {server_params.command}")
    print(f"Args: {server_params.args}")
    print(f"Env: {server_params.env}")
    
    try:
        async with stdio_client(server_params) as (read, write):
            from mcp.client.session import ClientSession
            async with ClientSession(read, write) as session:
                print(f"✓ Connection established")
                
                # Try to initialize
                print(f"Attempting to initialize...")
                await session.initialize()
                print(f"✅ {server_name} initialized successfully!")
                
                # Try to list tools
                tools_result = await session.list_tools()
                print(f"✓ Tools available: {len(tools_result.tools)}")
                for tool in tools_result.tools[:3]:  # Show first 3
                    print(f"  - {tool.name}")
                if len(tools_result.tools) > 3:
                    print(f"  ... and {len(tools_result.tools) - 3} more")
                
                yield session
                
    except Exception as e:
        print(f"❌ {server_name} FAILED")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        print(f"Traceback:\n{traceback.format_exc()}")
        yield None

async def main():
    print("="*60)
    print("MCP Server Connection Diagnostics")
    print("="*60)
    
    # Get Python executable
    python_path = sys.executable
    print(f"\nUsing Python: {python_path}")
    print(f"Backend directory: {backend_dir}")
    
    # Define servers to test
    servers = {
        "Gmail": StdioServerParameters(
            command=python_path,
            args=[str(backend_dir / "mcp_servers" / "gmail_server.py")],
            env=None
        ),
        "Google Drive": StdioServerParameters(
            command=python_path,
            args=[str(backend_dir / "mcp_servers" / "google_drive_server.py")],
            env=None
        ),
        "Google Calendar": StdioServerParameters(
            command=python_path,
            args=[str(backend_dir / "mcp_servers" / "google_calendar_server.py")],
            env=None
        ),
        "RAG": StdioServerParameters(
            command=python_path,
            args=[str(backend_dir / "mcp_servers" / "rag_server.py")],
            env=None
        ),
    }
    
    results = {}
    
    for server_name, server_params in servers.items():
        async with test_server_connection(server_name, server_params) as session:
            results[server_name] = session is not None
        
        # Small delay between tests
        await asyncio.sleep(0.5)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for server_name, success in results.items():
        status = "✅ WORKING" if success else "❌ FAILED"
        print(f"{status} - {server_name}")
    
    all_working = all(results.values())
    
    if all_working:
        print("\n🎉 All servers are working!")
        print("The issue might be in how your client.py is configured.")
    else:
        print("\n⚠️ Some servers failed to connect.")
        print("\nTroubleshooting steps:")
        print("1. Check that failed server files don't have syntax errors")
        print("2. Try running failed servers directly:")
        for server_name, success in results.items():
            if not success:
                print(f"   python backend/mcp_servers/{server_name.lower().replace(' ', '_')}_server.py")
        print("3. Check for missing dependencies")
        print("4. Ensure credentials/token.json exists for Google servers")

if __name__ == "__main__":
    asyncio.run(main())