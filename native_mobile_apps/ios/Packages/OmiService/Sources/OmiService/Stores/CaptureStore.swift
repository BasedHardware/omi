// swiftlint:disable file_length
// One state machine for every capture source (phone, Omi, watch); its extensions need its private
// state, so they stay in this file rather than being split for length.
import Foundation
import Observation
import OmiAudio
import OmiCore
import OmiDevice
import OmiNetwork
import OmiPersistence

/// Live capture: phone microphone, the Omi wearable or the Apple Watch → `/v4/listen` → live transcript → a
/// finalized conversation. Mirrors the Flutter `capture_provider.dart` contract.
@MainActor
@Observable
public final class CaptureStore {
    public enum Source: Equatable, Sendable { case phone, device, watch }

    public enum Phase: Equatable, Sendable {
        case idle
        case starting
        case live(since: Date)
        case finishing
        case failed(String)
    }

    public internal(set) var phase: Phase = .idle
    public private(set) var source: Source?
    public internal(set) var segments: [LiveSegment] = []
    /// The on-device recognizer's current partial line (not yet final).
    public private(set) var partial: LiveSegment?
    /// The iPhone's recognizer only previews words; the server's segments are the transcript.
    var previewOnly = false
    /// The iPhone's whole current line in preview mode; `partial` shows only what the server's
    /// segments do not show yet.
    var preview: LiveSegment?
    /// When the iPhone's preview line last changed (it goes stale if recognition stops).
    var previewUpdatedAt: Date?
    /// When this recording started, for the "first live words" line in the transcription log.
    var startedAt: Date?
    public internal(set) var level: Float = 0
    public private(set) var serverStatus: String?
    public private(set) var lastConversationID: String?
    /// The conversation being recorded (`conversation_session`), for naming voices live.
    public private(set) var liveConversationID: String?
    /// Audio is held back while the conversation stays open (Flutter pause; for the Omi, its mute).
    public internal(set) var isPaused = false
    /// The live conversation gets a star when it ends (double tap set to star).
    public private(set) var starsConversation = false
    /// Phone audio goes to a file on the phone instead of the socket: the connection dropped
    /// (uploaded when the recording stops) or Transcribe later is on (uploaded when asked).
    public internal(set) var isBuffering = false
    /// A recording ended unexpectedly (Home shows it; `CaptureStore+Recovery.swift`).
    public internal(set) var recovery: CaptureRecovery?
    /// Where buffered phone audio goes (the app: `SyncStore`).
    @ObservationIgnored public weak var phoneBuffer: (any PhoneAudioBuffering)?
    /// Transcription and capture events (Settings › Developer, the transcription log).
    @ObservationIgnored public var log: DebugLog?
    /// Who transcribes the live recording (`CaptureStore+Transcription.swift`).
    public internal(set) var transcriber: Transcriber = .omi
    /// The plan's minutes ran low or out (Flutter `freemium_threshold_reached`); nil otherwise.
    public internal(set) var transcriptionNotice: TranscriptionNotice?
    /// The user's own speech-to-text provider (Settings › Listening › Advanced transcription).
    @ObservationIgnored public var customSTT: CustomSTTSettings?
    /// Builds the transcriber for a provider (the app: `CustomTranscriber` on URLSession).
    @ObservationIgnored public var makeCustomTranscriber: ((CustomSTTConfig) -> any CustomTranscribing)?
    @ObservationIgnored var customTranscriber: (any CustomTranscribing)?
    /// The Omi's opus as PCM16, for a custom provider.
    @ObservationIgnored var opusToPCM: OpusPCM16Decoder?
    /// Store audio on phone is writing a copy of this recording.
    @ObservationIgnored var keepsCopy = false
    /// The options of the open socket (a switch to the iPhone's transcription reopens with them).
    @ObservationIgnored var listenOptionsInUse: ListenSocket.Options?
    /// Omi audio that arrived while no socket was open (starting, finishing, reconnecting): it is
    /// sent first once a socket opens (`CaptureStore+Lifecycle.swift`).
    @ObservationIgnored var heldDeviceAudio: [Data] = []
    @ObservationIgnored var heldDeviceAudioBytes = 0
    /// The Omi's socket dropped and is being reopened with the same recording id.
    @ObservationIgnored var reconnectingDevice = false
    /// Waits before each attempt to reopen it; the last one repeats until it opens.
    @ObservationIgnored var deviceReconnectDelays: [Duration] = [.seconds(1), .seconds(2), .seconds(5), .seconds(10), .seconds(30)]
    /// The phone's socket dropped mid-recording and is being reopened the same way. The audio of
    /// the gap goes to the phone's file meanwhile, so the reconnect never costs words.
    @ObservationIgnored var reconnectingPhone = false
    /// Waits before each attempt to reopen the phone's socket (see `deviceReconnectDelays`).
    @ObservationIgnored var phoneReconnectDelays: [Duration] = [.seconds(1), .seconds(2), .seconds(5), .seconds(10), .seconds(30)]

