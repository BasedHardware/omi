"""
Tools for dynamically loading and creating tools from installed apps.

This module allows apps to define custom tools that become available
in the Omi chat when the app is installed by a user.
"""

import contextvars
from typing import List, Optional, Callable, Any, Dict
import httpx
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import StructuredTool
from langchain_core.runnables import RunnableConfig

from database.apps import get_app_by_id_db
from database.redis_db import (
    get_cached_user_geolocation,
    delete_app_cache_by_id,
    get_enabled_apps,
)
from database.webhook_health import (
    record_app_webhook_failure,
    record_app_webhook_success,
    is_app_webhook_disabled,
    disable_app_in_firestore,
)
from models.app import App, ChatTool
from utils.mcp_client import call_mcp_tool
from utils.http_client import get_webhook_circuit_breaker
from utils.executors import db_executor, run_blocking
from utils.notifications import send_notification
import logging

logger = logging.getLogger(__name__)


def _notify_app_owner(app_id: str, title: str, body: str):
    """Send a push notification to the app owner about webhook health."""
    try:
        app_data = get_app_by_id_db(app_id)
        if app_data and app_data.get('uid'):
            send_notification(app_data['uid'], title, body)
    except Exception as e:
        logger.warning(f'Failed to notify app owner for {app_id}: {e}')


def _handle_app_webhook_disable(app_id: str, action: int, error: str):
    if action == 1:
        logger.warning(f'App {app_id} webhook failing for 24h+ (day 1 warning): {error}')
        _notify_app_owner(
            app_id,
            'Webhook Failing',
            f'Your app webhook has been failing for 24+ hours. Error: {error[:100]}. '
            'It will be auto-disabled in 48 hours if failures continue.',
        )
    elif action == 2:
        logger.warning(f'App {app_id} webhook failing for 48h+ (day 2 final warning): {error}')
        _notify_app_owner(
            app_id,
            'Webhook Final Warning',
            f'Your app webhook has been failing for 48+ hours. Error: {error[:100]}. '
            'It will be auto-disabled in 24 hours if failures continue.',
        )
    elif action == 3:
        logger.warning(f'App {app_id} auto-disabled after 72h of webhook failures: {error}')
        disable_app_in_firestore(app_id, error, 72)
        delete_app_cache_by_id(app_id)
        _notify_app_owner(
            app_id,
            'Webhook Auto-Disabled',
            f'Your app has been auto-disabled after 72+ hours of webhook failures. Error: {error[:100]}. '
            'Please fix your endpoint and re-enable from your developer dashboard.',
        )


# Import agent_config_context for accessing user context
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)

# Global mapping of tool names to status messages
_tool_status_messages: Dict[str, str] = {}


def _create_pydantic_model_from_schema(tool_name: str, parameters: Dict[str, Any]) -> type:
    """
    Create a Pydantic model from a JSON schema parameters definition.

    Args:
        tool_name: Name of the tool (used for model naming)
        parameters: JSON schema with 'properties' and 'required' keys

    Returns:
        A Pydantic model class
    """
    properties = parameters.get('properties', {})
    required = set(parameters.get('required', []))

    field_definitions = {}

    for param_name, param_schema in properties.items():
        param_type = param_schema.get('type', 'string')
        param_desc = param_schema.get('description', '')
        is_required = param_name in required

        # Map JSON schema types to Python types
        if param_type == 'string':
            py_type = str
        elif param_type == 'integer':
            py_type = int
        elif param_type == 'boolean':
            py_type = bool
        elif param_type == 'number':
            py_type = float
        elif param_type == 'array':
            py_type = list
        else:
            py_type = str

        # Create field with or without default
        if is_required:
            field_definitions[param_name] = (py_type, Field(..., description=param_desc))
        else:
            # For optional fields, wrap in Optional and provide None default
            field_definitions[param_name] = (Optional[py_type], Field(default=None, description=param_desc))

    # Create a unique model name
    model_name = f"{tool_name.replace('-', '_').replace('.', '_')}Input"

    # Create and return the dynamic Pydantic model
    return create_model(model_name, **field_definitions)


