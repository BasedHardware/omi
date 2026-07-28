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
}

/// The parts of the pipeline that fail independently. Storage is one of them: it is the single
/// shared dependency, and a database that will not open makes capture pointless rather than partial.
private enum CaptureComponent: CaseIterable {
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

    var segmentSource: SegmentSource { self == .microphone ? .mic : .system }
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
    private var screenWatcher: ScreenWatcher?

    private var lineFeed: AsyncStream<TranscriptLine>.Continuation?
    private var lineTask: Task<Void, Never>?
    private var heartbeatTask: Task<Void, Never>?
    private var todayTask: Task<Void, Never>?

    private init() {}

    // MARK: - Lifecycle

    /// Idempotent: the app delegate calls this on launch, and onboarding may call it again once
    /// permissions land.
    func start() {
        guard !hasStarted else { return }
        hasStarted = true
        capabilities = Permissions.report()
        startLineConsumer()

        // Restore any Omi session from a previous launch, then start the two uploaders. Both are
        // no-ops while signed out — captures queue locally and go up once an account is attached.
        OmiAuth.shared.restore()
        // Re-register on every launch, not only during onboarding. Registration is idempotent and
        // writes only when something actually differs — but without this, an install that has
        // already onboarded can never pick up a changed binary path or a renamed connector, so a
        // rename reaches new users and silently strands existing ones.
        Task.detached(priority: .utility) {
            let result = ClaudeRegistrar.register()
            ContextLog.info("Claude registration on launch: \(result.message)", "claude")
        }
        ScreenActivityUploader.shared.start()
        Task { await ConversationUploader.shared.drain() }

        Task { [weak self] in
            guard let self else { return }
            await self.ensureStorage()
            self.startPermittedSources()
            self.publishState()
            await self.refreshTodaySeconds()
        }

        startHeartbeatLoop()
        startTodaySecondsLoop()
        observeTermination()
        ContextLog.info("Engine started", "engine")
    }

    func pause() {
        guard !isPaused else { return }
        isPaused = true
        stopAllSources()
        // Ends the conversation, not just the capture. The app delegate also routes quit through
        // here, and a session left open reports a recording that stopped hours ago.
        store.closeOpenSession()
        ContextLog.info("Capture paused", "engine")
        publishState(synchronously: true)
    }

