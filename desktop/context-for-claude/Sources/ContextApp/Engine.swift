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
/// `transcription` is not a sensor — it is the cloud (Intel) or cloud+local (Silicon) STT gap so
/// menu bar and MCP `status` can report "nothing is being transcribed" without inventing coverage.
private enum CaptureComponent: CaseIterable {
    case storage
    case microphone
    case systemAudio
    case screen
    case transcription

    var capability: Capability? {
        switch self {
        case .storage, .transcription: return nil
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
        case .transcription: return "Transcription"
        }
    }

    var segmentSource: SegmentSource { self == .microphone ? .mic : .system }
}

/// The capture pipeline: three sensors, cloud transcription (plus optional local Parakeet on
/// Apple Silicon), one database writer, and the published state the menu bar and
/// `context-for-claude-mcp` read.
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
    /// Watches cloud socket + sign-in so Intel hosts can surface an honest transcription gap.
    private var transcriptionWatch: Set<AnyCancellable> = []
    /// Sums mic and system into the single stream the backend transcribes.
    private let mixer = AudioMixer()
    /// The latest text seen per backend segment id, so a revised segment replaces rather than
    /// duplicates. Cleared whenever the server rolls to a new conversation.
    private var cloudSegmentText: [String: String] = [:]
    private var cloudConversationId: String?

    static let shared = Engine()

    @Published private(set) var isCapturing = false
    /// Why capture is not whole right now: paused by the user, a permission never granted, or a
    /// source that died. Nil only when everything permitted is actually running.
    @Published private(set) var pausedReason: String?
    @Published private(set) var capabilities: [CapabilityReport] = []
    /// Wall-clock seconds of today that Context for Claude actually covered. The one number in the menu bar.
    @Published private(set) var todaySeconds: Double = 0
    /// The most recent transcript line, so the popover can show the app is alive.
    @Published private(set) var lastLine: String?

    private let store = EngineStore()
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

    private var hasStarted = false
    private var isPaused = false
    private var isStorageReady = false
    /// What is genuinely capturing right now — the engine's own bookkeeping, not a poll of the
    /// sources, so state never depends on when another object flips its `isRunning`.
    private var running: Set<CaptureComponent> = []
    private var reasons: [CaptureComponent: String] = [:]

    private var audioSources: [CaptureComponent: AudioSource] = [:]
    private var transcribers: [CaptureComponent: Transcriber] = [:]
    private var chunkFeeds: [CaptureComponent: AsyncStream<Data>.Continuation] = [:]
    private var pumps: [CaptureComponent: Task<Void, Never>] = [:]
    private var starts: [CaptureComponent: Task<Void, Never>] = [:]
    /// Silicon-only: Parakeet `start()` side tasks. Cancelled in `teardownAudio` so a stop mid-load
    /// cannot resurrect a pump on a transcriber the engine no longer owns.
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
        capabilities = Permissions.report()
        startLineConsumer()
        // Started with capture, not with the account. The socket reports `.idle` until there is a
        // session and connects when one lands, so putting it behind the sign-in restore would only
        // make it inherit that call's latency.
        startCloudTranscription()

        // 3. Sensors, before storage and before the account. Nothing they produce is lost while the
        //    database opens — `EngineStore` holds it, bounded, until there is somewhere to put it.
        startPermittedSources()
        publishState()

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

        ContextLog.info("Engine started", "engine")
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
                if !self.running.isEmpty || ContextTime.now >= deadline { break }
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
    /// path: cloud is the only ASR, and gaps are reported honestly via `CaptureComponent.transcription`.
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
        }
        let cloud = CaptureHostPolicy.resolvedCloudTranscriptionState(
            socket: snapshot,
            isSignedIn: OmiAuth.shared.isSignedIn
        )
        if let gap = CaptureHostPolicy.cloudTranscriptionGapReason(
            usesLocalSTT: HostArchitecture.usesLocalSTT,
            isSignedIn: OmiAuth.shared.isSignedIn,
            cloud: cloud
        ) {
            note(.transcription, gap)
        } else {
            clear(.transcription)
        }
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
            personId: segment.personId
        )
        lastLine = line.text
        lineFeed?.yield(line)
    }

    func pause() {
        guard !isPaused else { return }
        isPaused = true
        stopAllSources()
        // The socket has to close with the capture. Left open with no audio arriving, the server
        // hangs up at 90 s and the client reconnects on backoff for as long as the app is paused —
        // a reconnect loop against the backend for a user who deliberately stopped recording.
        ListenSocket.shared.stop()
        mixer.stop()
        // Transcription gaps describe a live cloud path. Pause owns the headline; drop the stale
        // note so resume starts clean rather than carrying a reason from the previous session.
        reasons.removeValue(forKey: .transcription)
        // Ends the conversation, not just the capture. The app delegate also routes quit through
        // here, and a session left open reports a recording that stopped hours ago.
        store.closeOpenSession()
        ContextLog.info("Capture paused", "engine")
        publishState(synchronously: true)
    }

    func resume() {
        // Wipe sensor reasons *before* restarting cloud transcription. `startCloudTranscription`
        // calls `refreshTranscriptionGap()`, and wiping after that used to erase the Intel gap so
        // a signed-out resume looked fully healthy with no ASR running.
        if isPaused {
            isPaused = false
            reasons = CaptureHostPolicy.reasonsAfterResumeWipe(reasons, storageKey: .storage)
            capabilities = Permissions.report()
            startPermittedSources()
            ContextLog.info("Capture resumed", "engine")
        }
        startCloudTranscription()
        publishState()
    }

    /// Re-reads the permission state and starts anything that is now allowed but not yet running —
    /// a grant that lands after launch, or a source that failed and can be retried.
    func refreshCapabilities() {
        capabilities = Permissions.report()
        startPermittedSources()
        publishState()
    }

    // MARK: - Sources

    /// Opens the database if it is not open yet. Idempotent, so launch and the maintenance loop's
    /// retry can both call it: a volume that was busy for a minute should not cost the rest of the
    /// session. Nothing that captures waits on it.
    private func ensureStorage() async {
        guard !isStorageReady else { return }
        if let failure = await store.open() {
            note(.storage, failure)
            return
        }
        isStorageReady = true
        clear(.storage)
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

    private func stopAllSources() {
        stopAudio(.microphone)
        stopAudio(.systemAudio)
        stopScreen()
    }

    /// Wires one audio device into the cloud mixer, and optionally a local Parakeet instance on
    /// Apple Silicon. Capture lifecycle must not wait on (or die with) local model load — cloud
    /// transcription needs the chunks either way.
    private func startAudio(_ component: CaptureComponent) {
        guard starts[component] == nil, !running.contains(component) else { return }
        guard let capability = component.capability, Permissions.check(capability) else {
            note(component, "\(component.label) off — permission not granted")
            return
        }
        guard let device = makeAudioSource(component) else { return }

        let decision = AudioCaptureDecision.make(usesLocalSTT: HostArchitecture.usesLocalSTT)
        let segmentSource = component.segmentSource
        let lines = lineFeed
        // A stream rather than a task per chunk: tasks reach an actor in whatever order the pool
        // schedules them, and reordered audio is a corrupted transcript. Bounded, because a stalled
        // consumer must cost a few dropped seconds rather than the whole machine's memory.
        let (chunks, feed) = AsyncStream<Data>.makeStream(
            of: Data.self, bufferingPolicy: .bufferingNewest(512))

        audioSources[component] = device
        chunkFeeds[component] = feed

        let transcriber: Transcriber?
        if decision.startLocalSTT {
            let local = Transcriber(source: segmentSource)
            transcribers[component] = local
            transcriber = local
        } else {
            transcriber = nil
        }

        starts[component] = Task { [weak self] in
            do {
                if let transcriber {
                    await transcriber.setOnLine { text, startedAt, endedAt in
                        lines?.yield(
                            TranscriptLine(
                                text: text, startedAt: startedAt, endedAt: endedAt, source: segmentSource))
                    }
                    if !Transcriber.isModelReady {
                        // ~600 MB on first run. Say so rather than looking silently broken for minutes.
                        self?.note(
                            component,
                            "\(component.label) warming up — first run downloads the transcription model")
                        self?.publishState()
                    }
                    // Side task: never await before device start. A throw must not tear down capture
                    // (`AudioCaptureDecision.teardownCaptureOnLocalSTTFailure` is always false).
                    // Stored so `teardownAudio` can cancel mid-load; completions no-op if this
                    // component's transcriber was already removed.
                    let localStart = Task { [weak self] in
                        do {
                            try await transcriber.start()
                            await MainActor.run {
                                guard let self, self.transcribers[component] != nil else { return }
                                // Model ready — drop the warming note if that was still the reason.
                                if self.reasons[component]?.contains("warming up") == true {
                                    self.clear(component)
                                }
                                self.localStarts[component] = nil
                                self.publishState()
                            }
                        } catch {
                            await MainActor.run {
                                guard let self, self.transcribers[component] != nil else { return }
                                self.localStarts[component] = nil
                                if Task.isCancelled { return }
                                self.note(
                                    component,
                                    "\(component.label) local transcription unavailable — \(error.localizedDescription). Cloud transcription continues.")
                                if !decision.teardownCaptureOnLocalSTTFailure {
                                    // Capture and cloud pump keep running.
                                    self.publishState()
                                    return
                                }
                                self.teardownAudio(component)
                                self.publishState()
                            }
                        }
                    }
                    self?.localStarts[component] = localStart
                }

                self?.pumps[component] = Task.detached(priority: .userInitiated) {
                    for await chunk in chunks {
                        // Cloud always sees every chunk. Local Parakeet (Silicon only) stays
                        // underneath so a dropped network degrades rather than going silent.
                        await MainActor.run {
                            switch component {
                            case .microphone: Engine.shared.mixerInput(mic: chunk)
                            case .systemAudio: Engine.shared.mixerInput(system: chunk)
                            default: break
                            }
                        }
                        if let transcriber {
                            await transcriber.append(chunk)
                        }
                    }
                }
                try await device.start(onChunk: { feed.yield($0) }, onLevel: { _ in })

                guard let self, !Task.isCancelled else {
                    // Stopped while the device was still coming up; do not leave an IOProc behind.
                    device.stop()
                    return
                }
                self.running.insert(component)
                // Permission / device gaps clear here. A "warming up" local note is cleared when
                // the model finishes (or is replaced by a local-unavailable note on failure).
                if self.reasons[component]?.contains("warming up") != true {
                    self.clear(component)
                }
                self.publishState()
            } catch {
                guard let self, !Task.isCancelled else { return }
                self.teardownAudio(component)
                self.note(component, "\(component.label) stopped — \(error.localizedDescription)")
                self.publishState()
            }
        }
    }

    private func makeAudioSource(_ component: CaptureComponent) -> AudioSource? {
        switch component {
        case .microphone:
            return MicCapture()
        case .systemAudio:
            // Redundant against the deployment target on purpose — the availability checker will
            // not take the platform floor as proof.
            if #available(macOS 14.4, *) { return SystemAudioCapture() }
            note(component, "\(component.label) off — needs macOS 14.4 or later")
            return nil
        case .storage, .screen, .transcription:
            return nil
        }
    }

    private func stopAudio(_ component: CaptureComponent) {
        starts[component]?.cancel()
        teardownAudio(component)
    }

    /// Releases everything one audio source owns. Runs on a clean stop and after a failure alike,
    /// so a half-built pipeline never leaks an IOProc, a tap, or a pump task.
    private func teardownAudio(_ component: CaptureComponent) {
        starts[component] = nil
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
        running.remove(component)
    }

    private func startScreen() {
        guard !running.contains(.screen) else { return }
        guard Permissions.check(.screen) else {
            // Screen Recording only takes effect after a relaunch; `Permissions` is what tells the
            // user that, so this stays a plain statement of the gap.
            note(.screen, "\(CaptureComponent.screen.label) off — Screen Recording permission not granted")
            return
        }
        let watcher = ScreenWatcher()
        let store = self.store
        watcher.onFrame = { frame in store.record(frame) }
        watcher.start(interval: HostArchitecture.screenCaptureInterval)
        screenWatcher = watcher
        running.insert(.screen)
        clear(.screen)
        publishState()
    }

    private func stopScreen() {
        screenWatcher?.onFrame = nil
        screenWatcher?.stop()
        screenWatcher = nil
        running.remove(.screen)
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

    private func note(_ component: CaptureComponent, _ reason: String) {
        guard reasons[component] != reason else { return }  // a steady failure logs once, not forever
        reasons[component] = reason
        ContextLog.error(reason, "engine")
    }

    private func clear(_ component: CaptureComponent) {
        guard reasons.removeValue(forKey: component) != nil else { return }
        ContextLog.info("\(component.label) is capturing", "engine")
    }

    /// `synchronously` for pause and quit: an async write can lose the race with process teardown,
    /// and the heartbeat is the only thing telling `context-for-claude-mcp` what happened.
    ///
    /// Truthfulness rules, in the order they are applied:
    /// - Paused is paused.
    /// - A store that has *failed* to open means nothing is being recorded, whatever the sensors are
    ///   doing, so `capturing` is false. A store that is merely still opening does not: the sensors
    ///   are genuinely capturing and `EngineStore` is holding the result.
    /// - No sensor live and nothing yet gone wrong is the launch window, and it says so rather than
    ///   presenting an empty reason, which reads as "everything is fine".
    private func publishState(synchronously: Bool = false) {
        let storageFailed = reasons[.storage] != nil
        let capturing = !isPaused && !running.isEmpty && !storageFailed
        let reason: String?
        if isPaused {
            reason = "Paused"
        } else {
            // Fixed order so the popover string does not shuffle between renders.
            let notes = CaptureComponent.allCases.compactMap { reasons[$0] }
            if notes.isEmpty {
                reason = running.isEmpty ? startingUpReason : nil
            } else {
                reason = notes.joined(separator: " · ")
            }
        }

        if isCapturing != capturing { isCapturing = capturing }
        if pausedReason != reason { pausedReason = reason }

        let state = CaptureState(
            capturing: capturing, pausedReason: reason, capabilities: capabilities)
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
                }
            }
        }
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
        stopAllSources()
        store.closeOpenSession()
        lineFeed?.finish()
        lineTask?.cancel()

        isCapturing = false
        // The same sentence `Queries.status` uses for a stale heartbeat, so Claude reads one story.
        pausedReason = "Context for Claude is not running"
        let final = CaptureState(
            capturing: false, pausedReason: pausedReason, capabilities: capabilities)
        // Snapshot first, then write on the heartbeat queue: a timer tick already in flight runs
        // ahead of this write and re-stamps `final` rather than resurrecting a "capturing" state on
        // top of it.
        heartbeat.set(final)
        heartbeatQueue.sync { Self.writeHeartbeat(final) }
        ContextLog.info("Engine stopped", "engine")
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
    private var openSessionId: Int64?
    /// The latest segment end across *both* transcribers. Session boundaries are a property of the
    /// conversation, not of one microphone.
    private var lastSegmentEndedAt: Double?

    /// One write the sensors produced before there was a database to put it in.
    private enum PendingWrite {
        case line(TranscriptLine, appHint: String?)
        case frame(Frame)
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
            do {
                // Both bounds, tighter one wins. Age alone is not enough on a machine that
                // captures heavily: 30 days of dense capture outgrows any disk long before the
                // oldest frame is old enough to delete.
                let removed = try store.enforceRetention(olderThanDays: days)
                if removed > 0 {
                    ContextLog.info("Retention removed \(removed) frames", "store")
                }
            } catch {
                ContextLog.error("Frame retention sweep failed: \(error.localizedDescription)", "store")
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
                    // A closed session is a finished conversation; the uploader turns it into a
                    // real one in the user's Omi account. Enqueued, not sent — it survives being
                    // signed out, offline, or rate limited.
                    Task { @MainActor in ConversationUploader.shared.enqueue(sessionId: previous) }
                }
                openSessionId = try store.openSession(at: line.startedAt, appHint: appHint)
            }
            guard let sessionId = openSessionId else { return }

            try store.insertSegment(
                Segment(
                    sessionId: sessionId,
                    startedAt: line.startedAt,
                    endedAt: line.endedAt,
                    source: line.source,
                    text: line.text,
                    speakerLabel: line.speakerLabel,
                    personId: line.personId))
            // `max`, because a 10 s window from the other transcriber can land out of order and
            // must not drag the session's end backwards.
            lastSegmentEndedAt = max(lastSegmentEndedAt ?? line.endedAt, line.endedAt)
        } catch {
            ContextLog.error("Dropped a transcript line: \(error.localizedDescription)", "store")
        }
    }

    private func insert(_ frame: Frame, into store: ContextStore) {
        do {
            try store.insertFrame(frame)
        } catch {
            ContextLog.error("Dropped a screen frame: \(error.localizedDescription)", "store")
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
            try? store.closeSession(id, at: self.lastSegmentEndedAt ?? ContextTime.now)
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
            let lastLineAt = ((try? Queries.transcript(store, sessionId: session.id)) ?? [])
                .map(\.at).max()
            try? store.closeSession(session.id, at: lastLineAt ?? session.startedAt)
            // Sessions orphaned by a crash still belong in the account.
            let orphan = session.id
            Task { @MainActor in ConversationUploader.shared.enqueue(sessionId: orphan) }
        }
    }
}
