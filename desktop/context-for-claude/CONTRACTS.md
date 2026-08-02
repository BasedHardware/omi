# Context for Claude — build contracts

Every agent building a piece of this package codes against this file. It is the only coordination
mechanism: stay inside your assigned files, implement the signatures below exactly, and the pieces
will link.

## Ground rules

1. **Only touch the files assigned to you.** Another agent owns every other file. Do not create
   files outside your assignment, do not edit `Package.swift`, `Models.swift`, `Paths.swift`, or
   this document.
2. **Do not run `swift build`.** The package does not compile until every agent has landed; a build
   attempt only produces misleading errors and fights other agents for the SPM lock. Integration and
   the build-fix loop happen centrally afterwards.
3. Swift language mode is **v5** (not strict-concurrency v6). Platform floor is **macOS 14.4**.
   Target the SDK in Xcode 26.2 / Swift 6.2.
4. Style: match the surrounding Omi desktop code. Comments explain *why*, never *what*. No purple in
   any UI, ever (`INV-UI-1`).
5. Log via `ContextLog.info/error(...)` (owned by the support agent). Never `print()` in
   `ContextApp`; **never write anything to stdout in `ContextMCP`** except JSON-RPC frames — stdout
   is the protocol channel there, so diagnostics go to stderr only.

## Already written — read, do not edit

- `Sources/ContextCore/Models.swift` — `Session`, `SegmentSource`, `Segment`, `Frame`, `Hit`,
  `SessionSummary`, `ActivityBlock`, `CapabilityReport`, `StatusInfo`, `ContextTime`.
- `Sources/ContextCore/Paths.swift` — `ContextPaths`, `CaptureState`.
- `Package.swift` — targets `ContextCore`, `ContextMCPKit`, `ContextMCP`, `ContextApp`, and two test
  targets.

## Target boundaries

| Target | May import | Purpose |
|---|---|---|
| `ContextCore` | Foundation, GRDB | Storage, queries, and pure policy. **No AppKit, no SwiftUI, no AVFoundation** — it has to link into the MCP binary. |
| `ContextMCPKit` | Foundation, ContextCore | JSON-RPC + tool dispatch. No UI, no capture. |
| `ContextMCP` | ContextMCPKit | `main.swift` only: wire stdin/stdout to `MCPServer`. |
| `ContextApp` | everything | The app: capture, transcription, UI, integration. |

---

## ContextCore

### `Sources/ContextCore/Store.swift` — owner: **store agent**

```swift
public final class ContextStore: @unchecked Sendable {
    /// Opens (creating if needed) the database at `url` and runs migrations.
    /// `readOnly` opens a WAL reader that never blocks the writer — this is what `context-for-claude-mcp` uses.
    public init(url: URL = ContextPaths.databaseURL, readOnly: Bool = false) throws

    public func read<T>(_ body: (Database) throws -> T) throws -> T
    public func write<T>(_ body: (Database) throws -> T) throws -> T   // throws if readOnly

    // Writes
    public func openSession(at: Double, appHint: String?) throws -> Int64
    public func closeSession(_ id: Int64, at: Double) throws
    public func insertSegment(_ segment: Segment) throws -> Int64
    public func insertFrame(_ frame: Frame) throws -> Int64

    /// Deletes frames (and their JPEGs) older than `days`. Transcripts are never pruned.
    @discardableResult
    public func pruneFrames(olderThanDays days: Int) throws -> Int
}

public enum ContextStoreError: Error { case readOnly, notInitialized }
```

Schema, created by GRDB `DatabaseMigrator` migration `"v1"`:

