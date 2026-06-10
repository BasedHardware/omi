# """
# MCP Server Registry
# """

# import asyncio
# from typing import Dict, List, Any
# from mcp import ClientSession, StdioServerParameters
# from mcp.client.stdio import stdio_client


# from .gmail_server import GmailServer


# __all__ = [ 'GmailServer']


# class MCPServerManager:
#     """Manages MCP server connections"""
    
#     def __init__(self):
#         self.servers = {}
#         self.sessions = {}
        
#     async def start_server(self, server_name: str, server_config: Dict[str, Any]):
#         """Start an MCP server"""
#         try:
#             if server_name == "gmail":
#                 server = GmailServer()
            
#             else:
#                 raise ValueError(f"Unknown server: {server_name}")
            
#             server_params = StdioServerParameters(
#                 command=server.command,
#                 args=server.args,
#                 env=server.env
#             )
            
#             async with stdio_client(server_params) as (read, write):
#                 async with ClientSession(read, write) as session:
#                     await session.initialize()
#                     self.sessions[server_name] = session
#                     self.servers[server_name] = server
                    
#             return server
            
#         except Exception as e:
#             print(f"Error starting server {server_name}: {e}")
#             raise
    
#     async def get_tools(self, server_name: str):
#         """Get tools from a specific server"""
#         if server_name not in self.sessions:
#             return []
        
#         session = self.sessions[server_name]
#         result = await session.list_tools()
#         return result.tools
    
#     async def call_tool(self, server_name: str, tool_name: str, arguments: Dict):
#         """Call a tool on a specific server"""
#         if server_name not in self.sessions:
#             raise ValueError(f"Server {server_name} not found")
        
#         session = self.sessions[server_name]
#         result = await session.call_tool(tool_name, arguments)
#         return result
    
#     async def stop_server(self, server_name: str):
#         """Stop an MCP server"""
#         if server_name in self.sessions:
#             del self.sessions[server_name]
#         if server_name in self.servers:
#             del self.servers[server_name]
    
#     async def stop_all(self):
#         """Stop all servers"""
#         for server_name in list(self.sessions.keys()):
#             await self.stop_server(server_name)