    /// Record now, transcribe later: the phone writes a file instead of streaming (Flutter batch mode).
    public var transcribesLater: Bool {
        didSet { preferences.set(transcribesLater, for: .batchModeEnabled) }
    }

    /// The server's speech model: `parakeet` (Omi Parakeet) or the backend's choice.
    public var usesParakeet: Bool {
        didSet { preferences.set(usesParakeet ? "parakeet" : "soniox", for: .transcriptionModel) }
    }

    /// The Omi stays muted across conversations and launches until unmuted.
    public var isDeviceMuted: Bool {
        didSet {
            guard isDeviceMuted != oldValue else { return }
            preferences.set(isDeviceMuted, for: .deviceMuted)
            if source == .device, isLive { isPaused = isDeviceMuted }
        }
    }

    /// Seconds of silence that end a conversation (`conversation_timeout`; -1 is four hours).
    /// Applies from the next conversation.
    public var conversationTimeout: Int {
        didSet { preferences.set(conversationTimeout, for: .conversationSilenceDuration) }
    }

    /// The choices Flutter offers: 2, 5, 10, 30 minutes and four hours.
    public static let conversationTimeouts = [120, 300, 600, 1800, -1]

    public var transcribesOnDevice: Bool {
        get { preferences.bool(.onDeviceTranscription, default: defaultOnDevice) }
        set { preferences.set(newValue, for: .onDeviceTranscription) }
    }

    /// Called after a conversation was finalized (refresh lists).
    @ObservationIgnored public var onConversationFinished: (() async -> Void)?
    /// A watch recording ended here (Stop in the app, or the watch's own stop): `WatchStore`.
    @ObservationIgnored public var onWatchCaptureEnded: (() -> Void)?
    /// Where the recording starts (`LocationStore`); `nil` without location access.
    @ObservationIgnored public var recordingLocation: (@MainActor @Sendable () async -> GeolocationSnapshot?)?

    let api: any APIClientProtocol
    let engine: any PhoneCaptureEngine
    private let deviceEngine: any DeviceTranscriptionEngine
    var deviceFeed: (@Sendable (Data) -> Void)?
    /// The wearable's codec while it streams, to start the next conversation after a double tap.
    private var deviceCodec: OmiGATT.Codec?
    let preferences: Preferences
    private let defaultOnDevice: Bool
    let userID: () -> String?
    var channel: (any LiveTranscriptionChannel)?
    /// A socket was opened for this recording (its conversation is finalized at the end).
    private var streamedToServer = false
    var tasks: [Task<Void, Never>] = []
    /// The phone microphone's streams: cancelled on pause, started again on resume. Written by
    /// `CaptureStore+Interruption` as well, which takes the microphone back after the system stole it.
    var phoneTasks: [Task<Void, Never>] = []