def create_app_tool(
    app_tool: ChatTool,
    app_id: str,
    app_name: str,
    mcp_server_url: Optional[str] = None,
    mcp_oauth_tokens: Optional[Dict] = None,
) -> Callable:
    """
    Dynamically create a LangChain tool from an app tool definition.

    Uses the stored parameters schema to create a properly typed tool
    that the LLM can understand and call with correct arguments.

    Args:
        app_tool: ChatTool definition from the app
        app_id: ID of the app providing this tool
        app_name: Name of the app (for display purposes)
        mcp_server_url: MCP server URL (for MCP tools)
        mcp_oauth_tokens: OAuth tokens dict (for MCP tools requiring auth)

    Returns:
        A LangChain StructuredTool
    """
    tool_name = f"{app_id}_{app_tool.name}"

    # Store status message in global mapping for UI display (if provided)
    if app_tool.status_message:
        _tool_status_messages[tool_name] = app_tool.status_message

    # Create a Pydantic model from the schema (or empty model if no parameters)
    if app_tool.parameters and isinstance(app_tool.parameters, dict) and app_tool.parameters.get('properties'):
        args_schema = _create_pydantic_model_from_schema(app_tool.name, app_tool.parameters)
    else:
        # Create an empty schema for tools with no parameters
        model_name = f"{app_tool.name.replace('-', '_').replace('.', '_')}Input"
        args_schema = create_model(model_name)

    if app_tool.is_mcp and mcp_server_url:
        _mcp_url = mcp_server_url
        _mcp_tokens = mcp_oauth_tokens
        _access_token = mcp_oauth_tokens.get('access_token') if mcp_oauth_tokens else None
        _transport = app_tool.transport

        async def mcp_tool_function(**kwargs) -> str:
            """MCP tool dynamically created from MCP server."""
            kwargs.pop('config', None)
            if await run_blocking(db_executor, is_app_webhook_disabled, app_id):
                return f"The {app_tool.name} tool is temporarily disabled due to sustained failures."
            cb = get_webhook_circuit_breaker(_mcp_url)
            if not cb.allow_request():
                return f"The {app_tool.name} tool is temporarily unavailable. Please try again shortly."
            try:
                result = await call_mcp_tool(_mcp_url, app_tool.name, kwargs, _access_token, _mcp_tokens, _transport)
                if result.startswith('Error') or result.startswith('MCP error'):
                    cb.record_failure()
                    action = await run_blocking(db_executor, record_app_webhook_failure, app_id, 0, result[:200])
                    await run_blocking(db_executor, _handle_app_webhook_disable, app_id, action, result[:200])
                else:
                    cb.record_success()
                    await run_blocking(db_executor, record_app_webhook_success, app_id)
                return result
            except Exception as e:
                cb.record_failure()
                action = await run_blocking(db_executor, record_app_webhook_failure, app_id, 0, type(e).__name__)
                await run_blocking(db_executor, _handle_app_webhook_disable, app_id, action, type(e).__name__)
                return f"Error calling MCP tool {app_tool.name}: {e}"

        return StructuredTool(
            name=tool_name,
            description=f"{app_tool.description} (from {app_name} app)",
            func=lambda **kwargs: None,
            coroutine=mcp_tool_function,
            args_schema=args_schema,
        )

    # Standard HTTP tool
    async def tool_function(**kwargs) -> str:
        """Tool dynamically created from app definition."""
        config_param = kwargs.pop('config', None)
        return await _call_tool_endpoint(kwargs, config_param, app_tool, app_id)

    # Create StructuredTool with the schema
    return StructuredTool(
        name=tool_name,
        description=f"{app_tool.description} (from {app_name} app)",
        func=lambda **kwargs: None,  # Sync placeholder (won't be used)
        coroutine=tool_function,
        args_schema=args_schema,
    )


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

    # Get geolocation from cache
    geolocation = None
    try:
        geolocation = get_cached_user_geolocation(uid)
    except Exception:
        pass

    # Prepare request payload
    payload = {
        **kwargs,
        'uid': uid,
        'app_id': app_id,
        'tool_name': app_tool.name,
    }
    if geolocation:
        payload['geolocation'] = geolocation

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

    if await run_blocking(db_executor, is_app_webhook_disabled, app_id):
        return f"The {app_tool.name} tool is temporarily disabled due to sustained failures. The app developer has been notified."

    cb = get_webhook_circuit_breaker(app_tool.endpoint)
    if not cb.allow_request():
        return f"The {app_tool.name} tool is temporarily unavailable. Please try again shortly."

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            method = app_tool.method.upper()
            request_kwargs = {
                'headers': headers,
            }

            if method in ['POST', 'PUT', 'PATCH']:
                request_kwargs['json'] = payload
            elif method == 'GET':
                request_kwargs['params'] = payload

            response = await client.request(method=method, url=app_tool.endpoint, **request_kwargs)

            if response.status_code >= 200 and response.status_code < 300:
                cb.record_success()
                await run_blocking(db_executor, record_app_webhook_success, app_id)
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
                cb.record_failure()
                action = await run_blocking(
                    db_executor,
                    record_app_webhook_failure,
                    app_id,
                    response.status_code,
                    f'HTTP {response.status_code}',
                )
                await run_blocking(
                    db_executor, _handle_app_webhook_disable, app_id, action, f'HTTP {response.status_code}'
                )

                if response.status_code in (401, 403):
                    return (
                        f"The {app_tool.name} tool is temporarily unavailable due to a "
                        f"configuration issue on the app's side. Please try again later "
                    )
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
        cb.record_failure()
        action = await run_blocking(db_executor, record_app_webhook_failure, app_id, 0, 'TimeoutException')
        await run_blocking(db_executor, _handle_app_webhook_disable, app_id, action, 'TimeoutException')
        return f"Error: Timeout calling {app_tool.name}. The app endpoint did not respond within 120 seconds."
    except httpx.ConnectError:
        cb.record_failure()
        action = await run_blocking(db_executor, record_app_webhook_failure, app_id, 0, 'ConnectError')
        await run_blocking(db_executor, _handle_app_webhook_disable, app_id, action, 'ConnectError')
        return f"Error: Could not connect to {app_tool.name}. The app endpoint may be unreachable."
    except Exception as e:
        cb.record_failure()
        action = await run_blocking(db_executor, record_app_webhook_failure, app_id, 0, type(e).__name__)
        await run_blocking(db_executor, _handle_app_webhook_disable, app_id, action, type(e).__name__)
        return f"Error calling {app_tool.name}: {str(e)}"