```sql
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  startedAt DOUBLE NOT NULL, endedAt DOUBLE, appHint TEXT);
CREATE INDEX idx_sessions_startedAt ON sessions(startedAt);

CREATE TABLE segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sessionId INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  startedAt DOUBLE NOT NULL, endedAt DOUBLE NOT NULL,
  source TEXT NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL,
  confidence DOUBLE, speakerLabel TEXT, personId TEXT);
CREATE INDEX idx_segments_startedAt ON segments(startedAt);
CREATE INDEX idx_segments_sessionId ON segments(sessionId, startedAt);

CREATE TABLE frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  capturedAt DOUBLE NOT NULL, appName TEXT, windowTitle TEXT, ocrText TEXT, imagePath TEXT);
CREATE INDEX idx_frames_capturedAt ON frames(capturedAt);
CREATE INDEX idx_frames_app ON frames(appName, capturedAt);
```

Plus FTS5 external-content tables `segments_fts(text)` and `frames_fts(ocrText, windowTitle, appName)`
with `content=` pointing at the base tables and the three standard sync triggers each
(`ai`, `ad`, `au`). Use `tokenize='porter unicode61'`.

PRAGMAs on open: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`.

`readOnly` mode must not attempt migrations and must not fail when the file does not exist —
throw `ContextStoreError.notInitialized` so callers can report "not capturing yet".

### `Sources/ContextCore/Queries.swift` — owner: **queries agent**

```swift
public enum Queries {
    public static func recall(_ store: ContextStore, query: String, since: Double? = nil,
                              until: Double? = nil, limit: Int = 40) throws -> [Hit]
    public static func recent(_ store: ContextStore, minutes: Int = 30, limit: Int = 120) throws -> [Hit]
    public static func sessions(_ store: ContextStore, since: Double? = nil, until: Double? = nil,
                                limit: Int = 30) throws -> [SessionSummary]
    public static func transcript(_ store: ContextStore, sessionId: Int64) throws -> [Hit]
    public static func screen(_ store: ContextStore, since: Double? = nil, until: Double? = nil,
                              app: String? = nil, limit: Int = 60) throws -> [Hit]
    public static func activity(_ store: ContextStore, since: Double, until: Double) throws -> [ActivityBlock]
    public static func status(_ store: ContextStore) throws -> StatusInfo
}
```

Behaviour that matters:
- `recall` searches **both** `segments_fts` and `frames_fts`, merges, sorts newest-first, caps at
  `limit`. Sanitize the user query into a safe FTS5 MATCH expression (quote each term, join with
  `OR`, drop FTS operators) — an unsanitized quote or `*` must never throw.
- `Hit.kind` is `"said"` for `source == mic`, `"heard"` for `source == system`, `"screen"` for frames.
- Screen hits collapse OCR whitespace and truncate to ~600 characters; the window title is the
  signal, the OCR is the detail.
- `activity` collapses consecutive frames of the same app into one block, closing a block when the
  app changes or a gap exceeds 120 s.
- `status` reads `CaptureState.read()`; if it is nil or `isStale`, report `capturing: false` with
  `pausedReason: "Context for Claude is not running"`.

### `Sources/ContextCore/Policy.swift` — owner: **policy agent**

```swift
/// Decides when one conversation ends and the next begins.
public struct SessionPolicy {
    public static let gapSeconds: Double = 300
    public init(gapSeconds: Double = SessionPolicy.gapSeconds)
    /// Given the end of the last stored segment and the start of a new one, should a new session open?
    public func shouldOpenNewSession(lastSegmentEndedAt: Double?, nextSegmentStartedAt: Double) -> Bool
}

/// Rejects the noise a streaming transducer emits when nobody is talking.
public enum TranscriptFilter {
    /// Trimmed text, or nil if the line should not be stored.
    public static func clean(_ raw: String) -> String?
    /// True when a window is below the speech floor and should never reach the model.
    public static func isSilent(rms: Float, floor: Float = 0.004) -> Bool
}