    /// Why capture is not running, when the reason came from outside the app (a call, Siri, the
    /// route losing its input). Shown on Home for as long as it lasts; `dismissNotice` clears it.
    public internal(set) var notice: CaptureNotice?
    /// The system has the microphone: the recording stays alive and the health loop keeps asking.
    @ObservationIgnored var suspendedBySystem = false
    /// A take-back is between "stop" and "running again": only one may be in flight at a time.
    @ObservationIgnored var takingMicrophoneBack = false
    /// The probe that takes the microphone back, every `healthTick`, while the phone records.
    @ObservationIgnored var healthTask: Task<Void, Never>?
    let healthTick: Duration
    let audioSession: any AudioSessionMonitoring

    public init(
        api: any APIClientProtocol,
        engine: any PhoneCaptureEngine,
        deviceEngine: any DeviceTranscriptionEngine,
        preferences: Preferences,
        defaultOnDevice: Bool,
        userID: @escaping () -> String?,
        healthTick: Duration = .seconds(3),
        audioSession: (any AudioSessionMonitoring)? = nil
    ) {
        self.api = api
        self.engine = engine
        self.deviceEngine = deviceEngine
        self.preferences = preferences
        self.defaultOnDevice = defaultOnDevice
        self.userID = userID
        self.healthTick = healthTick
        self.audioSession = audioSession ?? AVAudioSessionMonitor()
        isDeviceMuted = preferences.bool(.deviceMuted, default: false)
        conversationTimeout = preferences.integer(.conversationSilenceDuration, default: 120)
        transcribesLater = preferences.bool(.batchModeEnabled, default: false)
        usesParakeet = preferences.string(.transcriptionModel) == "parakeet"
        recovery = Self.recoveredInterruption(preferences)
    }

    public var isLive: Bool {
        if case .live = phase { return true }
        return phase == .starting
    }

    public var transcriptText: String {
        (segments + (partial.map { [$0] } ?? [])).map(\.text).joined(separator: " ")
    }

    /// The newest words for one-line live displays (Home's live bar, the Omi card). With server
    /// transcription the iPhone's own line is the freshest while it keeps updating; the server's
    /// segments take over when the iPhone falls silent.
    public var liveWords: String {
        if previewOnly, let preview, let previewUpdatedAt, Date().timeIntervalSince(previewUpdatedAt) < 3 {
            return preview.text
        }
        return transcriptText
    }

    // MARK: Phone

    public func startPhone() async {
        guard !isLive, let uid = userID() else { return }
        reset(source: .phone)
        await finalizeLeftoverConversation()
        guard phase == .starting, source == .phone else { return }
        var plan = transcriptionPlan(laterRequested: transcribesLater && phoneBuffer != nil, opus: true)
        let later = plan == .later
        let locate = later ? nil : recordingLocation
        async let place = locate?()
        let streams: PhoneCaptureStreams
        do {
            streams = try await startPhoneStreams(&plan)
        } catch {
            engine.stop()
            phase = .failed(Self.describe(error))
            return
        }
        if later {
            // Nothing is streamed: the file waits in Capture & Transcription until the user processes it.
            beginBuffering(manual: true)
            setLive()
            pipe(streams)
            return
        }
        do {
            var options = listenOptions(.init(
                codec: .pcm16, source: .phone, language: language, conversationTimeout: conversationTimeout,
                clientTranscription: plan != .omi
            ))
            options.geolocation = await place
            let channel = try await api.openListenSocket(uid: uid, options: options)
            self.channel = channel
            listenOptionsInUse = options
            streamedToServer = true
            setLive()
            beginTranscriber(plan)
            beginKeptCopy(.phone)
            listen(to: channel, acceptServerSegments: plan == .omi)
            pipe(streams)
        } catch where phoneBuffer != nil {
            // No connection: record on the phone and upload when the recording ends.
            log?.add(.warning, "stt", "listen socket failed: \(error)")
            beginBuffering(manual: false)
            setLive()
            beginKeptCopy(.phone)
            pipe(streams)
        } catch {
            engine.stop()
            phase = .failed(Self.describe(error))
        }
    }

