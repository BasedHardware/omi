# Hybrid provider settings (ADR)

## Context

Desktop hybrid mode (`OMI_DESKTOP_BACKEND_MODE=local`) stores provider credentials in the
local daemon SQLite `settings` table. Requests go **directly** to configured endpoints,
never through Omi Python/Rust proxies.

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

Loopback and direct vendor APIs (OpenAI, Anthropic, Deepgram, etc.) are allowed.

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

- If `ai_provider` / `provider` is unset → sets OpenAI-compatible defaults.
- If `chat_provider` is unset → sets the same defaults.

| Variable | Default |
|----------|---------|
| `OMI_HYBRID_DEFAULT_CHAT_BASE_URL` | `http://127.0.0.1:11434/v1` |
| `OMI_HYBRID_DEFAULT_CHAT_MODEL` | `llama3.2` |

The desktop app also calls `HybridProviderBootstrap.ensureDefaultsIfNeeded()` on
local guest session startup. Chat resolves `chat_provider` → `ai_provider` → BYOK OpenAI
(see `HybridChatClient`).

Configure or override in **Settings → Plan and Usage** (local mode) or via `PUT /v1/settings`.

## Test connection

`POST /v1/settings/test-provider` with body `{ "key": "ai_provider" }` runs a minimal
request against the configured provider (chat completions ping for `openai_compatible`).
