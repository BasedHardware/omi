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
- `GET /v1/model-catalog` returns the local model catalog and availability.

Callers should resolve `post_transcript`, `proactive`, and `chat` slots explicitly
instead of duplicating the legacy setting-key scan order.

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
- `OMI_HYBRID_DIRECT_CHAT_ENABLED=1` — enables hybrid OpenAI-compatible chat (`HybridChatClient`) when combined with `chat_provider`; sessions/messages persist via daemon SQLite (`run.sh` defaults this on in local mode).
- `OMI_HYBRID_OPTIONAL_CLOUD_STT=1` — exposes `optionalCloudSTT` capability
- `OMI_HYBRID_OPTIONAL_CLOUD_CHAT=1` — exposes `optionalCloudChat` capability

Default hybrid optional tiers: both cloud toggles off. `run.sh` local mode defaults direct STT/embeddings/chat capability env flags on for GUI launches; hosted Listen and pi-mono remain disabled without explicit optional-cloud flags / cloud backends.

## Local dev defaults (seed)

When the daemon starts via `make serve-local` or `desktop/run.sh` in local mode,
`desktop/local-backend/tools/seed_hybrid_defaults.sh` runs idempotently:

- If `post_transcript`, `proactive`, or `chat` lacks a provider account, the script
  creates/reuses a local OpenAI-compatible account and points those slots at it.
- `memory_search` remains `local_wiki`.

| Variable | Default |
|----------|---------|
| `OMI_HYBRID_DEFAULT_CHAT_BASE_URL` | `http://127.0.0.1:11434/v1` |
| `OMI_HYBRID_DEFAULT_CHAT_MODEL` | `gpt-5.4-mini` |
| `OMI_HYBRID_DEFAULT_PROVIDER_ACCOUNT_ID` | `local-openai-compatible` |

The desktop app also calls `HybridProviderBootstrap.ensureDefaultsIfNeeded()` on
local guest session startup. Chat resolves `chat_provider` → `ai_provider` → BYOK OpenAI
(see `HybridChatClient`).

Configure or override in **Settings → Plan and Usage** (local mode) or via `PUT /v1/settings`.

## ChatGPT / Codex subscription (desktop)

When the user connects **ChatGPT plan** in Settings → Advanced:

- A loopback proxy (`desktop/codex-proxy`, default `http://127.0.0.1:10531/v1`) uses `~/.codex/auth.json` from Codex CLI login.
- Daemon `chat_provider` and `ai_provider` are set to that URL (not `embedding_provider`).
- Memory search uses **local wiki + FTS5** instead of vector embeddings unless `OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED=1`.
- Deepgram / live transcription behavior is unchanged.

Build proxy: `cd desktop/codex-proxy && cargo build --release`

## Test connection

`POST /v1/settings/test-provider` with body `{ "key": "ai_provider" }` runs a minimal
request against a legacy configured provider (chat completions ping for
`openai_compatible`). New UI should read and write policy through `/v1/provider-policy`
and use `/v1/provider-policy/resolve/{slot}` before making task-specific calls.