    // MARK: Device

    /// Starts streaming the wearable's audio (called when the device reports its codec).
    public func startDevice(codec: OmiGATT.Codec) async {
        guard !isLive, let uid = userID() else { return }
        reset(source: .device)
        isPaused = isDeviceMuted
        deviceCodec = codec
        // Audio arriving meanwhile is held (`ingestDeviceAudio`) and sent once the socket is open.
        await finalizeLeftoverConversation()
        guard phase == .starting, source == .device else { return }
        // The iPhone's recognizer and custom providers need opus (all current Omi firmware); pcm
        // devices use the server.
        let opus = codec == .opusFS320 || codec == .opus
        var plan = transcriptionPlan(laterRequested: false, opus: opus)
        let onDevice = plan == .iPhone
        do {
            // Server transcription: the same recognizer as a live preview, when speech is allowed.
            let preview = plan == .omi && opus
            if case .custom = plan { opusToPCM = try? OpusPCM16Decoder() }
            // The plan's own switch to the iPhone is best effort (speech permission); the user's is required.
            let transcription = onDevice || preview ? try await startDevicePreview(required: onDevice && transcribesOnDevice) : nil
            if onDevice, transcription == nil {
                plan = .omi
                transcriptionNotice = .minutesRunningLow(seconds: 0)
            }
            if let transcription {
                previewOnly = preview
                deviceFeed = transcription.feed
                tasks.append(Task { [weak self] in
                    for await update in transcription.transcript {
                        self?.applyOnDevice(update.segment, isFinal: update.isFinal)
                    }
                })
            }
            var options = listenOptions(ListenSocket.Options(
                codec: ListenSocket.Options.Codec(rawValue: codec.listenValue) ?? .opusFS320,
                sampleRate: codec.sampleRate, source: .omi, language: language, conversationTimeout: conversationTimeout,
                clientTranscription: plan != .omi
            ))
            options.geolocation = await recordingLocation?()
            let channel = try await api.openListenSocket(uid: uid, options: options)
            self.channel = channel
            listenOptionsInUse = options
            streamedToServer = true
            setLive()
            beginTranscriber(plan)
            beginKeptCopy(.device(codec: codec))
            listen(to: channel, acceptServerSegments: plan == .omi)
            sendHeldDeviceAudio()
        } catch {
            deviceEngine.stop()
            deviceFeed = nil
            discardHeldDeviceAudio()
            phase = .failed(Self.describe(error))
        }
    }

    private func startDevicePreview(required: Bool) async throws -> DeviceTranscription? {
        if required { return try await deviceEngine.start() }
        do {
            return try await deviceEngine.start()
        } catch {
            // Words then only come from the server, seconds later: worth a line in the log.
            log?.add(.warning, "stt", "live preview unavailable: \(Self.describe(error))")
            return nil
        }
    }

    /// One codec frame from the wearable.
    public func ingestDeviceAudio(_ frame: Data) {
        guard source == .device, !isPaused else { return }
        guard let channel else {
            holdDeviceAudio(frame)
            return
        }
        channel.send(audio: frame)
        deviceFeed?(frame)
        if keepsCopy { phoneBuffer?.appendKeptCopy(frame) }
        if let customTranscriber, let pcm = opusToPCM?.decode(frame) { customTranscriber.feed(pcm) }
    }

    // MARK: Internals

    private var language: String {
        TranscriptionLanguage.current(preferences)
    }

    private func reset(source: Source) {
        self.source = source
        previewOnly = false
        transcriber = .omi
        transcriptionNotice = nil
        opusToPCM = nil
        preview = nil
        previewUpdatedAt = nil
        startedAt = Date()
        segments = []
        partial = nil
        serverStatus = nil
        isPaused = false
        notice = nil
        suspendedBySystem = false
        takingMicrophoneBack = false
        reconnectingPhone = false
        liveConversationID = nil
        phase = .starting
    }

