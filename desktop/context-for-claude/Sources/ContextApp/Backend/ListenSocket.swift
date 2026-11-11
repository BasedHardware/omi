import Combine
import ContextCore
import Foundation

/// One transcript line, attributed by the Omi backend rather than by this app.
///
/// `speaker` and `personId` are the whole reason the cloud path exists: the server diarizes the
/// mixed stream and matches voices against the account's enrolled speech profiles, so a line can be
/// attributed to a *named person* instead of to "whichever device the sound arrived on".
struct CloudSegment: Sendable, Equatable {
    let text: String
    /// Diarization label for this session, e.g. `"SPEAKER_00"`. Stable within a conversation only.
    let speaker: String?
    /// True when the backend's speech profile matched this line to the signed-in user.
    let isUser: Bool
    /// The Omi person this voice belongs to, when the account has one enrolled for it.
    let personId: String?
    /// **Seconds from the start of the conversation, not a Unix epoch.** Convert with
    /// `ListenSocket.conversationStartedAt`.
    let start: Double
    let end: Double
    /// The backend's own id for this line.
    ///
    /// The server re-sends a segment whenever it revises one — a later word changes the punctuation,
    /// diarization reassigns the speaker, a speech profile finally matches a voice — so the same id
    /// arrives more than once with better text. A consumer that appends on every batch stores the
    /// same sentence several times; upsert on this instead.
    let id: String?

    init(
        text: String,
        speaker: String? = nil,
        isUser: Bool,
        personId: String? = nil,
        start: Double,
        end: Double,
        id: String? = nil
    ) {
        self.text = text
        self.speaker = speaker
        self.isUser = isUser
        self.personId = personId
        self.start = start
        self.end = end
        self.id = id
    }
}

/// The live link to `wss://api.omi.me/v4/listen`.
///
/// Audio goes up as raw PCM; transcript segments, the conversation id, and lifecycle events come
/// back on the same socket. There is deliberately **no client-sent finalize**: in conversation mode
/// the server closes a conversation on its own silence timeout, and the explicit finalize endpoints
/// are capped at ten calls an hour — a client that called them would spend the day's quota by
/// mid-afternoon and then fail silently.
///
/// What this class is really for is the failure path. Replacing a local transcriber with a network
/// one means every dropped Wi-Fi packet is now a chance to lose speech that used to be safe, so the
/// three things below are the contract, not optimisations:
///
/// - **Reconnect with the same `client_conversation_id`.** The server binds a conversation to that
///   id, so a reconnect resumes the conversation instead of splitting one meeting into five.
/// - **Buffer while reconnecting, bounded, oldest first.** A minute of audio is held; past that the
///   loss is real and is logged as a duration so a gap in the transcript can be explained.
/// - **Stop permanently when the answer is permanent.** A trial that has expired, a codec the server
///   refuses, credentials it will not accept twice: retrying any of those is a loop that never ends
///   and never works.
@MainActor
final class ListenSocket: ObservableObject {
    /// `nonisolated` so `send` can be reached from a capture thread without a hop. Everything else
    /// on this class is main-actor only; the singleton reference and `send` are the two things that
    /// have to be callable from wherever CoreAudio hands over a buffer.
    /// Plain construction, deliberately: `init` below is `nonisolated`, so no assumption about the
    /// calling thread is needed — and any assumption made here would be false. A `static let` is
    /// realised on whichever thread touches it first, and the first toucher is usually the CoreAudio
    /// thread inside `send`, not the main actor.
    nonisolated static let shared = ListenSocket()

    enum State: Equatable {
        /// Not connected and not trying: stopped, or signed out. Audio handed over is discarded.
        case idle
        case connecting
        case live
        /// Dropped, with a reconnect already scheduled. Audio is being buffered.
        case failed(String)
        /// The account's trial is over. A permanent stop — never a retry loop.
        case paywalled
        /// Airgap Mode is on, so no audio is being sent anywhere. Reversible: turning the switch off
        /// reconnects. Distinct from `.idle` because the reason is a setting the user can undo, and
        /// distinct from `.failed` because nothing failed.
        case airgapped
    }

    /// Fired for every batch the server sends, on the main actor, in arrival order.
    var onSegments: (([CloudSegment]) -> Void)?
    /// The backend conversation these segments belong to. Fires again on every reconnect, and again
    /// with a *new* id when the server rolls the conversation over on its own timeout.
    var onConversationId: ((String) -> Void)?

