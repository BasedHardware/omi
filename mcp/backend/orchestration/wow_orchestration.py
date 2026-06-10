from __future__ import annotations

import asyncio
import atexit
import logging
import operator
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Literal, Optional, TypedDict
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, Command
from pydantic import BaseModel, Field, field_validator
try:
    from langgraph.prebuilt import create_react_agent
except ImportError:
    from langchain.agents import create_react_agent

load_dotenv()

servers_dir = Path(__file__).resolve().parent.parent / "mcp_servers"

# ============================================================================
# LOGGING — Windows-safe: never crashes on emoji / non-cp1252 bytes
# ============================================================================

class _SafeStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            enc = getattr(self.stream, "encoding", "utf-8") or "utf-8"
            self.stream.write(
                msg.encode(enc, errors="replace").decode(enc, errors="replace")
                + self.terminator
            )
            self.flush()
        except Exception:
            self.handleError(record)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            f"orchestrator_{datetime.now():%Y%m%d}.log",
            encoding="utf-8",
        ),
        _SafeStreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ============================================================================
# MCP CLIENT POOL
# ============================================================================

class MCPClientPool:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not MCPClientPool._initialized:
            self.github_client = None
            self.google_workspace_client = None
            self._lock = asyncio.Lock()
            MCPClientPool._initialized = True

    async def get_github_client(self):
        if self.github_client is not None:
            return self.github_client
        async with self._lock:
            if self.github_client is not None:
                return self.github_client
            from langchain_mcp_adapters.client import MultiServerMCPClient
            pat = os.getenv("GITHUB_PAT")
            if not pat:
                raise ValueError("GITHUB_PAT environment variable not set")
            self.github_client = MultiServerMCPClient({
                "github": {
                    "transport": "http",
                    "url": "https://api.githubcopilot.com/mcp/",
                    "headers": {"Authorization": f"Bearer {pat}"},
                }
            })
            logger.info("GitHub MCP client initialised")
            return self.github_client

    async def cleanup(self):
        for name, client in [
            ("GitHub", self.github_client),
            ("Google Workspace", self.google_workspace_client),
        ]:
            if client is not None:
                try:
                    if hasattr(client, "close"):
                        await client.close()
                    elif hasattr(client, "cleanup"):
                        await client.cleanup()
                    logger.info(f"{name} client closed")
                except Exception as exc:
                    logger.error(f"Error closing {name} client: {exc}")
        self.github_client = None
        self.google_workspace_client = None


mcp_pool = MCPClientPool()


def _cleanup_on_exit():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(mcp_pool.cleanup())
        else:
            loop.run_until_complete(mcp_pool.cleanup())
    except Exception as exc:
        logger.error(f"atexit cleanup error: {exc}")


atexit.register(_cleanup_on_exit)

# ============================================================================
# DIRECT RAG SERVICE
# ============================================================================

def _build_rag_retrieval_service():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", "")).strip()
    if not url or not key:
        logger.warning("SUPABASE_URL/KEY not set — user RAG disabled")
        return None
    try:
        from knowledge_engine.embedding_service import EmbeddingService
        from knowledge_engine.vector_store import SupabaseVectorStore
        from knowledge_engine.retrieval import HybridRetrieval
        dim = int(os.getenv("EMBEDDING_DIM", "384"))
        svc = HybridRetrieval(
            embedding_service=EmbeddingService(embedding_dim=dim),
            vector_store=SupabaseVectorStore(
                supabase_url=url, supabase_key=key, embedding_dim=dim
            ),
        )
        logger.info("User RAG retrieval service ready (direct)")
        return svc
    except Exception as exc:
        logger.error(f"Failed to build RAG retrieval service: {exc}")
        return None


_rag_retrieval_service = None


def get_rag_retrieval_service():
    global _rag_retrieval_service
    if _rag_retrieval_service is None:
        _rag_retrieval_service = _build_rag_retrieval_service()
    return _rag_retrieval_service


# ============================================================================
# MODELS
# ============================================================================

class ContextItem(BaseModel):
    source: Literal["web_search", "rag", "conversation", "club_search"]
    content: str
    relevance_score: float = Field(ge=0, le=1)
    metadata: dict = Field(default_factory=dict)


class WorkerTask(BaseModel):
    id: int = 0
    title: str = ""
    worker_type: Literal["github", "conversational", "gmail", "calendar"] = "conversational"
    description: str = ""
    parameters: dict = Field(default_factory=dict)
    requires_context: bool = False
    context_type: Optional[str] = None
    google_service: Optional[str] = None