    func listen(to channel: any LiveTranscriptionChannel, acceptServerSegments: Bool) {
        tasks.append(Task { [weak self] in
            for await event in channel.events {
                self?.handle(event, acceptServerSegments: acceptServerSegments)
            }
        })
    }
}

// Stop: an extension in this file, so it keeps access to private state.
public extension CaptureStore {
    // MARK: Stop

    /// Stops capture and finalizes the conversation (`POST v1/conversations`).
    func stop() async {
        guard await finish() else { return }
        discardHeldDeviceAudio()
        await onConversationFinished?()
    }

    /// Double tap on the Omi: finalize this conversation and keep listening in a new one. The
    /// device stays connected, so no new codec (and no `onReady`) arrives to restart capture.
    func endDeviceConversation() async {
        guard source == .device, isLive, deviceCodec != nil else { return }
        guard await finish() else { return }
        // Unless the Omi disconnected while finalizing; its next connect restarts capture.
        if let deviceCodec { await startDevice(codec: deviceCodec) }
        await onConversationFinished?()
    }

    /// Ends the live session and finalizes its conversation; false when nothing was live.
    private func finish() async -> Bool {
        guard isLive else { return false }
        phase = .finishing
        stopCaptureHealth()
        if source == .phone { engine.stop() }
        if source == .watch { onWatchCaptureEnded?() }
        if source == .device {
            deviceEngine.stop()
            deviceFeed = nil
        }
        if let partial { flushFinal(partial) }
        endTranscriber()
        endKeptCopy()
        channel?.close(reason: "user_stop")
        channel = nil
        reconnectingDevice = false
        reconnectingPhone = false
        tasks.forEach { $0.cancel() }
        tasks = []
        phoneTasks.forEach { $0.cancel() }
        phoneTasks = []
        level = 0
        isPaused = false
        endBuffering()
        markEnded()
        // A phone recording that never reached the server has no conversation to finalize.
        let finalizes = source != .phone || streamedToServer
        let id = finalizes ? await finalizeOpenConversation() : nil
        streamedToServer = false
        lastConversationID = id ?? lastConversationID
        await applyStar(to: id)
        phase = .idle
        return true
    }

    /// The wearable disconnected: keep what was said. The backend does not finalize an Omi
    /// conversation when its socket closes, so it stays remembered and is finalized when capture
    /// starts again (`finalizeLeftoverConversation`).
    func deviceDisconnected() {
        guard source == .device else { return }
        deviceCodec = nil
        discardHeldDeviceAudio()
        reconnectingDevice = false
        guard isLive else { return }
        endTranscriber()
        endKeptCopy()
        channel?.close(reason: "device_disconnected")
        channel = nil
        deviceEngine.stop()
        deviceFeed = nil
        isPaused = false
        markEnded()
        streamedToServer = false
        phase = .idle
    }
}