/// 16-bit PCM helpers, pure and unit-testable.
public enum PCM {
    public static func rms(int16LE data: Data) -> Float
    public static func downmixToMono(interleaved samples: [Float], channels: Int) -> [Float]
    public static func int16LE(from samples: [Float]) -> Data
    public static func floatSamples(int16LE data: Data) -> [Float]
}
```

`TranscriptFilter.clean` drops: empty/whitespace-only text, text with no letter or digit (a silent
window makes Parakeet emit "…"), and single repeated tokens like "AND AND AND" (≥4 identical
consecutive words).

### `Sources/ContextCore/ClaudeConfig.swift` — owner: **registrar agent (pure half)**

```swift
public enum ClaudeConfig {
    public static let serverName = "context-for-claude"

    public static var claudeCodeConfigURL: URL      // ~/.claude.json
    public static var claudeDesktopConfigURL: URL   // ~/Library/Application Support/Claude/claude_desktop_config.json

    /// Merges an `context-for-claude` stdio entry into an existing config document without disturbing
    /// anything else in it. Returns the new document.
    public static func merged(into existing: [String: Any], mcpBinaryPath: String) -> [String: Any]

    /// True when `existing` already points `context-for-claude` at exactly `mcpBinaryPath`.
    public static func isRegistered(in existing: [String: Any], mcpBinaryPath: String) -> Bool

    public static func removed(from existing: [String: Any]) -> [String: Any]
}
```

The entry written into `mcpServers` is exactly:
```json
{ "type": "stdio", "command": "<absolute path>", "args": [], "env": {} }
```
Both surfaces use the same top-level `mcpServers` key. **`~/.claude.json` is a large document with
the user's whole project history in it — merge, never rewrite, and always write atomically via a
temp file + replace so a crash cannot truncate it.** Preserve unknown keys verbatim.

---

## ContextMCPKit

### `Sources/ContextMCPKit/JSONRPC.swift` — owner: **mcp protocol agent**

Line-delimited JSON-RPC 2.0 over stdio (one JSON object per line; that is what Claude Code and
Claude Desktop speak to stdio servers).

```swift
public struct RPCRequest: Sendable { public let id: JSONValue?; public let method: String; public let params: JSONValue? }
public enum JSONValue: Codable, Sendable { case null, bool(Bool), number(Double), string(String),
                                           array([JSONValue]), object([String: JSONValue]) }
public extension JSONValue {
    var stringValue: String? { get }
    var intValue: Int? { get }
    var doubleValue: Double? { get }
    subscript(key: String) -> JSONValue? { get }
}

public enum RPC {
    public static func decode(line: String) -> RPCRequest?
    public static func result(id: JSONValue?, _ value: JSONValue) -> String   // encoded response line
    public static func error(id: JSONValue?, code: Int, message: String) -> String
}
```

### `Sources/ContextMCPKit/Tools.swift` — owner: **mcp tools agent**

```swift
public struct ToolDefinition: Sendable {
    public let name: String
    public let description: String
    public let inputSchema: JSONValue
}