class ExecutionPlan(BaseModel):
    reasoning: str
    needs_context: bool = False
    context_type: Optional[str] = None
    tasks: List[WorkerTask] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=list)
    rag_queries: List[str] = Field(default_factory=list)
    club_queries: List[str] = Field(default_factory=list)

    @field_validator("context_type", mode="before")
    @classmethod
    def normalise_context_type(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("null", "none", ""):
                return None
            if s in ("web", "rag", "club", "mixed"):
                return s
        return None


class TaskResult(BaseModel):
    task_id: int
    worker_type: str
    success: bool
    output: str
    used_context: bool = False
    error: Optional[str] = None


# ── Custom reducer for hitl_approved_payload ──────────────────────────────────
# Must be defined BEFORE OrchestratorState so the Annotated type can reference it.

def _merge_hitl_payloads(left: list, right: list) -> list:
    """
    Custom reducer for hitl_approved_payload.
    Dedup by task id (not description — description can change after approval
    which would cause the same task to appear twice and execute twice).
    Falls back to worker_type:description only if id is 0 or missing.
    Filters out any non-dict values (ints, Nones) that checkpoint replay may inject.
    """
    combined = list(left or []) + list(right or [])
    seen: set = set()
    result = []
    for p in combined:
        if not isinstance(p, dict):
            continue
        task = p.get("task") or {}
        task_id = task.get("id", 0)
        if task_id:
            key = f"id:{task_id}"
        else:
            key = f"{task.get('worker_type', '')}:{task.get('description', '')}"
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


class OrchestratorState(TypedDict):
    user_id: str
    user_query: str
    conversation_history: List[str]
    plan: Optional[ExecutionPlan]
    web_context: List[ContextItem]
    rag_context: List[ContextItem]
    club_context: List[ContextItem]
    combined_context: str
    tasks: List[WorkerTask]
    results: Annotated[List[dict], operator.add]   # always plain dicts for reliable reducer merge
    final_response: str
    hitl_approved_payload: Annotated[List[dict], _merge_hitl_payloads]


# ============================================================================
# LLMs
# ============================================================================

_model = os.getenv("ORCHESTRATOR_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
llm = ChatGroq(model=_model, temperature=0.7, api_key=os.getenv("GROQ_API_KEY"))

_planning_model = os.getenv("PLANNING_MODEL", "llama-3.3-70b-versatile")
planning_llm = ChatGroq(model=_planning_model, temperature=0.0, api_key=os.getenv("GROQ_API_KEY"))

_worker_model = os.getenv("WORKER_MODEL", "llama-3.1-8b-instant")
worker_llm = ChatGroq(model=_worker_model, temperature=0.1, api_key=os.getenv("GROQ_API_KEY"))

_wiki_tool = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())
web_search_agent = create_react_agent(llm, tools=[_wiki_tool])

print(f"Orchestrator LLM : {_model}")
print(f"Planning LLM     : {_planning_model}")
print(f"Worker LLM       : {_worker_model}")

# ============================================================================
# PLANNING
# ============================================================================

PLANNING_SYSTEM = """You are an intelligent planning agent. You MUST return a valid JSON object.

REQUIRED FIELDS (all must be present, reasoning must be non-empty):
  reasoning     : string  — ALWAYS fill this first. Briefly explain your routing decision.
  needs_context : boolean — true if external lookup is needed, false otherwise.
  context_type  : string or null — one of "web", "rag", "club", "mixed", or null.
  tasks         : list of task objects.
  search_queries: list of strings (empty list if not used).
  rag_queries   : list of strings (empty list if not used).
  club_queries  : list of strings (empty list if not used).

STEP 1 — Choose context_type (pick exactly one):
  "web"   - general / Wikipedia knowledge needed
  "rag"   - user-uploaded research papers or documents needed
  "club"  - robotics club events, announcements, coordinators needed
  "mixed" - multiple context sources needed
  null    - no external lookup needed (greetings, direct gmail/calendar tasks, simple chat)

STEP 2 — Populate the matching query list:
  If context_type = "club"  → add queries to club_queries
  If context_type = "rag"   → add queries to rag_queries
  If context_type = "web"   → add queries to search_queries
  If context_type = "mixed" → populate all relevant query lists
  If context_type = null    → leave all query lists as empty lists []

STEP 3 — Set needs_context:
  needs_context = true  when context_type is "web", "rag", "club", or "mixed"
  needs_context = false when context_type is null

STEP 4 — Choose worker_type and google_service per task:
  "conversational"            - chat, explanation, analysis, answering from retrieved context
  "github"                    - GitHub repos, PRs, files, code
  "gmail"  + google_service="gmail"      - read/search/send emails, summarize inbox
  "calendar" + google_service="calendar" - create/read/list events, summarize schedule

  IMPORTANT:
1.For ANY gmail or calendar task, you MUST set BOTH:
    worker_type: "gmail" or "calendar"
    google_service: "gmail" or "calendar"   <- always set this, never omit it
2.Every task MUST have a unique integer id starting from 1.
    Never use id=0. Use id=1, id=2, id=3, etc.

STEP 5 — Task splitting for "fetch context then act" queries:
  When the user wants to retrieve information AND then send an email or create
  a calendar event based on that information, create TWO tasks:
    Task 1: worker_type="conversational" — retrieves and summarises the context
    Task 2: worker_type="gmail" or "calendar" — the write action
  Set context_type to the appropriate source ("rag", "club", "web", or "mixed").
  The confirmation_node will use the fetched context to draft the email/event fields.

EXAMPLES:
  "What events is the robotics club running?"
    -> reasoning="User wants club event info, routing to club search.",
       context_type="club", needs_context=true, club_queries=["robotics club events"],
       tasks=[{id=1, worker_type="conversational", google_service=null}]

  "Summarize my last 5 emails"
    -> reasoning="Direct Gmail read task, no context lookup needed.",
       context_type=null, needs_context=false,
       tasks=[{id=1, worker_type="gmail", google_service="gmail"}]

  "Send an email to john@example.com about tomorrow's meeting"
    -> reasoning="Direct Gmail write task, no context lookup needed.",
       context_type=null, needs_context=false,
       tasks=[{id=1, worker_type="gmail", google_service="gmail", parameters={to: "john@example.com"}}]

  "Search my docs and email the summary to john@example.com"
    -> reasoning="Needs RAG context first, then Gmail send.",
       context_type="rag", needs_context=true, rag_queries=["docs summary"],
       tasks=[
         {id=1, worker_type="conversational", google_service=null, description="Summarise retrieved docs"},
         {id=2, worker_type="gmail", google_service="gmail", description="Email summary to john@example.com", parameters={to: "john@example.com"}}
       ]

  "Check the club schedule and create a calendar event for the next meeting"
    -> reasoning="Needs club context first, then Calendar create.",
       context_type="club", needs_context=true, club_queries=["next club meeting schedule"],
       tasks=[
         {id=1, worker_type="conversational", google_service=null, description="Find next club meeting from schedule"},
         {id=2, worker_type="calendar", google_service="calendar", description="Create calendar event for next club meeting"}
       ]

  "Schedule a standup tomorrow at 10am with alice@co.com"
    -> reasoning="Direct Calendar write, no context needed.",
       context_type=null, needs_context=false,
       tasks=[{id=1, worker_type="calendar", google_service="calendar",
               parameters={summary: "Standup", start: "<tomorrow>T10:00:00", end: "<tomorrow>T10:30:00", attendees: "alice@co.com"}}]

  "What is machine learning?"
    -> reasoning="General knowledge question, using web search.",
       context_type="web", needs_context=true, search_queries=["machine learning"],
       tasks=[{id=1, worker_type="conversational", google_service=null}]

  "Hi, how are you?"
    -> reasoning="Simple greeting, no lookup needed.",
       context_type=null, needs_context=false,
       tasks=[{id=1, worker_type="conversational", google_service=null}]
"""


def planning_agent_node(state: OrchestratorState) -> dict:
    print("\n" + "=" * 60)
    print("PLANNING AGENT: Analysing query...")
    print("=" * 60)
    logger.info(f"Planning for query: {state['user_query'][:120]}")

    planner = planning_llm.with_structured_output(ExecutionPlan)
    history = state.get("conversation_history", [])
    # conversation_history is already built_context() output — just prepend it
    context_block = "\n".join(history) if history else ""
    messages = [
        SystemMessage(content=PLANNING_SYSTEM),
        HumanMessage(content=(
            f"{context_block}\n\nUser Query: {state['user_query'][:500]}"
            if context_block else
            f"User Query: {state['user_query'][:500]}"
        ))
    ]

    plan: ExecutionPlan | None = None
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            plan = planner.invoke(messages)
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Planning attempt {attempt}/3 failed: {exc}")

    if plan is None:
        logger.error(f"All planning attempts failed. Last error: {last_exc}")
        raise last_exc

    has_club = bool(plan.club_queries)
    has_rag  = bool(plan.rag_queries)
    has_web  = bool(plan.search_queries)

    if sum([has_club, has_rag, has_web]) >= 2:
        inferred_type = "mixed"
    elif has_club:
        inferred_type = "club"
    elif has_rag:
        inferred_type = "rag"
    elif has_web:
        inferred_type = "web"
    else:
        inferred_type = None

    final_context_type = inferred_type or plan.context_type
    final_needs_context = final_context_type is not None

    plan = plan.model_copy(update={
        "context_type": final_context_type,
        "needs_context": final_needs_context,
    })

    # ── Guard: ensure all tasks have unique non-zero ids ─────────────
    tasks = list(plan.tasks)
    for i, task in enumerate(tasks):
        if task.id == 0:
            tasks[i] = task.model_copy(update={"id": i + 1})

    # Fix duplicate ids
    seen_task_ids: set = set()
    max_id = max((t.id for t in tasks), default=0)
    for i, task in enumerate(tasks):
        if task.id in seen_task_ids:
            max_id += 1
            tasks[i] = task.model_copy(update={"id": max_id})
        seen_task_ids.add(tasks[i].id)

    plan = plan.model_copy(update={"tasks": tasks})

    print(f"Plan: needs_context={plan.needs_context}  "
          f"context_type={plan.context_type}  "
          f"tasks={len(plan.tasks)}  "
          f"club_q={plan.club_queries}  "
          f"rag_q={plan.rag_queries}")
    logger.info(f"Plan reasoning: {plan.reasoning}")
    return {"plan": plan, "tasks": plan.tasks}


def route_after_planning(state: OrchestratorState) -> str:
    """
    Routes to the correct context node.
    Uses explicit `is None` check — `plan.context_type or ""` would turn
    None into "" which falls through to execute_tasks, skipping all context nodes.
    """
    plan = state.get("plan")
    if not plan or not plan.needs_context or plan.context_type is None:
        return "execute_tasks"
    return {
        "web":   "web_search",
        "rag":   "rag_search",
        "club":  "club_search",
        "mixed": "gather_mixed_context",
    }.get(plan.context_type, "execute_tasks")


# ============================================================================
# CONTEXT PROVIDERS
# ============================================================================

class WebSearchProvider:
    async def search(self, query: str) -> List[ContextItem]:
        print(f"  WEB: '{query}'")
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: web_search_agent.invoke(
                    {"messages": [{"role": "user", "content": query}]}
                ),
            )
            content = ""
            for msg in reversed(result.get("messages", [])):
                if hasattr(msg, "content") and msg.content:
                    content = msg.content
                    break
            content = content or str(result)
            print(f"  Web done: {len(content)} chars")
            return [ContextItem(source="web_search", content=content[:1000],
                                relevance_score=0.9, metadata={"query": query})]
        except Exception as exc:
            logger.error(f"Web search error: {exc}")
            return [ContextItem(source="web_search",
                                content=f"Search failed: {query}",
                                relevance_score=0.1,
                                metadata={"error": str(exc), "query": query})]


