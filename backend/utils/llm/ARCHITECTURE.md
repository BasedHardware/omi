# `backend/utils/llm`

LLM-backed feature layer for the backend. Every module here turns a product
feature (chat, memory extraction, notifications, personas, app generation, …)
into one or more model calls, and routes those calls through a shared
**gateway-first** transport with a legacy direct-provider fallback.

The package is large because it collects *all* per-feature LLM prompts and
response parsers in one place. New code should join the matching group below
rather than adding another top-level concern.

## Transport & routing core

The shared plumbing every feature call goes through.

- `gateway_client.py` — resolves the LLM gateway base URL / service token and
  low-level request helpers.
- `gateway_serving.py` — gateway-first serving with fallback to a legacy
  provider on hard transport failures.
- `gateway_anthropic.py` — gateway-first Anthropic Messages client with a
  direct-transport fallback.
- `gateway_byok.py` — BYOK (bring-your-own-key) credential envelope helpers for
  gateway routing.
- `gateway_shadow.py` — dev/shadow comparison wrapping (sampled, prod-gated).
- `gateway_observability.py` — records gateway vs. direct outcomes for
  comparison and health.
- `clients.py` — LLM client construction plus the shared error callback wiring.
- `providers.py` / `model_config.py` — provider-specific chat-model
  construction and model/profile selection per feature.
- `byok_errors.py` — classifies and normalizes BYOK/provider LLM errors.
- `usage_tracker.py` — feature-level token-usage accounting.

## Chat & conversation

- `chat.py` — chat prompt assembly, context handling, response normalization.
- `conversation_processing.py` — post-conversation structuring (speaker id
  matching, discard detection, summarization).
- `conversation_folder.py` — conversation → folder assignment.
- `followup.py` — follow-up question generation.
- `persona.py` — persona chat, memory condensation for personas.
- `openglass.py` — vision (image description) model calls.

## Memory & knowledge graph

- `memories.py` — memory extraction (standard + high-recall).
- `working_observations.py` — working-observation batch synthesis
  (`working_memory.py` is a backward-compatible shim, WS-G11).
- `knowledge_graph.py` — node/edge extraction from memories.
- `promotion_proposals.py` / `promotion_routes.py` — durable-memory patch
  proposals and their routing (`durable_memory_patches.py` and
  `l2_memory_routes.py` are backward-compatible shims, WS-G11).

## Proactive, notifications & insights

- `notifications.py` — relevance retrieval and notification content.
- `proactive_notification.py` — proactive notification drafting + validation.
- `goals.py` — goal-tracking LLM utilities.
- `trends.py` — trend extraction.
- `temporal.py` — current-date grounding injected into prompts.

## Apps, integrations & policy

- `app_generator.py` / `app_generation_prompts.py` — AI app generation.
- `external_integrations.py` — structured summaries for external integrations.
- `fair_use_classifier.py` — LLM-based purpose detection for fair-use policy.

## Conventions

- Prefer routing new calls through the gateway core above; do not add a new
  direct-provider path.
- Backward-compatible shims (`working_memory.py`, `durable_memory_patches.py`,
  `l2_memory_routes.py`) only re-export from their real modules — put
  implementation in the target module, not the shim.
- Keep prompts and provider selection separate from route and auth handling.
- Construct provider clients lazily and sanitize provider responses before
  logging them.
- Add hermetic backend-unit coverage for routing and fallback changes; fallback
  branches use the shared fallback telemetry helper.
