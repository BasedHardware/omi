# Hybrid provider settings (ADR)

## Context

Desktop hybrid mode (`OMI_DESKTOP_BACKEND_MODE=local`) stores provider policy in the
local daemon SQLite `settings` table. Requests go **directly** to configured endpoints,
never through Omi Python/Rust proxies.

The current durable policy key is `provider_policy`. Older raw provider keys are still
read as a compatibility bridge while desktop UI migrates to the typed policy API.

## Model catalog and provider policy

The local daemon exposes a subscription/profile-aware catalog at
`GET /v1/model-catalog`. Each entry reports:

- model ID and display name;
- compatible provider kinds and configured account IDs;
- allowed task slots;
- availability for the local profile/subscription state;
- capability flags for JSON mode, tool calls, multimodal input, streaming, and
  local/remote origin.

Local profile defaults are centralized in this catalog/policy layer:

| Slot | Default model | Account behavior |
|------|---------------|------------------|
| `post_transcript` | `gpt-5.4-mini` | selected by default; unusable until a provider account is configured |
| `proactive` | `gpt-5.4-mini` | selected by default; unusable until a provider account is configured |
| `chat` | profile/subscription default (`gpt-5.4-mini` for this profile) | configurable |
| `memory_search` | `local_wiki` | always local; no embedding provider required |

Slot resolution returns both the selected model and a readable reason. A slot can
therefore report a default model while also explaining that it cannot run because no
provider account or subscription integration is configured.

## Provider policy

`provider_policy` is versioned JSON:

```json
{
  "version": 1,
  "provider_accounts": [
    {
      "id": "local-ollama",
      "kind": "openai_compatible",
      "base_url": "http://127.0.0.1:11434/v1",
      "api_key": null,
      "display_name": "Local Ollama",
      "capabilities": {
        "chat_completions": true,
        "json_mode": true,
        "tool_calls": false,
        "vision": false,
        "speech_to_text": false
      },
      "subscription_integration": null
    }
  ],
  "model_slots": {
    "post_transcript": {
      "provider_account_id": "local-ollama",
      "model_id": "gpt-5.4-mini",
      "options": {
        "json_mode": true,
        "tool_support": false
      }
    },
    "memory_search": {
      "provider_account_id": null,
      "model_id": "local_wiki",
      "options": {}
    }
  }
}
```

Stable slot names are:

| Slot | Purpose |
|------|---------|
| `chat` | Ask Omi / local chat completions |
| `post_transcript` | Conversation title, overview, memories, and action items |
| `proactive` | Proactive local intelligence |
| `vision` | Screenshot / OCR-adjacent multimodal model calls |
| `stt` | Speech-to-text provider policy |
| `memory_search` | Local memory retrieval policy |

`memory_search` is `local_wiki` for this local profile and does not require
`embedding_provider` or embeddings readiness.

## Provider policy API

Desktop clients should prefer these daemon APIs over manual JSON editing:

- `GET /v1/provider-policy` returns the typed policy plus legacy-derived slots.
- `PUT /v1/provider-policy` validates and persists the typed policy.
- `GET /v1/provider-policy/resolve/{slot}` resolves one slot to its provider account,
  model, options, source (`provider_policy`, `legacy_setting`, or `default`), and a
  readable success/failure reason.
- `POST /v1/provider-policy/test-slot/{slot}` validates the actual resolved task
  path. OpenAI-compatible slots run a minimal chat-completions JSON ping; `memory_search`
  reports local wiki readiness without requiring embeddings.
- `GET /v1/model-catalog` returns the local model catalog and availability.

Callers should resolve `post_transcript`, `proactive`, and `chat` slots explicitly
instead of duplicating the legacy setting-key scan order.

## Proactive assistants

In desktop local daemon mode, proactive assistant model calls resolve
`GET /v1/provider-policy/resolve/proactive` and use the returned
OpenAI-compatible provider account/model. The slot defaults to `gpt-5.4-mini`,
but resolution is not actionable until the policy includes a provider account
for that slot. The desktop client must surface the daemon's resolution reason
instead of silently falling back to `chat_provider`, `ai_provider`, Omi-hosted
Gemini proxy URLs, or Omi-hosted chat completion proxies.

