# Context for Claude

A menu-bar-only macOS app that keeps Claude caught up on what you see and say.

It captures the two ambient streams Omi already captures — audio (your mic, plus the other side of
your calls) and screen (active window and its text) — transcribes the audio via **Omi cloud ASR**
(`/v4/listen`), runs **on-device Parakeet in parallel on Apple Silicon only**, uploads finished
conversations to your Omi account, and serves all of it to Claude over MCP.

The point: you stop explaining context to Claude. It asks Context for Claude instead.

> Standalone. It is not part of the Omi desktop app, shares no code or data with it, and is not
> meant to be merged.

## What you need

- macOS 14.4 or later
- Apple Silicon **or** Intel (Intel uses cloud transcription only — a signed-in Omi account and
  network are required for transcripts; offline/airgap is unsupported on Intel)
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

`scripts/build.sh` builds for the **host architecture** (no arm64-only triple). For Intel QA, build
on an Intel Mac (or ship a universal/lipo’d release artifact).

Then follow onboarding. It is one click: sign in to Omi, grant microphone, call audio and screen,
and it registers itself with Claude Code and Claude Desktop and starts at login. On Apple Silicon,
onboarding may also warm the on-device Parakeet model (~600 MB); Intel skips that step.

**Restart Claude Code and Claude Desktop afterwards** — both read their MCP config at startup, so a
session that was already open will not see Context for Claude until it is relaunched.

### Why signing matters

`build.sh` refuses to ad-hoc sign. An ad-hoc signature changes on every build, so macOS treats each
build as a different app and revokes Screen Recording and microphone consent every time — for every
Omi app on the machine. A stable identity is the only reason the grants stick.

The same fact is why shipping an update is not routine: an update replaces the signed bundle, so a
release signed with a different certificate than the one before it revokes every user's permissions
at once, silently. See [`docs/releasing.md`](docs/releasing.md).

## Updates

Installed copies update themselves with [Sparkle](https://sparkle-project.org) — the same mechanism
`desktop/macos` uses, with none of its identity. Its own feed ([`appcast.xml`](appcast.xml), served
straight from this repository), its own EdDSA key, its own bundle. An update prompt shows this app's
name, icon and release notes, and never Omi's.

The build you make locally does **not** update itself, and that is enforced rather than assumed:
`UpdatePolicy` refuses to update any bundle whose signature carries no Team ID, which is every
locally signed build. Otherwise a developer's copy would quietly replace itself with the shipping one
and lose its capture permissions doing it.

Airgap Mode covers the update check like every other remote client (`NetworkEgress.Client`).

Cutting a release — including generating the update key, which has not been done yet — is
[`docs/releasing.md`](docs/releasing.md).

## What Claude gets

Seven tools. The descriptions are written for Claude, so it reaches for them unprompted.

| tool | answers |
|---|---|
| `recall` | "What do I know about X?" — searches live local capture **and** your Omi history |
| `recent` | "What's going on right now?" — the last N minutes, local, no backend lag |
| `conversations` | Recent conversations with time, duration, app and preview |
| `transcript` | One conversation in full (Omi: named speakers; local capture: me/them by mic vs system) |
| `screen` | What was on screen: window titles and their text |
| `activity` | The shape of a day — contiguous blocks per app |
| `status` | Capture health and coverage windows, for both halves |

`status` is the one that makes the rest trustworthy: it reports exactly what window of time was
recorded, so Claude can tell "that never happened" apart from "that was never captured". On Intel,
when cloud ASR is unavailable, `status` and the menu bar say so explicitly rather than inventing
coverage.

Local hits are literal full-text matches. Omi's are a **semantic** search with no relevance floor —
it returns nearest neighbours even when nothing matches — so those are counted separately, labelled
as related rather than matching, and carry a caveat telling Claude to treat them as leads.

## How it is put together

```
Context for Claude.app                        context-for-claude-mcp
  mic ─┐                             (stdio, spawned by Claude)
  sys ─┼→ AudioMixer ─→ /v4/listen ─┐
       │                 (cloud ASR) │
       └→ Parakeet* ────────────────┼→ context.db (SQLite, WAL, FTS5) ←┘ read-only
  screen → Vision OCR ──────────────┘         │
                                              └→ Omi account (from-segments + screen-activity)

  * Apple Silicon only — runs in parallel with cloud ASR (local resilience). Never loaded on Intel.
```

Two processes, one database, no IPC. The MCP server is spawned per Claude session, holds no
permissions, and works whether or not the app is running. A heartbeat file carries live capture
state across.

Capture is ported from `desktop/macos` rather than reinvented, keeping the details that are
invisible until they bite: a CoreAudio IOProc on the default input device (not `AVAudioEngine`,
whose implicit aggregate device degrades Bluetooth A2DP), CoreAudio process taps with drift
compensation for system audio, and (on Silicon) a fresh `TdtDecoderState` per window so the
transducer does not loop.

Cloud transcription mixes mic + system on one socket so the backend can diarize and match the
user's speech profile. Local Parakeet (Silicon) runs in parallel and approximates attribution as
"mic is you, system is everyone else" — not full multi-speaker diarization.

Conversations upload through `POST /v1/conversations/from-segments` (retryable queue; cloud
`/v4/listen` already handles live ASR). `source: "phone"` gets memories extracted immediately
where `source: "desktop"` defers them and opts into a trial paywall.

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
