# Context for Claude — design

**Status:** approved to build (2026-07-28)
**Location:** `desktop/context-for-claude/` on branch `feat/ambient-context`. Standalone app. **Not** merged into
the Omi macOS app, not a new repo, no PR.

## What it is

A menu-bar-only macOS app that captures the same two ambient streams Omi already captures — audio
(your mic + the other side of your calls) and screen (active window + OCR) — stores them locally, and
serves them to Claude over MCP. Claude gets continuous ambient context about your life without you
pasting anything.

Success looks like: you type a request into Claude that references people, plans, and decisions you
never told Claude about, and it just knows — because it queried Context for Claude.

## What it is not

No tabs. No main window. No chat. No accounts, no sign-in, no backend, no cloud. No summarization
layer — Claude is the intelligence; this is the sensor and the memory. Nothing leaves the machine
except what Claude explicitly asks for.

## Scope for v1

In: microphone audio, system/call audio, screen capture + OCR, local transcription, local storage,
MCP server, menu bar, onboarding, launch at login.

Out (deliberately, revisit only after v1 is loved): iMessage/WhatsApp ingestion, Gmail, Calendar,
Contacts — Claude already has connectors for mail and calendar, and screen OCR already catches chat
apps when they are on screen.

## Architecture

Three units, one SQLite file between them.

```
 ┌─────────────────────── Context for Claude.app (LSUIElement, no dock) ────────────────────┐
 │  MicCapture ──────┐                                                           │
 │  (CoreAudio       ├─→ Transcriber(mic)     ──┐                                │
 │   IOProc)         │   (FluidAudio Parakeet)  │                                │
 │                   │                          ├─→ ContextStore ──→ context.db  │
 │  SystemAudio ─────┤─→ Transcriber(system)  ──┤    (GRDB, WAL,                 │
 │  (CoreAudio       │   (FluidAudio Parakeet)  │     FTS5)                      │
 │   process tap)    │                          │                                │
 │                   │                          │                                │
 │  ScreenWatcher ───┴─→ Vision OCR ────────────┘                                │
 │  (ScreenCaptureKit, active window, 3 s)                                       │
 └───────────────────────────────────────────────────────────────────────────────┘
                                    │ reads (read-only, WAL)
                                    ▼
                        ambient-mcp (stdio JSON-RPC)
                                    │
                    ┌───────────────┴───────────────┐
              Claude Code                     Claude Desktop
            (~/.claude.json)         (claude_desktop_config.json)
```

`ambient-mcp` ships inside the app bundle at `Contents/MacOS/ambient-mcp` and is registered by
absolute path in both Claude configs during onboarding. It never captures anything and needs no
permissions — it only reads the database. One permission grant, two Claude surfaces.

### Capture — same as Omi, deliberately

The user's requirement is that capture behaves exactly as Omi's already does, so we port Omi's
proven approach rather than inventing one:

- **Mic:** raw CoreAudio `AudioDeviceCreateIOProcIDWithBlock` on the default input device — *not*
  `AVAudioEngine`, whose implicit aggregate device degrades Bluetooth A2DP. Downmix to mono,
  `AVAudioConverter` to 16 kHz, emit Int16 LE.
- **System/call audio:** CoreAudio process taps (macOS 14.4+): `CATapDescription(stereoGlobalTapButExcludeProcesses:)`
  → private aggregate device. `kAudioSubTapDriftCompensationKey = 1` is mandatory; without it all
  system audio crackles.
- **Transcription:** FluidAudio (Parakeet TDT 0.6B CoreML, on the ANE), fully on-device. 10 s
  windows, a **fresh `TdtDecoderState` per window** (persisting it makes the transducer loop), RMS
  floor to skip silence, drop windows with no letters or digits.
- **Speaker attribution without diarization:** two independent transcribers. Mic ⇒ `me`,
  system ⇒ `them`. Cheap, correct, no model.
- **Screen:** ScreenCaptureKit capture of the *active window* every 3 s, Vision `VNRecognizeTextRequest`
  for OCR, dHash dedupe so an idle screen costs nothing. App name and window title recorded with
  every frame.

### Storage

`~/Library/Application Support/Context for Claude/context.db`, GRDB, WAL, FTS5.

```sql
sessions(id, startedAt, endedAt, appHint)
segments(id, sessionId, startedAt, endedAt, source, speaker, text)   -- source: mic|system, speaker: me|them
frames(id, capturedAt, appName, windowTitle, ocrText, imagePath)
segments_fts(text)          -- FTS5, contentless-synced by trigger
frames_fts(ocrText, windowTitle, appName)
```

A session is a contiguous run of speech; a gap longer than 5 minutes starts a new one. `appHint`
records the frontmost app when the session opened, which is how a Zoom or Meet session becomes
identifiable as a meeting without any meeting-detection logic.