async def web_search_node(state: OrchestratorState) -> dict:
    plan = state["plan"]
    print("\n== WEB CONTEXT ==")
    provider = WebSearchProvider()
    results = await asyncio.gather(
        *[provider.search(q) for q in plan.search_queries[:2]],
        return_exceptions=True,
    )
    all_ctx = [item for r in results if not isinstance(r, Exception) for item in r]
    combined = "\n\n".join(
        f"[Web: '{i.metadata.get('query')}']\n{i.content}"
        for i in sorted(all_ctx, key=lambda x: x.relevance_score, reverse=True)
    )
    return {"web_context": all_ctx, "combined_context": combined}


class RagSearchProvider:
    async def search(self, query: str) -> List[ContextItem]:
        print(f"  RAG: '{query}'")
        svc = get_rag_retrieval_service()
        if svc is None:
            return [ContextItem(source="rag",
                                content="RAG not available. Check SUPABASE_URL/KEY.",
                                relevance_score=0.0, metadata={"query": query})]
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, lambda: svc.retrieve(query=query, top_k=5)
            )
            chunks = results.get("chunks", [])
            if not chunks:
                return [ContextItem(source="rag",
                                    content="No documents found.",
                                    relevance_score=0.0,
                                    metadata={"query": query, "num_results": 0})]
            formatted = "\n---\n".join(
                f"Result {i+1} (score: {c['score']:.3f})\n"
                f"Source: {c['metadata'].get('filename', 'unknown')}\n{c['text']}"
                for i, c in enumerate(chunks)
            )
            print(f"  RAG done: {len(chunks)} chunks")
            return [ContextItem(source="rag", content=formatted[:2000],
                                relevance_score=chunks[0]["score"],
                                metadata={"query": query, "num_results": len(chunks)})]
        except Exception as exc:
            logger.error(f"RAG error: {exc}")
            return [ContextItem(source="rag", content=f"RAG failed: {exc}",
                                relevance_score=0.0,
                                metadata={"error": str(exc), "query": query})]


async def rag_search_node(state: OrchestratorState) -> dict:
    plan = state["plan"]
    print("\n== RAG CONTEXT ==")
    provider = RagSearchProvider()
    results = await asyncio.gather(
        *[provider.search(q) for q in plan.rag_queries[:2]],
        return_exceptions=True,
    )
    all_ctx = [item for r in results if not isinstance(r, Exception) for item in r]
    combined = "\n\n".join(
        f"[RAG: '{i.metadata.get('query')}']\n{i.content}"
        for i in sorted(all_ctx, key=lambda x: x.relevance_score, reverse=True)
    )
    print(f"  RAG total: {len(combined)} chars")
    return {"rag_context": all_ctx, "combined_context": combined}