    func resume() {
        guard isPaused else { return }
        isPaused = false
        // Reasons recorded before the pause describe a pipeline that no longer exists. Storage is
        // the exception: that failure is about the database, not about a source.
        reasons = reasons.filter { $0.key == .storage }
        capabilities = Permissions.report()
        startPermittedSources()
        ContextLog.info("Capture resumed", "engine")
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

    /// Opens the database if it is not open yet. Idempotent, so launch and the heartbeat's retry can
    /// both call it: a volume that was busy for a minute should not cost the rest of the session.
    private func ensureStorage() async {
        guard !isStorageReady else { return }
        if let failure = await store.open() {
            note(.storage, failure)
            return
        }
        isStorageReady = true
        clear(.storage)
        // Retention is a one-off sweep on the store's queue: thousands of file removals must never
        // sit in front of the first transcript line.
        store.pruneFrames(olderThanDays: 30)
    }

    private func startPermittedSources() {
        guard isStorageReady, !isPaused else { return }
        startAudio(.microphone)
        startAudio(.systemAudio)
        startScreen()
    }

    private func stopAllSources() {
        stopAudio(.microphone)
        stopAudio(.systemAudio)
        stopScreen()
    }

    /// Wires one audio device into one transcriber. Identical for the mic and the system tap: the
    /// only difference is which device can fail and what the user is told when it does.
    private func startAudio(_ component: CaptureComponent) {
        guard starts[component] == nil, !running.contains(component) else { return }
        guard let capability = component.capability, Permissions.check(capability) else {
            note(component, "\(component.label) off — permission not granted")
            return
        }
        guard let device = makeAudioSource(component) else { return }

        let transcriber = Transcriber(source: component.segmentSource)
        let segmentSource = component.segmentSource
        let lines = lineFeed
        // A stream rather than a task per chunk: tasks reach an actor in whatever order the pool
        // schedules them, and reordered audio is a corrupted transcript. Bounded, because a stalled
        // transcriber must cost a few dropped seconds rather than the whole machine's memory.
        let (chunks, feed) = AsyncStream<Data>.makeStream(
            of: Data.self, bufferingPolicy: .bufferingNewest(512))

        audioSources[component] = device
        transcribers[component] = transcriber
        chunkFeeds[component] = feed

        starts[component] = Task { [weak self] in
            do {
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
                // The model load is a cold-start compile measured in minutes, and the device must
                // not wait behind it — every second spent loading used to be a second of the user's
                // life that was never recorded. `Transcriber` buffers from the moment `start()` is
                // entered, so the capture begins now and the backlog decodes once the model lands.
                let modelReady = Task { try await transcriber.start() }
                self?.pumps[component] = Task.detached(priority: .userInitiated) {
                    for await chunk in chunks { await transcriber.append(chunk) }
                }
                try await device.start(onChunk: { feed.yield($0) }, onLevel: { _ in })
                try await modelReady.value

                guard let self, !Task.isCancelled else {
                    // Stopped while the device was still coming up; do not leave an IOProc behind.
                    device.stop()
                    return
                }
                self.running.insert(component)
                self.clear(component)
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
        case .storage, .screen:
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
        watcher.start(interval: 3.0)
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
    private func publishState(synchronously: Bool = false) {
        let capturing = !isPaused && isStorageReady && !running.isEmpty
        let reason: String?
        if isPaused {
            reason = "Paused"
        } else {
            // Fixed order so the popover string does not shuffle between renders.
            let notes = CaptureComponent.allCases.compactMap { reasons[$0] }
            reason = notes.isEmpty ? nil : notes.joined(separator: " · ")
        }

        if isCapturing != capturing { isCapturing = capturing }
        if pausedReason != reason { pausedReason = reason }

        let state = CaptureState(
            capturing: capturing, pausedReason: reason, capabilities: capabilities)
        if synchronously {
            Self.writeHeartbeat(state)
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
    /// running app as gone. Re-reading permissions on the same tick also retries anything that is
    /// permitted but not running — an unplugged mic recovers without the user doing anything.
    private func startHeartbeatLoop() {
        heartbeatTask = Task { [weak self] in
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
        heartbeatTask?.cancel()
        todayTask?.cancel()
        stopAllSources()
        store.closeOpenSession()
        lineFeed?.finish()
        lineTask?.cancel()

        isCapturing = false
        // The same sentence `Queries.status` uses for a stale heartbeat, so Claude reads one story.
        pausedReason = "Context for Claude is not running"
        Self.writeHeartbeat(
            CaptureState(capturing: false, pausedReason: pausedReason, capabilities: capabilities))
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
    private let policy = SessionPolicy()

    private var store: ContextStore?
    private var openSessionId: Int64?
    /// The latest segment end across *both* transcribers. Session boundaries are a property of the
    /// conversation, not of one microphone.
    private var lastSegmentEndedAt: Double?

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
            guard let store = self.store else { return }
            do {
                if self.openSessionId == nil
                    || self.policy.shouldOpenNewSession(
                        lastSegmentEndedAt: self.lastSegmentEndedAt,
                        nextSegmentStartedAt: line.startedAt)
                {
                    if let previous = self.openSessionId {
                        try store.closeSession(previous, at: self.lastSegmentEndedAt ?? line.startedAt)
                        // A closed session is a finished conversation; the uploader turns it into a
                        // real one in the user's Omi account. Enqueued, not sent — it survives being
                        // signed out, offline, or rate limited.
                        Task { @MainActor in ConversationUploader.shared.enqueue(sessionId: previous) }
                    }
                    self.openSessionId = try store.openSession(at: line.startedAt, appHint: appHint)
                }
                guard let sessionId = self.openSessionId else { return }

                try store.insertSegment(
                    Segment(
                        sessionId: sessionId,
                        startedAt: line.startedAt,
                        endedAt: line.endedAt,
                        source: line.source,
                        text: line.text))
                // `max`, because a 10 s window from the other transcriber can land out of order and
                // must not drag the session's end backwards.
                self.lastSegmentEndedAt = max(self.lastSegmentEndedAt ?? line.endedAt, line.endedAt)
            } catch {
                ContextLog.error("Dropped a transcript line: \(error.localizedDescription)", "store")
            }
        }
    }

    func record(_ frame: Frame) {
        queue.async {
            guard let store = self.store else { return }
            do {
                try store.insertFrame(frame)
            } catch {
                ContextLog.error("Dropped a screen frame: \(error.localizedDescription)", "store")
            }
        }
    }

    func pruneFrames(olderThanDays days: Int) {
        queue.async {
            guard let store = self.store else { return }
            do {
                let removed = try store.pruneFrames(olderThanDays: days)
                if removed > 0 {
                    ContextLog.info("Pruned \(removed) frames older than \(days) days", "store")
                }
            } catch {
                ContextLog.error("Frame retention sweep failed: \(error.localizedDescription)", "store")
            }
        }
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