// Server events: an extension in this file, so it keeps access to private state.
extension CaptureStore {
    func handle(_ event: ListenEvent, acceptServerSegments: Bool) {
        switch event {
        case let .segments(incoming) where acceptServerSegments:
            for segment in incoming {
                upsert(segment)
            }
            if previewOnly, !incoming.isEmpty { partial = preview.flatMap(previewTail) }
        case let .status(status):
            serverStatus = status
            let failed = status.hasPrefix("stt_failed") || status.hasPrefix("disconnected")
            log?.add(failed ? .warning : .info, "stt", status)
            if status.hasPrefix("disconnected"), source == .device {
                // The Omi still streams: reopen the socket, resuming the same conversation.
                deviceSocketLost()
                return
            }
            if status.hasPrefix("disconnected"), isLive, source == .phone, !isBuffering, phoneBuffer != nil {
                // Keep recording and take the socket back: the gap goes to the phone's file.
                phoneSocketLost()
                return
            }
            if status.hasPrefix("stt_failed") || status.hasPrefix("disconnected"), isLive, source == .phone, transcriber == .omi {
                fail(status)
            }
        case let .conversationStarted(id):
            liveConversationID = id
            rememberOpenConversation(id)
        case let .processingStarted(id):
            forgetOpenConversation(id)
        case let .conversationCreated(id):
            forgetOpenConversation(id)
            lastConversationID = id
            liveConversationID = nil
            segments = []
            Task {
                await applyStar(to: id)
                await onConversationFinished?()
            }
        case let .segmentsDeleted(ids):
            segments.removeAll { ids.contains($0.id) }
        case let .translated(incoming):
            applyTranslations(incoming)
        case let .freemiumThreshold(remaining, requiresOnDevice):
            Task { await freemiumThresholdReached(remainingSeconds: remaining, requiresOnDevice: requiresOnDevice) }
        default:
            break
        }
    }
}

// The phone engine and on-device words: an extension in this file, so it keeps access to private state.
extension CaptureStore {
    /// With server transcription the iPhone's recognizer still runs as a live preview (words appear
    /// as they are spoken; the server's segments replace them). Without speech permission the
    /// recording simply runs without the preview.
    func startPhoneEngine(onDevice: Bool, preview: Bool) async throws -> PhoneCaptureStreams {
        guard preview else { return try await engine.start(transcribeOnDevice: onDevice) }
        if let streams = try? await engine.start(transcribeOnDevice: true) {
            previewOnly = streams.transcript != nil
            return streams
        }
        engine.stop()
        return try await engine.start(transcribeOnDevice: false)
    }

    func pipe(_ streams: PhoneCaptureStreams) {
        phoneTasks.append(Task { [weak self] in for await chunk in streams.pcm16 {
            self?.routePhoneAudio(chunk)
        } })
        phoneTasks.append(Task { [weak self] in for await value in streams.level {
            self?.level = value
        } })
        if let transcript = streams.transcript {
            phoneTasks.append(Task { [weak self] in
                for await update in transcript {
                    self?.applyOnDevice(update.segment, isFinal: update.isFinal)
                }
            })
        }
    }

    func applyOnDevice(_ segment: LiveSegment, isFinal: Bool) {
        if let startedAt, preview == nil, partial == nil, segments.isEmpty {
            log?.add(.info, "stt", "first live words after \(Int(Date().timeIntervalSince(startedAt) * 1000)) ms")
        }
        // Server transcription: the iPhone's words only show until the server's segment arrives.
        if previewOnly {
            preview = segment
            previewUpdatedAt = Date()
            partial = previewTail(segment)
            return
        }
        if isFinal {
            flushFinal(segment)
        } else {
            partial = segment
        }
    }

    /// The words of the iPhone's line the server has not sent yet. The recognizer repeats its
    /// whole line (up to ~50 s) with every update; without this the words the server already
    /// shows would appear twice. Both clocks start with the recording.
    func previewTail(_ line: LiveSegment) -> LiveSegment? {
        let served = segments.filter { $0.end > line.start + 0.3 }
            .reduce(0) { $0 + $1.text.split(whereSeparator: \.isWhitespace).count }
        let words = line.text.split(whereSeparator: \.isWhitespace)
        guard served < words.count else { return nil }
        return LiveSegment(
            id: line.id, text: words.dropFirst(served).joined(separator: " "), speaker: line.speaker, speakerID: line.speakerID,
            isUser: line.isUser, start: line.start, end: line.end
        )
    }

    func flushFinal(_ segment: LiveSegment) {
        partial = nil
        upsert(segment)
        channel?.sendSuggestedTranscript([segment], provider: "apple_on_device")
    }

    func upsert(_ segment: LiveSegment) {
        if let index = segments.firstIndex(where: { $0.id == segment.id }) {
            segments[index] = segment
        } else {
            segments.append(segment)
        }
    }
}