public enum Tools {
    public static let all: [ToolDefinition]
    /// Executes a tool against the store and returns the text payload for the MCP content block.
    public static func call(name: String, arguments: JSONValue?, store: ContextStore?) throws -> String
}
```

Seven tools, exact names and parameters:

| name | params |
|---|---|
| `recall` | `query` (string, required), `since` (string, ISO date or relative like `"2 days ago"`), `until` (string), `limit` (int, default 40) |
| `recent` | `minutes` (int, default 30) |
| `conversations` | `since` (string), `until` (string), `limit` (int, default 30) |
| `transcript` | `session_id` (int, required) |
| `screen` | `since` (string), `until` (string), `app` (string), `limit` (int, default 60) |
| `activity` | `since` (string, required), `until` (string) |
| `status` | none |

Descriptions must be written **for Claude**, stating when to reach for the tool, e.g.
`recall`: *"Search everything the user has said, heard, or had on screen. Use this whenever the user
refers to people, plans, decisions, or things they have discussed that you have no record of."*

Date parsing: accept ISO-8601, `yyyy-MM-dd`, and relative English (`"30 minutes ago"`, `"2 days ago"`,
`"last week"`, `"today"`, `"yesterday"`). Unparseable input is an explicit tool error, not a silent
`nil`. Put the parser in this file as `public enum DateArg { public static func parse(_ s: String) -> Double? }`.

Output is human-readable **Markdown**, not raw JSON — Claude consumes it far better. Group by day,
one line per hit, prefixed with time and speaker/app. When a result set is empty, say so and say what
the coverage window is, so Claude can distinguish "never happened" from "not captured".

When `store` is nil (database missing), every tool returns a plain sentence explaining that Omi
Context for Claude has not captured anything yet — never an exception.

### `Sources/ContextMCPKit/MCPServer.swift` — owner: **mcp protocol agent**

```swift
public final class MCPServer {
    public init(store: ContextStore?)
    /// Reads lines from `input`, writes response lines to `output`. Returns when input closes.
    public func run(input: FileHandle = .standardInput, output: FileHandle = .standardOutput)
    /// Testable single-message path.
    public func handle(line: String) -> String?
}
```

Implements `initialize` (protocolVersion `"2024-11-05"`, `serverInfo` name `"context-for-claude"`,
version `"1.0.0"`, capabilities `{"tools":{}}`), `notifications/initialized` (no response),
`tools/list`, `tools/call`, and `ping`. Unknown methods return JSON-RPC error `-32601`.

### `Sources/ContextMCP/main.swift` — owner: **mcp protocol agent**

Opens `ContextStore(readOnly: true)`, tolerating `notInitialized` by passing `nil`, then
`MCPServer(store:).run()`. Nothing else.

---

## ContextApp

### `Sources/ContextApp/Support/Log.swift` — owner: **support agent**

```swift
public enum ContextLog {
    static func info(_ message: String, _ category: String = "app")
    static func error(_ message: String, _ category: String = "app")
}
```
`os.Logger` with subsystem `com.omi.context-for-claude`, plus a mirror to `/tmp/context-for-claude.log` when
`CONTEXT_DEBUG=1` — that file is how the build/verify loop sees what happened.

### `Sources/ContextApp/Capture/AudioSource.swift` — owner: **mic agent**

```swift
protocol AudioSource: AnyObject {
    /// Chunks are 16 kHz mono Int16 little-endian PCM.
    func start(onChunk: @escaping @Sendable (Data) -> Void, onLevel: @escaping @Sendable (Float) -> Void) async throws
    func stop()
    var isRunning: Bool { get }
}
enum AudioCaptureError: LocalizedError { case noInputDevice, formatUnavailable, ioProcFailed(OSStatus), tapFailed(OSStatus), aggregateFailed(OSStatus) }
```

### `Sources/ContextApp/Capture/MicCapture.swift` — owner: **mic agent**

`final class MicCapture: AudioSource`. Port the approach in
`desktop/macos/Desktop/Sources/AudioCaptureService.swift`: CoreAudio
`AudioDeviceCreateIOProcIDWithBlock` on `kAudioHardwarePropertyDefaultInputDevice` — **not**
`AVAudioEngine**, whose implicit aggregate device degrades Bluetooth A2DP. Downmix stereo to mono by
averaging, `AVAudioConverter` to 16 kHz, clamp to Int16. Install property listeners for default-device
and format changes and rebuild on either. Include the silent-mic watchdog (1 s peak windows; sustained
silence on a live device rebuilds the stack).

Also expose `static func checkPermission() -> Bool` and `static func requestPermission() async -> Bool`
over `AVCaptureDevice` `.audio`.

### `Sources/ContextApp/Capture/SystemAudioCapture.swift` — owner: **system audio agent**

