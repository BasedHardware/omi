# utils/llm

LLM orchestration for the backend. Everything that builds prompts, calls a model, and shapes
the result lives here. Import rule (from `backend/AGENTS.md`): this package may import from
`database/` but never from `routers/` or `main.py`.

Model access is lazy: construct clients through the getters in `clients.py` / `providers.py`
at call time, never at import (import purity is enforced in CI).

## Model access and gateway

- `clients.py` — model instances and the `get_llm(feature)` entry point, with prompt caching and usage callbacks.
- `providers.py`, `model_config.py` — provider registry and the pure model-token / required-env config contract.
- `byok_errors.py` — typed bring-your-own-key error surface.
- `gateway_*.py` (`gateway_client`, `gateway_serving`, `gateway_anthropic`, `gateway_byok`, `gateway_shadow`, `gateway_observability`) — the Omi-managed `omi:auto:*` LLM gateway lane: client, serving, provider adapters, BYOK routing, shadow comparison, and observability.

## Chat and conversation

- `chat.py` — chat message processing and tool use.
- `conversation_processing.py`, `conversation_folder.py`, `followup.py` — post-conversation analysis, foldering, and follow-up generation.

## Memory

- `memories.py`, `working_memory.py`, `working_observations.py` — memory extraction and the working-memory tier.
- `durable_memory_patches.py`, `l2_memory_routes.py`, `knowledge_graph.py` — durable patches, L2 routing, and knowledge-graph rebuild.

## Persona, clone, and drafting

- `persona.py` — persona (voice) management.
- `reply_draft.py` — the review-first reply-draft primitive shared by the on-behalf responder.
- `on_behalf.py` — the AI clone: drafts a reply as the user for one contact and returns a server-owned safety-floor verdict (see `utils/clone_policy.py`). Send authorization is a local/persisted decision, never a request field.
- `clone_benchmark.py` — scores the clone against the user's own past replies.

## Generation, notifications, and signals

- `app_generator.py`, `app_generation_prompts.py` — app/persona generation.
- `notifications.py`, `proactive_notification.py` — notification copy and proactive triggers.
- `goals.py`, `trends.py`, `promotion_proposals.py`, `promotion_routes.py` — goal tracking, trends, and promotion proposals/routing.
- `external_integrations.py`, `openglass.py`, `fair_use_classifier.py`, `usage_tracker.py` — integration prompts, OpenGlass vision, fair-use classification, and per-feature usage tracking.
