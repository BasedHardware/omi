import ContextCore
import AppKit
import Combine
import Foundation

/// One transcribed line on its way from a transcriber to the database.
private struct TranscriptLine: Sendable {
    let text: String
    let startedAt: Double
    let endedAt: Double
    let source: SegmentSource
    /// Backend diarization label and resolved person, when the cloud transcribed this line.
    /// Both nil on the local path, which cannot tell voices apart at all.
    var speakerLabel: String?
    var personId: String?
    /// The durable backend identity that makes a revised cloud segment an update rather than a new
    /// transcript row. Both are nil for the local fallback path.
    var backendConversationId: String? = nil
    var backendSegmentId: String? = nil
}

/// What the app says about itself between launch and the first live sensor.
///
/// Silence would be the wrong answer here: a nil `pausedReason` next to `capturing: false` reads as
/// "nothing is wrong", which is exactly the lie this window used to tell.
private let startingUpReason = "Starting up"

/// The last state the main actor published, so the heartbeat timer can re-stamp and rewrite it
/// without ever touching the main actor.
///
/// Freshness of the heartbeat file means "this process is alive"; the fields mean "and this is the
/// last thing it knew about itself". Keeping those two separable is the whole point — the main
/// thread can be taken away for minutes by a system authorization prompt, and a reader must still be
/// able to tell a wedged app from an absent one.
private final class HeartbeatSnapshot: @unchecked Sendable {
    private let lock = NSLock()
    private var state = CaptureState(capturing: false, pausedReason: startingUpReason)

    func set(_ new: CaptureState) {
        lock.lock()
        state = new
        lock.unlock()
    }

    func restamped() -> CaptureState {
        lock.lock()
        defer { lock.unlock() }
        var copy = state
        copy.updatedAt = ContextTime.now
        return copy
    }
}

/// The parts of the pipeline that fail independently. Storage is one of them: it is the single
/// shared dependency, and a database that will not open makes capture pointless rather than partial.
///
/// Internal rather than file-private because the function that turns these into published state is
/// the one with a wrong answer available, and it has to be assertable without a microphone, a
/// database or a window server.
enum CaptureComponent: CaseIterable {
    case storage
    case microphone
    case systemAudio
    case screen

    var capability: Capability? {
        switch self {
        case .storage: return nil
        case .microphone: return .microphone
        case .systemAudio: return .systemAudio
        case .screen: return .screen
        }
    }

    var label: String {
        switch self {
        case .storage: return "Storage"
        case .microphone: return "Microphone"
        case .systemAudio: return "Call audio"
        case .screen: return "Screen"
        }
    }

    /// The name this component travels under in `capture-state.json`, so the app and
    /// `context-for-claude-mcp` are talking about the same stream.
    var streamName: String {
        switch self {
        case .storage: return StreamName.storage
        case .microphone: return StreamName.microphone
        case .systemAudio: return StreamName.systemAudio
        case .screen: return StreamName.screen
        }
    }

    var segmentSource: SegmentSource { self == .microphone ? .mic : .system }
}

/// What one component is doing, as **one** value.
///
/// This replaces a `Set` of what was running standing beside a dictionary of what had gone wrong,
/// and the replacement is the whole of this fix. Two containers can put a component in neither of
/// them, and that is precisely where the screen sat for twenty-nine hours: absent from `running`,
/// carrying a reason that no aggregate consulted, while `running` was non-empty because the
/// microphone was alive — so `!running.isEmpty` said `capturing: true` over a database that had not
/// taken a screen frame since the previous afternoon. One value per component cannot be in neither
/// state, and the aggregate is computed *from* these values rather than beside them.
enum ComponentState: Equatable {
    /// Asked to start, nothing observed from it yet. The optional sentence is for the starts that
    /// take a while and need to say why — the first run downloading a 600 MB transcription model
    /// looks identical to a wedged one otherwise.
    case starting(String?)
    /// Running and producing.
    case live
    /// Needs the user. A permission this install had and no longer has, a grant this process cannot
    /// use until it is relaunched, or hardware the OS is refusing.
    case blocked(String)
    /// Believed running and producing nothing for longer than its own patience.
    case stalled(String)
    /// Deliberately not running: switched off, never permitted, unsupported, or paused.
    case off(String)

    /// How this reaches the heartbeat file.
    var wire: StreamState {
        switch self {
        case .starting: return .starting
        case .live: return .live
        case .blocked: return .blocked
        case .stalled: return .stalled
        case .off: return .off
        }
    }

    /// The sentence a person reads, or nil when there is nothing to say. `live` says nothing on
    /// purpose: a working component is the absence of news.
    var detail: String? {
        switch self {
        case .starting(let note): return note
        case .live: return nil
        case .blocked(let reason), .stalled(let reason), .off(let reason): return reason
        }
    }

    var isLive: Bool { self == .live }
}

/// The capture pipeline: three sensors, two transcribers, one database writer, and the published
/// state the menu bar and `context-for-claude-mcp` read.
///
/// The organising rule is that **every source fails alone**. A mic that never comes back, a system
/// tap the OS refuses, a Screen Recording grant that only takes effect after a relaunch — each one
/// records its own reason and leaves the others capturing, because a day with two of three streams
/// is worth far more than no day at all.
///
/// The main actor holds state and publishes it. It never touches SQLite: every write goes to
/// `EngineStore`, which owns its own serial queue.
@MainActor
final class Engine: ObservableObject {
    /// Keeps the sign-in subscription that provisions the MCP key alive.
    private var keyProvisioning: Set<AnyCancellable> = []
    private var settingsSubscriptions: Set<AnyCancellable> = []
    /// Watches cloud socket + sign-in so Intel hosts can surface an honest transcription gap.
    private var transcriptionWatch: Set<AnyCancellable> = []
    private var transcriptionGapReason: String?
    /// Sums mic and system into the single stream the backend transcribes.
    private let mixer = AudioMixer()
    /// The latest text seen per backend segment id, so a revised segment replaces rather than
    /// duplicates. Cleared whenever the server rolls to a new conversation.
    private var cloudSegmentText: [String: String] = [:]
    private var cloudConversationId: String?

    static let shared = Engine()

    /// True only when **everything that should be running is running**.
    ///
    /// It used to be `!running.isEmpty`, which is an or over three independent sensors read by every
    /// surface downstream as an and. Derived now, and derived in `ContextCore`, so the menu bar, the
    /// heartbeat file and Claude cannot come to three different conclusions from the same facts.
    @Published private(set) var isCapturing = false
    /// The three-valued answer, because "on" and "off" cannot say *half*. Surfaces with room for
    /// more than a dot read this instead of `isCapturing`.
    @Published private(set) var health: CaptureHealth = .off
    /// Why capture is not whole right now: paused by the user, a permission never granted, or a
    /// source that died. Nil only when everything permitted is actually running.
    @Published private(set) var pausedReason: String?
    /// **The menu bar's rows, and only the menu bar's.** One row per *capability* — "Microphone"
    /// standing for the mic and the system-audio tap, "Screen" for the pixels and the window text —
    /// which is a presentation decision about what the app does, not a report of what macOS granted.
    ///
    /// It stopped being only the menu bar's in `03c88c032b`, which switched this from
    /// `Permissions.report()` to `Permissions.groupedReport()` and, because the same array is
    /// written into `capture-state.json`, silently changed the machine-readable wire from one row
    /// per TCC record to a group verdict. `screen` then read `granted: false` whenever Accessibility
    /// alone was missing — over a live screen stream — and the MCP `status` tool told Claude a whole
    /// class of local context was missing while frames were landing. `publishState` publishes
    /// `Permissions.report()` for exactly that reason: the wire names TCC records, the menu bar
    /// names capabilities, and neither has to be read as the other.
    @Published private(set) var capabilities: [CapabilityReport] = []
    /// Wall-clock seconds of today that Context for Claude actually covered. The one number in the menu bar.
    @Published private(set) var todaySeconds: Double = 0
    /// The most recent transcript line, so the popover can show the app is alive.
    @Published private(set) var lastLine: String?

    private let store = EngineStore()

    /// The writable store, once it is open, for read-only surfaces that need one. Nil until the
    /// first open succeeds. Rewind reads through this rather than opening a second connection, so
    /// the window and the writer can never disagree about what has been committed.
    var contextStore: ContextStore? { store.currentStore() }
    /// The heartbeat is a tiny atomic file write, but it happens on a timer while audio is running;
    /// keep it off both the main thread and the store's queue.
    private let heartbeatQueue = DispatchQueue(label: "com.omi.context-for-claude.heartbeat", qos: .utility)
    private let heartbeat = HeartbeatSnapshot()

    /// Retention runs this long after the store opens. Long enough that the first frames, the first
    /// transcript lines and the first session of a launch are all already written.
    private static let retentionDelaySeconds: TimeInterval = 120
    /// How long the account work waits for a sensor to come up before going ahead anyway. A Mac with
    /// nothing granted has nothing to wait for, and sign-in still has to be possible there.
    private static let accountGraceSeconds: Double = 5

