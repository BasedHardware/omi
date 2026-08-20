# Retrieval architecture

`backend/utils/retrieval` owns the context-selection and tool-execution path for core chat.

## Flow

`graph.py` selects the chat path and streams the response. `agentic.py` owns the stable core-tool registry, tool schema conversion, and agentic execution. `web_search_gate.py` re-decides the Anthropic server-side web_search offer on each agent-loop request once private tool output is in the transcript. `rag.py`, `hybrid.py`, and `safety.py` provide retrieval, ranking, and response-safety boundaries.

## Tool boundaries

The `tools/` package exposes LangChain tools with user identity supplied through `RunnableConfig`. Tools call persistence and provider code through `database/` or `tool_services/`; they do not own HTTP routes. `tool_services/` contains reusable retrieval operations shared by tools and route handlers. `tool_result_boundaries.py` and `tools/result_bounds.py` keep large provider results bounded before they reach the model.


## Invariants

- `CORE_TOOLS` remains stable and ordered so prompt-cache prefixes remain reusable.
- Tool calls receive the authenticated UID from request configuration and never infer identity from user text.
- Retrieval results are bounded before model invocation.