class ClubSearchProvider:
    async def search(self, query: str) -> List[ContextItem]:
        print(f"  CLUB: '{query}'")
        try:
            loop = asyncio.get_event_loop()
            cat_resp = await loop.run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=(
                        "Reply with exactly ONE word from: "
                        "events, announcements, coordinators, general"
                    )),
                    HumanMessage(content=query),
                ]),
            )
            category = cat_resp.content.strip().lower()
            if category not in {"events", "announcements", "coordinators", "general"}:
                category = "general"
            search_cat = None if category == "general" else category
            print(f"  Club category: {category}")

            from knowledge_engine.club.retrieval import get_club_retriever
            retriever = get_club_retriever()
            club_results = await loop.run_in_executor(
                None,
                lambda: retriever.retrieve(query=query, category=search_cat, top_k=3),
            )

            if not club_results:
                return [ContextItem(source="club_search",
                                    content="No club info found.",
                                    relevance_score=0.0,
                                    metadata={"query": query, "category": category})]

            combined = "\n\n".join(
                f"Result {i+1} (score: {r.get('score', 0):.2f}):\n{r.get('content', '')}"
                for i, r in enumerate(club_results)
            )
            avg = sum(r.get("score", 0.5) for r in club_results) / len(club_results)
            print(f"  Club done: {len(club_results)} chunks")
            return [ContextItem(source="club_search", content=combined.strip(),
                                relevance_score=avg,
                                metadata={"query": query, "category": category,
                                          "results_count": len(club_results)})]
        except Exception as exc:
            logger.error(f"Club search error: {exc}")
            return [ContextItem(source="club_search",
                                content=f"Club search failed: {exc}",
                                relevance_score=0.1,
                                metadata={"error": str(exc), "query": query})]


async def club_search_node(state: OrchestratorState) -> dict:
    plan = state["plan"]
    print("\n== CLUB CONTEXT ==")
    provider = ClubSearchProvider()
    results = await asyncio.gather(
        *[provider.search(q) for q in plan.club_queries[:2]],
        return_exceptions=True,
    )
    all_ctx = [item for r in results if not isinstance(r, Exception) for item in r]
    combined = "\n\n".join(
        f"[Club: '{i.metadata.get('query')}']\n{i.content}"
        for i in sorted(all_ctx, key=lambda x: x.relevance_score, reverse=True)
    )
    print(f"  Club total: {len(combined)} chars")
    return {"club_context": all_ctx, "combined_context": combined}


async def gather_mixed_context_node(state: OrchestratorState) -> dict:
    plan = state["plan"]
    print("\n== MIXED CONTEXT ==")
    coros = []
    if plan.search_queries:
        coros.append(("web", web_search_node(state)))
    if plan.rag_queries:
        coros.append(("rag", rag_search_node(state)))
    if plan.club_queries:
        coros.append(("club", club_search_node(state)))

    results = await asyncio.gather(*[c[1] for c in coros], return_exceptions=True)
    web_ctx, rag_ctx, club_ctx, parts = [], [], [], []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Mixed context error: {result}")
            continue
        src = coros[i][0]
        if src == "web":
            web_ctx = result.get("web_context", [])
        elif src == "rag":
            rag_ctx = result.get("rag_context", [])
        elif src == "club":
            club_ctx = result.get("club_context", [])
        if result.get("combined_context"):
            parts.append(result["combined_context"])

    combined = "\n\n".join(parts)[:3000]
    print(f"  Mixed total: {len(combined)} chars")
    return {"web_context": web_ctx, "rag_context": rag_ctx,
            "club_context": club_ctx, "combined_context": combined}


# ============================================================================
# WORKERS
# Helper: always return TaskResult as plain dict for reliable state merging
# ============================================================================

def _task_result(**kwargs) -> dict:
    """Create a TaskResult and immediately serialize to dict.
    LangGraph's operator.add reducer works on plain Python lists/dicts.
    Pydantic models in the results list can cause silent merge failures
    depending on checkpointer serialization, so we normalize early.
    """
    return TaskResult(**kwargs).model_dump()


GITHUB_TOOLS = [
    "create_repository", "get_file_contents", "create_or_update_file",
    "create_pull_request", "list_pull_requests", "update_pull_request",
    "search_repositories", "get_me",
]

PARAM_TYPE_MAP = {
    "search_repositories": {"perPage": int, "page": int},
    "list_pull_requests": {"perPage": int, "page": int},
    "create_pull_request": {"draft": bool},
}

def fix_tool_parameters(tool_call: dict) -> dict:
    tool_name = tool_call.get("name")
    parameters = tool_call.get("parameters", {})
    if tool_name in PARAM_TYPE_MAP:
        for param_name, expected_type in PARAM_TYPE_MAP[tool_name].items():
            if param_name in parameters:
                value = parameters[param_name]
                if expected_type == int and isinstance(value, str):
                    try:
                        parameters[param_name] = int(value)
                    except ValueError:
                        pass
                elif expected_type == bool and isinstance(value, str):
                    parameters[param_name] = value.lower() == "true"
    return tool_call


async def github_worker_node(payload: dict) -> dict:
    from auth.mcp_token_bridge import get_github_session
    from auth.github_oauth import clear_github_token

    task_data = payload["task"]
    context   = payload.get("context", "")
    task_id   = task_data["id"]
    user_id   = payload.get("user_id")

    print(f"\n  GITHUB_WORKER: Task {task_id} for user {user_id}")

    if not user_id:
        return {"results": [_task_result(
            task_id=task_id, worker_type="github", success=False,
            output="No user_id in payload — cannot fetch GitHub token.",
        )]}

    try:
        # One session for the entire agent run — no new handshake per iteration
        async with get_github_session(user_id) as (all_tools, err):
            if err:
                return {"results": [_task_result(
                    task_id=task_id, worker_type="github", success=False, output=err,
                )]}

            filtered = [t for t in all_tools if t.name in GITHUB_TOOLS]
            if not filtered:
                return {"results": [_task_result(
                    task_id=task_id, worker_type="github", success=False,
                    output="No GitHub tools available.",
                )]}

            prompt = (
                "Github username: nainaamodii\n"
                f"GitHub Task: {task_data.get('description', '')}\n"
                + (f"\nContext:\n{context[:800]}\n" if context else "")
                + f"\nQuery: {payload.get('user_query', '')}\n\n"
                "IMPORTANT: Ensure numeric params like perPage/page are numbers, not strings\n"
            )

            agent    = create_react_agent(worker_llm, filtered)
            response = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})

            if "tool_calls" in response:
                response["tool_calls"] = [
                    fix_tool_parameters(c) for c in response["tool_calls"]
                ]

            output = next(
                (m.content for m in reversed(response.get("messages", []))
                 if getattr(m, "content", None)),
                str(response),
            )
            return {"results": [_task_result(
                task_id=task_id, worker_type="github",
                success=True, output=output, used_context=bool(context),
            )]}

    except Exception as exc:
        error_str = str(exc)
        if "401" in error_str or "unauthorized" in error_str.lower():
            await clear_github_token(user_id)
            return {"results": [_task_result(
                task_id=task_id, worker_type="github", success=False,
                output="GitHub token revoked. Please reconnect in Settings → Integrations.",
                error=error_str,
            )]}
        logger.error(f"GitHub task {task_id} failed: {exc}")
        return {"results": [_task_result(
            task_id=task_id, worker_type="github", success=False,
            output=f"GitHub failed: {exc}", error=error_str,
        )]}