    @Published private(set) var state: State = .idle

    /// Unix epoch that `CloudSegment.start`/`.end` are measured from, or nil before the first batch.
    ///
    /// The server sends offsets relative to the conversation, not timestamps, and it never tells the
    /// client which wall-clock instant zero was. This is anchored from the first batch of a
    /// conversation — arrival time minus the latest offset in it — and then held fixed, so every
    /// segment in that conversation lands on one consistent timeline instead of drifting with
    /// network latency. It is late by the pipeline's own lag, on the order of a second.
    ///
    /// Always read it *inside* `onSegments`; it is set before the callback and reset when the server
    /// rolls over to a new conversation.
    private(set) var conversationStartedAt: Double?

    // MARK: - Configuration

    private static let logCategory = "listen"
    private static let path = "v4/listen"
    private static let language = "en"
    private static let sampleRate = 16_000
    private static let bytesPerSecond = 32_000

    /// Sixty seconds of audio. Long enough to cover a lift, a Wi-Fi handover, or a laptop lid; short
    /// enough that the memory is unremarkable and that what is finally dropped is genuinely stale.
    private static let maxBufferedBytes = 60 * bytesPerSecond

    /// A backstop between the capture threads and the main actor. At 100 ms a chunk this is over
    /// three minutes of slack, which only matters if the main actor is blocked outright — a system
    /// permission prompt does exactly that.
    /// `nonisolated` because the initializer that reads it is: this is the one constant the socket
    /// needs before it has an actor.
    nonisolated private static let inboundHighWaterMark = 2048

    private static let reconnectBaseDelay: TimeInterval = 1
    private static let reconnectDelayCap: TimeInterval = 30

    /// A blocked network produces a drop per frame. Report the total on a timer instead.
    private static let dropReportInterval: TimeInterval = 10

    // MARK: - Connection state

    private var session: URLSession?
    private var task: URLSessionWebSocketTask?
    private var socketDelegate: SocketDelegate?
    private var receiveTask: Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?

    /// Bumped on every connection attempt. Every callback carries the value it was created under, so
    /// a close frame and a failed read racing to report the same dead socket cannot both act on it.
    private var connectionId = 0

    /// The caller wants a socket. Distinct from `state`, which says whether there is one.
    private var wantsConnection = false
    /// Latched by a trial-expired close and cleared only by an explicit `stop()`, so no automatic
    /// path can reopen a socket the backend has already refused on billing grounds.
    private var isPaywalled = false
    /// One forced token refresh per connection, reset once a connection opens.
    private var didRefreshToken = false

    private var reconnectAttempt = 0

    /// Held across reconnects; minted fresh by `start()`. This is what stops a flaky network from
    /// fragmenting one meeting into a row of two-minute conversations.
    private var clientConversationId: String?
    private var serverConversationId: String?

    // MARK: - Audio buffering

    private var pending: [Data] = []
    private var pendingBytes = 0
    private var droppedBytes = 0
    private var lastDropReportAt: Double = 0

    private let inbound: AsyncStream<Data>.Continuation
    private let inboundChunks: AsyncStream<Data>
    private var pump: Task<Void, Never>?
    private var signIn: AnyCancellable?
    /// Registered by `start()`. Airgap Mode has to close a live socket, not just refuse the next
    /// one — a switch that leaves the microphone streaming until relaunch is not an airgap.
    private var airgapObserver: UUID?

    /// Nonisolated because `shared` is: a main-actor initializer would have to be reached from the
    /// main actor before any capture thread could touch the singleton, which is precisely the
    /// ordering guarantee a capture path cannot make.
    nonisolated private init() {
        let (stream, continuation) = AsyncStream<Data>.makeStream(
            of: Data.self, bufferingPolicy: .bufferingNewest(Self.inboundHighWaterMark))
        inbound = continuation
        inboundChunks = stream
    }

    /// One consumer, one queue. `send` is called from a CoreAudio thread, and independent tasks
    /// reach the main actor in whatever order the pool schedules them — reordered PCM is not a
    /// glitch a transcriber can recover from, it is a sentence with its words shuffled.
    private func startPump() {
        guard pump == nil else { return }
        let chunks = inboundChunks
        pump = Task { [weak self] in
            for await chunk in chunks {
                guard let self else { return }
                self.deliver(chunk)
            }
        }
    }

    // MARK: - Lifecycle