def load_app_tools(uid: str) -> List[Callable]:
    """
    Load all tools from enabled apps for a user.

    Args:
        uid: User ID

    Returns:
        List of LangChain tool functions
    """
    enabled_app_ids = get_enabled_apps(uid)
    tools = []

    for app_id in enabled_app_ids:
        app_data = get_app_by_id_db(app_id)
        if not app_data:
            continue

        if app_data.get('disabled'):
            continue

        try:
            app = App(**app_data)
        except Exception as e:
            logger.error(f"Error parsing app {app_id}: {e}")
            continue

        # Only load tools if app has chat_tools defined
        if app.chat_tools and len(app.chat_tools) > 0:
            # Extract MCP config from external_integration if present
            mcp_server_url = None
            mcp_oauth_tokens = None
            if app.external_integration:
                mcp_server_url = app.external_integration.mcp_server_url
                mcp_oauth_tokens = app.external_integration.mcp_oauth_tokens

            for app_tool in app.chat_tools:
                try:
                    tool_func = create_app_tool(
                        app_tool,
                        app.id,
                        app.name,
                        mcp_server_url=mcp_server_url,
                        mcp_oauth_tokens=mcp_oauth_tokens,
                    )
                    tools.append(tool_func)
                    logger.info(f"✅ Loaded tool '{app_tool.name}' from app '{app.name}' ({app_id})")
                except Exception as e:
                    logger.error(f"❌ Error creating tool {app_tool.name} for app {app_id}: {e}")

    logger.info(f"📦 Loaded {len(tools)} app tools for user {uid}")
    return tools