async def google_workspace_worker_node(payload: dict) -> dict:
    """
    Google worker — one MCP session for the entire agent run.

    The root cause of the repeated MCP handshakes was calling client.get_tools()
    and tool.ainvoke() outside of `async with client:`.  MultiServerMCPClient
    opens a brand-new transport session for every call made outside its context.
    By wrapping the whole worker in `async with get_google_workspace_session()`,
    we enter the context once, get tools once, and all agent iterations share
    that same open connection — regardless of how many tool calls the agent makes.
    """
    from auth.mcp_token_bridge import get_google_workspace_session

    if "task" in payload:
        task_data  = payload["task"]
        context    = payload.get("context", "")
        user_query = payload.get("user_query", "")
        user_id    = payload.get("user_id") or ""
    else:
        task_data  = payload
        context    = ""
        user_query = ""
        user_id    = ""

    task_id        = task_data.get("id", 0)
    google_service = (
        task_data.get("google_service") or task_data.get("worker_type") or ""
    ).lower()

    print(f"  GOOGLE_WORKER: Task {task_id} ({google_service})")

    if not user_id:
        return {"results": [_task_result(
            task_id=task_id, worker_type=f"google_{google_service}",
            success=False,
            output="Google action failed: no user_id. Please log in again.",
            error="missing_user_id",
        )]}

    try:
        # ── One session open for the entire block ──────────────────────────
        async with get_google_workspace_session(user_id) as (all_tools, err):
            if err:
                return {"results": [_task_result(
                    task_id=task_id, worker_type=f"google_{google_service}",
                    success=False, output=err,
                )]}

            gmail_kw = {"gmail", "email", "message", "inbox", "send", "draft", "thread", "label"}
            cal_kw   = {"calendar", "event", "schedule", "meeting", "attendee"}

            if google_service == "gmail":
                filtered = [t for t in all_tools
                            if any(kw in t.name.lower() for kw in gmail_kw)]
            elif google_service == "calendar":
                filtered = [t for t in all_tools
                            if any(kw in t.name.lower() for kw in cal_kw)]
            else:
                filtered = all_tools

            filtered = filtered[:5]

            if not filtered:
                return {"results": [_task_result(
                    task_id=task_id, worker_type=f"google_{google_service}",
                    success=False, output=f"No tools found for: {google_service}",
                )]}

            logger.info(
                f"Google {google_service}: {len(filtered)} tools: "
                f"{[t.name for t in filtered]}"
            )

            if google_service == "gmail":
                system_content = """You are a Gmail assistant. Use the available Gmail tools to fulfill requests.

Tool contracts:
- search_gmail_messages(query, max_results) -> list of objects, each with an "id" field.
- get_gmail_message_content(message_id) -> full email: subject, sender, date, body.
- get_gmail_messages_content_batch(message_ids) -> content of multiple emails.
  IMPORTANT: message_ids must be a non-empty list. Never call with empty list.
- send_gmail_message(to, subject, body) -> sends an email.
- get_gmail_attachment_content(message_id, attachment_id) -> retrieves attachment.

Present email summaries as: Subject | From | Date | Key points (2 lines max each).

EXECUTION RULES:
- Call each tool ONCE only. Never repeat a tool call.
- After a successful tool response (even 202 Accepted), consider the action DONE.
- Do NOT retry if you receive a confirmation or an ID in the response.
- Respond to the user immediately after one successful tool call.
"""
            elif google_service == "calendar":
                system_content = """You are a Google Calendar assistant. Use ONLY these exact tools:

AVAILABLE TOOLS:
1. list_calendars()
   - Lists all calendars. Call this first if you need a calendar_id other than "primary".
   - Returns: list of calendars with id, summary fields.

2. get_events(calendar_id, time_min, time_max, max_results)
   - Retrieves events from a calendar.
   - calendar_id: use "primary" unless user specifies another calendar.
   - time_min / time_max: ISO 8601 format REQUIRED e.g. "2026-04-12T00:00:00Z"
   - max_results: integer e.g. 10
   - FORBIDDEN parameters: do NOT include "detailed", "single_events", or any other param.

3. manage_event(calendar_id, summary, start_time, end_time, description, location, attendees, event_id)
   - USE THIS to CREATE a new event (omit event_id).
   - USE THIS to UPDATE an existing event (include event_id).
   - calendar_id: use "primary" unless user specifies.
   - start_time / end_time: ISO 8601 format REQUIRED e.g. "2026-04-12T10:00:00Z"
   - summary: event title (string).
   - attendees: optional list of email strings e.g. ["user@gmail.com"]
   - event_id: only for updates, get it from get_events first.

4. create_calendar(summary)
   - Creates a BRAND NEW separate calendar. NOT for creating events.
   - Only call if user explicitly says "create a new calendar".

CRITICAL RULES:
- To create an EVENT → use manage_event (NOT create_calendar).
- Never pass Python booleans (True/False) — use JSON (true/false).
- If time is not specified, default to tomorrow 10:00–11:00 in the user's timezone.
- Always use "primary" as calendar_id unless user specifies a different calendar name.

EXECUTION RULES:
- Call each tool ONCE only. Never repeat a tool call.
- After a successful tool response (even 202 Accepted), consider the action DONE.
- Do NOT retry if you receive a confirmation or an ID in the response.
- Respond to the user immediately after one successful tool call.

Present schedules in chronological order: Date | Time | Event title | Key details.
"""
            else:
                system_content = (
                    "You are a Google Workspace assistant. "
                    "When a tool returns IDs or references, pass them to subsequent tools. "
                    "Call each tool once only. Be concise."
                )

            task_desc = task_data.get("description", "")[:500]
            prompt    = f"User request: {user_query}\nTask: {task_desc}"
            if context:
                prompt += f"\n\nAdditional context:\n{context[:1500]}"

            # Agent runs entirely inside the open session — all tool calls reuse
            # the same MCP connection, so there is only ever ONE handshake per
            # worker invocation no matter how many iterations the agent takes.
            agent    = create_react_agent(worker_llm, filtered)
            response = await agent.ainvoke({
                "messages": [
                    SystemMessage(content=system_content),
                    HumanMessage(content=prompt),
                ]
            })

            output = next(
                (m.content for m in reversed(response.get("messages", []))
                 if getattr(m, "content", None)),
                str(response),
            )
            return {"results": [_task_result(
                task_id=task_id, worker_type=f"google_{google_service}",
                success=True, output=output[:2000], used_context=bool(context),
            )]}

    except Exception as exc:
        logger.error(f"Google Workspace task {task_id} failed: {exc}")
        return {"results": [_task_result(
            task_id=task_id, worker_type=f"google_{google_service}",
            success=False, output=f"Google Workspace failed: {exc}",
            error=str(exc),
        )]}