    /// Opens the socket, or reports `.idle` and does nothing at all when nobody is signed in.
    ///
    /// Idempotent: calling it again while a socket is up or coming up changes nothing.
    func start() async {
        startPump()
        guard !wantsConnection else { return }
        wantsConnection = true
        isPaywalled = false
        reconnectAttempt = 0
        clientConversationId = UUID().uuidString.lowercased()
        serverConversationId = nil
        conversationStartedAt = nil
        observeSignIn()
        observeAirgap()
        await connect(forceTokenRefresh: false)
    }

    /// Hands 16 kHz mono Int16 little-endian PCM to the backend, ~100 ms at a time.
    ///
    /// Safe to call from any thread — including straight out of an `AudioMixer` chunk handler on a
    /// CoreAudio IO thread. Never blocks and never throws: audio that cannot be sent right now is
    /// buffered, and audio that will never be sent (signed out, stopped, paywalled) is dropped here
    /// rather than accumulating for a socket that is not coming.
    nonisolated func send(_ pcm: Data) {
        guard !pcm.isEmpty else { return }
        inbound.yield(pcm)
    }

    /// Closes the socket and forgets the conversation. The server finalizes what it has on its own
    /// timeout; there is nothing to tell it.
    func stop() {
        guard wantsConnection || state != .idle else { return }
        wantsConnection = false
        isPaywalled = false
        signIn = nil
        // Removed rather than left guarded: `start()` re-registers, and a stopped socket that keeps
        // accumulating engine observers across a day of start/stop cycles is a leak.
        if let airgapObserver { ExclusionEngine.shared.removeObserver(airgapObserver) }
        airgapObserver = nil
        reconnectTask?.cancel()
        reconnectTask = nil
        closeConnection(normally: true)
        discardBuffer(reason: "capture stopped")
        clientConversationId = nil
        serverConversationId = nil
        conversationStartedAt = nil
        reconnectAttempt = 0
        state = .idle
        ContextLog.info("Stopped", Self.logCategory)
    }

    // MARK: - Connecting

    private func connect(forceTokenRefresh: Bool) async {
        guard wantsConnection, !isPaywalled else { return }

        // Ahead of the sign-in check: the payload on this socket is the user's microphone and system
        // audio, so the strongest constraint has to be the first one read. Nothing is buffered for
        // later either — see `reportAirgapped`.
        guard !NetworkEgress.isSuppressed(.listenSocket) else {
            reportAirgapped()
            return
        }

        guard OmiAuth.shared.isSignedIn else {
            reportSignedOut()
            return
        }

        reconnectTask?.cancel()
        reconnectTask = nil
        closeConnection(normally: false)
        state = .connecting

        connectionId &+= 1
        let generation = connectionId

        let headers: [String: String]
        do {
            headers = try await OmiAPI.shared.headers(forceRefresh: forceTokenRefresh)
        } catch {
            guard wantsConnection, generation == connectionId else { return }
            guard OmiAuth.shared.isSignedIn else {
                reportSignedOut()
                return
            }
            scheduleReconnect(reason: "credentials unavailable")
            return
        }

        guard wantsConnection, generation == connectionId else { return }
        // **Asked again, on the other side of the await.** The guard at the top of this function ran
        // before `OmiAPI.shared.headers` suspended, and a token that is still valid returns without
        // its own airgap check — so a switch flipped while this was suspended would find nothing else
        // between here and `task.resume()`. Of everything airgap gates, this is the socket that
        // matters most: it carries the microphone and the system-audio tap. The two guards beside it
        // re-read `wantsConnection` and `generation` across the same await for the same reason; this
        // is the third fact that can change while nobody is looking.
        guard !NetworkEgress.isSuppressed(.listenSocket) else {
            reportAirgapped()
            return
        }
        guard let url = Self.listenURL(clientConversationId: clientConversationId) else {
            permanentFailure("The Omi backend URL is unusable, so transcription cannot start.")
            return
        }

        var request = URLRequest(url: url)
        // `OmiAPI` already builds the platform, version and device-id-hash headers the backend
        // stamps onto a conversation, and its `Authorization` is carried through **unchanged**.
        //
        // The scheme prefix is load-bearing on this endpoint, not decoration: the upgrade is
        // authenticated by `_verify_ws_auth` (`backend/utils/other/endpoints.py`), which rejects
        // anything that is not exactly two space-separated words and then verifies the *second* one.
        // A bare token is one word, so it never reaches Firebase — it closes 1008 "Invalid
        // authorization token" before the socket is accepted. Only `Content-Type` is dropped; there
        // is no body on an upgrade.
        for (field, value) in headers where field != "Content-Type" {
            request.setValue(value, forHTTPHeaderField: field)
        }
        request.timeoutInterval = 30

        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 30
        // The backend's own 10 s heartbeat keeps the connection busy, so the default resource
        // timeout never fires on a healthy socket. Parking a stalled connect instead of failing it
        // is the wrong trade here: this class already has a backoff, and a request waiting silently
        // for connectivity would leave audio buffering with nothing on screen to explain why.
        configuration.waitsForConnectivity = false
        configuration.urlCache = nil

        let delegate = SocketDelegate()
        delegate.onOpen = { [weak self] in
            Task { @MainActor in self?.handleOpen(generation) }
        }
        delegate.onClose = { [weak self] code, reason in
            Task { @MainActor in
                self?.handleDisconnect(
                    code: code, reason: reason, httpStatus: nil, error: nil, generation: generation)
            }
        }
        delegate.onFailure = { [weak self] status, error in
            Task { @MainActor in
                guard let self, generation == self.connectionId, let task = self.task else { return }
                self.handleDisconnect(
                    code: task.closeCode,
                    reason: task.closeReason.flatMap { String(data: $0, encoding: .utf8) },
                    httpStatus: status,
                    error: error,
                    generation: generation)
            }
        }

        let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        let task = session.webSocketTask(with: request)
        self.session = session
        self.socketDelegate = delegate
        self.task = task

        ContextLog.info(
            "Connecting to \(Self.path) (conversation \(clientConversationId ?? "none"))", Self.logCategory)
        task.resume()
        receive(on: task, generation: generation)
    }

