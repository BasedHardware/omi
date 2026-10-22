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
  matching, discard detection, summarization). The section writer uses
  [readable, grounded note guidance](../../docs/conversation-note-style.md).
- `conversation_folder.py` — conversation → folder assignment.
- `followup.py` — follow-up question generation.
- `persona.py` — persona chat, memory condensation for personas.
- `openglass.py` — vision (image description) model calls.

## Memory & knowledge graph

- `memories.py` — memory extraction (standard + high-recall).
- `working_observations.py` — working-observation batch synthesis.
- `knowledge_graph.py` — node/edge extraction from memories.

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

## Agent harness

`shaped_agent.py` is the sanctioned model/tool loop (`Mount`, `Budget`, `run_loop`) behind the
notes agent (`notes_agent*.py`), Dream (`utils/agent_capabilities/session.py`) and shaped chat.

### Tool design rules

Every agent on the harness gets these from shared code, not per-agent prompt text:

1. **Time windows default to context.** A run carries a `ContextWindow` (`utils/model_text.py`)
   on its `Mount` (and Dream's `Session`): the conversation for notes, the trailing day for
   Dream, the attached chat timeframe or the last 24 hours for chat. Time-range tools take
   optional start/end and fill missing bounds with `ContextWindow.resolve`. Dream's
   lexical/semantic search keeps its bounds as optional all-history filters.
2. **Times in UTC.** Everything the harness shows the model goes through `model_json` /
   `model_view`, so instants end in `Z`. Time arguments go through `parse_tool_time`: offsets
   convert, `Z` and naive times are UTC, and anything unreadable is a tool error naming the
   field and `TIME_FORMAT_HINT`, never a silently wrong window. Chat keeps its labelled local
   display (`format_instant`), so its tools read naive times in the user's zone instead.
3. **Normalize before validating.** An output or tool-argument schema declares near-miss keys
   as data: `output_aliases: ClassVar[dict[str, tuple[str, ...]]]` (for example
   `ExtractedSection` maps `body` to `body_markdown`). `normalize_output` / `validate_output`
   apply them recursively before validation; add an alias there, never ad-hoc code.
4. **Send-back budgets per failure class.** Output checks return `Problem(kind, message)`;
   `SendBackBudget` holds one budget per class (notes: format, content, evidence). Format
   problems go back alone, each class is charged only for its own send-backs, and once a class
   is spent the output is repaired and accepted instead.

Tests: `tests/unit/test_agent_tool_rules.py`.

## Conventions

- Prefer routing new calls through the gateway core above; do not add a new
  direct-provider path.
- Keep prompts and provider selection separate from route and auth handling.
- Construct provider clients lazily and sanitize provider responses before
  logging them.
- Add hermetic backend-unit coverage for routing and fallback changes; fallback
  branches use the shared fallback telemetry helper.