async def conversational_worker_node(payload: dict) -> dict:
    task_data = payload["task"]
    user_query = payload["user_query"]
    context = payload.get("context", "")
    task_id = task_data["id"]
    ctx_info = f" [{len(context)} chars context]" if context else " [no context]"
    print(f"  CONVERSATIONAL: task {task_id}{ctx_info}")
    try:
        conversation_history = payload.get("conversation_history", [])
 
        # Build system message
        system_msg = SystemMessage(content=(
            "You are a helpful Robotic Club assistant. "
            "You can retrieve context from user docs, web, and club resources. "
            "You can execute Gmail, Google Calendar, and GitHub operations for the user. "
            "You are here to assist the robotics club member and improve their productivity.\n\n"
            "IMPORTANT: The conversation history below contains everything said earlier in this "
            "session, including the user's name, preferences, and prior questions. "
            "Always use it to maintain continuity — never say you don't know something "
            "the user already told you this session.\n"
            "When knowledge-base context is provided, base your answer on it and cite details."
        ))
    
        # Build messages list: inject history as alternating human/ai turns
        from langchain_core.messages import AIMessage
        messages = [system_msg]
    
        for line in conversation_history:
            line = line.strip()
            if not line:
                continue
            # Route ALL bracketed metadata lines into system context
            if line.startswith("["):
                messages[0] = SystemMessage(
                    content=messages[0].content + f"\n\n{line}"
                )
                continue
            if line.startswith("user:"):
                messages.append(HumanMessage(content=line[5:].strip()))
            elif line.startswith("assistant:"):
                messages.append(AIMessage(content=line[10:].strip()))
            else:
                messages.append(HumanMessage(content=line))
    
        # Add the actual current query
        current_prompt = (
            f"User Query: {user_query}"
            + (f"\n\nContext from knowledge base:\n{context}" if context else "")
            + f"\n\nTask: {task_data.get('description', 'Respond to the user query')}"
        )
        messages.append(HumanMessage(content=current_prompt))
    
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: llm.invoke(messages))
    

        return {"results": [TaskResult(task_id=task_id, worker_type="conversational",
                                       success=True, output=response.content,
                                       used_context=bool(context))]}
    except Exception as exc:
        logger.error(f"Conversational task {task_id} failed: {exc}")
        return {"results": [_task_result(
            task_id=task_id, worker_type="conversational",
            success=False, output=f"Failed: {exc}", error=str(exc)
        )]}


# ============================================================================
# FANOUT (original — no HITL, kept for reference)
# ============================================================================

def fanout_to_workers(state: OrchestratorState):
    context = state.get("combined_context", "")
    user_id = state.get("user_id", "")

    sends = []
    for task in state["tasks"]:
        payload = {
            "task": task.model_dump(),
            "user_query": state["user_query"],
            "user_id": user_id,
            "conversation_history": state.get("conversation_history", [])
        }
        if context:
            payload["context"] = context

        wtype = task.worker_type.lower()

        if wtype == "github":
            sends.append(Send("github_worker", payload))
        elif task.worker_type in ("gmail", "calendar") or \
             task.worker_type.startswith("google_") or task.google_service:
            sends.append(Send("google_workspace_worker", payload))
        else:
            sends.append(Send("conversational_worker", payload))

    return sends


# ============================================================================
# AGGREGATOR
# ============================================================================

async def results_aggregator_node(state: OrchestratorState) -> dict:
    raw_approved = [
        p for p in (state.get("hitl_approved_payload") or [])
        if isinstance(p, dict) and p
    ]

    # Final dedup by task id before executing — guards against any reducer edge cases
    seen_ids: set = set()
    approved = []
    for p in raw_approved:
        task = p.get("task") or {}
        task_id = task.get("id", 0)
        dedup_key = (
            f"id:{task_id}" if task_id
            else f"{task.get('worker_type', '')}:{task.get('description', '')}"
        )
        if dedup_key not in seen_ids:
            seen_ids.add(dedup_key)
            approved.append(p)

    if len(approved) != len(raw_approved):
        logger.warning(
            f"Aggregator dedup removed {len(raw_approved) - len(approved)} duplicate payload(s)"
        )

    logger.info(
        f"HITL aggregator: {len(approved)} approved payloads: "
        f"{[(p.get('task', {}).get('worker_type'), p.get('task', {}).get('id')) for p in approved]}"
    )

    google_results = []
    if approved:
        print(f"\n== HITL GOOGLE WORKER: {len(approved)} approved task(s) ==")
        worker_outputs = await asyncio.gather(
            *[google_workspace_worker_node(p) for p in approved],
            return_exceptions=True,
        )
        for out in worker_outputs:
            if isinstance(out, Exception):
                cause = getattr(out, "__cause__", None) or getattr(out, "__context__", None)
                logger.error(f"Google worker error: {out} | cause: {cause}")
            else:
                google_results.extend(out.get("results", []))

    # Normalize all results to plain dicts then wrap as TaskResult for output building
    def _to_result(r) -> TaskResult:
        if isinstance(r, dict):
            return TaskResult(**r)
        return r

    raw_results = list(state.get("results") or []) + google_results
    all_results = [_to_result(r) for r in raw_results if r]

    print(f"\n== AGGREGATING {len(all_results)} result(s) ==")

    if not all_results:
        return {"final_response": "No tasks executed.", "hitl_approved_payload": []}
    if len(all_results) == 1:
        return {"final_response": all_results[0].output, "hitl_approved_payload": []}

    results_text = "\n\n".join(
        f"[{r.worker_type.upper()}] {r.output[:400]}" for r in all_results
    )
    response = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: llm.invoke([
            SystemMessage(content="Integrate results from multiple sources helpfully."),
            HumanMessage(content=(
                f"Query: {state['user_query']}\n\n"
                f"Results:\n{results_text}\n\nProvide a coherent final response."
            )),
        ]),
    )
    return {"final_response": response.content, "hitl_approved_payload": []}


