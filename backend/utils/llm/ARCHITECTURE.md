# LLM utilities

`backend/utils/llm` owns provider selection, request-scoped LLM invocation, and
feature-specific interpretation of model output. HTTP authentication and response
shaping belong in `backend/routers/`; durable records and transactional writes
belong in `backend/database/` and `backend/models/`.

## Provider and gateway boundary

- `model_config.py` and `providers.py` define the supported model/provider
  contract. `clients.py` is the sole shared client factory; it creates clients
  lazily, applies request callbacks, and owns bounded client caches.
- `byok_errors.py` classifies provider failures and coordinates the user-facing
  BYOK health signal. `usage_tracker.py` records bounded usage metadata.
- `gateway_client.py`, `gateway_byok.py`, `gateway_anthropic.py`,
  `gateway_serving.py`, `gateway_observability.py`, and `gateway_shadow.py`
  implement the managed-gateway path. They own gateway request envelopes,
  request-scoped BYOK headers, transport fallback decisions, and shape-only
  observability; they do not own Firebase session validity or durable chat
  state.

All blocking model calls from async entry points must use the `llm_executor`
through `run_blocking`. Provider clients and credentials remain request-scoped
or bounded in-memory caches; never persist raw provider keys or raw model
responses in this package.

## Feature coordinators

- Conversation features: `chat.py`, `conversation_processing.py`,
  `conversation_folder.py`, `followup.py`, and `external_integrations.py`
  build prompts and validate model output for chat, completed conversations,
  folders, follow-ups, and integration payloads.
- Memory and insight features: `memories.py`, `working_memory.py`,
  `working_observations.py`, `l2_memory_routes.py`, `promotion_proposals.py`,
  `promotion_routes.py`, `temporal.py`, `trends.py`, `goals.py`, and
  `knowledge_graph.py` create proposed interpretations. Canonical memory
  persistence and lifecycle transitions stay in the memory services and
  database layer. `durable_memory_patches.py` only preserves the established
  import surface for the proposal types while callers migrate to
  `promotion_proposals.py`.
- Product features: `app_generator.py` and `app_generation_prompts.py` create
  marketplace app drafts; `persona.py`, `openglass.py`, `notifications.py`,
  `proactive_notification.py`, and `fair_use_classifier.py` implement their
  respective prompt and output contracts.

## Safe change points

- Add or change a provider/model in `model_config.py` and `providers.py`, then
  update the matching client, gateway, and configuration tests together.
- Add a model-backed product behavior in its feature coordinator; keep route
  authorization, database writes, retry ownership, and API schemas outside
  this package.
- Treat model output as untrusted: parse it into a typed result, validate it at
  the owning feature boundary, and log only sanitized or shape-level details.