    /// How long an audio source may go without delivering a chunk before the app stops calling it
    /// live.
    ///
    /// Ninety seconds. `MicCapture` has its own one-second silence watchdog and rebuilds itself
    /// three times before giving up, so anything that survives to here has already exhausted every
    /// recovery the device layer has — this is the backstop for the case that layer cannot see,
    /// where the IOProc is alive and simply never calls back.
    private static let audioSilenceSeconds: Double = 90

    /// How often a stalled screen watcher is torn down and rebuilt. Some of what the WindowServer
    /// refuses is transient — a display reconfiguration, a fast user switch — and a fresh connection
    /// is the cheapest thing that clears it. Bounded so an unrecoverable stall costs one rebuild
    /// every five minutes rather than one every thirty seconds.
    private static let screenRecycleSeconds: Double = 300

    private var hasStarted = false
    /// Published because the popover's own control depends on it: with `isCapturing` now meaning
    /// "everything is running", a degraded recorder would otherwise offer a **Resume** button for a
    /// pause that never happened.
    @Published private(set) var isPaused = false
    private var isStorageReady = false
    /// What every component is doing — the engine's own bookkeeping, not a poll of the sources, so
    /// state never depends on when another object flips its `isRunning`.
    private var componentStates: [CaptureComponent: ComponentState] = [:]
    /// When each component last produced anything. The evidence behind "believed running and
    /// producing nothing", and the one field of the heartbeat that can prove a stream is alive
    /// rather than merely started.
    private var lastOutput: [CaptureComponent: Double] = [:]
    private var screenRecycledAt: Double?

    private var audioSources: [CaptureComponent: AudioSource] = [:]
    /// Identifies one permission/device run. A canceled start may finish after a stop and restart;
    /// it must not publish state or install a local transcriber into the new run.
    private var audioRunIDs: [CaptureComponent: UUID] = [:]
    private var transcribers: [CaptureComponent: Transcriber] = [:]
    private var chunkFeeds: [CaptureComponent: AsyncStream<Data>.Continuation] = [:]
    private var pumps: [CaptureComponent: Task<Void, Never>] = [:]
    private var starts: [CaptureComponent: Task<Void, Never>] = [:]
    /// Silicon-only: Parakeet start side tasks. Created only when a cloud fallback is actually
    /// needed, and cancelled in teardownAudio so a stop mid-load cannot resurrect a pump on a
    /// transcriber the engine no longer owns.
    private var localStarts: [CaptureComponent: Task<Void, Never>] = [:]
    private var screenWatcher: ScreenWatcher?

    private var lineFeed: AsyncStream<TranscriptLine>.Continuation?
    private var lineTask: Task<Void, Never>?
    /// A dispatch timer rather than a `Task`, because a main-actor task stops beating exactly when
    /// the main thread is stuck — see `startHeartbeatTimer()`.
    private var heartbeatTimer: DispatchSourceTimer?
    private var maintenanceTask: Task<Void, Never>?
    private var accountTask: Task<Void, Never>?
    private var todayTask: Task<Void, Never>?

    private init() {}

    // MARK: - Lifecycle

    /// Idempotent: the app delegate calls this on launch, and onboarding may call it again once
    /// permissions land.
    ///
    /// The order below is the fix for a defect that cost 10–24 minutes of capture on every relaunch,
    /// and it is load-bearing. Launch used to run, in this order: a synchronous Keychain read, then
    /// the database open, then capture, then the first heartbeat. Each step could stall the one
    /// behind it, and one of them stalls for minutes at a time — `OmiAuth.restore()` reads this
    /// app's Keychain item with `SecItemCopyMatching` on the main actor, and a bundle whose
    /// signature has changed (every rebuild, every update a user installs) makes macOS put an
    /// authorization prompt in front of that read. An `.accessory` app has no window to bring that
    /// prompt forward with, so it sat unanswered: measured 2026-07-28, 22 minutes on one launch and
    /// 5–9 seconds on three others, during which the app held no database handle, wrote no frames
    /// and emitted no heartbeat — so it truthfully reported itself as not running, for 22 minutes,
    /// while its own process was alive.
    ///
    /// So: the heartbeat first, then the sensors, then storage, and everything that can block the
    /// main actor dead last, behind all of it.
    func start() {
        guard !hasStarted else { return }
        hasStarted = true

        // 1. Say something about ourselves before doing anything that can stall. The write lands on
        //    `heartbeatQueue`, so it does not depend on the main thread staying free.
        publishState()
        startHeartbeatTimer()

        // 2. Permissions and the transcript consumer: what the sensors need in order to start.
        capabilities = Permissions.groupedReport()
        startLineConsumer()
        // Started with capture, not with the account. The socket reports `.idle` until there is a
        // session and connects when one lands, so putting it behind the sign-in restore would only
        // make it inherit that call's latency.
        startCloudTranscription()

        // 3. Sensors, before storage and before the account. Nothing they produce is lost while the
        //    database opens — `EngineStore` holds it, bounded, until there is somewhere to put it.
        startPermittedSources()
        publishState()
        observeScreenCaptureSetting()

        // 4. Storage. Nothing above waits on this.
        Task { [weak self] in
            guard let self else { return }
            await self.ensureStorage()
            self.publishState()
            await self.refreshTodaySeconds()
        }

        startMaintenanceLoop()
        startTodaySecondsLoop()
        observeTermination()

        // 5. Re-register on every launch, not only during onboarding. Registration is idempotent and
        //    writes only when something actually differs — but without this, an install that has
        //    already onboarded can never pick up a changed binary path or a renamed connector, so a
        //    rename reaches new users and silently strands existing ones. Detached: it never touches
        //    the main actor, so it does not belong on it.
        Task.detached(priority: .utility) {
            let result = ClaudeRegistrar.register()
            ContextLog.info("Claude registration on launch: \(result.message)", "claude")
        }

        // 6. The account, last of all.
        startAccountServices()

        // `milestone`, not `info`: this is the opening bracket of a run. Errors read back from
        // `log show` hours later are a scatter of sentences with no way to tell which process they
        // belong to, or whether capture ever came up at all — measured, on a report where the only
        // surviving line for a whole run was the one `applicationWillTerminate` writes. `info` is
        // gone within minutes, so the bracket has to be a level that is not.
        ContextLog.milestone("Engine started", "engine")
    }

    /// Everything that touches the user's Omi account: the stored session, the MCP credential, and
    /// the two uploaders. All of it is a no-op while signed out — captures queue locally and go up
    /// once an account is attached — which is exactly why none of it belongs in front of capture.
    ///
    /// `OmiAuth.restore()` is the specific hazard: it reads the Keychain synchronously on the main
    /// actor, and macOS can hold that read behind an authorization prompt for as long as the user
    /// takes to notice it. That is survivable now — the heartbeat beats on its own dispatch timer
    /// and the audio devices are already running on their CoreAudio threads — but only if it happens
    /// after the pipeline is up rather than before it.
    private func startAccountServices() {
        accountTask = Task { [weak self] in
            // Let the sensors take their main-actor turns first. Bounded, because a Mac with nothing
            // granted has no sensor to wait for and must still be able to sign in.
            let deadline = ContextTime.now + Self.accountGraceSeconds
            while true {
                guard let self else { return }
                if !self.liveComponents.isEmpty || ContextTime.now >= deadline { break }
                try? await Task.sleep(for: .milliseconds(50))
            }
            guard let self else { return }

            OmiAuth.shared.restore()

            // The MCP server needs its own Omi credential rather than borrowing one out of another
            // server's entry in ~/.claude.json. A fresh install is still signed out here, so this is
            // a no-op until the sign-in below fires it again.
            Task { await MCPKeyProvisioner.shared.ensureKey() }
            OmiAuth.shared.$isSignedIn
                .removeDuplicates()
                .filter { $0 }
                .sink { _ in Task { await MCPKeyProvisioner.shared.ensureKey() } }
                .store(in: &self.keyProvisioning)

            // Started unconditionally, and that is now safe: each of these owns its own Airgap Mode
            // guard and observes the switch live (`NetworkEgress`). Gating them here instead would
            // read the flag exactly once per launch and leave `syncNow()` and the reconnect paths
            // ungated — which is how the switch came to suppress favicons and nothing else.
            ScreenActivityUploader.shared.start()
            Task { await ConversationUploader.shared.drain() }
        }
    }

    /// Streams mixed audio to the Omi backend, which transcribes it with real diarization and the
    /// user's own speech profile — attribution this app can only approximate locally as
    /// "mic is me, system is everyone else".
    ///
    /// On Apple Silicon the local Parakeet path stays underneath so a dead network or a paywalled
    /// account degrades to a worse transcript rather than to silence. On Intel there is no local
    /// path: cloud is the only ASR, and gaps are reported honestly via `transcriptionGapReason`.
    func mixerInput(mic: Data? = nil, system: Data? = nil) {
        if let mic { mixer.setMicAudio(mic) }
        if let system { mixer.setSystemAudio(system) }
    }