# ============================================================================
# HITL GRAPH NODES
# ============================================================================

def fanout_to_workers_hitl(state: OrchestratorState):
    """
    Routes tasks to workers. Google tasks go to confirmation_node first.
    GitHub and conversational bypass HITL.
    """
    context = state.get("combined_context", "")
    user_id = state.get("user_id", "")

    sends = []
    for task in state["tasks"]:
        payload = {
            "task": task.model_dump(),
            "user_query": state["user_query"],
            "user_id": user_id,
            "conversation_history": state.get("conversation_history", [])
        }
        if context:
            payload["context"] = context

        if task.worker_type == "github":
            sends.append(Send("github_worker", payload))
        elif task.worker_type in ("gmail", "calendar") or \
             task.worker_type.startswith("google_") or task.google_service:
            # ALL Google tasks → confirmation gate first
            sends.append(Send("confirmation_node", payload))
        else:
            sends.append(Send("conversational_worker", payload))
    return sends


def route_after_confirmation(state: OrchestratorState) -> str:
    return "aggregator"


async def hitl_google_worker_node(state: OrchestratorState) -> dict:
    """Kept for reference — not used in current graph topology."""
    payloads = state.get("hitl_approved_payload") or []
    approved = [p for p in payloads if p is not None]
    if not approved:
        return {"results": [], "hitl_approved_payload": []}

    results = []
    for payload in approved:
        result = await google_workspace_worker_node(payload)
        results.extend(result.get("results", []))

    return {"results": results, "hitl_approved_payload": []}


# ============================================================================
# GRAPH BUILDERS
# ============================================================================

def build_smart_orchestrator():
    """Original graph — no HITL."""
    g = StateGraph(OrchestratorState)

    g.add_node("planning",                planning_agent_node)
    g.add_node("web_search",              web_search_node)
    g.add_node("rag_search",              rag_search_node)
    g.add_node("club_search",             club_search_node)
    g.add_node("gather_mixed_context",    gather_mixed_context_node)
    g.add_node("execute_tasks",           lambda s: s)
    g.add_node("github_worker",           github_worker_node)
    g.add_node("google_workspace_worker", google_workspace_worker_node)
    g.add_node("conversational_worker",   conversational_worker_node)
    g.add_node("aggregator",              results_aggregator_node)

    g.add_edge(START, "planning")
    g.add_conditional_edges("planning", route_after_planning, {
        "web_search": "web_search", "rag_search": "rag_search",
        "club_search": "club_search", "gather_mixed_context": "gather_mixed_context",
        "execute_tasks": "execute_tasks",
    })
    for ctx in ("web_search", "rag_search", "club_search", "gather_mixed_context"):
        g.add_edge(ctx, "execute_tasks")
    g.add_conditional_edges("execute_tasks", fanout_to_workers, {
        "github_worker": "github_worker",
        "google_workspace_worker": "google_workspace_worker",
        "conversational_worker": "conversational_worker",
    })
    for w in ("github_worker", "google_workspace_worker", "conversational_worker"):
        g.add_edge(w, "aggregator")
    g.add_edge("aggregator", END)
    return g.compile()


def build_smart_orchestrator_with_hitl(checkpointer=None):
    """
    HITL graph.

    confirmation_node (called via Send from execute_tasks) receives the task
    payload, calls interrupt(), and on resume returns either:
      {"hitl_approved_payload": [payload]}  → approved
      {"results": [TaskResult(...)]}        → rejected

    confirmation_node always edges to aggregator.
    Aggregator executes all approved Google payloads via asyncio.gather.
    """
    from hitl.confirmation import confirmation_node

    g = StateGraph(OrchestratorState)

    g.add_node("planning",              planning_agent_node)
    g.add_node("web_search",            web_search_node)
    g.add_node("rag_search",            rag_search_node)
    g.add_node("club_search",           club_search_node)
    g.add_node("gather_mixed_context",  gather_mixed_context_node)
    g.add_node("execute_tasks",         lambda s: s)
    g.add_node("github_worker",         github_worker_node)
    g.add_node("conversational_worker", conversational_worker_node)
    g.add_node("aggregator",            results_aggregator_node)

    # HITL node
    g.add_node("confirmation_node",     confirmation_node)

    g.add_edge(START, "planning")
    g.add_conditional_edges("planning", route_after_planning, {
        "web_search": "web_search", "rag_search": "rag_search",
        "club_search": "club_search", "gather_mixed_context": "gather_mixed_context",
        "execute_tasks": "execute_tasks",
    })
    for ctx in ("web_search", "rag_search", "club_search", "gather_mixed_context"):
        g.add_edge(ctx, "execute_tasks")

    # Fanout: Google → confirmation, others → direct workers
    g.add_conditional_edges("execute_tasks", fanout_to_workers_hitl, {
        "github_worker":         "github_worker",
        "confirmation_node":     "confirmation_node",
        "conversational_worker": "conversational_worker",
    })

    # confirmation_node always goes to aggregator
    g.add_edge("confirmation_node", "aggregator")

    for w in ("github_worker", "conversational_worker"):
        g.add_edge(w, "aggregator")
    g.add_edge("aggregator", END)

    return g.compile(checkpointer=checkpointer)


# ============================================================================
# ORCHESTRATOR
# ============================================================================

