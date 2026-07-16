# LLM utilities

Shared model routing, provider adapters, gateway integration, and LLM-backed
domain helpers used by backend routes and background processing.

## Package map

- `model_config.py` resolves feature names to quality-of-service profiles,
  providers, models, and route options.
- `clients.py` is the compatibility entry point for callers selecting an LLM by
  feature. It applies BYOK context, usage/error callbacks, gateway routing, and
  legacy fallback policy.
- `providers.py` constructs and caches provider-specific LangChain clients.
  Product feature behavior does not belong there.
- `gateway_client.py`, `gateway_anthropic.py`, `gateway_byok.py`,
  `gateway_serving.py`, `gateway_shadow.py`, and `gateway_observability.py` own
  the Omi gateway transport, rollout, fallback, shadowing, and telemetry seams.
- `byok_errors.py` and `usage_tracker.py` centralize provider error handling and
  usage accounting.
- `chat.py`, `conversation_processing.py`, `conversation_folder.py`, and
  `followup.py` implement chat and conversation extraction workflows.
- `memories.py`, `working_memory.py`, `working_observations.py`,
  `durable_memory_patches.py`, `knowledge_graph.py`, `l2_memory_routes.py`,
  `promotion_routes.py`, and `promotion_proposals.py` provide LLM-backed memory
  transformations. Authoritative persistence remains outside this package.
- The remaining feature modules own their named prompt and transformation
  workflows, including apps, goals, notifications, persona, temporal context,
  trends, and external integrations.

## Boundaries

- HTTP authentication and response shaping belong in `backend/routers/`.
- Persistent reads and writes belong in `backend/database/`; shared data
  contracts belong in `backend/models/`.
- New provider construction belongs in `providers.py`; new feature routing
  belongs in `model_config.py` and should be consumed through `clients.py`.
- Gateway behavior must stay behind the gateway modules so feature workflows do
  not depend directly on transport or service-token details.
- Blocking model calls from `async def` code must be offloaded through
  `llm_executor`; synchronous helpers may be called from FastAPI `def` routes or
  an existing executor lane.

## Data and credential safety

BYOK credentials are request-scoped and must never be cached as raw values,
persisted, included in durable task payloads, or logged. Prompts, model output,
and provider error bodies may contain user data; follow the repository logging
rules and sanitize them before logging.
