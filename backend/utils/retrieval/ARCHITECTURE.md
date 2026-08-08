# Retrieval architecture

This package provides the context and tool surfaces used by Omi’s agentic chat paths.

## Flow

1. `agentic.py` assembles the agent runtime and provider-specific streaming/tool behavior.
2. `tools/` exposes bounded tool adapters for conversations, memories, action items, integrations, files, screens, graphs, and web retrieval.
3. `tool_services/` owns reusable service-layer operations used by tool adapters.
4. `rag.py` implements the legacy vector-backed conversation retrieval path and context rendering.
5. `hybrid.py` reranks a bounded vector candidate set with BM25 and reciprocal-rank fusion.
6. `safety.py` limits tool loops, tool count, and context growth; `tool_result_boundaries.py` preserves memory evidence boundaries before results return to the model.

## Boundaries

- Tools are the model-facing boundary; service modules are the reusable implementation boundary.
- Retrieval results must remain bounded and must preserve authorization and memory evidence markers.
- Managed chat uses the gateway’s OpenAI-compatible route; direct specialist providers remain explicit and isolated.
- New tools should be exported from `tools/__init__.py`, covered by focused tests, and routed through existing safety and result-boundary helpers where applicable.
