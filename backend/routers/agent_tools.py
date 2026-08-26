"""
Agent tools router — exposes Python backend tools to agents.

Endpoints:
- GET  /v1/agent/tools         — returns tool definitions (name, description, parameters)
- POST /v1/agent/execute-tool  — executes a named tool and returns the result
"""

import logging
from typing import Any

from utils.executors import db_executor, run_blocking

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.retrieval.agentic import agent_config_context, CORE_TOOLS
from utils.retrieval.tool_result_boundaries import preserve_chat_memory_tool_result_boundary
from utils.retrieval.tools.app_tools import load_app_tools

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class AgentToolsResponse(BaseModel):
    tools: list[AgentToolSchema]


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


@router.get("/v1/agent/tools", response_model=AgentToolsResponse)
def list_tools(uid: str = Depends(get_current_user_uid)):
    """Return all available tool definitions for a user."""
    tools = []

    for t in CORE_TOOLS:
        tools.append(_tool_schema(t))

    degraded = False
    try:
        app_tools = load_app_tools(uid)
    except Exception:
        # Whole app-tool lane unavailable — core tools still serve.
        logger.error("⚠️ Error loading app tools for agent_tools", exc_info=True)
        app_tools = []
        degraded = True
    for t in app_tools:
        try:
            tools.append(_tool_schema(t))
        except Exception:
            # One malformed schema must not drop the remaining app tools.
            logger.error(f"⚠️ Skipping app tool with malformed schema: {getattr(t, 'name', '?')}", exc_info=True)
            degraded = True
    if degraded:
        record_fallback(
            component='agent_tools',
            from_mode='full_toolset',
            to_mode='partial_toolset',
            reason='malformed_doc',
            outcome='degraded',
        )

    return {"tools": tools}


class ExecuteToolRequest(BaseModel):
    tool_name: str
    params: dict = {}


class ExecuteToolResponse(BaseModel):
    result: str | None = None
    error: str | None = None


@router.post("/v1/agent/execute-tool", response_model=ExecuteToolResponse)
async def execute_tool(
    body: ExecuteToolRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "agent:execute_tool")),
):
    """Execute a named tool and return its result."""
    # Set up agent_config_context so tools can resolve the UID
    config = {
        "configurable": {
            "user_id": uid,
        },
    }
    agent_config_context.set(config)

    # Find the tool. `load_app_tools` reads Redis plus one Firestore document
    # per enabled app, so it must not run on the event loop — see the canonical
    # path in utils/retrieval/agentic.py.
    all_tools = list(CORE_TOOLS)
    try:
        app_tools = await run_blocking(db_executor, load_app_tools, uid)
        all_tools.extend(app_tools)
    except Exception as error:
        logger.error("⚠️ Error loading app tools error_type=%s", type(error).__name__)
        record_fallback(
            component='agent_tools',
            from_mode='full_toolset',
            to_mode='partial_toolset',
            reason='other',
            outcome='degraded',
        )

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
            # Every CORE_TOOLS entry is a sync @tool that fans out to Firestore
            # and Pinecone, so invoking it here would park the whole event loop
            # for the duration. `run_blocking` copies the current context, so
            # `agent_config_context` still resolves inside the worker thread.
            # Pass config as second arg (LangChain RunnableConfig), not as tool input
            result = await run_blocking(db_executor, target.invoke, params, config=config)
        result = preserve_chat_memory_tool_result_boundary(body.tool_name, str(result))
        return {"result": result}
    except Exception as error:
        # Exception text can embed caller params (pydantic renders
        # `input_value=...`), so keep it off both the log and response planes.
        logger.error("❌ Error executing tool %s error_type=%s", body.tool_name, type(error).__name__)
        return {"error": "Tool execution failed"}
