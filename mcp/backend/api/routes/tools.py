# tool management endpoints
# backend/api/routes/tools.py

from fastapi import APIRouter, HTTPException
from api.models.request import ToolExecutionRequest
from api.models.response import ToolsListResponse, ResponseStatus, ServerStatusResponse
from core.agent import agent_manager
from core.config import settings
from auth.dependencies import get_current_user, CurrentUser
from auth.google_oauth import get_google_connection_status
from auth.github_oauth import get_github_connection_status

router = APIRouter()

@router.get("/tools/status")
async def get_tools_status(user: CurrentUser):
    """
    Returns which external tools are connected for the current user.
    Useful for the frontend to show/hide tool availability in the UI.
    """
    google, github = await __import__("asyncio").gather(
        get_google_connection_status(user["id"]),
        get_github_connection_status(user["id"]),
    )
    return {
        "tools": {
            "google_workspace": {
                "connected": google["connected"],
                "email": google.get("email"),
                "capabilities": ["gmail", "calendar"] if google["connected"] else [],
            },
            "github": {
                "connected": github["connected"],
                "username": github.get("username"),
                "capabilities": ["repos", "pull_requests", "files"] if github["connected"] else [],
            },
        }
    }
    


@router.get("/tools", response_model=ToolsListResponse)
async def list_tools():
    """
    List all available tools from MCP servers.
    
    Returns:
        - Tool names
        - Descriptions
        - Required parameters
        - Which server provides each tool
        
    Frontend can use this to show capabilities to users.
    """
    if not agent_manager.is_initialized:
        raise HTTPException(
            status_code=503,
            detail="Agent not initialized"
        )
    
    try:
        tools_info = agent_manager.get_tools_info()
        
        # Get list of active servers
        active_servers = []
        if settings.enable_gmail:
            active_servers.append("gmail")
        if settings.enable_google_drive:
            active_servers.append("google_drive")
        if settings.enable_google_calendar:
            active_servers.append("google_calendar")
        
        return ToolsListResponse(
            status=ResponseStatus.SUCCESS,
            tools=tools_info,
            total_count=len(tools_info),
            servers_active=active_servers
        )
    
    except Exception as e:
        print(f"❌ Error listing tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/servers")
async def list_servers():
    """
    List all MCP servers and their status.
    
    Useful for debugging and monitoring.
    """
    servers = []
    
    # Check Gmail
    if settings.enable_gmail:
        servers.append({
            "name": "gmail",
            "enabled": True,
            "status": "active" if agent_manager.is_initialized else "inactive",
            "description": "Gmail email management"
        })
    
    # Check Google Drive
    if settings.enable_google_drive:
        servers.append({
            "name": "google_drive",
            "enabled": True,
            "status": "active" if agent_manager.is_initialized else "inactive",
            "description": "Google Drive file management"
        })
    
    # Check Google Calendar
    if settings.enable_google_calendar:
        servers.append({
            "name": "google_calendar",
            "enabled": True,
            "status": "active" if agent_manager.is_initialized else "inactive",
            "description": "Google Calendar event management"
        })
    
    return {
        "servers": servers,
        "total_count": len(servers)
    }


@router.post("/tools/execute")
async def execute_tool(request: ToolExecutionRequest):
    """
    Manually execute a specific tool.
    
    Useful for:
    - Testing individual tools
    - Direct tool access without agent reasoning
    - Debugging
    
    Example:
        POST /api/tools/execute
        {
            "tool_name": "gmail_get_messages",
            "arguments": {"max_results": 5}
        }
    """
    if not agent_manager.is_initialized:
        raise HTTPException(
            status_code=503,
            detail="Agent not initialized"
        )
    
    try:
        # Find the tool
        tool = None
        for t in agent_manager.tools:
            if t.name == request.tool_name:
                tool = t
                break
        
        if not tool:
            raise HTTPException(
                status_code=404,
                detail=f"Tool '{request.tool_name}' not found"
            )
        
        # Execute the tool
        # Note: This is a simplified version
        # Real implementation would use tool.invoke() or similar
        result = await tool.ainvoke(request.arguments)
        
        return {
            "status": "success",
            "tool_name": request.tool_name,
            "result": result,
            "arguments": request.arguments
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Tool execution error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute tool: {str(e)}"
        )


@router.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """
    Get detailed information about a specific tool.
    
    Returns:
        - Full description
        - Parameter schema
        - Examples
        - Server that provides it
    """
    if not agent_manager.is_initialized:
        raise HTTPException(
            status_code=503,
            detail="Agent not initialized"
        )
    
    # Find the tool
    for tool_info in agent_manager.get_tools_info():
        if tool_info.name == tool_name:
            return tool_info
    
    raise HTTPException(
        status_code=404,
        detail=f"Tool '{tool_name}' not found"
    )