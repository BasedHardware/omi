import Foundation
import Observation
import OmiCore
import OmiNetwork

/// Phone calls through Omi (Flutter `PhoneCallProvider`): the verified caller ID, verifying a number,
/// past calls, and one call at a time with its live two-channel transcript. A finished call becomes a
/// conversation on the server (the transcription socket carries `source=phone_call`).
@MainActor
@Observable
public final class PhoneCallStore {
    public enum Phase: Equatable, Sendable {
        case idle, connecting, ringing, active
        /// Shown for `Timing.endedLinger` ("Call Ended" or the failure), then back to idle.
        case ended
    }

    public enum TranscriptionStatus: Equatable, Sendable {
        case idle, connecting, active, reconnecting, failed
        /// The socket is open but no call audio reached it yet.
        case noAudio
    }

    /// Delays, shortened in tests.
    public struct Timing: Sendable {
        public var verificationPoll: Duration = .seconds(2)
        public var endedLinger: Duration = .seconds(2)
        public var reconnectBase: Duration = .seconds(1)
        public var noAudioTimeout: Duration = .seconds(3)
        /// The conversation is built after the socket closes; past calls reload after this.
        public var historyRefreshDelay: Duration = .seconds(5)

        public init() {}
    }

    // MARK: Numbers, verification, history (PhoneCallStore+Numbers.swift)

    public internal(set) var numbers: [VerifiedPhoneNumber] = []
    public internal(set) var numbersLoaded = false
    /// The plan has no calls (403) or this month's free calls are used up (402).
    public internal(set) var unavailable: PhoneCallErrorDetail?
    public internal(set) var quota: PhoneCallQuota?
    public internal(set) var history: [Conversation] = []
    public internal(set) var verification: Verification?
    public internal(set) var verificationFailure: PhoneCallFailure?
    public internal(set) var isStartingVerification = false

    // MARK: The call

    public private(set) var phase: Phase = .idle
    public private(set) var remoteNumber: String?
    public private(set) var contactName: String?
    public private(set) var isMuted = false
    public private(set) var isSpeakerOn = false
    /// When the other side picked up; the screen counts the duration from here.
    public private(set) var connectedAt: Date?
    public internal(set) var transcript = PhoneCallTranscript()
    public internal(set) var transcription: TranscriptionStatus = .idle
    /// Why the last call did not start or ended early; cleared by the next attempt.
    public internal(set) var failure: PhoneCallFailure?
    public private(set) var callID: String?
    /// The full-screen call view is up (false while minimized to the banner).
    public var showsCallScreen = false
    /// After a call is over (conversation lists refresh).
    public var onCallFinished: (() async -> Void)?

    let api: any APIClientProtocol
    let engine: any PhoneCallEngine
    let userID: () -> String?
    let language: () -> String
    let timing: Timing
    let now: () -> Date

    // Transcription socket state (PhoneCallStore+Transcription.swift).
    var socket: (any PhoneCallTranscriptChannel)?
    /// Frames that arrived while no socket was open (~2 s, as Flutter).
    var pendingFrames: [Data] = []
    static let maxPendingFrames = 100
    var framesSent = 0
    var socketAccepted = false
    var reconnectAttempts = 0
    static let maxReconnectAttempts = 10
    var socketTask: Task<Void, Never>?
    var reconnectTask: Task<Void, Never>?
    var watchdogTask: Task<Void, Never>?
    /// Bumped per call and on sign-out: late events of an earlier call are ignored.
    var generation = 0
    private var engineTasks: [Task<Void, Never>] = []

    public init(
        api: any APIClientProtocol,
        engine: any PhoneCallEngine,
        userID: @escaping () -> String?,
        language: @escaping () -> String = { "multi" },
        timing: Timing = Timing(),
        now: @escaping () -> Date = Date.init
    ) {
        self.api = api
        self.engine = engine
        self.userID = userID
        self.language = language
        self.timing = timing
        self.now = now
    }

    public var isInProgress: Bool {
        [.connecting, .ringing, .active].contains(phase)
    }

    /// Who the call is with: the picked contact, else the number.
    public var otherParty: String {
        contactName ?? remoteNumber.map(PhoneNumberFormat.display) ?? ""
    }

    // MARK: Calling