Screenshot-aware assistants resolve `GET /v1/provider-policy/resolve/vision`
separately. When that slot resolves to an allowed provider, the assistant may
send multimodal screenshot input to that provider. When the slot is missing or
unavailable, the desktop app uses local macOS OCR/Rewind text from the captured
screen and logs the OCR-only path. Local proactive memory/task/conversation
context comes from local daemon/Rewind SQLite data and FTS-backed local wiki
search; embedding provider readiness is not required.

## Post-transcript processing

Finalized transcript jobs resolve `/v1/provider-policy/resolve/post_transcript`
inside the daemon. When the slot resolves to an `openai_compatible` account, the
daemon asks that model for strict JSON containing:

- `title`
- `overview`
- `action_items`: array of `{ "title", "description" }`
- `memories`: array of `{ "content", "category" }`

Successful jobs persist title/overview on the conversation, replace prior
local-processing memories/action items for that conversation, and record
`local_processing` provenance metadata with the job ID, slot source, provider
account, and model ID. Malformed model JSON is treated as a provider failure, so
the durable job retry counter advances and eventually leaves an inspectable
failed job.

When the slot has no usable provider account, the daemon completes with
deterministic fallback title/overview, conversation status `processed_fallback`,
and job result metadata containing `mode: "fallback"` plus the slot resolution
reason.

Minimal local stub policy:

```bash
curl -fsS -X PUT http://127.0.0.1:8765/v1/provider-policy \
  -H 'content-type: application/json' \
  -d '{
    "version": 1,
    "provider_accounts": [{
      "id": "local-openai-compatible",
      "kind": "openai_compatible",
      "base_url": "http://127.0.0.1:11434/v1",
      "api_key": null,
      "display_name": "Local OpenAI-compatible",
      "capabilities": {
        "chat_completions": true,
        "json_mode": true,
        "tool_calls": false,
        "vision": false,
        "speech_to_text": false
      },
      "subscription_integration": null
    }],
    "model_slots": {
      "post_transcript": {
        "provider_account_id": "local-openai-compatible",
        "model_id": "gpt-5.4-mini",
        "options": { "json_mode": true, "tool_support": false }
      }
    }
  }'
```

After importing a transcript, inspect:

```bash
curl -fsS http://127.0.0.1:8765/v1/provider-policy/resolve/post_transcript
curl -fsS http://127.0.0.1:8765/v1/processing-jobs/status
curl -fsS http://127.0.0.1:8765/v1/conversations/<conversation-id>
```

## Settings keys

| Key | Purpose | `kind` values (v1) |
|-----|---------|-------------------|
| `ai_provider` | Post-transcript processing (title/overview JSON) | `openai_compatible` |
| `provider` | Legacy alias for `ai_provider` | same |
| `stt_provider` | Live speech-to-text (epic 02+) | `openai_compatible`, `deepgram_direct` (reserved) |
| `chat_provider` | Chat / agent completions (epic 04+) | `openai_compatible`, `anthropic_direct` (reserved) |
| `embedding_provider` | Vector embeddings (epic 01+) | `openai_compatible`, `gemini_direct` (reserved) |
| `vision_provider` | Multimodal / screenshot models (epic 05+) | `openai_compatible`, `gemini_direct` (reserved) |

Set a key to JSON `null` to clear it.

Legacy mapping:

| Legacy key | Typed slot |
|------------|------------|
| `ai_provider` | `post_transcript` |
| `provider` | `post_transcript` fallback alias |
| `chat_provider` | `chat` |
| `vision_provider` | `vision` |
| `stt_provider` | `stt` |
| `embedding_provider` | accepted as legacy data only; not required for this profile |

## OpenAI-compatible object shape

```json
{
  "kind": "openai_compatible",
  "base_url": "http://127.0.0.1:11434/v1",
  "model": "local-model",
  "api_key": "optional-for-ollama"
}
```

## Host policy

`base_url` must be `http` or `https`. Hosts matching Omi cloud, Firebase, and Google
identity/Firestore endpoints are **denied** (see `is_denied_provider_host` in
`src/providers.rs`).

Loopback providers (`localhost`, `127.0.0.1`, `::1`) may omit an API key. Non-loopback
providers must include `api_key` or an explicit `subscription_integration` value.
Direct vendor APIs (OpenAI, Anthropic, Deepgram, etc.) are allowed when configured this
way.

## Optional cloud tiers (desktop only)

