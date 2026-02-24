"""
Agent tools router — exposes Python backend tools to the VM agent.

Two endpoints:
- GET  /v1/agent/tools         — returns tool definitions (name, description, parameters)
- POST /v1/agent/execute-tool  — executes a named tool and returns the result
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.other.endpoints import get_current_user_uid
from utils.retrieval.agentic import agent_config_context, CORE_TOOLS
from utils.retrieval.tools.app_tools import load_app_tools
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _tool_schema(t) -> dict:
    """Extract a clean JSON schema from a LangChain tool."""
    schema = t.args_schema.model_json_schema() if t.args_schema else {}
    props = schema.get("properties", {})
    required = list(schema.get("required", []))

    # Strip the 'config' parameter — it's internal LangChain plumbing
    props.pop("config", None)
    if "config" in required:
        required.remove("config")

    return {
        "name": t.name,
        "description": t.description or "",
        "parameters": {
            "type": "object",
            "properties": props,
            "required": required,
        },
    }


@router.get("/v1/agent/tools")
def list_tools(uid: str = Depends(get_current_user_uid)):
    """Return all available tool definitions for a user."""
    tools = []

    for t in CORE_TOOLS:
        tools.append(_tool_schema(t))

    try:
        app_tools = load_app_tools(uid)
        for t in app_tools:
            tools.append(_tool_schema(t))
    except Exception as e:
        logger.error(f"⚠️ Error loading app tools for agent_tools: {e}")

    return {"tools": tools}


class ExecuteToolRequest(BaseModel):
    tool_name: str
    params: dict = {}


@router.post("/v1/agent/execute-tool")
async def execute_tool(
    body: ExecuteToolRequest,
    uid: str = Depends(get_current_user_uid),
):
    """Execute a named tool and return its result."""
    # Set up agent_config_context so tools can resolve the UID
    config = {
        "configurable": {
            "user_id": uid,
        },
    }
    agent_config_context.set(config)

    # Find the tool
    all_tools = list(CORE_TOOLS)
    try:
        app_tools = load_app_tools(uid)
        all_tools.extend(app_tools)
    except Exception as e:
        logger.error(f"⚠️ Error loading app tools: {e}")

    target = None
    for t in all_tools:
        if t.name == body.tool_name:
            target = t
            break

    if target is None:
        raise HTTPException(status_code=404, detail=f"Tool '{body.tool_name}' not found")

    # Strip config param if caller accidentally included it
    params = {k: v for k, v in body.params.items() if k != "config"}

    try:
        # Prefer async coroutine if available (app tools), else sync invoke
        if hasattr(target, "coroutine") and target.coroutine is not None:
            result = await target.coroutine(**params)
        else:
            # Pass config as second arg (LangChain RunnableConfig), not as tool input
            result = target.invoke(params, config=config)
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"❌ Error executing tool {body.tool_name}: {e}")
        return {"error": str(e)}
