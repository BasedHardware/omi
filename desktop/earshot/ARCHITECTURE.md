# Earshot — architecture

A menu-bar-only macOS app that captures ambient audio and screen context, stores it locally, and
serves it to Claude over MCP. Standalone: it shares no code, no data, and no process with the Omi
desktop app in `desktop/macos/`.

## Why it is shaped this way

The product is one sentence — *Claude should already know what you have seen and said* — and every
structural decision follows from it:

- **Two processes, one database.** The app captures; a tiny `earshot-mcp` binary answers Claude's
  questions. They never talk to each other. Claude spawns the MCP server per session, so it must
  work whether or not the app happens to be running; a shared SQLite file in WAL mode is the whole
  IPC mechanism, and a heartbeat JSON file carries live capture state.
- **No summarization layer.** Claude is the intelligence. Adding an LLM here would mean choosing what
  matters before knowing the question, which is exactly the mistake that makes ambient tools feel
  lossy.
- **Capture is ported, not reinvented.** The mic, system-audio and screen paths are lifted from the
  Omi desktop app because they encode years of real-world corrections (Bluetooth A2DP, tap drift
  compensation, transducer decoder state) that are invisible until they bite.

## Targets

| Target | Kind | Depends on | Contains |
|---|---|---|---|
| `EarshotCore` | library | GRDB | Storage, queries, and every pure policy. No AppKit, no AVFoundation — it has to link into the MCP binary. |
| `EarshotMCPKit` | library | EarshotCore | JSON-RPC framing, the seven tools, MCP handshake. |
| `EarshotMCP` | executable | EarshotMCPKit | `main.swift`. Opens the store read-only, pumps stdio. |
| `EarshotApp` | executable | EarshotCore, FluidAudio | Capture, transcription, menu bar, onboarding, Claude registration. |

The library/executable split exists so the protocol layer is testable without a bundle and so the
MCP binary stays free of every UI and capture dependency — it must start in milliseconds and hold no
permissions.

## Data flow

```
MicCapture ────────→ Transcriber(mic)    ──┐
  CoreAudio IOProc     FluidAudio Parakeet │
                                           ├──→ Engine ──→ EarshotStore ──→ earshot.db
SystemAudioCapture ─→ Transcriber(system) ─┤    session      GRDB, WAL,
  CoreAudio tap        FluidAudio Parakeet │    boundaries   FTS5
                                           │
ScreenWatcher ──────→ Vision OCR ──────────┘
  ScreenCaptureKit
```

Audio flows as 16 kHz mono Int16 little-endian `Data` from capture to transcription — one format,
agreed once, so a source and a transcriber can be swapped independently.

Speaker attribution needs no diarization model: the mic is the user, the system tap is everyone
else. Two transcribers, never mixed.

`Engine` owns the only writer. Each source runs in its own task and fails independently — a dead mic
must not stop screen capture — and the reason surfaces in the menu bar *and* in the MCP `status`
tool, so Claude can report a gap instead of fabricating over it.

## Storage

`~/Library/Application Support/Earshot/`

```
earshot.db              sessions, segments, frames + two FTS5 indexes
Frames/YYYY-MM-DD/      screen JPEGs, pruned after 30 days
capture-state.json      heartbeat: capturing / paused reason / capabilities
```

A session is a contiguous run of speech; a gap over five minutes starts a new one
(`SessionPolicy`). Transcripts are kept forever; frames are the expensive part and are the only
thing pruned.

## The MCP surface

Seven tools — `recall`, `recent`, `conversations`, `transcript`, `screen`, `activity`, `status` —
returning Markdown rather than JSON, because Claude reads prose better than it reads a dump. Tool
descriptions are written to tell Claude *when to reach for them*; they are the product's real
interface and deserve more care than the code behind them.

`status` exists so that "I have no record of that" can be distinguished from "that never happened".

## Files

```
Sources/EarshotCore/     Models  Paths  Store  Queries  Policy  ClaudeConfig
Sources/EarshotMCPKit/   JSONRPC  MCPServer  Tools
Sources/EarshotMCP/      main
Sources/EarshotApp/      EarshotApp  Engine  Permissions
                         Capture/    AudioSource  MicCapture  SystemAudioCapture  ScreenWatcher
                         Transcribe/ Transcriber
                         MenuBar/    StatusView
                         Onboarding/ Ink  Backdrop  RandomizedText  OnboardingWindow  OnboardingView
                         Integration/ClaudeRegistrar  LoginItem
                         Support/    Log
```

`CONTRACTS.md` holds the interface each file must satisfy; `docs/earshot-design-system.md` holds the
exact visual values. Both are load-bearing — this package was built by many hands at once, and those
two documents are what made the pieces fit.

## Building

```
scripts/build.sh            # build, bundle, sign, install to /Applications/Earshot.app
scripts/build.sh --run      # …and launch it
swift test --package-path desktop/earshot
```

Signed with the local `Omi Local Dev Signing` identity, never ad-hoc — ad-hoc signing resets Screen
Recording permission for every Omi app on the machine.