    private func startCloudTranscription() {
        mixer.start { chunk in
            ListenSocket.shared.send(chunk)
        }

        ListenSocket.shared.onConversationId = { [weak self] id in
            guard let self else { return }
            if self.cloudConversationId != id {
                self.cloudConversationId = id
                self.cloudSegmentText.removeAll()
            }
        }

        ListenSocket.shared.onSegments = { [weak self] segments in
            guard let self else { return }
            for segment in segments where !segment.text.isEmpty {
                self.acceptCloudLine(segment)
            }
        }

        if transcriptionWatch.isEmpty {
            ListenSocket.shared.$state
                .receive(on: DispatchQueue.main)
                .sink { [weak self] _ in self?.refreshTranscriptionGap() }
                .store(in: &transcriptionWatch)
            OmiAuth.shared.$isSignedIn
                .receive(on: DispatchQueue.main)
                .sink { [weak self] _ in self?.refreshTranscriptionGap() }
                .store(in: &transcriptionWatch)
        }
        refreshTranscriptionGap()

        Task { await ListenSocket.shared.start() }
    }

    /// Surfaces cloud-only gaps on Intel (and clears them when the socket is live). Silicon keeps
    /// local fallback, so a cloud outage is not reported as "nothing is being transcribed".
    private func refreshTranscriptionGap() {
        let snapshot: CloudSocketSnapshot
        switch ListenSocket.shared.state {
        case .idle: snapshot = .idle
        case .connecting: snapshot = .connecting
        case .live: snapshot = .live
        case .failed(let detail): snapshot = .failed(detail)
        case .paywalled: snapshot = .paywalled
        case .airgapped: snapshot = .airgapped
        }
        let cloud = CaptureHostPolicy.resolvedCloudTranscriptionState(
            socket: snapshot,
            isSignedIn: OmiAuth.shared.isSignedIn
        )
        transcriptionGapReason = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: HostArchitecture.usesLocalSTT,
            isSignedIn: OmiAuth.shared.isSignedIn,
            cloud: cloud
        )
        publishState()
    }

    /// A line the backend transcribed, written on the same path as a local one so sessions,
    /// upload and search see no difference between the two sources.
    ///
    /// Two things here are not obvious and both were wrong first time.
    ///
    /// `segment.start` is **seconds from the start of the conversation**, not a Unix epoch — the
    /// server applies its own offset before sending. Treating it as an epoch put every cloud line
    /// in January 1970, and `SessionPolicy` then saw a 56-year gap before each one and opened a
    /// fresh session per line. The conversation's own anchor puts them back on the real clock.
    ///
    /// And the backend **re-sends a segment under the same id** when punctuation, diarization or a
    /// speech-profile match improves it. Appending on every batch stores the same sentence over and
    /// over, so a revision replaces its predecessor instead.
    private func acceptCloudLine(_ segment: CloudSegment) {
        let base = ListenSocket.shared.conversationStartedAt ?? ContextTime.now
        // Keyed on attribution as well as text. The backend re-sends a segment under the same id
        // when it improves — and an improvement is very often *only* the diarization or a
        // speech-profile match, with the words unchanged. A text-only key discarded exactly the
        // revisions this app moved to cloud transcription to receive.
        if let id = segment.id {
            let revision = "\(segment.text)|\(segment.speaker ?? "")|\(segment.personId ?? "")|\(segment.isUser)"
            if cloudSegmentText[id] == revision { return }
            cloudSegmentText[id] = revision
        }
        let line = TranscriptLine(
            text: segment.text,
            startedAt: base + segment.start,
            endedAt: base + segment.end,
            source: segment.isUser ? .mic : .system,
            speakerLabel: segment.speaker,
            personId: segment.personId,
            backendConversationId: cloudConversationId,
            backendSegmentId: segment.id
        )
        lastLine = line.text
        lineFeed?.yield(line)
    }

    func pause() {
        guard !isPaused else { return }
        isPaused = true
        stopAllSources(reason: "Paused")
        // The socket has to close with the capture. Left open with no audio arriving, the server
        // hangs up at 90 s and the client reconnects on backoff for as long as the app is paused —
        // a reconnect loop against the backend for a user who deliberately stopped recording.
        ListenSocket.shared.stop()
        mixer.stop()
        // Transcription gaps describe a live cloud path. Pause owns the headline; drop the stale
        // note so resume starts clean rather than carrying a reason from the previous session.
        transcriptionGapReason = nil
        // Ends the conversation, not just the capture. The app delegate also routes quit through
        // here, and a session left open reports a recording that stopped hours ago.
        store.closeOpenSession()
        // `milestone` for the reason `ContextLog` gives: the app has stopped recording on the
        // user's behalf and cannot ask them about it later. "It quietly stopped capturing" is the
        // report this line answers, and answering it requires the line to still be there when the
        // report arrives — which, at `info`, it is not.
        ContextLog.milestone("Capture paused", "engine")
        publishState(synchronously: true)
    }

    func resume() {
        guard isPaused else { return }
        isPaused = false
        // States recorded before the pause describe a pipeline that no longer exists. Storage is
        // the exception: that failure is about the database, not about a source. Wipe *before*
        // `startCloudTranscription()` so `refreshTranscriptionGap()` can re-apply the Intel gap.
        for component in CaptureComponent.allCases where component != .storage {
            componentStates[component] = .starting(nil)
            lastOutput[component] = nil
        }
        capabilities = Permissions.groupedReport()
        startPermittedSources()
        // The other half of the pause. A gap in the recording is only legible as deliberate when
        // both ends of it survive; a persisted "paused" with an evicted "resumed" is worse than
        // neither, because it reads as capture that never came back.
        ContextLog.milestone("Capture resumed", "engine")
        startCloudTranscription()
        publishState()
    }

    /// Re-reads the permission state and starts anything that is now allowed but not yet running —
    /// a grant that lands after launch, or a source that failed and can be retried.
    ///
    /// **The bracket around `startPermittedSources()` is a breadcrumb, not decoration.** A grant is
    /// the one moment this app builds a CoreAudio process tap, opens an input device and connects a
    /// fresh `ScreenCaptureKit` request against rights macOS has just re-evaluated — and "it crashes
    /// when I give permissions" is what a user calls the app disappearing there. The two ways it can
    /// disappear need different fixes and are indistinguishable after the fact: a run whose last
    /// line is the opening milestone died *inside* the restart, while a run carrying both and then
    /// stopping was asked to quit. Everything the restart itself writes is `info` and evicted from
    /// the unified log within minutes, so without this pair a report that arrives an hour later can
    /// answer neither question.
    ///
    /// Gated on `capabilityRestartNote` rather than logged on entry, because this runs every second
    /// while the menu bar popover is open and every thirty seconds from the maintenance loop: a
    /// milestone at that rate would bury the log it exists to make readable.
    func refreshCapabilities() {
        let previous = capabilities
        capabilities = Permissions.groupedReport()
        let note = Self.capabilityRestartNote(from: previous, to: capabilities)
        if let note { ContextLog.milestone("Capabilities changed (\(note)) — restarting capture", "engine") }
        startPermittedSources()
        if let note { ContextLog.milestone("Capabilities changed (\(note)) — restart returned", "engine") }
        publishState()
    }

    /// What moved between two capability reads, named for the log — or nil when nothing moved and
    /// there is therefore nothing worth bracketing.
    ///
    /// Nil for the first read of a launch (`previous` empty). A row appearing for the first time is
    /// not a change anybody made, and `start()` seeds `capabilities` before anything reaches here.
    ///
    /// Compares the whole row rather than `granted` alone. A microphone group whose first missing
    /// member moves from the microphone to the system-audio tap is `granted: false` both times and a
    /// different state of the world — and it is precisely the one that restarts a source, so a
    /// comparison that could not see it would leave the restart it caused unbracketed.
    ///
    /// Pure and `nonisolated` so the thing this line can actually get wrong — becoming per-tick
    /// noise — is assertable without a TCC grant.
    nonisolated static func capabilityRestartNote(
        from previous: [CapabilityReport], to current: [CapabilityReport]
    ) -> String? {
        guard !previous.isEmpty else { return nil }
        let before = Dictionary(previous.map { ($0.name, $0) }, uniquingKeysWith: { _, last in last })
        let moved = current.compactMap { row -> String? in
            guard let was = before[row.name], was != row else { return nil }
            return "\(row.name): \(was.detail) → \(row.detail)"
        }
        return moved.isEmpty ? nil : moved.joined(separator: ", ")
    }

    // MARK: - Sources

    /// Opens the database if it is not open yet. Idempotent, so launch and the maintenance loop's
    /// retry can both call it: a volume that was busy for a minute should not cost the rest of the
    /// session. Nothing that captures waits on it.
    private func ensureStorage() async {
        guard !isStorageReady else { return }
        if let failure = await store.open() {
            setState(.storage, .blocked(failure))
            return
        }
        isStorageReady = true
        setState(.storage, .live)
        // Seeded from the rows on disk, once the database is open: a flag written on the first
        // successful capture cannot speak for the frames captured before the flag existed, and the
        // install that most needs the distinction is exactly the one that was already running when
        // its grant died. Screen only — an audio segment does not say whether it came from the
        // microphone or the system tap, and guessing there would raise the false alarm this whole
        // distinction exists to avoid.
        if await store.hasAnyFrames() {
            Permissions.noteCaptureSucceeded(.screen)
            // The seed may have just turned "you never granted this" into "this stopped working",
            // which is a different sentence and a different state.
            refreshCapabilities()
        }
        // Retention is housekeeping, and housekeeping is not allowed on the startup path: this only
        // *schedules* the sweep, minutes out, on a queue of its own. It used to be enqueued here on
        // the store's own serial queue, which put thousands of file unlinks in front of the frames
        // and transcript lines of the session that had just started.
        store.scheduleRetentionSweep(olderThanDays: 30, after: Self.retentionDelaySeconds)
    }

    /// Deliberately not gated on `isStorageReady`. Screen and audio capture depend on permissions
    /// and on the devices, not on SQLite: a store that is slow to open must cost the user latency in
    /// search, never minutes of their life going unrecorded. What the sensors produce meanwhile is
    /// held by `EngineStore` until there is a database to put it in.
    private func startPermittedSources() {
        guard !isPaused else { return }
        startAudio(.microphone)
        startAudio(.systemAudio)
        startScreen()
    }

    private func stopAllSources(reason: String) {
        stopAudio(.microphone, reason: reason)
        stopAudio(.systemAudio, reason: reason)
        stopScreen(reason: reason)
    }

    /// Wires one audio device into the cloud mixer. On Apple Silicon, local Parakeet is started only
    /// after cloud ownership is no longer viable; while the socket is connecting it buffers audio,
    /// so warming two ~600 MB ASR managers during every healthy launch is unnecessary. Capture
    /// lifecycle must not wait on (or die with) local model load — cloud transcription needs the
    /// chunks either way.
    private func startAudio(_ component: CaptureComponent) {
        guard starts[component] == nil, !isLive(component) else { return }
        guard let capability = component.capability else { return }
        guard Permissions.check(capability) else {
            setState(component, missingPermissionState(component, capability))
            return
        }
        guard let device = makeAudioSource(component) else { return }

        let decision = AudioCaptureDecision.make(usesLocalSTT: HostArchitecture.usesLocalSTT)
        let segmentSource = component.segmentSource
        let lines = lineFeed
        let runID = UUID()
        // A stream rather than a task per chunk: tasks reach an actor in whatever order the pool
        // schedules them, and reordered audio is a corrupted transcript. Bounded, because a stalled
        // transcriber must cost a few dropped seconds rather than the whole machine's memory.
        let (chunks, feed) = AsyncStream<Data>.makeStream(
            of: Data.self, bufferingPolicy: .bufferingNewest(512))

        audioSources[component] = device
        audioRunIDs[component] = runID
        chunkFeeds[component] = feed

        starts[component] = Task { [weak self] in
            do {
                self?.pumps[component] = Task.detached(priority: .userInitiated) {
                    for await chunk in chunks {
                        // Every chunk reaches the cloud. The local model owns only the fallback:
                        // feeding both while cloud is live persists two independent transcripts of
                        // the same audio. Decide at ingestion time, before model latency can blur a
                        // cloud-state transition with the line it later emits.
                        let localFallback = await MainActor.run { () -> Transcriber? in
                            switch component {
                            case .microphone: Engine.shared.mixerInput(mic: chunk)
                            case .systemAudio: Engine.shared.mixerInput(system: chunk)
                            default: break
                            }
                            // A chunk of PCM is the only proof this device is genuinely alive
                            // rather than merely started. `AudioSource.isRunning` is a flag the
                            // source sets; this is bytes.
                            Engine.shared.noteOutput(component)
                            let cloudState = ListenSocket.shared.state
                            guard TranscriptOwnership.shouldFeedLocalFallback(when: cloudState) else {
                                return nil
                            }
                            return Engine.shared.startLocalFallbackIfNeeded(
                                component: component,
                                runID: runID,
                                decision: decision,
                                segmentSource: segmentSource,
                                lines: lines,
                                cloudState: cloudState)
                        }
                        if let localFallback {
                            await localFallback.append(chunk)
                        }
                    }
                }
                try await device.start(onChunk: { feed.yield($0) }, onLevel: { _ in })

                guard let self, self.audioRunIDs[component] == runID, !Task.isCancelled else {
                    // Stopped while the device was still coming up; do not leave an IOProc behind.
                    device.stop()
                    return
                }
                if self.transcribers[component] == nil || Transcriber.isModelReady {
                    self.setState(component, .live)
                }
                // The device came up, so this install has demonstrably been allowed to use it. That
                // is what makes a later refusal legible as a regression rather than as a user who
                // never granted it — see `Permissions.hasEverCaptured`.
                Permissions.noteCaptureSucceeded(capability)
                self.noteOutput(component)
                self.publishState()
            } catch {
                guard let self, self.audioRunIDs[component] == runID, !Task.isCancelled else { return }
                self.teardownAudio(component)
                // A start that failed because the capability is gone is a permission story, not a
                // device error, and the boundary that saw the refusal has already lowered the grant
                // by the time the throw arrives here. Without this the state carried an opaque HAL
                // status — "System audio tap could not be created (1852797029)" — with no route to
                // the switch, until the maintenance loop got round to the same conclusion 30 s later.
                self.setState(
                    component,
                    Permissions.check(capability)
                        ? .blocked("\(component.label) stopped — \(error.localizedDescription)")
                        : self.missingPermissionState(component, capability))
                self.publishState()
            }
        }
    }

    /// Installs the local fallback for one audio run, but only after the socket has lost the
    /// ability to carry the audio. Connecting and signed-in idle are deliberately excluded:
    /// ListenSocket buffers both states, so eagerly starting two Parakeet managers there would
    /// spend the steady-state memory budget on a path cloud is already covering.
    ///
    /// The invariant is: every chunk still goes to the cloud; local receives only chunks for which
    /// TranscriptOwnership has selected fallback ownership. Once a local instance exists, it
    /// remains available during reconnects, and its bounded Transcriber buffer absorbs model load
    /// latency. The run id makes stop/restart a hard ownership boundary.
    private func startLocalFallbackIfNeeded(
        component: CaptureComponent,
        runID: UUID,
        decision: AudioCaptureDecision,
        segmentSource: SegmentSource,
        lines: AsyncStream<TranscriptLine>.Continuation?,
        cloudState: ListenSocket.State
    ) -> Transcriber? {
        guard audioRunIDs[component] == runID, decision.startLocalSTT else { return nil }
        if let transcriber = transcribers[component] { return transcriber }
        guard TranscriptOwnership.shouldStartLocalFallback(
            when: cloudState, isSignedIn: OmiAuth.shared.isSignedIn) else { return nil }

        let transcriber = Transcriber(source: segmentSource)
        transcribers[component] = transcriber

        // Side task: never await before device start. A throw must not tear down capture
        // (AudioCaptureDecision.teardownCaptureOnLocalSTTFailure is always false).
        let localStart = Task { [weak self] in
            await transcriber.setOnLine { text, startedAt, endedAt in
                lines?.yield(
                    TranscriptLine(
                        text: text, startedAt: startedAt, endedAt: endedAt, source: segmentSource))
            }
            guard !Task.isCancelled,
                  let self,
                  self.audioRunIDs[component] == runID,
                  self.transcribers[component] != nil else { return }
            if !Transcriber.isModelReady {
                // ~600 MB on first run. Say so rather than looking silently broken for minutes.
                self.setState(
                    component,
                    .starting(
                        "\(component.label) warming up — first run downloads the transcription model"))
                self.publishState()
            }
            do {
                try await transcriber.start()
                await MainActor.run {
                    guard self.audioRunIDs[component] == runID,
                          self.transcribers[component] != nil else { return }
                    self.localStarts[component] = nil
                    if case .starting = self.componentStates[component] {
                        self.setState(component, .live)
                    }
                    self.publishState()
                }
            } catch {
                await MainActor.run {
                    guard self.audioRunIDs[component] == runID,
                          self.transcribers[component] != nil else { return }
                    self.localStarts[component] = nil
                    if Task.isCancelled { return }
                    ContextLog.error(
                        "\(component.label) local transcription unavailable — "
                            + "\(error.localizedDescription). Cloud transcription continues.",
                        "engine")
                    if !decision.teardownCaptureOnLocalSTTFailure {
                        self.publishState()
                        return
                    }
                    self.teardownAudio(component)
                    self.setState(
                        component,
                        .blocked("\(component.label) stopped — \(error.localizedDescription)"))
                    self.publishState()
                }
            }
        }
        localStarts[component] = localStart
        return transcriber
    }

    private func makeAudioSource(_ component: CaptureComponent) -> AudioSource? {
        switch component {
        case .microphone:
            return MicCapture()
        case .systemAudio:
            // Redundant against the deployment target on purpose — the availability checker will
            // not take the platform floor as proof.
            if #available(macOS 14.4, *) { return SystemAudioCapture() }
            setState(component, .off("\(component.label) off — needs macOS 14.4 or later"))
            return nil
        case .storage, .screen:
            return nil
        }
    }

    /// The state a component with no permission is in — and the distinction that matters most in
    /// this whole file.
    ///
    /// **Never granted is `off`.** The app is doing exactly what it was allowed to do; a user who
    /// declined system audio has not got a broken recorder and must not be told they have, every
    /// day, forever.
    ///
    /// **A grant this install has actually used and no longer has is `blocked`.** That is a promise
    /// that has stopped being kept, and macOS makes it silently: a Screen Recording grant is keyed
    /// to the app's code signature, so re-signing the bundle — or shipping an update under a
    /// different identity — drops it while a microphone grant, keyed differently, survives. Measured
    /// here on 2 August 2026: the last screen frame landed at 14:20:48, the bundle was re-signed at
    /// 14:33:28, and nothing was captured or said for the next twenty-nine hours.
    private func missingPermissionState(
        _ component: CaptureComponent, _ capability: Capability
    ) -> ComponentState {
        Self.missingPermissionState(
            label: component.label,
            capability: capability,
            hasEverCaptured: Permissions.hasEverCaptured(capability))
    }

    /// The rule on its own, because the distinction above is the part with a wrong answer available
    /// and every input to it is something only this Mac can answer. The sentence is
    /// `Permissions.staleGrantReason`, shared with the screen half rather than written twice: all
    /// three capabilities lose their grant to the same `tccd` code-requirement mismatch, and the
    /// remedy for it — off and back on, not "back on" — has to be the same words wherever it is said.
    nonisolated static func missingPermissionState(
        label: String, capability: Capability, hasEverCaptured: Bool
    ) -> ComponentState {
        guard hasEverCaptured else { return .off("\(label) off — permission not granted") }
        return .blocked(Permissions.staleGrantReason(subject: label, for: capability))
    }

    private func stopAudio(_ component: CaptureComponent, reason: String) {
        starts[component]?.cancel()
        teardownAudio(component)
        setState(component, .off(reason))
    }

    /// Releases everything one audio source owns. Runs on a clean stop and after a failure alike,
    /// so a half-built pipeline never leaks an IOProc, a tap, or a pump task.
    private func teardownAudio(_ component: CaptureComponent) {
        starts[component] = nil
        audioRunIDs[component] = nil
        localStarts.removeValue(forKey: component)?.cancel()
        chunkFeeds[component]?.finish()  // ends the pump's `for await`
        chunkFeeds[component] = nil
        pumps[component]?.cancel()
        pumps[component] = nil
        audioSources[component]?.stop()
        audioSources[component] = nil
        if let transcriber = transcribers.removeValue(forKey: component) {
            // Flushes the window in flight. On quit this never gets to run, which costs at most the
            // last partial window — the alternative is blocking termination on the model.
            Task { await transcriber.finish() }
        }
    }

    /// Brings the screen half up, or says — every time, in a state the rest of the app can act on —
    /// exactly why it cannot.
    ///
    /// The `screenNeedsRelaunch` branch is the one that was missing, and it is not a nicety. A grant
    /// made after this process connected to the window server is a grant this process cannot use, so
    /// starting a watcher on the strength of the preflight produces the worst state available: a
    /// stream the engine believes is live, ticking every three seconds, capturing nothing, and
    /// telling nobody. Refusing to start and saying "reopen me" is the honest answer, and it is the
    /// only one that leads anywhere.
    private func startScreen() {
        // The watcher handle, not the component state: a stalled watcher is not live and must not be
        // joined by a second one.
        guard screenWatcher == nil else { return }
        guard SettingsStore.shared.screenCaptureEnabled else {
            setState(.screen, .off("Screen capture is off in Settings"))
            return
        }
        if let block = Permissions.screenBlock() {
            setState(.screen, blockState(block))
            if block.isRegression {
                // `info` is evicted from the unified log within minutes; the last time this happened
                // it left no trace at all of the twenty-nine hours that followed.
                ContextLog.milestone(block.reason, "engine")
            }
            return
        }
        let watcher = ScreenWatcher()
        let store = self.store
        watcher.onFrame = { [weak self] frame in
            store.record(frame)
            // A frame on its way to the database is the only unarguable proof the screen half
            // works. It is what makes a later refusal legible as "this stopped working" rather than
            // as "you never turned it on".
            self?.noteOutput(.screen)
            Permissions.noteCaptureSucceeded(.screen)
        }
        watcher.onAXNodes = { records in store.record(axNodes: records) }
        // Every reason the watcher stands down reaches the menu bar and `capture-state.json`, and
        // they do **not** all mean the same thing. "Pause on Inactivity" is the app doing as it was
        // told and leaves the recorder healthy; a dropped grant and a WindowServer that has stopped
        // answering are failures and have to make the whole app read as degraded. One string could
        // not carry that difference, which is why this channel now carries a `ScreenStandDown`.
        watcher.onStandDown = { [weak self] standDown in
            guard let self else { return }
            guard let standDown else {
                self.setState(.screen, .live)
                self.publishState()
                return
            }
            switch standDown {
            case .paused(let sentence):
                self.setState(.screen, .off(sentence))
            case .blocked(let block):
                self.setState(.screen, self.blockState(block))
            case .stalled(let sentence):
                self.setState(.screen, .stalled(sentence))
            }
            self.publishState()
        }
        watcher.start(interval: HostArchitecture.screenCaptureInterval)
        screenWatcher = watcher
        setState(.screen, .live)
        publishState()
    }

    /// A screen block as a component state. Only "never granted" is `off` — everything else is
    /// something the user has to be shown.
    private func blockState(_ block: Permissions.ScreenBlock) -> ComponentState {
        block == .notGranted ? .off(block.reason) : .blocked(block.reason)
    }

    private func stopScreen(reason: String) {
        // `stop()` is what clears the hand-overs, and it clears *all* of them. Doing it here left
        // `onAXNodes` set: cancelling the loop does not resume a tick already suspended in OCR or in
        // an accessibility walk, so that tick finished and wrote a window's full accessibility text
        // into the database after the user had switched screen capture off — into rows that no
        // `frames` row references and that pruning therefore never reaches.
        screenWatcher?.stop()
        screenWatcher = nil
        // Whatever the watcher was last standing down for is no longer why capture is off: the
        // caller owns the reason now, and a stale "no activity for 5 minutes" underneath a
        // deliberate stop would contradict it.
        setState(.screen, .off(reason))
        publishState()
    }

    private func observeScreenCaptureSetting() {
        SettingsStore.shared.$screenCaptureEnabled
            .dropFirst()
            .removeDuplicates()
            .sink { [weak self] enabled in
                guard let self, !self.isPaused else { return }
                if enabled {
                    self.startScreen()
                } else {
                    self.stopScreen(reason: "Screen capture is off in Settings")
                }
            }
            .store(in: &settingsSubscriptions)
    }

    // MARK: - Transcript lines

    /// One consumer for both transcribers, on the main actor. Lines arrive from two actors on two
    /// threads; funnelling them through a single stream keeps `lastLine` and the session boundary
    /// decision in one order.
    private func startLineConsumer() {
        let (lines, feed) = AsyncStream<TranscriptLine>.makeStream(
            of: TranscriptLine.self, bufferingPolicy: .bufferingNewest(256))
        lineFeed = feed
        lineTask = Task { [weak self] in
            for await line in lines {
                guard let self else { return }
                self.handleLine(line)
            }
        }
    }

    private func handleLine(_ line: TranscriptLine) {
        lastLine = line.text
        // Read the frontmost app here: the store's queue must not touch AppKit, and by the time a
        // session opens on that queue the user may already have switched windows.
        store.record(line, appHint: NSWorkspace.shared.frontmostApplication?.localizedName)
    }

    // MARK: - Published state

    /// The one writer of component state, and the one place a transition is logged.
    ///
    /// Idempotent by design: a steady failure logs once rather than every thirty seconds for as long
    /// as it lasts. `off` logs at info because it is the app doing as it was told — a deliberate
    /// stand-down at error level would teach whoever reads these logs to ignore the level, which is
    /// how a real failure goes unread.
    private func setState(_ component: CaptureComponent, _ next: ComponentState) {
        guard componentStates[component] != next else { return }
        let wasLive = componentStates[component]?.isLive ?? false
        componentStates[component] = next

        // The single point every capture transition passes through, which is why the analytics hook
        // is here and not in the four start/stop methods: those have early returns, failure paths and
        // a teardown that runs on both a clean stop and a crash, so instrumenting them would have
        // meant four chances to miss a transition. This one is already guarded by the
        // did-it-actually-change check above, so it cannot double-count either.
        if wasLive != next.isLive, let source = AnalyticsEvent.CaptureSource(component) {
            UsageClock.shared.mark(source, live: next.isLive)
            ContextAnalytics.record(.captureStateChanged(source: source, live: next.isLive))
        }

        switch next {
        case .live:
            ContextLog.info("\(component.label) is capturing", "engine")
        case .blocked(let reason), .stalled(let reason):
            ContextLog.error(reason, "engine")
        case .off(let reason):
            ContextLog.info(reason, "engine")
        case .starting(let note):
            if let note { ContextLog.info(note, "engine") }
        }
    }

    private func isLive(_ component: CaptureComponent) -> Bool {
        componentStates[component]?.isLive ?? false
    }

    private var liveComponents: [CaptureComponent] {
        CaptureComponent.allCases.filter { isLive($0) }
    }

    /// Stamps a component as having produced something just now. Deliberately does **not**
    /// republish: this is called on every audio chunk and every stored frame, and rewriting the
    /// heartbeat file at that rate would cost more than the fact is worth. The next publish — at
    /// worst thirty seconds away, from the maintenance loop — carries it.
    private func noteOutput(_ component: CaptureComponent) {
        lastOutput[component] = ContextTime.now
    }

    /// **The whole published state, as a pure function of what each component is doing.**
    ///
    /// Static and parameterised because this is the function with a wrong answer available, and the
    /// wrong answer it used to give is the defect: `capturing = !isPaused && !running.isEmpty &&
    /// !storageFailed` is an *or* over three independent sensors, and every reader downstream — the
    /// menu bar, `capture-state.json`, the MCP `status` tool, the user — takes it for an *and*. With
    /// a live microphone and a dead screen it said `true`, for twenty-nine hours, over a database
    /// that had not taken a screen frame since the previous afternoon.
    ///
    /// Nothing here can say it again: `CaptureState` derives `capturing` from the stream reports and
    /// there is no parameter for it. What remains is assembling the reports honestly, which is what
    /// the tests drive.
    ///
    /// Truthfulness rules, in the order they are applied:
    /// - Paused is paused, and says so instead of listing the reasons a paused pipeline has.
    /// - A store that has *failed* to open means nothing is being recorded whatever the sensors are
    ///   doing (``CaptureHealth``). A store that is merely still opening does not: the sensors are
    ///   genuinely capturing and `EngineStore` is holding the result.
    /// - No sensor live and nothing yet gone wrong is the launch window, and it says so rather than
    ///   presenting an empty reason, which reads as "everything is fine".
    static func publishedState(
        components: [CaptureComponent: ComponentState],
        isPaused: Bool,
        capabilities: [CapabilityReport] = [],
        lastOutput: [CaptureComponent: Double] = [:],
        updatedAt: Double = ContextTime.now,
        transcriptionGap: String? = nil
    ) -> CaptureState {
        // Fixed order so neither the popover string nor the stream list shuffles between renders.
        let states = CaptureComponent.allCases.map { ($0, components[$0] ?? .starting(nil)) }
        let streams = states.map { pair in
            StreamReport(
                name: pair.0.streamName,
                state: pair.1.wire,
                detail: pair.1.detail,
                lastOutputAt: lastOutput[pair.0])
        }

        let reason: String?
        if isPaused {
            reason = "Paused"
        } else {
            var notes = states.compactMap { $0.1.detail }
            if let transcriptionGap { notes.append(transcriptionGap) }
            if notes.isEmpty {
                reason = states.contains { $0.1.isLive } ? nil : startingUpReason
            } else {
                reason = notes.joined(separator: " · ")
            }
        }

        return CaptureState(
            streams: streams,
            pausedReason: reason,
            capabilities: capabilities,
            updatedAt: updatedAt)
    }

    /// `synchronously` for pause and quit: an async write can lose the race with process teardown,
    /// and the heartbeat is the only thing telling `context-for-claude-mcp` what happened.
    private func publishState(synchronously: Bool = false) {
        let state = Self.publishedState(
            components: componentStates,
            isPaused: isPaused,
            // Not `capabilities`: those are grouped for the menu bar, and a group verdict written
            // under a stream's name is read by every machine downstream as that stream's grant.
            capabilities: Permissions.report(),
            lastOutput: lastOutput,
            transcriptionGap: transcriptionGapReason)

        if isCapturing != state.capturing { isCapturing = state.capturing }
        if health != state.health { health = state.health }
        if pausedReason != state.pausedReason { pausedReason = state.pausedReason }

        // Before the write, so a timer tick that fires in between re-stamps the new state, not the
        // one it replaced.
        heartbeat.set(state)
        if synchronously {
            heartbeatQueue.sync { Self.writeHeartbeat(state) }
        } else {
            heartbeatQueue.async { Self.writeHeartbeat(state) }
        }
    }

    /// `nonisolated` on purpose: this runs on `heartbeatQueue`, and inheriting the class's main-actor
    /// isolation would put a synchronous file write back on the main thread — the exact thing the
    /// queue exists to avoid.
    private nonisolated static func writeHeartbeat(_ state: CaptureState) {
        do {
            try state.write()
        } catch {
            ContextLog.error("Heartbeat write failed: \(error.localizedDescription)", "engine")
        }
    }

    /// The heartbeat has to beat faster than `CaptureState.stalenessSeconds` or `status()` reports a
    /// running app as gone.
    ///
    /// A `DispatchSourceTimer` on `heartbeatQueue`, not a `Task`, and that is the point. Every task
    /// on this class runs on the main actor, and the main thread can be taken away for minutes at a
    /// time by a synchronous system dialog — a Keychain authorization prompt is the one that
    /// actually did it here. A heartbeat that stops when the main thread stops makes the product
    /// claim it is not running at the exact moment a reader needs to know that it is, so this one
    /// beats independently. It re-stamps the last state the main actor published: freshness says the
    /// process is alive, the fields say what it last knew about itself.
    private func startHeartbeatTimer() {
        let timer = DispatchSource.makeTimerSource(queue: heartbeatQueue)
        timer.schedule(deadline: .now() + .seconds(30), repeating: .seconds(30), leeway: .seconds(1))
        let snapshot = heartbeat
        timer.setEventHandler { Self.writeHeartbeat(snapshot.restamped()) }
        timer.resume()
        heartbeatTimer = timer
    }

    /// Retries what launch could not finish: a store on a volume that was busy, a permission granted
    /// after launch, a source that died. Separate from the heartbeat on purpose — recovery needs the
    /// main actor, and the heartbeat must not be hostage to it.
    ///
    /// Thirty seconds is also the cadence at which a permission is re-read, which is what makes
    /// "constantly working" more than an intention: a grant restored in System Settings is noticed
    /// within half a minute with nothing for the user to press. What that cadence **cannot** fix is
    /// a Screen Recording grant made after this process connected to the window server — those
    /// rights are fixed at connection time — so that case is detected and named rather than silently
    /// retried forever; see `startScreen`.
    private func startMaintenanceLoop() {
        maintenanceTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                guard let self else { return }
                if self.isPaused {
                    self.publishState()
                } else {
                    await self.ensureStorage()
                    self.refreshCapabilities()
                    self.superviseSources()
                }
            }
        }
    }

    /// The failures with no callback behind them.
    ///
    /// Every recovery path in this file so far is event-driven: a start that throws, a watcher that
    /// reports, a permission that is re-read. None of those fire for a source that simply *stops* —
    /// `MicCapture` gives up rebuilding after three attempts and tears itself down deliberately, "so
    /// the app reports state from `isRunning`", except that nothing was ever reading `isRunning`
    /// after the start succeeded. That is the same failure class as the screen, one stream over: a
    /// component believed live with nothing checking.
    private func superviseSources() {
        guard !isPaused else { return }
        for component in [CaptureComponent.microphone, .systemAudio] where isLive(component) {
            guard let source = audioSources[component] else { continue }
            if !source.isRunning {
                teardownAudio(component)
                setState(component, .blocked("\(component.label) stopped — the audio device went away"))
                startAudio(component)
                continue
            }
            // The device says it is running and no bytes have arrived. `MicCapture`'s own
            // one-second silence watchdog rebuilds the stack three times before it gives up, so
            // anything reaching this branch has outlived every recovery the device layer has.
            if let last = lastOutput[component], ContextTime.now - last > Self.audioSilenceSeconds {
                setState(
                    component,
                    .stalled(
                        "\(component.label) has delivered no audio for "
                            + "\(Int(Self.audioSilenceSeconds)) seconds"))
            }
        }
        recycleStalledScreen()
        publishState()
    }

    /// Rebuilds a screen watcher the WindowServer has stopped answering.
    ///
    /// Some of what it refuses is recoverable — a display reconfiguration, a fast user switch, a
    /// wake from sleep — and a fresh `SCShareableContent` connection is the cheapest thing that
    /// clears it, so this is worth one attempt. What it **cannot** clear is capture rights this
    /// process is not carrying, because those were decided when the process connected to the window
    /// server and no amount of restarting a `Task` inside it changes them. So the rebuild is bounded
    /// to one every ``screenRecycleSeconds`` and the stalled sentence keeps saying "reopening
    /// usually fixes it", which is the truth rather than a promise this code can keep.
    private func recycleStalledScreen() {
        guard case .stalled(let reason)? = componentStates[.screen] else {
            screenRecycledAt = nil
            return
        }
        let now = ContextTime.now
        if let screenRecycledAt, now - screenRecycledAt < Self.screenRecycleSeconds { return }
        screenRecycledAt = now
        ContextLog.error("Rebuilding the screen watcher after a stall: \(reason)", "engine")
        stopScreen(reason: reason)
        startScreen()
    }

    private func startTodaySecondsLoop() {
        todayTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                guard let self else { return }
                await self.refreshTodaySeconds()
            }
        }
    }

    private func refreshTodaySeconds() async {
        let seconds = await store.todaySeconds()
        if todaySeconds != seconds { todaySeconds = seconds }
    }

    // MARK: - Quit

    /// `queue: nil` on purpose: with an `OperationQueue` the block is *enqueued*, and the main run
    /// loop may never take another pass before the process exits — the flush below would be skipped
    /// exactly when it matters. A nil queue runs the block synchronously on the posting thread,
    /// which for `willTerminate` is always the main thread.
    private func observeTermination() {
        NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification, object: nil, queue: nil
        ) { _ in
            MainActor.assumeIsolated { Engine.shared.handleTermination() }
        }
    }

    /// The last thing the app does. Everything here is synchronous: an `await` issued after AppKit
    /// starts tearing the process down never resumes, and a session left open looks — forever — like
    /// one that is still running.
    private func handleTermination() {
        heartbeatTimer?.cancel()
        heartbeatTimer = nil
        maintenanceTask?.cancel()
        accountTask?.cancel()
        todayTask?.cancel()
        stopAllSources(reason: "Context for Claude is not running")
        store.closeOpenSession()
        lineFeed?.finish()
        lineTask?.cancel()

        isCapturing = false
        // The same sentence `Queries.status` uses for a stale heartbeat, so Claude reads one story.
        pausedReason = "Context for Claude is not running"
        let final = CaptureState(
            capturing: false, pausedReason: pausedReason, capabilities: Permissions.report())
        // Snapshot first, then write on the heartbeat queue: a timer tick already in flight runs
        // ahead of this write and re-stamps `final` rather than resurrecting a "capturing" state on
        // top of it.
        heartbeat.set(final)
        heartbeatQueue.sync { Self.writeHeartbeat(final) }
        // The closing bracket, and the only proof this teardown actually ran. Everything above it
        // is what stops `status()` reporting a recording that ended hours ago; a run whose last
        // line is the delegate's termination milestone and *not* this one is a run where the
        // session was left open, which is a different bug from the one that ended the process.
        ContextLog.milestone("Engine stopped", "engine")
    }
}

