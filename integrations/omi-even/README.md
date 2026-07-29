# omi on Even Realities G2

Connects [Omi](https://omi.me) to Even Realities G2 smart glasses across four surfaces.

```
G2 glasses ──BLE──> Even phone app ──┬── "Add Agent"  ──HTTPS──> tunnel ─┐
                                     │   (on-device speech-to-text)      │
                                     └── omi Hub plugin ──LAN/WS────────>┤
                                                                          v
                                                           ┌──────────────────────┐
                                                           │ bridge (Mac, FastAPI)│
                                                           │ holds Firebase session│
                                                           └──────────┬───────────┘
                                        ┌─────────────────────────────┼──────────────────┐
                                        v                             v                  v
                               POST /v2/messages          WS /v4/listen      POST /v2/voice-
                               (chat, streamed)           (capture)          message/transcribe
```

| Surface | What it does |
|---|---|
| **Even AI answers from Omi** | Hold the temple, ask a question, Even's own assistant answers from your Omi memory. No app to open — the glasses do speech-to-text themselves. |
| **`omi` Hub app** | An app named `omi` on the glasses: chat, memories, action items, today. |
| **G2 mics feed Omi** | Glasses audio becomes real Omi conversations, like the pendant. |
| **Omi pushes to glasses** | New action items surface on the display while the app is running. |

Everything runs through **one local bridge**, because Omi's chat endpoint and capture
socket both accept only a Firebase ID token — no API key family works
(`backend/utils/other/endpoints.py:81`). Keeping one process means one credential.

## Run it

```bash
cd bridge && ./run.sh
```

Prints the URL and token to paste into the Even app under **Add Agent**, plus the
`ws://` address for the Hub app. `OMI_SKIP_TUNNEL=1` skips the tunnel (LAN only).

No login prompt: the bridge reuses the session the Omi macOS app already holds,
via the repo's own `desktop/macos/scripts/omi-auth-dump.sh`, and mints fresh ID
tokens from its refresh token. Sign into the desktop app once and it stays working.

## Verified against live Omi

Not mocks — real account (`Operator` plan), real memories:

| Check | Result |
|---|---|
| Firebase session from desktop app, no browser login | ID token minted, `/v1/users/me/usage-quota` → 200 |
| Chat with memory grounding | 9.3s, correct answer about actual current work |
| Even AI path through the public tunnel | 10.5s, 246-char answer that fits the display |
| Unauthorized request | 401 with and without a bad token |
| Capture → Omi conversation | `source: rayban_meta`, status `completed`, transcript + auto title |
| App WebSocket | memories, action items, streaming chat, graceful empty states |

## Things that will bite you

- **`source` must be `rayban_meta`.** `ConversationSource._missing_` maps any unknown
  string to `unknown` rather than raising, so a typo silently mislabels every
  conversation instead of failing. It is also photo-capable, so
  `resolve_photo_conversation_source` won't rewrite provenance later.
- **The chat stream is not SSE.** Frames are `\n\n`-*separated* with bare prefixes,
  newlines arrive as the literal `__CRLF__`, and `done:` is base64 JSON. `EventSource`
  drops most of it. Parser ported from `app/lib/backend/http/api/messages.dart:59`.
- **A quota breach returns HTTP 200**, not 402, with a canned `done:` message. Read the
  text, not the status.
- **Stopping capture needs trailing silence.** The STT endpointer only emits its final
  segment once the utterance ends. Measured: a 7.4s clip yielded 2.8s without it, the
  full text with it. `CaptureSession.stop()` handles this.
- **Disconnect does not finalize a conversation** unless `source == 'desktop'` and the
  close code is 1000, so `stop()` calls `POST /v1/conversations` explicitly.
- **The listen socket closes after 90s of inbound silence**; the bridge sends keepalives.
- **The server's heartbeat is the literal text `ping`** — not JSON. Parsing it blindly
  throws every 10 seconds.
- **A quick tunnel gets a new URL on every restart**, so you'd re-register in the Even
  app each time. Use `cloudflared tunnel create omi-even` for a stable one.

## Limits worth knowing

- **No speaker on the G2.** Answers are read, never spoken — Omi's TTS endpoint is
  useless here. Everything is shaped to ~380 characters of monochrome text.
- **Push only reaches a running app.** The Hub host keeps a backgrounded plugin alive in
  a headless WebView, but a closed app receives nothing. There is no OS notification path.
- **The Add Agent contract is undocumented.** Even publishes no spec; the implementation
  targets the observed request shape and logs every request to `add-agent-capture.log`
  so drift is visible.
- **Always-on capture records everyone nearby.** The app shows a recording indicator and
  has a hard off switch, but in two-party-consent jurisdictions this carries real legal
  exposure.

## Layout

```
bridge/
  server.py        FastAPI: Add Agent endpoint, /app socket, health, push loop
  omi_auth.py      Firebase session from the desktop app + token refresh
  omi_client.py    /v2/messages frame parser, transcribe, memories, action items
  capture.py       PCM relay to /v4/listen
  display.py       Markdown/URL/emoji stripping, truncation, pagination
  run.sh           Bring up bridge + tunnel, print Add Agent details
  tests/           Hermetic pytest suite
app/               The `omi` Hub plugin (Vite + TypeScript)
```

`integrations/evenhub-g2/` next door is the untouched quickstart app, kept as a
known-good reference and smoke test.
