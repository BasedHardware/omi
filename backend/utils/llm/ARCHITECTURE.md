# LLM orchestration utilities

Prompt construction and LLM-call helpers for chat, conversation
post-processing, memory extraction, notifications, and app generation. Callers
in `routers/` and the background workers own request auth, persistence, and
response shaping; this package owns prompt shape and model invocation only.

## Boundaries

- **Model access** — `clients.py`, `model_config.py`, and `providers.py` build
  model instances and resolve model/provider tokens. Every LLM call routes
  through these; do not construct SDK clients elsewhere in the package.
- **Managed gateway lane** — `gateway_client.py`, `gateway_serving.py`,
  `gateway_anthropic.py`, `gateway_byok.py`, `gateway_shadow.py`, and
  `gateway_observability.py` route Omi-managed and BYOK traffic through the
  internal `llm_gateway/` service with legacy-transport fallback. `byok_errors.py`
  turns provider-key failures into user-facing notifications.
- **Chat and conversation** — `chat.py` runs chat-message processing;
  `conversation_processing.py` and `conversation_folder.py` post-process and
  categorize persisted conversations. `followup.py` and `trends.py` derive
  follow-ups and trends from that content.
- **Memory** — `memories.py`, `working_memory.py`, `working_observations.py`,
  `durable_memory_patches.py`, `knowledge_graph.py`, and `l2_memory_routes.py`
  extract and maintain user facts; `promotion_proposals.py` and
  `promotion_routes.py` propose ST→LT promotions. Durable maintenance ownership
  stays in the memory-maintenance job, not here.
- **Proactive surfaces** — `proactive_notification.py` and `notifications.py`
  compose notification copy; `goals.py` tracks goal progress; `temporal.py`
  grounds insights and extraction in the caller's current date.
- **Apps and personas** — `app_generator.py` with `app_generation_prompts.py`
  generate apps from prompts; `persona.py` manages persona generation;
  `openglass.py` and `external_integrations.py` cover their respective surfaces.
- **Usage** — `fair_use_classifier.py` classifies usage against soft caps and
  `usage_tracker.py` records LLM usage. Enforcement and billing state live in
  `database/fair_use.py` and the payment surfaces, not here.

## Data and credential safety

Prompts here receive already-authorized user content. Request-scoped BYOK keys
may reach the gateway helpers for a single call but must never be persisted,
placed in durable task payloads, or logged. Sanitize any model or provider
response before logging (`utils.log_sanitizer`).