Retention: frames older than 30 days and their JPEGs are pruned on launch. Transcripts are kept.

### MCP surface

Seven tools, each answering one question a person would actually ask. Descriptions are written for
Claude, so Claude reaches for them unprompted.

| Tool | Answers |
|---|---|
| `recall(query, since?, until?, limit?)` | "What do I know about X?" — FTS across speech **and** screen text, merged, newest-first, each hit dated and attributed |
| `recent(minutes?)` | "What's going on right now?" — merged transcript + screen for the last N minutes |
| `conversations(since?, until?, limit?)` | "What conversations have I had?" — sessions with time, duration, app context, preview |
| `transcript(session_id)` | Full transcript of one conversation, speaker-attributed |
| `screen(since?, until?, app?, limit?)` | "What was I looking at?" — window titles + OCR |
| `activity(since, until)` | Condensed app-usage blocks — the shape of a day |
| `status()` | Capture health, permissions, coverage window. Lets Claude say "I only have data from 2pm" instead of guessing |

Every timestamp is returned as both epoch and a human-readable local string, because Claude reasons
about "last Tuesday" far better than about `1753660800`.

### UI — two surfaces, that's all

**Menu bar** (`MenuBarExtra`, `LSUIElement`): the 8-dot Omi mark, faintly animated while capturing.
Click gives a small popover: one status line, three permission rows with live state, a pause toggle,
which Claude surfaces are connected, and Quit. No tabs, no settings page, no lists.

**Onboarding**, four steps, in the omi-v4 idiom — dark, warm, borderless, one thought per screen:

1. **Intro** — Literata 46 pt, −2.07 tracking, cream `#FFFCEC`, word-by-word reveal.
   *"Hi, I'm Omi. I sit quietly in the background and give **Claude** everything you've *seen and said*—so it stops asking, and just **knows.**"* → `Hi Omi!`
2. **First…** — three first-person permission rows, 5 %-white on rounded-16, 20 pt checkbox, live
   status word on the right. No continue button; it advances itself the moment all three land.
   - *"I would like to use your microphone, so I can hear what you talk about."*
   - *"I would like to hear your calls, so I catch the other side too."*
   - *"I would like to see your screen, so I know what you're working on."*
3. **Connect** — *"Now I'll introduce myself to Claude."* Writes the MCP entry into Claude Code and
   Claude Desktop, shows what it did. → `Continue`
4. **Done** — *"I'm listening."* / *"I live up here."* with a cue toward the menu bar, then the
   window dissolves into a full-screen edge glow.

Visual system carried over verbatim from omi-v4: nine blurred `24σ` color blobs just outside the
frame under an oval radial alpha mask that rises over 1.8 s and drifts on a 14 s loop while working;
`NSVisualEffectView(.hudWindow, .behindWindow)` behind a borderless floating window on `#171716`;
Literata headlines, Inter everywhere else; cream stadium buttons, 56 pt tall, 32 pt horizontal
padding, ink label. Reduce Motion is honoured throughout.

### Launch at login

`SMAppService.mainApp.register()` during onboarding step 4. Always-on is the point.

## Failure behaviour

Nothing about this app is allowed to be load-bearing on a good day and silent on a bad one.

- Any capture source can fail independently. Mic dying does not stop screen; the system tap dying
  does not stop the mic. Each failure sets a reason string that shows in the popover *and* is
  returned by `status()`, so Claude can report the gap rather than fabricate over it.
- Silent-mic watchdog: 1 s peak windows; sustained silence on a live device rebuilds the CoreAudio
  stack (Bluetooth SCO/A2DP switches are the usual cause).
- Screen Recording and system-audio consent survive only if the bundle signature is stable — the app
  is signed with the existing `Omi Local Dev Signing` identity, never ad-hoc, because ad-hoc signing
  resets Screen Recording for every Omi app on the machine.
- The MCP server opens the database read-only and never blocks the writer; if the database is
  missing it returns an explicit "not capturing yet" rather than an error.

## Testing

- `ContextCoreTests` — schema migration, FTS round-trip, session gap segmentation, retention prune,
  every `Queries` function against a seeded fixture database.
- `ContextAppTests` — audio format conversion (stereo→mono→16 kHz→Int16), transcriber window
  boundaries and silence rejection, session-gap policy, permission state machine, and
  `ClaudeRegistrar` writing/merging both config shapes without clobbering existing servers.
- `ContextMCPKitTests` — JSON-RPC framing, `initialize`/`tools/list`/`tools/call` handshake, each tool's
  schema and output against the fixture database.
- End-to-end, by hand, on the real machine: build, sign, install, grant, speak, look at something,
  then ask Claude a question that can only be answered from ambient context.

## Non-goals

No merging upstream. No cloud sync. No summarization. No second window. No purple, anywhere.
