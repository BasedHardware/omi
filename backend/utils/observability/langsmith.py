"""
LangSmith observability configuration and status logging.

This module provides utilities for checking and logging LangSmith tracing status
at application startup, creating per-request tracers for scoped tracing,
and for submitting feedback to LangSmith.
"""

import os
from typing import Optional, List, Any, Dict
import logging

logger = logging.getLogger(__name__)


def is_langsmith_enabled() -> bool:
    """
    Check if LangSmith tracing is enabled via environment variables.

    Checks both new (LANGSMITH_*) and legacy (LANGCHAIN_*) env var formats.

    Returns:
        True if tracing is enabled, False otherwise
    """
    # Check new-style env vars first
    langsmith_tracing = os.environ.get("LANGSMITH_TRACING", "").lower()
    if langsmith_tracing == "true":
        return True

    # Check legacy env vars
    langchain_tracing = os.environ.get("LANGCHAIN_TRACING_V2", "").lower()
    if langchain_tracing == "true":
        return True

    return False


def is_selfhost_deployment() -> bool:
    """True when this deployment declares itself self-hosted (OMI_ENV_STAGE=selfhost, ADR-0058).

    LangSmith is a SaaS: the traces it exports carry the prompts themselves plus uid/app_id metadata,
    so on an on-prem deployment they are conversation content leaving the premises. The tracer path
    below was gated on ONE condition — "is an API key present?" — and the module's own startup log
    spells out the consequence: "Global tracing off but API key present -> per-request tracing
    enabled". So LANGCHAIN_TRACING_V2=false plus an inherited key still exported chat traces.

    The tracing flag is deliberately NOT the gate: upstream ships exactly that combination in its
    cloud values and relies on per-request tracing, so honouring the flag here would change upstream
    product behaviour rather than add the abstraction this fork carries. The deployment's own
    declaration is the gate instead, resolved through the existing env-loader stage helper rather
    than a parallel notion of "self-hosted". Cloud behaviour is unchanged; a self-hosted stack stops
    depending on nobody having configured a key.

    NOTE (ADR-0057, still Proposed): the stage answers "am I a real deployment", not "may data leave
    for a vendor" — two orthogonal axes. Keying a data-sovereignty guard on it is right only by
    coincidence; when the explicit vendor-egress switch lands, this gate moves onto it.
    """
    try:
        from utils.env_loader import EnvStage, resolve_stage_from_env

        return resolve_stage_from_env() == EnvStage.SELFHOST.value
    except Exception:  # pragma: no cover - a stage helper failure must not enable egress
        return False


def get_langsmith_project() -> str:
    """
    Get the configured LangSmith project name.

    Returns:
        Project name or "default" if not set
    """
    return os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT") or "default"


def get_langsmith_endpoint() -> str:
    """
    Get the configured LangSmith API endpoint.

    Returns:
        Endpoint URL or default LangSmith endpoint
    """
    return (
        os.environ.get("LANGSMITH_ENDPOINT")
        or os.environ.get("LANGCHAIN_ENDPOINT")
        or "https://api.smith.langchain.com"
    )


def has_langsmith_api_key() -> bool:
    """
    Check if a LangSmith API key is configured.

    Returns:
        True if an API key is set (doesn't validate the key)
    """
    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    return bool(api_key and len(api_key) > 0 and api_key != "lsv2_pt_REPLACE_WITH_YOUR_KEY")


def log_langsmith_status() -> None:
    """
    Log the current LangSmith tracing configuration status.

    This should be called at application startup to provide visibility
    into whether tracing is properly configured.
    """
    global_enabled = is_langsmith_enabled()
    has_key = has_langsmith_api_key()
    project = get_langsmith_project()
    endpoint = get_langsmith_endpoint()

    if global_enabled and has_key:
        logger.info(f"🔍 LangSmith: GLOBAL tracing ENABLED")
        logger.info(f"   Project: {project}")
        logger.info(f"   Endpoint: {endpoint}")
    elif has_key:
        # Global tracing off but API key present - per-request tracing for chat
        logger.info(f"🔍 LangSmith: Per-request tracing (chat only)")
        logger.info(f"   Project: {project}")
        logger.info(f"   Prompt Hub: enabled")
    else:
        logger.info(f"📊 LangSmith: DISABLED (no API key)")
        logger.info(f"   Set LANGSMITH_API_KEY to enable tracing and prompt fetching")


def get_chat_tracer_callbacks(
    run_id: Optional[str] = None,
    run_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    """
    Create LangSmith tracer callbacks for per-request tracing.

    This enables tracing for specific requests (e.g., chat) without enabling
    global tracing. Returns an empty list if API key is not configured.

    Args:
        run_id: Optional explicit run ID for the trace (for feedback attachment)
        run_name: Optional name for the run (e.g., "chat.agentic.stream")
        tags: Optional tags for the run (e.g., ["chat", "agentic"])
        metadata: Optional metadata dict for the run

    Returns:
        List containing LangChainTracer callback if API key is set, else empty list
    """
    if is_selfhost_deployment():
        return []
    if not has_langsmith_api_key():
        return []

    try:
        from langchain_core.tracers import LangChainTracer

        project = get_langsmith_project()

        tracer = LangChainTracer(
            project_name=project,
            tags=tags or [],
        )

        return [tracer]

    except Exception as e:
        logger.error(f"⚠️  Failed to create LangSmith tracer: {e}")
        return []


def submit_langsmith_feedback(
    run_id: str,
    score: float,
    key: str = "user_feedback",
    comment: Optional[str] = None,
) -> bool:
    """
    Submit feedback to LangSmith for a specific run.

    Args:
        run_id: The LangSmith run ID to attach feedback to
        score: Feedback score (typically 0.0 for negative, 1.0 for positive)
        key: Feedback key/category (default: "user_feedback")
        comment: Optional comment/reason for the feedback

    Returns:
        True if feedback was successfully submitted, False otherwise

    Note: Feedback submission only requires an API key, not global tracing.
    The run_id must be from a traced run (e.g., chat requests with per-request tracing).
    """
    if not has_langsmith_api_key():
        logger.warning(f"⚠️  LangSmith feedback skipped: API key not configured")
        return False

    try:
        from langsmith import Client

        client = Client()

        # Submit feedback to LangSmith
        # Note: feedback_source_type defaults to "api" which is valid
        client.create_feedback(  # type: ignore[reportUnknownMemberType]  # langsmith create_feedback partially typed
            run_id=run_id,
            key=key,
            score=score,
            comment=comment,
        )

        logger.info(f"✅ LangSmith feedback submitted: run_id={run_id}, score={score}, key={key}")
        return True

    except Exception as e:
        logger.error(f"❌ LangSmith feedback error: {e}")
        return False
