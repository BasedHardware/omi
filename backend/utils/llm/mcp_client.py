# client_setup.py

from langchain_mcp_adapters.client import MultiServerMCPClient
import os
from typing import Optional, List, Any


class MCPClientManager:
    """Manages the MCP client and tools initialization"""

    def __init__(self, omi_api_key: Optional[str] = None):
        # Hardcoded API key for testing (in production, use environment variables)
        self.omi_api_key = omi_api_key
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: List[Any] = []
        self._initialized = False

    async def initialize(self) -> List[Any]:
        """
        Initializes the MCP client and fetches the tools.
        Returns the list of available tools.
        """
        if self._initialized:
            print("✅ MCP Client already initialized, returning cached tools.")
            return self.tools

        print("🔧 Initializing MCP Client...")

        try:
            self.client = MultiServerMCPClient(
                {
                    "omi": {
                        "command": "python",
                        "args": ["-m", "mcp_server_omi"],
                        "transport": "stdio",
                        "env": {"OMI_API_KEY": self.omi_api_key},
                    },
                }
            )

            # Fetch tools from the MCP server
            self.tools = await self.client.get_tools()
            self._initialized = True

            print(f"✅ Successfully initialized {len(self.tools)} MCP tools:")
            for tool in self.tools:
                print(f"  - {tool.name}: {tool.description}")

            return self.tools

        except Exception as e:
            print(f"❌ Failed to initialize MCP client: {e}")
            self.tools = []
            self._initialized = False
            return self.tools

    def get_tools(self) -> List[Any]:
        """Returns the cached tools (must call initialize first)"""
        if not self._initialized:
            raise RuntimeError("MCP Client not initialized. Call initialize() first.")
        return self.tools

    async def cleanup(self):
        """Clean up the MCP client resources"""
        if self.client:
            try:
                print("🧹 Cleaning up MCP client...")
                # The MultiServerMCPClient might have cleanup methods
                # This is a placeholder for proper cleanup
                self._initialized = False
            except Exception as e:
                print(f"Warning: Error during MCP client cleanup: {e}")


# Global instance for the application
mcp_manager = MCPClientManager()