extension CaptureStore {
    static func describe(_ error: any Error) -> String {
        switch error {
        case CaptureFailure.microphonePermission: "microphone"
        case CaptureFailure.speechPermission: "speech"
        case CaptureFailure.speechUnavailable: "speechUnavailable"
        default: String(describing: error)
        }
    }
}

// The watch: an extension in this file, so it keeps access to private state.
public extension CaptureStore {
    // MARK: Watch

    /// Starts a conversation from the Apple Watch microphone (16 kHz PCM16 relayed by `WatchStore`).
    /// The server transcribes: the on-device recognizers take the phone mic or opus.
    func startWatch() async {
        guard !isLive, let uid = userID() else { return }
        reset(source: .watch)
        await finalizeLeftoverConversation()
        guard phase == .starting, source == .watch else { return }
        do {
            var options = listenOptions(.init(
                codec: .pcm16, sampleRate: Int(WatchAudioChunk.sampleRate), source: .appleWatch, language: language
            ))
            options.geolocation = await recordingLocation?()
            let channel = try await api.openListenSocket(uid: uid, options: options)
            self.channel = channel
            streamedToServer = true
            setLive()
            listen(to: channel, acceptServerSegments: true)
        } catch {
            phase = .failed(Self.describe(error))
        }
    }

    /// 100 ms of PCM16 per socket message, the phone mic's pacing, instead of one 1.5 s burst.
    internal static let watchFrameBytes = 3200

    /// One chunk of watch audio; dropped unless a watch recording is live.
    func ingestWatchAudio(_ pcm: Data) {
        guard source == .watch, case .live = phase, let channel else { return }
        var offset = pcm.startIndex
        while offset < pcm.endIndex {
            let end = min(offset + Self.watchFrameBytes, pcm.endIndex)
            channel.send(audio: pcm.subdata(in: offset ..< end))
            offset = end
        }
    }
}

// Pause and star: an extension in this file, so they keep access to private state.
public extension CaptureStore {
    // MARK: Pause

    /// Stops sending audio but keeps the conversation open (Flutter `phonePaused` / `pendantPaused`):
    /// the phone releases its microphone; the Omi keeps streaming and its frames are dropped. For
    /// the Omi this is its mute, which outlasts the conversation.
    func pause() {
        guard case .live = phase, !isPaused else { return }
        isPaused = true
        if source == .device { isDeviceMuted = true }
        guard source == .phone else { return }
        // The user chose this: no banner, and the health loop stops asking for the microphone.
        notice = nil
        suspendedBySystem = false
        engine.stop()
        phoneTasks.forEach { $0.cancel() }
        phoneTasks = []
        level = 0
        if let partial { flushFinal(partial) }
    }

    func resume() async {
        guard case .live = phase, isPaused else { return }
        isPaused = false
        if source == .device { isDeviceMuted = false }
        guard source == .phone, channel != nil || isBuffering else { return }
        // The user asks for the microphone back; the health loop's probe answers, so a refusal
        // (the caller still has it) leaves the recording alive with the reason on screen instead
        // of ending a conversation whose words are already sent or on disk.
        suspendedBySystem = false
        notice = nil
        await takeMicrophoneBack()
    }

    // MARK: Star

    /// Double tap set to star: marks the live conversation (or takes the mark back).
    func toggleStar() {
        guard isLive else { return }
        starsConversation.toggle()
    }

    /// A voice named in the live transcript (`LiveSpeakersStore`), after its REST assignment.
    func sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: [String]) {
        channel?.sendSpeakerAssigned(speakerID: speakerID, personID: personID, personName: personName, segmentIDs: segmentIDs)
    }

    private func applyStar(to id: String?) async {
        guard starsConversation, let id else { return }
        starsConversation = false
        try? await api.starConversation(id: id, starred: true)
    }
}