    /// Places a call to a typed or picked number. `false`: it did not start, `failure` says why.
    @discardableResult
    public func call(_ rawNumber: String, contactName: String? = nil) async -> Bool {
        guard !isInProgress else {
            failure = .alreadyInProgress
            return false
        }
        guard let caller = numbers.first?.phoneNumber else {
            failure = .noVerifiedNumber
            return false
        }
        resetCall()
        generation += 1
        let callGeneration = generation
        let number = PhoneNumberFormat.dialable(rawNumber, callerNumber: caller)
        let id = String(Int64(now().timeIntervalSince1970 * 1000))
        phase = .connecting
        remoteNumber = number
        self.contactName = contactName
        callID = id

        guard await engine.requestMicrophonePermission() else { return abort(.microphonePermission, callGeneration) }
        guard callGeneration == generation else { return false }
        let token: PhoneCallToken
        do {
            token = try await api.phoneCallToken()
        } catch {
            return abort(.server(Self.detail(of: error)), callGeneration)
        }
        guard callGeneration == generation else { return false }
        do {
            let streams = try await engine.start(PhoneCallRequest(
                accessToken: token.accessToken, phoneNumber: number, callID: id, contactName: contactName
            ))
            guard callGeneration == generation else {
                engine.end()
                return false
            }
            observe(streams, generation: callGeneration)
            showsCallScreen = true
            return true
        } catch {
            return abort(.engine(error.localizedDescription), callGeneration)
        }
    }

    /// Hangs up; the conversation finishes on the server.
    public func end() {
        guard isInProgress else { return }
        engine.end()
        finish(nil, generation: generation)
    }

    /// Waits for the engine's confirmation (`muted`), like Flutter.
    public func toggleMute() {
        guard isInProgress else { return }
        engine.setMuted(!isMuted)
    }

    public func toggleSpeaker() {
        guard isInProgress else { return }
        engine.setSpeaker(!isSpeakerOn)
    }

    public func sendDigit(_ digit: String) {
        guard phase == .active else { return }
        engine.sendDigits(digit)
    }

    /// Sign-out: the call ends and nothing of this account stays.
    public func clearUserData() {
        if isInProgress { engine.end() }
        generation += 1
        resetCall()
        phase = .idle
        numbers = []
        numbersLoaded = false
        unavailable = nil
        quota = nil
        history = []
        verification = nil
        verificationFailure = nil
    }

    // MARK: Engine events

    private func observe(_ streams: PhoneCallStreams, generation callGeneration: Int) {
        engineTasks.append(Task { [weak self] in
            for await event in streams.events {
                self?.handle(event, generation: callGeneration)
            }
            // The engine stopped without saying why: the call is over.
            self?.finish(nil, generation: callGeneration)
        })
        engineTasks.append(Task { [weak self] in
            for await frame in streams.audio {
                guard let self, callGeneration == generation else { return }
                forward(frame)
            }
        })
    }

    func handle(_ event: PhoneCallEngineEvent, generation callGeneration: Int) {
        guard callGeneration == generation, isInProgress else { return }
        switch event {
        case .ringing:
            if phase == .connecting { phase = .ringing }
        case .connected:
            phase = .active
            if connectedAt == nil {
                connectedAt = now()
                connectTranscription()
            }
        case .ended:
            finish(nil, generation: callGeneration)
        case let .failed(message):
            finish(.engine(message), generation: callGeneration)
        case let .muted(muted):
            isMuted = muted
        case let .speaker(on):
            isSpeakerOn = on
        }
    }

    func finish(_ reason: PhoneCallFailure?, generation callGeneration: Int) {
        guard callGeneration == generation, isInProgress else { return }
        if let reason { failure = reason }
        phase = .ended
        disconnectTranscription()
        transcription = .idle
        pendingFrames = []
        let timing = timing
        Task { [weak self] in
            try? await Task.sleep(for: timing.endedLinger)
            guard let self, callGeneration == generation, phase == .ended else { return }
            resetCall()
            phase = .idle
            await onCallFinished?()
            try? await Task.sleep(for: timing.historyRefreshDelay)
            await loadHistory()
        }
    }

    private func abort(_ reason: PhoneCallFailure, _ callGeneration: Int) -> Bool {
        guard callGeneration == generation else { return false }
        resetCall()
        phase = .idle
        failure = reason
        return false
    }

    private func resetCall() {
        engineTasks.forEach { $0.cancel() }
        engineTasks = []
        disconnectTranscription()
        remoteNumber = nil
        contactName = nil
        callID = nil
        connectedAt = nil
        isMuted = false
        isSpeakerOn = false
        transcript.removeAll()
        transcription = .idle
        failure = nil
        pendingFrames = []
        framesSent = 0
        socketAccepted = false
        showsCallScreen = false
    }

    static func detail(of error: any Error) -> PhoneCallErrorDetail? {
        guard case let APIError.http(_, body) = error else { return nil }
        return PhoneCallErrorDetail(body: body)
    }
}