/// Chooses one transcript owner for each audio chunk. Cloud is preferred only after the socket is
/// truly live; every other state is an explicit local-fallback state so a sign-in delay, reconnect,
/// or permanent cloud refusal never turns capture into silence.
enum TranscriptOwnership {
    static func shouldFeedLocalFallback(when cloudState: ListenSocket.State) -> Bool {
        cloudState != .live
    }

    /// Starting local ASR is stricter than feeding an already-running instance. The socket holds
    /// PCM while connecting (including signed-in idle), so those states do not justify loading the
    /// model. Signed-out idle and every explicit refusal/offline state still need local startup.
    static func shouldStartLocalFallback(
        when cloudState: ListenSocket.State, isSignedIn: Bool
    ) -> Bool {
        switch cloudState {
        case .live, .connecting:
            return false
        case .idle:
            return !isSignedIn
        case .failed, .paywalled, .airgapped:
            return true
        }
    }
}

// MARK: - Store writer

/// Owns the one writable `ContextStore`, the open session, and nothing else.
///
/// A serial `DispatchQueue` rather than an actor for one reason: quitting has to flush
/// synchronously. Every stored property below is touched only inside `queue`, which is what makes
/// the `@unchecked Sendable` honest — and what lets two transcribers race into `record` without
/// ever splitting a session in half.
private final class EngineStore: @unchecked Sendable {
    private let queue = DispatchQueue(label: "com.omi.context-for-claude.store", qos: .utility)
    /// Retention runs here and never on `queue`. Age-based pruning unlinks one file per deleted
    /// frame — thousands of them on a Mac that has been capturing for a month — and the queue that
    /// does that must not be the queue a transcript line is waiting in.
    private let retentionQueue = DispatchQueue(
        label: "com.omi.context-for-claude.retention", qos: .background)
    private let policy = SessionPolicy()

