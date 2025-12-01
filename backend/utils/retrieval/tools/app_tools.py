"""
Tools for dynamically loading and creating tools from installed apps.

This module allows apps to define custom tools that become available
in the Omi chat when the app is installed by a user.
"""

import contextvars
from typing import List, Optional, Callable, Any, Dict
import httpx
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from models.app import ChatTool

# Import agent_config_context for accessing user context
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)

# Global mapping of tool names to status messages
_tool_status_messages: Dict[str, str] = {}


def _infer_parameters_from_description(tool_name: str, description: str) -> Dict[str, Any]:
    """
    Infer parameter types from tool name and description.
    Returns a dict mapping parameter names to their types and defaults.
    """
    description_lower = description.lower()
    tool_name_lower = tool_name.lower()

    params = {}

    # Common patterns for Slack and similar tools
    if 'send' in tool_name_lower and 'message' in tool_name_lower:
        params['message'] = (str, ...)  # Required string
        if 'channel' in description_lower:
            params['channel'] = (Optional[str], None)  # Optional string

    # Search tools
    if 'search' in tool_name_lower:
        params['query'] = (str, ...)  # Required string
        if 'channel' in description_lower:
            params['channel'] = (Optional[str], None)

    # List tools
    if 'list' in tool_name_lower:
        # Usually no required parameters
        pass

    # Generic message parameter if description mentions "message"
    if 'message' in description_lower and 'message' not in params:
        params['message'] = (str, ...)

    # Generic query parameter if description mentions "query" or "search"
    if ('query' in description_lower or 'search' in description_lower) and 'query' not in params:
        params['query'] = (str, ...)

    return params


def create_app_tool(app_tool: ChatTool, app_id: str, app_name: str) -> Callable:
    """
    Dynamically create a LangChain tool from an app tool definition.

    Args:
        app_tool: ChatTool definition from the app
        app_id: ID of the app providing this tool
        app_name: Name of the app (for display purposes)

    Returns:
        A LangChain tool function
    """
    tool_name = f"{app_id}_{app_tool.name}"

    # Infer parameters from description if not provided in schema
    if app_tool.parameters and isinstance(app_tool.parameters, dict):
        # Use provided parameters schema
        param_fields = {}
        properties = app_tool.parameters.get('properties', {})
        required = app_tool.parameters.get('required', [])

        for param_name, param_schema in properties.items():
            param_type = param_schema.get('type', 'string')
            is_required = param_name in required

            # Map JSON schema types to Python types
            if param_type == 'string':
                py_type = str if is_required else Optional[str]
            elif param_type == 'integer':
                py_type = int if is_required else Optional[int]
            elif param_type == 'boolean':
                py_type = bool if is_required else Optional[bool]
            else:
                py_type = str if is_required else Optional[str]

            if is_required:
                param_fields[param_name] = (py_type, ...)
            else:
                param_fields[param_name] = (py_type, None)
    else:
        # Infer from description
        param_fields = _infer_parameters_from_description(app_tool.name, app_tool.description)

    # Build function signature dynamically based on tool name
    # For send_slack_message, we want: message: str, channel: Optional[str] = None, config: RunnableConfig = None
    if 'send' in app_tool.name.lower() and 'message' in app_tool.name.lower():
        # Special handling for send_slack_message
        async def tool_function(message: str, channel: Optional[str] = None, config: RunnableConfig = None) -> str:
            """Tool dynamically created from app definition."""
            kwargs = {'message': message}
            if channel:
                kwargs['channel'] = channel
            return await _call_tool_endpoint(kwargs, config, app_tool, app_id)

    elif 'search' in app_tool.name.lower():
        # Special handling for search tools
        async def tool_function(query: str, channel: Optional[str] = None, config: RunnableConfig = None) -> str:
            """Tool dynamically created from app definition."""
            kwargs = {'query': query}
            if channel:
                kwargs['channel'] = channel
            return await _call_tool_endpoint(kwargs, config, app_tool, app_id)

    else:
        # Generic fallback - use **kwargs but with better description
        async def tool_function(**kwargs) -> str:
            """Tool dynamically created from app definition."""
            config_param = kwargs.pop('config', None)
            return await _call_tool_endpoint(kwargs, config_param, app_tool, app_id)

    # Create the tool
    dynamic_tool = tool(tool_function)
    dynamic_tool.name = tool_name
    dynamic_tool.description = f"{app_tool.description} (from {app_name} app)"

    # Store status message in global mapping for UI display (if provided)
    if app_tool.status_message:
        _tool_status_messages[tool_name] = app_tool.status_message

    return dynamic_tool


