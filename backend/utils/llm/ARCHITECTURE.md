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

## Capture/speaker/notes refactor (L3)

`notes_packet.py` is the input authority for agent, one-shot, rich and fallback
notes: resolved output language, local capture time (#4773), density/length,
wake-word rules, trusted contact spellings, and L2 speaker evidence. It builds
and compares packets in shadow without any second model call. `output_language.py`
resolves the account preference, then the conversation language, then English.

`notes_output.py` is the internal parser/tool schema. `notes_output_contract.py`
validates title, length, participants, tasks and citations and applies the same
static repairs to every arm. A coverage floor violation is sent back within the
agent's existing budget; a depleted budget preserves grounded short notes rather
than fabricating padding. Repaired agent submissions survive a later deadline or
malformed turn, so salvage does not buy a second full-transcript writer.

Open-loop extraction (delegations, others' commitments, one observed issue or
blocker) rides `conversation_processing.py` behind `OPEN_LOOPS_ENABLED`
(`config/open_loops.py`, default on): the rules append to the one-shot mount
instructions and the fields live on schema subclasses (`OpenLoopNotesOutput`,
`OpenLoopStructuredExtraction`) so the flag-off prompt and the agentic submit
tool stay byte-identical. The parsed extractions flow through a mutable sink to
`utils/conversations/process_conversation.py`, which persists them in the
server-only `open_loop_extractions` conversation field; the deterministic card
writer and the storage contract live in `utils/open_loops/` (see its README).
The agentic lane's hand-written submit schema does not request these fields yet,
so long agent-written meetings currently extract none.

The open-loop daily pass (PR 2) runs as a fail-open sibling step of the daily
recap job (`utils/other/notifications`): one usage-tracked call on the
`open_loop_daily` lane (Luna, reasoning pinned low) per user per local day,
over the recap's own render of the day plus the loop store (`store.py` rules:
expiry, task-aware dedupe — link, never drop — cooldown, ≤3 value-≥3 slots).
Cards persist per day server-side and are not served until PR 3.

`NOTES_PACKET_V2_MODE` and `STT_LANGUAGE_HINTS_MODE` are read exclusively through
`config/refactor_modes.py`. Both default to shadow, with no serving cohort in a
manifest. `off` restores legacy output. Shadow records only counts/sizes, never
packet text, contact names or account identifiers. Cohort selection uses the
existing `_SERVE_PERCENT` and `_SERVE_UID_SHA256S` contract.

`notes_short_clip.py` keeps transcript fragments below 12 words with the existing
deterministic minimum and no emoji or paid notes, for every processing trigger.
Duration never determines discarding; described photos retain their normal path.
`daily_recap_fingerprint.py` refreshes the same recap ID when input IDs, revisions
or legacy summary content change, preserving the completed-delivery receipt.

`utils/episodes/moment_render.py` uses the notes voice-key renderer and owner gate.
Its `name_segments(segments, names)` contract is for L4; `incremental.render_moment`
accepts optional `uid`/`conversation_id` for L3 cohort and L2 evidence lookup.
Pass `conversation_language` or the resolved `output_language` to the incremental
update. `conversation_topic.generate_conversation_topic` accepts optional segments
so it can exclude explicit `language_conformance=out_of_profile` inputs. These
consumers never guess language conformance from short text. Persisting that
classification belongs to the STT/transcript producer, outside this lane.

The single-language Soniox hint overlay preserves `STT_LEARNED_LANGUAGE_PROFILE`
and `STT_MULTI_LANGUAGE_HINTS`, never selects another provider and never changes
prerecorded language gates. Off and shadow return the existing hint list.

Metrics: `omi_notes_refactor_shadow_total{check,outcome}`,
`omi_notes_refactor_results_total{check,outcome}`, and existing
`omi_notes_agent_repairs_total{kind=salvaged_submission}`. Owner dazheng reviews
synthetic acceptance, attribution/citation violations, latency and paid usage
before expanding to 1%, 10%, 100% by 2026-10-26, with a complete 24h lookback at
each step. Any error or attribution regression blocks expansion; rollback is off.
The retired evidence writer and prompt contract live only under
`testing/episode_notes/`; live episode lifecycle code is a separate feature.