    private var store: ContextStore?

    /// The open store, for read-only surfaces that need one — the Rewind window in particular.
    ///
    /// Read through `queue` like every other access, because the store is opened lazily *on* that
    /// queue: touching the property directly would race the open. Returns nil until the first open
    /// succeeds, and callers must handle that rather than force it — a timeline window that appears
    /// with no database behind it is worse than one that declines to appear.
    func currentStore() -> ContextStore? { queue.sync { store } }

    private var openSessionId: Int64?
    /// The latest segment end across *both* transcribers. Session boundaries are a property of the
    /// conversation, not of one microphone.
    private var lastSegmentEndedAt: Double?

    /// One write the sensors produced before there was a database to put it in.
    private enum PendingWrite {
        case line(TranscriptLine, appHint: String?)
        case frame(Frame)
        case axNodes([AXNodeRecord])
    }

    /// Capture now starts before the store opens, so everything produced in that window has to go
    /// somewhere. Bounded and oldest-dropped: an open that is never going to succeed must cost a
    /// bounded amount of memory, and if something has to go it is the oldest, not the newest.
    ///
    /// A screen frame every 3 s plus a transcript line every 10 s from each of two sources is about
    /// 32 writes a minute, so this holds roughly half an hour — comfortably longer than any store
    /// open that is going to succeed at all.
    private static let pendingLimit = 1_000
    private var pending: [PendingWrite] = []
    private var droppedWhileOpening = 0
    private var hasLoggedDrop = false