    private func handleOpen(_ generation: Int) {
        guard generation == connectionId, wantsConnection else { return }
        state = .live
        reconnectAttempt = 0
        didRefreshToken = false
        ContextLog.info("Connected", Self.logCategory)
        reportDrops(force: true)
        flushBuffer()
    }

    private func receive(on task: URLSessionWebSocketTask, generation: Int) {
        receiveTask?.cancel()
        receiveTask = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    let message = try await task.receive()
                    guard let self, generation == self.connectionId else { return }
                    self.handle(message)
                } catch {
                    guard let self, generation == self.connectionId else { return }
                    // A server close arrives as both a delegate callback and a failed read, in
                    // either order. The task itself carries the code and reason, so whichever lands
                    // first has the full picture and the generation guard discards the other.
                    self.handleDisconnect(
                        code: task.closeCode,
                        reason: task.closeReason.flatMap { String(data: $0, encoding: .utf8) },
                        httpStatus: (task.response as? HTTPURLResponse)?.statusCode,
                        error: error,
                        generation: generation)
                    return
                }
            }
        }
    }

    // MARK: - Inbound messages

    private func handle(_ message: URLSessionWebSocketTask.Message) {
        switch message {
        case .string(let text):
            handle(text: text)
        case .data(let data):
            guard let text = String(data: data, encoding: .utf8) else { return }
            handle(text: text)
        @unknown default:
            return
        }
    }

    /// Three shapes share this socket, and they are told apart in this order:
    ///
    /// 1. the literal text `ping` — the server's 10 s heartbeat. It is **not** JSON, and handing it
    ///    to a JSON parser is the classic bug on this endpoint: every heartbeat becomes a decode
    ///    error, the log fills, and a real parse failure is impossible to see.
    /// 2. a JSON **array** — transcript segments.
    /// 3. a JSON **object** with a `type` key — a lifecycle event.
    private func handle(text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed != "ping" else { return }
        guard let data = trimmed.data(using: .utf8),
            let json = try? JSONSerialization.jsonObject(with: data)
        else {
            ContextLog.error("Unreadable frame (\(trimmed.count) bytes)", Self.logCategory)
            return
        }

        if json is [Any] {
            handleSegments(data)
        } else if let object = json as? [String: Any], let type = object["type"] as? String {
            handleEvent(type: type, payload: object)
        }
    }

    private func handleSegments(_ data: Data) {
        guard let wire = try? Self.decoder.decode([WireSegment].self, from: data) else {
            ContextLog.error("Could not decode a transcript batch", Self.logCategory)
            return
        }
        let segments = wire.compactMap(\.segment)
        guard !segments.isEmpty else { return }
        anchorTimeline(with: segments)
        ContextLog.info("Received \(segments.count) segment(s)", Self.logCategory)
        onSegments?(segments)
    }

    private func handleEvent(type: String, payload: [String: Any]) {
        switch type {
        case "conversation_session":
            guard let id = payload["conversation_id"] as? String, !id.isEmpty else { return }
            if id != serverConversationId {
                // A different id means the server rolled the conversation over on its own timeout,
                // and started a fresh relative timeline with it. The old anchor would date every
                // line from here on to whenever the previous conversation began.
                serverConversationId = id
                conversationStartedAt = nil
                ContextLog.info("Conversation \(id)", Self.logCategory)
            }
            onConversationId?(id)
        case "memory_created":
            // The conversation finished server-side and became a memory. The payload carries the
            // whole conversation, transcript included; only the id is safe to log.
            let id = (payload["conversation_id"] as? String) ?? "unknown"
            ContextLog.info("Conversation \(id) finished server-side", Self.logCategory)
        case "service_status":
            let status = (payload["status"] as? String) ?? "unknown"
            ContextLog.info("Service status: \(status)", Self.logCategory)
        case "freemium_threshold_reached":
            // Sent when the account runs out of transcription credit. Sometimes it precedes a
            // trial-expired close, sometimes the socket stays open — the close is the authority, so
            // this only goes in the log.
            ContextLog.error("The account has reached its transcription limit", Self.logCategory)
        default:
            ContextLog.info("Event \(type)", Self.logCategory)
        }
    }

    /// Pins the conversation's relative timeline to wall clock, once per conversation.
    private func anchorTimeline(with segments: [CloudSegment]) {
        guard conversationStartedAt == nil else { return }
        let latestEnd = segments.map(\.end).max() ?? 0
        conversationStartedAt = ContextTime.now - latestEnd
    }

    // MARK: - Disconnecting

    private func handleDisconnect(
        code: URLSessionWebSocketTask.CloseCode,
        reason: String?,
        httpStatus: Int?,
        error: Error?,
        generation: Int
    ) {
        guard generation == connectionId else { return }
        closeConnection(normally: false)

        let detail = reason?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let raw = code.rawValue

        // 1008 + `trial_expired`: the desktop paywall. The backend has decided this account may not
        // transcribe, and it will decide the same thing every time. Stop, say why, and stay stopped.
        if detail.localizedCaseInsensitiveContains("trial_expired") {
            isPaywalled = true
            state = .paywalled
            discardBuffer(reason: "trial expired")
            ContextLog.error(
                "Omi trial expired — cloud transcription is off until the account is upgraded",
                Self.logCategory)
            return
        }

        // 1003: the server rejected the audio format itself. Reconnecting sends the same bytes.
        if raw == 1003 {
            permanentFailure(
                "The Omi backend rejected this audio format\(detail.isEmpty ? "" : " (\(detail))").")
            return
        }

        // The auth close codes are outside `CloseCode`'s known cases, so the reason text is checked
        // alongside the number rather than after it: whether a 4001 survives the round trip through
        // an @objc enum is not something this path should depend on.
        if raw == Self.closeRelogin || detail.localizedCaseInsensitiveContains("re-login") {
            permanentFailure("Sign in to Omi again to keep transcribing.")
            return
        }

        if raw == Self.closeTokenRefresh || httpStatus == 401 || httpStatus == 403
            || Self.isAuthRejection(detail)
        {
            if detail.localizedCaseInsensitiveContains("invalid authorization token") {
                // The endpoint reads `Authorization` as "<scheme> <token>" and takes the second
                // half. Seeing this means the header lost its scheme, which no retry will fix.
                ContextLog.error(
                    "The backend could not parse this Mac's Authorization header", Self.logCategory)
            }
            guard !didRefreshToken else {
                permanentFailure("Omi would not accept this Mac's credentials. Sign in again.")
                return
            }
            didRefreshToken = true
            ContextLog.info("Auth rejected — refreshing the token and reconnecting once", Self.logCategory)
            Task { await connect(forceTokenRefresh: true) }
            return
        }

        // Any other policy close — an unsupported language, an account the backend will not serve —
        // is a settled answer too.
        if raw == 1008 {
            permanentFailure(detail.isEmpty ? "The Omi backend refused the connection." : detail)
            return
        }

        // Everything else is worth another try: 1001 when the server saw no audio for 90 s, 1011
        // for a server fault, and every transport error underneath.
        scheduleReconnect(reason: Self.describe(code: code, detail: detail, error: error))
    }

    private func scheduleReconnect(reason: String) {
        guard wantsConnection, !isPaywalled else {
            state = .idle
            return
        }
        // A reconnect is another connection, so it answers to the same switch. Without this a socket
        // dropped a moment before the toggle would come back on its own timer.
        guard !NetworkEgress.isSuppressed(.listenSocket) else {
            reportAirgapped()
            return
        }
        guard OmiAuth.shared.isSignedIn else {
            reportSignedOut()
            return
        }

        reconnectAttempt += 1
        let delay = Self.reconnectDelay(attempt: reconnectAttempt)
        state = .failed("\(reason) — reconnecting")
        ContextLog.error(
            "Dropped: \(reason). Reconnect \(reconnectAttempt) in \(String(format: "%.1f", delay))s"
                + " (holding \(AudioMixer.describeSeconds(pendingBytes)))",
            Self.logCategory)

        reconnectTask?.cancel()
        reconnectTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(delay))
            guard !Task.isCancelled else { return }
            await self?.connect(forceTokenRefresh: false)
        }
    }

    /// Exponential with equal jitter, capped. The cap is what makes this safe to leave running all
    /// day; the jitter is what stops every Mac that lost the same access point from coming back in
    /// the same millisecond, forever.
    private static func reconnectDelay(attempt: Int) -> TimeInterval {
        let exponential = min(reconnectDelayCap, reconnectBaseDelay * pow(2, Double(max(0, attempt - 1))))
        return exponential / 2 + Double.random(in: 0...(exponential / 2))
    }

    private func permanentFailure(_ message: String) {
        wantsConnection = false
        reconnectTask?.cancel()
        reconnectTask = nil
        state = .failed(message)
        discardBuffer(reason: "connection refused")
        ContextLog.error(message, Self.logCategory)
    }

    private func reportSignedOut() {
        closeConnection(normally: true)
        reconnectTask?.cancel()
        reconnectTask = nil
        discardBuffer(reason: "signed out")
        state = .idle
        ContextLog.info("Signed out — not connecting", Self.logCategory)
    }

    /// Closes the socket because Airgap Mode is on, and **throws the buffered audio away**.
    ///
    /// The buffer exists to survive a network blip, and holding a minute of the user's microphone
    /// for a socket that is not coming is the opposite of what the switch promises. Nothing is lost
    /// that the app was keeping: the local transcriber runs underneath the cloud one for exactly
    /// this reason (see `TranscriptOwnership`), so speech still becomes a transcript on this Mac —
    /// what is given up is the backend's diarization and speech-profile attribution, which is a
    /// quality loss, not a data loss. Hence `.degraded`.
    private func reportAirgapped() {
        let wasConnected = task != nil || state == .connecting
        closeConnection(normally: true)
        reconnectTask?.cancel()
        reconnectTask = nil
        discardBuffer(reason: "Airgap Mode is on")
        reconnectAttempt = 0
        guard state != .airgapped else { return }
        state = .airgapped
        ContextLog.info(
            wasConnected
                ? "Airgap Mode on — closed the cloud transcription socket; transcribing locally"
                : "Airgap Mode on — not connecting for cloud transcription; transcribing locally",
            Self.logCategory)
        NetworkEgress.recordSuppression(.listenSocket, outcome: .degraded)
    }

    /// Tears down the current socket and invalidates its session.
    ///
    /// `URLSession` holds its delegate until it is invalidated, so skipping this leaks a session, a
    /// delegate and a task on every reconnect — which on a bad network is every thirty seconds.
    private func closeConnection(normally: Bool) {
        receiveTask?.cancel()
        receiveTask = nil
        if let task {
            if normally {
                task.cancel(with: .normalClosure, reason: nil)
            } else {
                task.cancel()
            }
        }
        task = nil
        socketDelegate = nil
        if normally {
            session?.finishTasksAndInvalidate()
        } else {
            session?.invalidateAndCancel()
        }
        session = nil
        connectionId &+= 1
    }

    // MARK: - Outbound audio

    private func deliver(_ pcm: Data) {
        // Policy lives in ContextCore so Intel's "no Parakeet under the mixer" contract is
        // hermetically testable. `.idle` + `wantsConnection` must buffer: that is the window
        // between `start()` setting the flag and `connect()` flipping to `.connecting`.
        // `.airgapped` always drops — never buffer audio the user has forbidden uploading.
        let phase: CloudOutboundPCMPhase
        switch state {
        case .idle: phase = .idle
        case .connecting: phase = .connecting
        case .live: phase = .live
        case .failed: phase = .failed
        case .paywalled: phase = .paywalled
        case .airgapped: phase = .airgapped
        }
        switch CaptureHostPolicy.outboundPCMAction(
            phase: phase,
            wantsConnection: wantsConnection,
            hasLiveTask: task != nil
        ) {
        case .transmit:
            guard let task else {
                enqueue(pcm)
                return
            }
            transmit(pcm, on: task)
        case .buffer:
            enqueue(pcm)
        case .drop:
            return
        }
    }

    private func transmit(_ pcm: Data, on task: URLSessionWebSocketTask) {
        let generation = connectionId
        task.send(.data(pcm)) { [weak self] error in
            guard let error else { return }
            Task { @MainActor in
                guard let self, generation == self.connectionId else { return }
                self.handleDisconnect(
                    code: task.closeCode,
                    reason: task.closeReason.flatMap { String(data: $0, encoding: .utf8) },
                    httpStatus: (task.response as? HTTPURLResponse)?.statusCode,
                    error: error,
                    generation: generation)
            }
        }
    }

    private func enqueue(_ pcm: Data) {
        pending.append(pcm)
        pendingBytes += pcm.count
        var dropped = 0
        while pendingBytes > Self.maxBufferedBytes, !pending.isEmpty {
            let oldest = pending.removeFirst()
            pendingBytes -= oldest.count
            dropped += oldest.count
        }
        guard dropped > 0 else { return }
        droppedBytes += dropped
        reportDrops(force: false)
    }

    private func flushBuffer() {
        guard let task, !pending.isEmpty else { return }
        let chunks = pending
        let bytes = pendingBytes
        pending = []
        pendingBytes = 0
        // `URLSessionWebSocketTask` sends in the order the frames were handed to it, so replaying
        // the backlog before anything new arrives keeps the audio in order.
        for chunk in chunks { transmit(chunk, on: task) }
        ContextLog.info("Sent \(AudioMixer.describeSeconds(bytes)) of buffered audio", Self.logCategory)
    }

    private func discardBuffer(reason: String) {
        guard pendingBytes > 0 else {
            reportDrops(force: true)
            return
        }
        ContextLog.error(
            "Discarded \(AudioMixer.describeSeconds(pendingBytes)) of audio — \(reason)", Self.logCategory)
        pending = []
        pendingBytes = 0
        reportDrops(force: true)
    }

    /// A blocked socket drops a frame every 100 ms; one line per frame would bury everything else.
    private func reportDrops(force: Bool) {
        guard droppedBytes > 0 else { return }
        let now = ContextTime.now
        guard force || now - lastDropReportAt >= Self.dropReportInterval else { return }
        lastDropReportAt = now
        ContextLog.error(
            "Lost \(AudioMixer.describeSeconds(droppedBytes)) of audio while offline"
                + " (the buffer holds \(AudioMixer.describeSeconds(Self.maxBufferedBytes)))",
            Self.logCategory)
        droppedBytes = 0
    }

    // MARK: - Sign-in

    /// Signing in mid-session has to bring the socket up, and signing out has to take it down
    /// without leaving a buffer growing behind it. Both happen without the engine being told.
    private func observeSignIn() {
        signIn = OmiAuth.shared.$isSignedIn
            .removeDuplicates()
            .dropFirst()
            .sink { [weak self] signedIn in
                Task { @MainActor in
                    guard let self, self.wantsConnection, !self.isPaywalled else { return }
                    if signedIn {
                        guard self.state == .idle else { return }
                        ContextLog.info("Signed in — connecting", Self.logCategory)
                        await self.connect(forceTokenRefresh: false)
                    } else {
                        self.reportSignedOut()
                    }
                }
            }
    }

    // MARK: - Airgap

    /// Turning Airgap Mode on has to close a *live* socket, not merely refuse the next one — a
    /// switch that leaves the microphone streaming until the next relaunch keeps no promise at all.
    /// Turning it off reconnects, under a fresh conversation id, because the server has long since
    /// finalized the one that was open.
    private func observeAirgap() {
        guard airgapObserver == nil else { return }
        // The engine calls observers on whichever thread made the change.
        airgapObserver = ExclusionEngine.shared.addObserver { [weak self] set in
            Task { @MainActor in
                guard let self, self.wantsConnection, !self.isPaywalled else { return }
                if set.airgapMode {
                    self.reportAirgapped()
                } else if self.state == .airgapped {
                    ContextLog.info("Airgap Mode off — reconnecting for cloud transcription", Self.logCategory)
                    // A new conversation, deliberately: the old id belongs to a conversation the
                    // server closed on its own silence timeout while this socket was down.
                    self.clientConversationId = UUID().uuidString.lowercased()
                    self.serverConversationId = nil
                    self.conversationStartedAt = nil
                    await self.connect(forceTokenRefresh: false)
                }
            }
        }
    }

    // MARK: - Wire format

    /// Every field but `text` is optional on purpose: one unexpected null must cost a field, not the
    /// whole batch of speech it arrived in.
    private struct WireSegment: Decodable {
        let id: String?
        let text: String?
        let speaker: String?
        let isUser: Bool?
        let personId: String?
        let start: Double?
        let end: Double?

        var segment: CloudSegment? {
            let cleaned = (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !cleaned.isEmpty else { return nil }
            return CloudSegment(
                text: cleaned,
                speaker: speaker,
                isUser: isUser ?? false,
                personId: personId,
                start: start ?? 0,
                end: max(start ?? 0, end ?? 0),
                id: id)
        }
    }

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    /// Close codes the backend uses for auth: refresh the token, and re-login.
    private static let closeTokenRefresh = 4001
    private static let closeRelogin = 4004

    private static func isAuthRejection(_ detail: String) -> Bool {
        let lowered = detail.lowercased()
        return lowered.contains("authoriz") || lowered.contains("token") || lowered.contains("auth error")
    }

    private static func describe(
        code: URLSessionWebSocketTask.CloseCode, detail: String, error: Error?
    ) -> String {
        if code == .goingAway {
            // 1001 is what the backend sends after 90 s without a byte from this client, and what
            // it sends when an instance goes away. Either way the fix is the same.
            return "the server closed an idle connection"
        }
        if !detail.isEmpty {
            return detail
        }
        if code != .invalid {
            return "the server closed the connection (\(code.rawValue))"
        }
        if let error = error as? URLError {
            return error.localizedDescription
        }
        return error?.localizedDescription ?? "the connection ended"
    }

    /// `wss://api.omi.me/v4/listen?…`, honouring an `OMI_PYTHON_API_URL` override for local testing.
    static func listenURL(clientConversationId: String?) -> URL? {
        guard var components = URLComponents(url: OmiAPI.baseURL, resolvingAgainstBaseURL: false) else {
            return nil
        }
        switch components.scheme?.lowercased() {
        case "https", "wss":
            components.scheme = "wss"
        case "http", "ws":
            components.scheme = "ws"
        default:
            return nil
        }
        let base = components.path.hasSuffix("/") ? components.path : components.path + "/"
        components.path = base + path

        var query = [
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "sample_rate", value: String(sampleRate)),
            URLQueryItem(name: "codec", value: "linear16"),
            URLQueryItem(name: "channels", value: "1"),
            // The account's enrolled voice profile is what turns "SPEAKER_01" into a person.
            URLQueryItem(name: "include_speech_profile", value: "true"),
            URLQueryItem(name: "source", value: "desktop"),
            URLQueryItem(name: "speaker_auto_assign", value: "enabled"),
        ]
        if let clientConversationId, !clientConversationId.isEmpty {
            query.append(URLQueryItem(name: "client_conversation_id", value: clientConversationId))
        }
        components.queryItems = query
        return components.url
    }
}

/// `URLSession` needs an `NSObject` delegate and calls it on its own queue; keeping it separate is
/// what lets `ListenSocket` stay entirely on the main actor.
private final class SocketDelegate: NSObject, URLSessionWebSocketDelegate, @unchecked Sendable {
    var onOpen: (@Sendable () -> Void)?
    var onClose: (@Sendable (URLSessionWebSocketTask.CloseCode, String?) -> Void)?
    var onFailure: (@Sendable (Int?, Error?) -> Void)?

    func urlSession(
        _ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?
    ) {
        onOpen?()
    }

    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        onClose?(closeCode, reason.flatMap { String(data: $0, encoding: .utf8) })
    }

    /// The backstop for a *rejected upgrade*, which is what an auth failure on `/v4/listen` actually
    /// looks like: the server answers the handshake with 403 and never opens a socket, so there is
    /// no close frame to observe. Fires on ordinary teardown too — the connection generation is what
    /// discards those.
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        onFailure?((task.response as? HTTPURLResponse)?.statusCode, error)
    }
}