Environment flags (desktop process, not daemon):

- `OMI_HYBRID_DIRECT_STT_ENABLED=1` — enables hybrid live transcription via Apple Speech in local daemon mode (also enabled by default when `desktop/run.sh` configures local mode; launcher writes this into bundled `.env` so GUI launches see it).
- `OMI_HYBRID_DIRECT_CHAT_ENABLED=1` — enables hybrid OpenAI-compatible chat (`HybridChatClient`) when the daemon `chat` slot resolves to a provider account; sessions/messages persist via daemon SQLite (`run.sh` defaults this on in local mode).
- `OMI_HYBRID_OPTIONAL_CLOUD_STT=1` — exposes `optionalCloudSTT` capability
- `OMI_HYBRID_OPTIONAL_CLOUD_CHAT=1` — exposes `optionalCloudChat` capability

Default hybrid optional tiers: both cloud toggles off. `run.sh` local mode defaults direct STT/chat capability env flags on for GUI launches and keeps direct embeddings off; this local profile uses local wiki/FTS memory search. Hosted Listen and pi-mono remain disabled without explicit optional-cloud flags / cloud backends.

## Local dev defaults (seed)

When the daemon starts via `make serve-local` or `desktop/run.sh` in local mode,
`desktop/local-backend/tools/seed_hybrid_defaults.sh` runs idempotently:

- The typed `provider_policy` is the source of truth once it exists. Legacy
  `ai_provider` / `chat_provider` settings are bridged only before a typed policy
  has been created.
- The seed script removes synthetic `legacy-*` accounts from the policy it writes,
  so compatibility bridge output is not permanently materialized.
- If the default local OpenAI-compatible endpoint is reachable, and
  `post_transcript`, `proactive`, or `chat` lacks a provider account, the script
  creates/reuses a local OpenAI-compatible account and points those slots at it.
- If the default endpoint is unavailable, the script leaves unconfigured slots
  without provider accounts so post-transcript processing can use deterministic
  fallback output instead of failing against a dead local model server.
- `memory_search` remains `local_wiki`.

| Variable | Default |
|----------|---------|
| `OMI_HYBRID_DEFAULT_CHAT_BASE_URL` | `http://127.0.0.1:11434/v1` |
| `OMI_HYBRID_DEFAULT_CHAT_MODEL` | `gpt-5.4-mini` |
| `OMI_HYBRID_DEFAULT_PROVIDER_ACCOUNT_ID` | `local-openai-compatible` |

The desktop app also calls `HybridProviderBootstrap.ensureDefaultsIfNeeded()` on
local guest session startup. Ask Omi resolves
`GET /v1/provider-policy/resolve/chat` before each local direct chat request and
uses the returned provider account/model. Legacy `chat_provider` rows are only
read by the daemon compatibility bridge when constructing the typed policy.

Configure or override in **Settings → Plan and Usage** (local mode). The app writes
`/v1/provider-policy` so users can inspect one provider account and slot model
choices without hand-editing JSON. Advanced callers may still use `PUT
/v1/provider-policy` directly.

## ChatGPT / Codex subscription (desktop)

When the user connects **ChatGPT plan** in Settings → Advanced:

- A loopback proxy (`desktop/codex-proxy`, default `http://127.0.0.1:10531/v1`) uses `~/.codex/auth.json` from Codex CLI login.
- Daemon `chat_provider` and `ai_provider` are set to that URL (not `embedding_provider`).
- Memory search readiness uses **local wiki + FTS5** for this profile, not vector
  embeddings.
- Deepgram / live transcription behavior is unchanged.

Build proxy: `cd desktop/codex-proxy && cargo build --release`

## Test connection

`POST /v1/provider-policy/test-slot/{slot}` validates the active slot path and is
the preferred readiness check for Settings UI. Example:

```bash
curl -fsS -X POST http://127.0.0.1:8765/v1/provider-policy/test-slot/chat \
  -H 'content-type: application/json' \
  -d '{}'
```

`POST /v1/settings/test-provider` with body `{ "key": "ai_provider" }` remains as
a legacy helper for raw setting-key providers. New UI should read and write
policy through `/v1/provider-policy`, use `/v1/provider-policy/resolve/{slot}`
before task-specific calls, and use `/v1/provider-policy/test-slot/{slot}` for
actionable readiness.