    /// Opens the database. Returns a human-readable reason on failure, nil on success. Idempotent:
    /// a retry after a transient failure must never end up with two writers on one file.
    func open() async -> String? {
        await withCheckedContinuation { (continuation: CheckedContinuation<String?, Never>) in
            queue.async {
                guard self.store == nil else { return continuation.resume(returning: nil) }
                do {
                    let opened = try ContextStore()
                    self.store = opened
                    self.closeSessionsLeftOpen(opened)
                    ContextLog.info("Store opened at \(opened.databaseURL.path)", "store")
                    // Inside the same queue block, before the continuation resumes: the queue is
                    // serial, so nothing captured after the open can be written ahead of what was
                    // captured before it — which is what keeps session boundaries in order.
                    self.flushPending(into: opened)
                    continuation.resume(returning: nil)
                } catch {
                    continuation.resume(
                        returning: "Could not open the database: \(error.localizedDescription)")
                }
            }
        }
    }

    /// Whether this database already holds screen frames — the evidence that seeds "screen capture
    /// has worked on this Mac before". On `queue` like every other read here, so a launch never
    /// blocks the main thread behind a database that is busy flushing what it just held.
    func hasAnyFrames() async -> Bool {
        await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
            queue.async {
                guard let store = self.store else { return continuation.resume(returning: false) }
                continuation.resume(returning: (try? Queries.hasAnyFrames(store)) ?? false)
            }
        }
    }

    func record(_ line: TranscriptLine, appHint: String?) {
        queue.async {
            guard let store = self.store else {
                return self.hold(.line(line, appHint: appHint))
            }
            self.append(line, appHint: appHint, to: store)
        }
    }

    func record(_ frame: Frame) {
        queue.async {
            guard let store = self.store else { return self.hold(.frame(frame)) }
            self.insert(frame, into: store)
        }
    }

    func record(axNodes records: [AXNodeRecord]) {
        queue.async {
            guard let store = self.store else { return self.hold(.axNodes(records)) }
            self.insert(axNodes: records, into: store)
        }
    }

    /// Retention, deferred: `delay` after the store opens, on a background queue, off the writer
    /// queue entirely. `ContextStore` serialises its own writer, so a sweep waits behind a live
    /// insert rather than the other way round — which is the correct direction for housekeeping.
    /// At most one sweep an hour. Worst-case overshoot is one active hour of frames — well under
    /// 1% of the cap — while the sweep itself stats every frame on disk, which is not something to
    /// do beside live capture more often than that.
    private static let retentionIntervalSeconds: TimeInterval = 3600

    func scheduleRetentionSweep(olderThanDays days: Int, after delay: TimeInterval) {
        retentionQueue.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self else { return }
            // `store` is `queue`'s property — that is what makes `@unchecked Sendable` honest here.
            // Read it there, then do the sweep off it.
            let store: ContextStore? = self.queue.sync { self.store }
            guard let store else { return }
            let defaults = UserDefaults.standard
            let strategy: StorageStrategy = {
                guard let raw = defaults.string(forKey: "context.settings.storageStrategy"),
                    let value = StorageStrategy(rawValue: raw) else { return .off }
                return value
            }()
            let limitBytes: Int64 = {
                if let stored = defaults.object(forKey: "context.settings.storageLimitBytes") as? Int {
                    return StorageLimit.clamp(Int64(stored))
                }
                return StorageLimit.defaultBytes
            }()
            if strategy == .limit {
                do {
                    // Both bounds, tighter one wins. Age alone is not enough on a machine that
                    // captures heavily: 30 days of dense capture outgrows any disk long before the
                    // oldest frame is old enough to delete.
                    let removed = try store.enforceRetention(olderThanDays: days, toFitBytes: limitBytes)
                    if removed > 0 {
                        ContextLog.info("Retention removed \(removed) frames", "store")
                    }
                } catch {
                    ContextLog.error("Frame retention sweep failed: \(error.localizedDescription)", "store")
                }
            }
            // Re-arm. This app is meant to run for weeks at login, so a sweep that happens once per
            // launch is a sweep that happens once a fortnight — which is how an unbounded store
            // gets there in the first place.
            self.scheduleRetentionSweep(olderThanDays: days, after: Self.retentionIntervalSeconds)
        }
    }

    // MARK: - Writes (queue only)

    private func append(_ line: TranscriptLine, appHint: String?, to store: ContextStore) {
        do {
            if openSessionId == nil
                || policy.shouldOpenNewSession(
                    lastSegmentEndedAt: lastSegmentEndedAt,
                    nextSegmentStartedAt: line.startedAt)
            {
                if let previous = openSessionId {
                    try store.closeSession(previous, at: lastSegmentEndedAt ?? line.startedAt)
                    // After the write and inside the `do`, so a close that threw is not counted.
                    UsageClock.shared.noteConversation()
                    // A closed session is a finished conversation; the uploader turns it into a
                    // real one in the user's Omi account. Enqueued, not sent — it survives being
                    // signed out, offline, or rate limited.
                    Task { @MainActor in ConversationUploader.shared.enqueue(sessionId: previous) }
                }
                openSessionId = try store.openSession(at: line.startedAt, appHint: appHint)
            }
            guard let sessionId = openSessionId else { return }

            let segment = Segment(
                sessionId: sessionId,
                startedAt: line.startedAt,
                endedAt: line.endedAt,
                source: line.source,
                text: line.text,
                speakerLabel: line.speakerLabel,
                personId: line.personId,
                backendConversationId: line.backendConversationId,
                backendSegmentId: line.backendSegmentId)
            // Wrapped rather than followed by an emit, so the report cannot outlive a throw. A
            // cloud segment counts the same as a local one: it is this Mac's audio, transcribed a
            // hop away. Once per install; every later write reports nothing.
            try ContextAnalytics.recordFirstArtifact(.conversation) {
                if segment.backendConversationId != nil, segment.backendSegmentId != nil {
                    try store.upsertCloudSegment(segment)
                } else {
                    try store.insertSegment(segment)
                }
            }
            // `max`, because a 10 s window from the other transcriber can land out of order and
            // must not drag the session's end backwards.
            lastSegmentEndedAt = max(lastSegmentEndedAt ?? line.endedAt, line.endedAt)
        } catch {
            ContextLog.error("Dropped a transcript line: \(error.localizedDescription)", "store")
        }
    }

    private func insert(_ frame: Frame, into store: ContextStore) {
        do {
            try ContextAnalytics.recordFirstArtifact(.screen) { try store.insertFrame(frame) }
        } catch {
            ContextLog.error("Dropped a screen frame: \(error.localizedDescription)", "store")
        }
    }

    /// Held in the same pen as frames and replayed in the same order, so the rows a frame's root hash
    /// points at are always written before the frame itself — even across a store that opened late.
    private func insert(axNodes records: [AXNodeRecord], into store: ContextStore) {
        do {
            try store.insertAXNodes(records, firstSeenFrameId: nil)
        } catch {
            ContextLog.error("Dropped an accessibility tree: \(error.localizedDescription)", "store")
        }
    }

    // MARK: - Holding pen (queue only)

    /// Queues one write until the store opens, dropping the oldest on overflow — and saying so.
    /// Silence here is precisely how capture disappears without anyone noticing.
    private func hold(_ write: PendingWrite) {
        pending.append(write)
        guard pending.count > Self.pendingLimit else { return }
        let overflow = pending.count - Self.pendingLimit
        pending.removeFirst(overflow)
        droppedWhileOpening += overflow
        guard !hasLoggedDrop else { return }  // once per opening, not once per dropped frame
        hasLoggedDrop = true
        ContextLog.error(
            "The store is still opening and the \(Self.pendingLimit)-write hold is full; "
                + "dropping the oldest capture from here on",
            "store")
    }

    private func flushPending(into store: ContextStore) {
        guard !pending.isEmpty else { return }
        let held = pending
        pending.removeAll()
        for write in held {
            switch write {
            case .line(let line, let appHint): append(line, appHint: appHint, to: store)
            case .frame(let frame): insert(frame, into: store)
            case .axNodes(let records): insert(axNodes: records, into: store)
            }
        }
        if droppedWhileOpening > 0 {
            ContextLog.error(
                "Wrote \(held.count) captures held while the store opened; "
                    + "\(droppedWhileOpening) older ones were dropped",
                "store")
        } else {
            ContextLog.info("Wrote \(held.count) captures held while the store opened", "store")
        }
        droppedWhileOpening = 0
        hasLoggedDrop = false
    }

    /// Wall-clock seconds of today covered by a session. Sessions never overlap, so summing their
    /// clipped spans is the honest answer to "how much of today did Context for Claude actually see".
    func todaySeconds() async -> Double {
        await withCheckedContinuation { (continuation: CheckedContinuation<Double, Never>) in
            queue.async {
                guard let store = self.store else { return continuation.resume(returning: 0) }
                let now = ContextTime.now
                let startOfToday = Calendar.current
                    .startOfDay(for: Date(timeIntervalSince1970: now))
                    .timeIntervalSince1970
                // Reach back a day so a session that began before midnight still contributes the
                // part of it that belongs to today.
                let summaries =
                    (try? Queries.sessions(
                        store, since: startOfToday - 86_400, until: nil, limit: 500)) ?? []

                var total: Double = 0
                for summary in summaries {
                    let start = max(summary.startedAt, startOfToday)
                    let end = min(summary.endedAt ?? now, now)
                    if end > start { total += end - start }
                }
                continuation.resume(returning: total)
            }
        }
    }

    /// Closes whatever session is open. `sync` on purpose: pause and quit both need it finished
    /// before the next line runs, and on quit an `await` would never resume.
    func closeOpenSession() {
        queue.sync {
            guard let store = self.store, let id = self.openSessionId else { return }
            if (try? store.closeSession(id, at: self.lastSegmentEndedAt ?? ContextTime.now)) != nil {
                UsageClock.shared.noteConversation()
            }
            self.openSessionId = nil
            Task { @MainActor in ConversationUploader.shared.enqueue(sessionId: id) }
        }
    }

    /// A crash or a force-quit leaves `endedAt` null forever, so an old session would still look
    /// live — and today's total would count a conversation from three days ago as still running.
    /// Close them at their last line before anything new opens.
    private func closeSessionsLeftOpen(_ store: ContextStore) {
        let sessions = (try? Queries.sessions(store, since: nil, until: nil, limit: 200)) ?? []
        for session in sessions where session.endedAt == nil {
            // The summary already carries the last line's time, so pulling the transcript back to
            // recover it read the whole conversation — every segment, its text, for all 200
            // sessions in the scan — on every launch, to close what is usually the single session a
            // crash left open. `sessions` measures an unclosed session to `MAX(segments.endedAt)`
            // in the query that produced the row, and to `startedAt` when it holds no lines at all,
            // which is the same fallback this loop used to spell out.
            let lastLineAt = session.startedAt + session.durationSeconds
            if (try? store.closeSession(session.id, at: lastLineAt)) != nil {
                UsageClock.shared.noteConversation()
            }
            // Sessions orphaned by a crash still belong in the account.
            let orphan = session.id
            Task { @MainActor in ConversationUploader.shared.enqueue(sessionId: orphan) }
        }
    }
}
