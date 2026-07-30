# Context for Claude

A menu-bar-only macOS app that keeps Claude caught up on what you see and say.

It captures the two ambient streams Omi already captures — audio (your mic, plus the other side of
your calls) and screen (active window and its text). Speech is transcribed in the cloud via
`/v4/listen`; screen text is OCR'd on device. Finished transcript segments are stored locally and
uploaded to your Omi account, and all of it is served to Claude over MCP.

The point: you stop explaining context to Claude. It asks Context for Claude instead.

> Standalone. It is not part of the Omi desktop app, shares no code or data with it, and is not
> meant to be merged.

## What you need

- macOS 14.4 or later (Apple silicon)
- Xcode 26 / Swift 6.2
- An Omi account
- A code-signing certificate. Any self-signed one works; `scripts/build.sh` tells you how to make
  one in about thirty seconds if you have none.

## Build and run

```bash
cd desktop/context-for-claude
./scripts/build.sh --run
```

That builds both products, assembles `Context for Claude.app`, signs it, installs it to `/Applications`, and
prints the absolute path of the MCP binary. Flags: `--no-install`, `--clean`, `--run`.

Then follow onboarding. It is one click: sign in to Omi, grant microphone, call audio and screen,
and it registers itself with Claude Code and Claude Desktop and starts at login.

**Restart Claude Code and Claude Desktop afterwards** — both read their MCP config at startup, so a
session that was already open will not see Context for Claude until it is relaunched.

### Why signing matters

`build.sh` refuses to ad-hoc sign. An ad-hoc signature changes on every build, so macOS treats each
build as a different app and revokes Screen Recording and microphone consent every time — for every
Omi app on the machine. A stable identity is the only reason the grants stick.

## What Claude gets

Seven tools. The descriptions are written for Claude, so it reaches for them unprompted.

| tool | answers |
|---|---|
| `recall` | "What do I know about X?" — searches live local capture **and** your Omi history |
| `recent` | "What's going on right now?" — the last N minutes, local, no backend lag |
| `conversations` | Recent conversations with time, duration, app and preview |
| `transcript` | One conversation in full, speaker-attributed |
| `screen` | What was on screen: window titles and their text |
| `activity` | The shape of a day — contiguous blocks per app |
| `status` | Capture health and coverage windows, for both halves |

`status` is the one that makes the rest trustworthy: it reports exactly what window of time was
recorded, so Claude can tell "that never happened" apart from "that was never captured".

Local hits are literal full-text matches. Omi's are a **semantic** search with no relevance floor —
it returns nearest neighbours even when nothing matches — so those are counted separately, labelled
as related rather than matching, and carry a caveat telling Claude to treat them as leads.

## How it is put together

```
Context for Claude.app                     context-for-claude-mcp
  mic ─┐                          (stdio, spawned by Claude)
  sys ─┼→ /v4/listen (cloud STT) ─┐        │
 screen ┴→ Vision OCR + AX tree ──┼→ context.db (SQLite, WAL, FTS5) ←┘ read-only
                                  └→ Omi account (from-segments + screen-activity)
```

Two processes, one database, no IPC. The MCP server is spawned per Claude session, holds no
permissions, and works whether or not the app is running. A heartbeat file carries live capture
state across.

Capture is ported from `desktop/macos` rather than reinvented. Mic and system audio mix into one
PCM stream for `wss://api.omi.me/v4/listen`, which diarizes and matches enrolled speech profiles;
screen capture still runs Vision OCR (and an accessibility-tree pass) on device.

Speaker attribution comes from the backend: mic-vs-system heuristics are only a last resort when a
line has no diarization label.

Conversations still upload through `POST /v1/conversations/from-segments` for durable cloud storage
and (product-aware) enrichment; `/v4/listen` is the live transcription path, not the upload path.
Local FTS searches the Mac copy of those segments before account enrichment finishes.

Free Context for Claude meters STT as **wall-clock** minutes only while PCM audio is flowing to
`/v4/listen` (silence does not count) at **3000 min/mo**, in a product-scoped pool separate from
Omi Desktop. The desktop trial exemption applies to that STT path via the `X-App-Product` header,
not to every desktop API — screen-activity sync and other endpoints keep their own billing rules.
When the STT pool is exhausted, the server stops forwarding audio to STT and the app latches speech
capture off until next month.

Detail: `ARCHITECTURE.md`. The interface contracts every file was built against: `CONTRACTS.md`.
Exact visual values: `docs/design-system.md`.

## Windows portable-core host

The app remains macOS-only. `windows/` is a Windows-only CMake build that proves the portable C++
decision rules can be called through their C ABI, and builds the pinned swift-winrt generator
(`79ffa65c`) for future Windows API projection work. It does not add microphone, system-audio,
screen capture, OCR, storage, MCP, or the macOS UI to Windows. Prerequisites and the exact Windows
validation commands: `windows/README.md`.

## Tests

```bash
swift test        # 67 tests
```

Hermetic — no network, no live services. Note that `OmiKeyResolver` deliberately refuses to resolve
any credential while XCTest is loaded; without that the suite quietly picks up a developer's own key
and starts querying a real Omi account.

```bash
python3 scripts/eval.py   # answer quality, scored
```

`swift test` proves the code does what it was written to do. The eval asks the shipping
`context-for-claude-mcp` binary real questions over stdio against a seeded throwaway database, and
scores ten classes of answer — mostly honesty under adversarial conditions: no confabulation,
filter integrity, uncertainty marking, coverage-window honesty. It prints a per-class score, one
overall number, and a diff against the previous run, and exits non-zero on a regression. Run it
after every change that could move what a model reads. What each class measures and how to read a
regression: `docs/evals.md`.

## Known issues

- **Screen sync returns HTTP 500.** Omi's Rust desktop-backend fails to authenticate itself to
  Firestore (`Expected OAuth 2 access token`). Nothing to fix client-side; frames queue locally with
  the cursor held, and sync when the backend is fixed. Audio is unaffected.
- **Very short conversations are discarded** by the server. A single ten-second line will upload,
  return `completed`, and be dropped — that is Omi's behaviour, not a bug here.
- Uninstall with `scripts/uninstall.sh` (`--purge-data` to also remove the local database).
