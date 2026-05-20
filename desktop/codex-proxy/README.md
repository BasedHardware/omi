# omi-codex-proxy

Small **localhost-only** HTTP proxy that turns `POST /v1/chat/completions` (OpenAI-style JSON) into `POST https://chatgpt.com/backend-api/codex/responses`, using OAuth tokens stored in **`~/.codex/auth.json`**.

## Prerequisites

Rust toolchain (`cargo`). HTTPS uses **rustls** (no OpenSSL dependency).

Create `~/.codex/auth.json` (minimal fields):

```json
{
  "access_token": "<ChatGPT bearer token>",
  "account_id": "<ChatGPT account id>",
  "refresh_token": "<optional refresh token>"
}
```

## Run

```bash
cd desktop/codex-proxy
# Optional: defaults to 10531 when unset
export OMI_CODEX_PROXY_PORT=10531
cargo run --release
```

## Endpoints

- `GET /health` → `200 OK` (`ok`).
- `POST /v1/chat/completions` → upstream Codex `responses`; **non-stream only** (`"stream": true` returns `501`).

Forwarded headers:

- `Authorization: Bearer <access_token>`
- `ChatGPT-Account-Id: <account_id>`
- `Content-Type: application/json`

On **`401`** from Codex (and if `refresh_token` is present), the proxy refreshes via `POST https://auth.openai.com/oauth/token` (`client_id=app_EMoamEEZ73f0CkXaXp7hrann`, `grant_type=refresh_token`), persists updated tokens back to `auth.json`, and retries once.

## Request / response mapping (basic)

**OpenAI → Codex**

- Copies `model` and maps OpenAI chat `messages` into a Codex Responses-style `input`:
  - String `content` becomes `[{ "type": "input_text", "text": "..." }]`.
  - Array `content` is passed through.

**Codex → OpenAI**

Parses common Responses payloads: **`output[].content[]`**, looking for **`output_text` / `text`** (or string `content`). If the upstream body already resembles `choices`, it is echoed.

If your Codex revision uses a slightly different envelope, extend `extract_assistant_text` / `codex_payload_from_openai_chat` in `src/main.rs`.

## Example curl

```bash
curl -sS http://127.0.0.1:${OMI_CODEX_PROXY_PORT:-10531}/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-5","messages":[{"role":"user","content":"Say hi in one word."}]}'
```