`@available(macOS 14.4, *) final class SystemAudioCapture: AudioSource`. Port
`desktop/macos/Desktop/Sources/SystemAudioCaptureService.swift`: `CATapDescription(stereoGlobalTapButExcludeProcesses: [])`,
`muteBehavior = .unmuted`, `AudioHardwareCreateProcessTap`, then a **private** aggregate device with
`kAudioAggregateDeviceTapListKey` and `kAudioSubTapDriftCompensationKey = 1` (mandatory — without it
all system audio crackles) at `kAudioAggregateDriftCompensationMaxQuality`, `TapAutoStart = true`.
Same 16 kHz mono Int16 output contract. Include `static func primePermission() -> Bool` which creates
and immediately tears down the identical tap so consent fires during onboarding rather than mid-call.

### `Sources/ContextApp/Capture/ScreenWatcher.swift` — owner: **screen agent**

```swift
@MainActor final class ScreenWatcher {
    var onFrame: ((Frame) -> Void)?
    func start(interval: TimeInterval = 3.0)
    func stop()
    var isRunning: Bool { get }
    static func hasPermission() -> Bool
    static func requestPermission()
}
```
ScreenCaptureKit capture of the **active window** (`SCShareableContent.excludingDesktopWindows`,
cached — WindowServer queries are expensive; refresh the cache at most every 5 s), Vision
`VNRecognizeTextRequest` (`.accurate`, `usesLanguageCorrection = true`) for OCR. dHash the frame and
skip OCR when it matches the previous hash — an idle screen must cost nothing. Skip capture when the
frontmost app is a screenshot tool, Mission Control is up, or the screen is locked. Write a JPEG
(quality 0.5, longest side ≤ 1600) into `ContextPaths.framesDirectory(for:)` and set `imagePath`.
Record `appName` and `windowTitle` on every frame even when OCR is skipped.

### `Sources/ContextApp/Transcribe/Transcriber.swift` — owner: **transcription agent**

```swift
actor Transcriber {
    init(source: SegmentSource)
    var onLine: (@Sendable (String, Double, Double) -> Void)?   // text, startEpoch, endEpoch
    func setOnLine(_ handler: @escaping @Sendable (String, Double, Double) -> Void)
    func start() async throws
    func append(_ data: Data)       // 16 kHz mono Int16 LE
    func finish() async
}
```
FluidAudio Parakeet TDT, on-device. `AsrModels.downloadAndLoad(version:)` — `.v2` for English,
`.v3` otherwise. 10 s windows drained by a 1 s pump. **A fresh `TdtDecoderState()` per window** —
persisting it across windows makes the transducer loop and Title-Case everything. Use
`TranscriptFilter.isSilent(rms:)` to skip dead windows before the model and `TranscriptFilter.clean`
on the output. Model download is ~600 MB on first run: expose
`static var isModelReady: Bool` and `static func prepareModels() async throws` so onboarding can
warm it with progress rather than the first conversation silently dropping.

### `Sources/ContextApp/Engine.swift` — owner: **engine agent**

```swift
@MainActor final class Engine: ObservableObject {
    static let shared: Engine
    @Published private(set) var isCapturing: Bool
    @Published private(set) var pausedReason: String?
    @Published private(set) var capabilities: [CapabilityReport]
    @Published private(set) var todaySeconds: Double
    @Published private(set) var lastLine: String?

    func start()
    func pause()
    func resume()
    func refreshCapabilities()
}
```
Owns `MicCapture`, `SystemAudioCapture`, two `Transcriber`s, `ScreenWatcher`, and the `ContextStore`
writer. Applies `SessionPolicy` to decide session boundaries, sets `appHint` from the frontmost app
when opening one, and writes `CaptureState` to the heartbeat file every 30 s and on every state
change. **Each source fails independently** — a dead mic must not stop screen capture; record the
reason in `pausedReason` and keep the rest alive. Prunes frames older than 30 days on launch.

### `Sources/ContextApp/Permissions.swift` — owner: **permissions agent**