def get_tool_status_message(tool_name: str) -> Optional[str]:
    """
    Get the status message for a tool if it exists.

    Args:
        tool_name: Full tool name (e.g., "01KBAJ9BF3X4JD4B8XM0QC896R_send_slack_message")

    Returns:
        Status message string or None if not found
    """
    return _tool_status_messages.get(tool_name)


async def _call_tool_endpoint(kwargs: dict, config: Optional[RunnableConfig], app_tool: ChatTool, app_id: str) -> str:
    """Helper function to call the tool endpoint asynchronously."""
    # Get user ID from config
    if config is None:
        try:
            config = agent_config_context.get()
        except LookupError:
            return f"Error: Configuration not available for {app_tool.name}"

    uid = config['configurable'].get('user_id') if config else None
    if not uid:
        return f"Error: User ID not found for {app_tool.name}"

    # Prepare request payload
    payload = {
        **kwargs,
        'uid': uid,
        'app_id': app_id,
        'tool_name': app_tool.name,
    }

    # Prepare headers
    headers = {
        'Content-Type': 'application/json',
    }

    # Add authentication if required
    if app_tool.auth_required:
        # Get user's API key or auth token for this app
        # For now, we'll pass the uid and let the app handle auth
        # In the future, you might want to store app-specific tokens
        pass

    try:
        # Call the app's endpoint asynchronously
        async with httpx.AsyncClient(timeout=30.0) as client:
            method = app_tool.method.upper()
            request_kwargs = {
                'headers': headers,
            }

            if method in ['POST', 'PUT', 'PATCH']:
                request_kwargs['json'] = payload
            elif method == 'GET':
                request_kwargs['params'] = payload

            response = await client.request(method=method, url=app_tool.endpoint, **request_kwargs)

            if response.status_code == 200:
                # Try to parse JSON response, fallback to text
                try:
                    result = response.json()
                    if isinstance(result, dict) and 'result' in result:
                        return str(result['result'])
                    elif isinstance(result, dict) and 'message' in result:
                        return str(result['message'])
                    elif isinstance(result, str):
                        return result
                    else:
                        return str(result)
                except ValueError:
                    return response.text
            else:
                error_msg = f"Error calling {app_tool.name}: HTTP {response.status_code}"
                try:
                    error_detail = response.json()
                    if isinstance(error_detail, dict) and 'error' in error_detail:
                        error_msg += f" - {error_detail['error']}"
                    else:
                        error_msg += f" - {str(error_detail)}"
                except ValueError:
                    error_msg += f" - {response.text[:200]}"
                return error_msg

    except httpx.TimeoutException:
        return f"Error: Timeout calling {app_tool.name}. The app endpoint did not respond within 30 seconds."
    except httpx.ConnectError:
        return f"Error: Could not connect to {app_tool.name}. The app endpoint may be unreachable."
    except Exception as e:
        return f"Error calling {app_tool.name}: {str(e)}"


def load_app_tools(uid: str) -> List[Callable]:
    """
    Load all tools from enabled apps for a user.

    Args:
        uid: User ID

    Returns:
        List of LangChain tool functions
    """
    from database.redis_db import get_enabled_apps
    from database.apps import get_app_by_id_db
    from models.app import App

    enabled_app_ids = get_enabled_apps(uid)
    tools = []

    for app_id in enabled_app_ids:
        app_data = get_app_by_id_db(app_id)
        if not app_data:
            continue

        try:
            app = App(**app_data)
        except Exception as e:
            print(f"Error parsing app {app_id}: {e}")
            continue

        # Only load tools if app has chat_tools defined
        if app.chat_tools and len(app.chat_tools) > 0:
            for app_tool in app.chat_tools:
                try:
                    tool_func = create_app_tool(app_tool, app.id, app.name)
                    tools.append(tool_func)
                    print(f"✅ Loaded tool '{app_tool.name}' from app '{app.name}' ({app_id})")
                except Exception as e:
                    print(f"❌ Error creating tool {app_tool.name} for app {app_id}: {e}")

    print(f"📦 Loaded {len(tools)} app tools for user {uid}")
    return tools