class SmartOrchestrator:
    """
    Smart Orchestrator with Human-in-the-Loop for Google write actions.

    process() → may return interrupted=True with confirmation_required
    resume()  → resumes the frozen graph with user's approve/reject + edits
    """

    def __init__(self):
        from hitl.checkpointer import get_checkpointer
        self._checkpointer = get_checkpointer()
        self.graph = build_smart_orchestrator_with_hitl(checkpointer=self._checkpointer)

        # Maps user_id → {"thread_id": str, "message": str, "interrupt_id": ...}
        self._pending_confirmations: dict[str, dict] = {}

        rag_ok = get_rag_retrieval_service() is not None
        print(f"\n{'='*60}")
        print(f"SMART ORCHESTRATOR READY  (model: {_model})")
        print(f"  Planning LLM : {_planning_model}")
        print(f"  User RAG     : {'ready' if rag_ok else 'UNAVAILABLE -- check .env'}")
        print(f"  Club RAG     : lazy (initialises on first club query)")
        print(f"  Workers      : conversational | github | gmail | calendar")
        print(f"  Worker LLM   : {os.getenv('WORKER_MODEL', 'llama-3.1-8b-instant')}")
        print(f"  HITL         : ENABLED (gmail send / calendar create/update/delete)")
        print(f"{'='*60}")

    def _make_config(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def _extract_interrupt(self, state_or_exc, user_id: str, thread_id: str) -> dict | None:
        """Detect LangGraph interrupt(s) from state dict or exception."""
        interrupts = []

        if isinstance(state_or_exc, dict):
            interrupt_data = state_or_exc.get("__interrupt__")
            if not interrupt_data:
                return None
            interrupts = interrupt_data
        else:
            exc = state_or_exc
            if "interrupt" not in type(exc).__name__.lower() and \
               "Interrupt" not in type(exc).__name__:
                return None
            try:
                val = exc.value if hasattr(exc, "value") else str(exc)
                if isinstance(val, (list, tuple)):
                    interrupts = list(val)
                else:
                    interrupts = [val]
            except Exception:
                interrupts = [str(exc)]

        if not interrupts:
            return None

        # Take the first pending interrupt
        first = interrupts[0]

        interrupt_id = getattr(first, "id", None)
        msg = getattr(first, "value", str(first))
        if isinstance(msg, bytes):
            msg = msg.decode()

        self._pending_confirmations[user_id] = {
            "thread_id":    thread_id,
            "message":      msg,
            "interrupt_id": interrupt_id,
        }
        return {
            "success": True, "interrupted": True,
            "confirmation_required": {"message": msg, "thread_id": user_id},
        }

    async def resume(self, user_id: str, user_response: str) -> dict:
        pending = self._pending_confirmations.pop(user_id, None)
        if not pending:
            return {"success": False, "interrupted": False,
                    "response": "No pending confirmation found. It may have expired.",
                    "metadata": {}}

        thread_id    = pending["thread_id"]
        interrupt_id = pending.get("interrupt_id")
        config       = self._make_config(thread_id)

        if interrupt_id is not None:
            resume_command = Command(resume={interrupt_id: user_response})
        else:
            resume_command = Command(resume=user_response)

        try:
            final = await self.graph.ainvoke(resume_command, config=config)
            interrupt_resp = self._extract_interrupt(final, user_id, thread_id)
            if interrupt_resp:
                return interrupt_resp
            return self._build_success_response(final)

        except Exception as exc:
            interrupt_resp = self._extract_interrupt(exc, user_id, thread_id)
            if interrupt_resp:
                return interrupt_resp
            logger.error(f"Resume error: {exc}", exc_info=True)
            return {"success": False, "interrupted": False,
                    "response": f"Resume error: {exc}", "metadata": {}}

    def _build_success_response(self, final: dict) -> dict:
        results = final.get("results", [])
        # Normalize to TaskResult objects for metadata counting
        normalized = []
        for r in results:
            if isinstance(r, dict):
                try:
                    normalized.append(TaskResult(**r))
                except Exception:
                    pass
            else:
                normalized.append(r)
        return {
            "success": True, "interrupted": False,
            "response": final.get("final_response", ""),
            "metadata": {
                "total_tasks":      len(normalized),
                "successful_tasks": sum(1 for r in normalized if r.success),
                "web_search_used":  bool(final.get("web_context")),
                "rag_search_used":  bool(final.get("rag_context")),
                "club_search_used": bool(final.get("club_context")),
                "workers_used":     list({r.worker_type for r in normalized}),
            },
        }

    async def process(self, user_query: str,
                      conversation_history: List[str] = None,
                      user_id: str = "") -> dict:
        if not user_query or not user_query.strip():
            return {"success": False, "interrupted": False,
                    "response": "Empty query.", "metadata": {}}

        # Unique thread_id per query prevents stale checkpoint replay
        thread_id = f"{user_id}_{uuid.uuid4().hex[:8]}" if user_id else uuid.uuid4().hex
        config    = self._make_config(thread_id)

        state: OrchestratorState = {
            "user_id":               user_id,
            "user_query":            user_query.strip(),
            "conversation_history":  conversation_history or [],
            "plan":                  None,
            "web_context":           [],
            "rag_context":           [],
            "club_context":          [],
            "combined_context":      "",
            "tasks":                 [],
            "results":               [],
            "final_response":        "",
            "hitl_approved_payload": [],
        }

        try:
            final = await self.graph.ainvoke(state, config=config)
            interrupt_resp = self._extract_interrupt(final, user_id, thread_id)
            if interrupt_resp:
                return interrupt_resp
            return self._build_success_response(final)

        except Exception as exc:
            interrupt_resp = self._extract_interrupt(exc, user_id, thread_id)
            if interrupt_resp:
                return interrupt_resp
            logger.error(f"Orchestrator error: {exc}", exc_info=True)
            return {"success": False, "interrupted": False,
                    "response": f"Orchestrator error: {exc}", "metadata": {}}

    def is_pending_confirmation(self, user_id: str) -> bool:
        return user_id in self._pending_confirmations

    def get_pending_message(self, user_id: str) -> str | None:
        entry = self._pending_confirmations.get(user_id)
        return entry["message"] if entry else None

    async def cleanup(self):
        await mcp_pool.cleanup()


# ============================================================================
# CLI
# ============================================================================

def interactive_mode():
    print(f"\n{'='*60}\nSMART ORCHESTRATOR -- CLI\n{'='*60}")
    orch = SmartOrchestrator()
    history: List[str] = []
    try:
        while True:
            try:
                query = input("\nQuery: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break
            if not query:
                continue
            if query.lower() in {"quit", "exit", "q"}:
                print("\nGoodbye!")
                break

            result = asyncio.run(orch.process(query, history))
            history.append(f"User: {query}")
            if result["success"]:
                history.append(f"Assistant: {result['response'][:100]}...")

            print(f"\n{'='*60}\nRESPONSE\n{'='*60}")
            print(result["response"])
            if result["success"]:
                m = result["metadata"]
                print(f"\nworkers={m['workers_used']}  "
                      f"rag={m['rag_search_used']}  "
                      f"club={m['club_search_used']}")
    finally:
        asyncio.run(orch.cleanup())


orchestrator = SmartOrchestrator()

if __name__ == "__main__":
    interactive_mode()