```swift
enum Capability: String, CaseIterable { case microphone, systemAudio, screen }
extension Capability { var title: String { get }   // the first-person onboarding sentence
                       var settingsPane: String { get } }
enum Permissions {
    static func check(_ c: Capability) -> Bool
    static func request(_ c: Capability) async -> Bool
    static func openSettings(for c: Capability)
    static func report() -> [CapabilityReport]
}
```
Two-stage macOS behaviour: the first request raises the system TCC prompt; a second tap opens the
exact System Settings pane (`x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone`
/ `Privacy_ScreenCapture`). Screen Recording only takes effect after a relaunch — surface that.

### `Sources/ContextApp/Integration/ClaudeRegistrar.swift` — owner: **registrar agent (I/O half)**

```swift
enum ClaudeRegistrar {
    struct Result { let claudeCode: Bool; let claudeDesktop: Bool; let message: String }
    static var mcpBinaryPath: String { get }        // Bundle.main/Contents/MacOS/context-for-claude-mcp
    static func register() -> Result
    static func status() -> (claudeCode: Bool, claudeDesktop: Bool)
}
```
Uses `ClaudeConfig` for all document manipulation. Creates the Claude Desktop config directory and
file if absent. Never throws out — a failure becomes `false` plus an explanatory `message`.

### `Sources/ContextApp/Integration/LoginItem.swift` — owner: **registrar agent**

```swift
enum LoginItem {
    static var isEnabled: Bool { get }
    static func enable() -> Bool     // SMAppService.mainApp.register()
    static func disable()
}
```

### `Sources/ContextApp/ContextApp.swift` — owner: **app shell agent**

`@main struct ContextApp: App` with a single `MenuBarExtra` scene, `.menuBarExtraStyle(.window)`.
`LSUIElement` is set in Info.plist so there is no dock icon and no main window. An
`NSApplicationDelegateAdaptor` registers the bundled fonts (`CTFontManagerRegisterFontsForURL` over
`Contents/Resources/Fonts`), starts `Engine.shared`, and opens `OnboardingWindow` when
`UserDefaults.standard.bool(forKey: "context.onboarded")` is false. Menu bar icon: the eight-dot Omi
mark drawn in code (see `Ink.swift`), faintly animated while capturing.

### `Sources/ContextApp/MenuBar/StatusView.swift` — owner: **menu bar agent**

The whole popover, ~320 pt wide: one status line ("Listening · 3h 12m today" / "Paused"), three
capability rows with live state that open Settings when tapped, a pause/resume button, a line saying
which Claude surfaces are connected, and Quit. Uses `Ink` for every colour and font. No tabs, no
lists, no settings page. That is the entire non-onboarding UI.

### Onboarding — owner: **onboarding agents (three of them)**

- `Sources/ContextApp/Onboarding/Ink.swift` — **design system agent.** Colours, fonts, the stadium
  button, the permission row, the eight-dot mark. Exact values in `docs/design-system.md`.
- `Sources/ContextApp/Onboarding/Backdrop.swift` + `RandomizedText.swift` — **atmosphere agent.**
  The nine-blob gradient and the word-by-word reveal.
- `Sources/ContextApp/Onboarding/OnboardingWindow.swift` + `OnboardingView.swift` — **flow agent.**
  The borderless floating window, the elliptical paper surface it paints, and the four steps.

### `scripts/build.sh` — owner: **build agent**

`swift build -c release` both products, assemble `Context for Claude.app`, copy `context-for-claude-mcp` into
`Contents/MacOS/`, copy `Resources/Fonts`, generate `Info.plist` (`LSUIElement`, usage strings,
`CFBundleIdentifier = com.omi.context-for-claude`), sign with `Omi Local Dev Signing` and the entitlements —
**never ad-hoc, which resets Screen Recording for every Omi app on this machine** — then install to
`/Applications/Context for Claude.app`. Idempotent, and it must not touch `/Applications/Omi.app` or
`Omi Beta.app`.
