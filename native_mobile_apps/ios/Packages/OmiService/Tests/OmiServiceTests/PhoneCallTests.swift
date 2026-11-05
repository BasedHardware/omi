import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// Twilio + CallKit stand-in: tests push the call's events and audio.
@MainActor
final class FakeCallEngine: PhoneCallEngine {
    let events = AsyncStream.makeStream(of: PhoneCallEngineEvent.self)
    let audio = AsyncStream.makeStream(of: PhoneCallAudio.self)
    var micGranted = true
    var startError: (any Error)?
    private(set) var requests: [PhoneCallRequest] = []
    private(set) var ended = 0
    private(set) var mutes: [Bool] = []
    private(set) var speakers: [Bool] = []
    private(set) var digits: [String] = []

    func requestMicrophonePermission() async -> Bool {
        micGranted
    }

    func start(_ request: PhoneCallRequest) async throws -> PhoneCallStreams {
        if let startError { throw startError }
        requests.append(request)
        return PhoneCallStreams(events: events.stream, audio: audio.stream)
    }

    func end() {
        ended += 1
    }

    func setMuted(_ muted: Bool) {
        mutes.append(muted)
    }

    func setSpeaker(_ on: Bool) {
        speakers.append(on)
    }

    func sendDigits(_ digits: String) {
        self.digits.append(digits)
    }

    func emit(_ event: PhoneCallEngineEvent) {
        events.continuation.yield(event)
    }

    func play(_ channel: PhoneCallAudio.Channel, bytes: Int = 4) {
        audio.continuation.yield(PhoneCallAudio(channel: channel, pcm16: Data(repeating: channel.rawValue, count: bytes)))
    }
}

struct EngineFailure: LocalizedError {
    var errorDescription: String? {
        "Call system rejected the request"
    }
}

@MainActor
func phoneStore(api: FakeAPIClient, engine: FakeCallEngine, verified: Bool = true) async -> PhoneCallStore {
    var timing = PhoneCallStore.Timing()
    timing.verificationPoll = .milliseconds(1)
    timing.endedLinger = .milliseconds(20)
    timing.reconnectBase = .milliseconds(5)
    timing.noAudioTimeout = .milliseconds(30)
    timing.historyRefreshDelay = .milliseconds(1)
    if verified {
        api.phoneCalls.numbers = [VerifiedPhoneNumber(id: "n1", phoneNumber: "+15551112222", verifiedAt: Fixtures.now, isPrimary: true)]
    }
    let store = PhoneCallStore(
        api: api, engine: engine, userID: { "uid-1" }, language: { "de" }, timing: timing,
        now: { Fixtures.now }
    )
    await store.loadNumbers()
    return store
}

func segment(_ id: String, _ text: String, isUser: Bool = false) -> LiveSegment {
    LiveSegment(
        id: id, text: text, speaker: isUser ? "SPEAKER_00" : "SPEAKER_01", speakerID: isUser ? 0 : 1, isUser: isUser, start: 0, end: 1
    )
}

@MainActor
struct PhoneCallLifecycleTests {
    let api = FakeAPIClient()
    let engine = FakeCallEngine()

    @Test func aCallGoesConnectingRingingActiveEndedIdle() async throws {
        let store = await phoneStore(api: api, engine: engine)
        var finished = false
        store.onCallFinished = { finished = true }

        #expect(await store.call("(555) 123-4567", contactName: "Anna"))
        #expect(store.phase == .connecting)
        #expect(store.showsCallScreen)
        // A number without + takes the caller's country code; the call id reaches Twilio.
        let request = try #require(engine.requests.first)
        #expect(request == PhoneCallRequest(
            accessToken: "twilio-token", phoneNumber: "+15551234567", callID: String(Int64(Fixtures.now.timeIntervalSince1970 * 1000)),
            contactName: "Anna"
        ))
        #expect(store.otherParty == "Anna")

        engine.emit(.ringing)
        try await waitUntil { store.phase == .ringing }
        #expect(store.phase == .ringing)
        #expect(api.phoneCalls.sockets.isEmpty)

        engine.emit(.connected)
        try await waitUntil { api.phoneCalls.socket != nil }
        #expect(store.phase == .active)
        #expect(store.connectedAt == Fixtures.now)
        let opened = try #require(api.phoneCalls.socketRequests.first)
        #expect(opened.uid == "uid-1" && opened.callID == request.callID && opened.language == "de")

        engine.emit(.ended)
        try await waitUntil { store.phase == .ended }
        #expect(api.phoneCalls.socket?.isClosed == true)
        try await waitUntil { store.phase == .idle }
        #expect(store.phase == .idle)
        #expect(store.remoteNumber == nil && store.transcript.isEmpty && !store.showsCallScreen)
        try await waitUntil { finished }
        #expect(finished)
    }

    @Test func hangingUpEndsTheCallInTheEngine() async throws {
        let store = await phoneStore(api: api, engine: engine)
        await store.call("+4930123456")
        engine.emit(.connected)
        try await waitUntil { store.phase == .active }
        store.end()
        #expect(engine.ended == 1)
        #expect(store.phase == .ended)
        #expect(store.failure == nil)
    }

    @Test func aSecondCallWhileOneIsOnIsRefused() async {
        let store = await phoneStore(api: api, engine: engine)
        #expect(await store.call("+4930123456"))
        #expect(await store.call("+4930999999") == false)
        #expect(store.failure == .alreadyInProgress)
        #expect(engine.requests.count == 1)
    }

    @Test func theBackendsReasonIsKeptWhenNoTokenComes() async {
        api.phoneCalls.tokenError = .http(status: 402, body: #"{"detail":{"error":"phone_call_quota_exceeded","monthly_limit":3}}"#)
        let store = await phoneStore(api: api, engine: engine)
        #expect(await store.call("+4930123456") == false)
        #expect(store.phase == .idle)
        #expect(store.failure == .server(.quotaExceeded(monthlyLimit: 3)))
        #expect(engine.requests.isEmpty)
    }

    @Test func withoutMicrophoneOrNumberNoCallStarts() async {
        engine.micGranted = false
        let store = await phoneStore(api: api, engine: engine)
        #expect(await store.call("+4930123456") == false)
        #expect(store.failure == .microphonePermission)
        #expect(api.phoneCalls.tokenRequests == 0)

        let unverified = await phoneStore(api: FakeAPIClient(), engine: FakeCallEngine(), verified: false)
        #expect(await unverified.call("+4930123456") == false)
        #expect(unverified.failure == .noVerifiedNumber)
    }

    @Test func theCallSystemRefusingIsAFailure() async {
        engine.startError = EngineFailure()
        let store = await phoneStore(api: api, engine: engine)
        #expect(await store.call("+4930123456") == false)
        #expect(store.failure == .engine("Call system rejected the request"))
        #expect(store.phase == .idle)
    }

    @Test func aTwilioFailureEndsTheCallWithItsMessage() async throws {
        let store = await phoneStore(api: api, engine: engine)
        await store.call("+4930123456")
        engine.emit(.failed("Call service error: busy"))
        try await waitUntil { store.phase == .ended }
        #expect(store.failure == .engine("Call service error: busy"))
    }

    @Test func muteAndSpeakerFollowTheEnginesConfirmation() async throws {
        let store = await phoneStore(api: api, engine: engine)
        await store.call("+4930123456")
        engine.emit(.connected)
        store.toggleMute()
        #expect(engine.mutes == [true])
        #expect(store.isMuted == false)
        engine.emit(.muted(true))
        try await waitUntil { store.isMuted }
        #expect(store.isMuted)
        store.toggleSpeaker()
        engine.emit(.speaker(true))
        try await waitUntil { store.isSpeakerOn }
        #expect(engine.speakers == [true])
        store.sendDigit("5")
        #expect(engine.digits == ["5"])
    }

    @Test func pastCallsAreThePhoneCallConversations() async {
        api.phoneCalls.history = [Fixtures.conversations[0]]
        let store = await phoneStore(api: api, engine: engine)
        await store.load()
        #expect(store.history.map(\.id) == ["c1"])
    }
}

@MainActor
struct PhoneCallTranscriptionTests {
    let api = FakeAPIClient()
    let engine = FakeCallEngine()

    func activeCall() async throws -> (PhoneCallStore, FakePhoneCallChannel) {
        let store = await phoneStore(api: api, engine: engine)
        await store.call("+4930123456")
        engine.emit(.connected)
        try await waitUntil { api.phoneCalls.socket != nil && store.transcription == .connecting }
        return (store, try #require(api.phoneCalls.socket))
    }

    @Test func audioBeforeTheSocketIsBufferedThenSentTaggedByChannel() async throws {
        let store = await phoneStore(api: api, engine: engine)
        await store.call("+4930123456")
        engine.play(.you)
        engine.play(.them)
        try await waitUntil { store.pendingFrames.count == 2 }
        #expect(store.pendingFrames.count == 2)

        engine.emit(.connected)
        try await waitUntil { store.socket != nil }
        engine.play(.you)
        let socket = try #require(api.phoneCalls.socket)
        try await waitUntil { socket.frames.count == 3 }
        #expect(socket.frames.map { $0.first } == [1, 2, 1])
        #expect(socket.frames[1] == Data([2, 2, 2, 2, 2]))
    }

    @Test func segmentsUpsertByIDAndTranslationsAttach() async throws {
        let (store, socket) = try await activeCall()
        socket.emit(.segments([segment("s1", "Hallo"), segment("s2", "Hi", isUser: true)]))
        try await waitUntil { store.transcript.segments.count == 2 }
        #expect(store.transcription == .active)
        socket.emit(.segments([segment("s1", "Hallo, wie geht's?")]))
        socket.emit(.translations(["s1": ["Hello, how are you?"], "unknown": ["dropped"]]))
        try await waitUntil { !store.transcript.translations.isEmpty }
        #expect(store.transcript.segments.map(\.text) == ["Hallo, wie geht's?", "Hi"])
        #expect(store.transcript.translations == ["s1": ["Hello, how are you?"]])
    }

    @Test func aDroppedSocketReconnectsAndKeepsTheTranscript() async throws {
        let (store, socket) = try await activeCall()
        socket.emit(.segments([segment("s1", "Hallo")]))
        try await waitUntil { store.transcription == .active }
        socket.drop()
        try await waitUntil { api.phoneCalls.sockets.count == 2 }
        #expect(api.phoneCalls.sockets.count == 2)
        #expect(store.transcript.segments.count == 1)
        #expect(api.phoneCalls.socketRequests.map(\.callID).allSatisfy { $0 == store.callID })
    }

    @Test func reconnectingGivesUpAfterTenTries() async throws {
        let (store, socket) = try await activeCall()
        api.phoneCalls.socketError = .transport("offline")
        socket.drop()
        // 5, 10, 20 … ms: ten tries take about five seconds of backoff at this base; check the counting instead.
        try await waitUntil { store.reconnectAttempts >= 3 }
        #expect(store.transcription == .reconnecting || store.transcription == .connecting)
        store.reconnectAttempts = PhoneCallStore.maxReconnectAttempts
        store.scheduleReconnect()
        #expect(store.transcription == .failed)
    }

    @Test func anAcceptedSocketWithoutAudioSaysSo() async throws {
        let (store, socket) = try await activeCall()
        // The backend's first frames are `service_status`; they count as accepted, like Flutter.
        socket.emit(.status("initiating"))
        try await waitUntil { store.transcription == .active }
        #expect(store.transcription == .active)
        try await waitUntil { store.transcription == .noAudio }
        #expect(store.transcription == .noAudio)
        engine.play(.them)
        try await waitUntil { store.transcription == .active }
        #expect(store.transcription == .active)
    }

    @Test func endingTheCallClosesTheSocketAndStopsReconnecting() async throws {
        let (store, socket) = try await activeCall()
        store.end()
        // A socket still opening when the call ends is closed as soon as it arrives.
        try await waitUntil { socket.isClosed }
        #expect(socket.isClosed)
        try await Task.sleep(for: .milliseconds(30))
        #expect(api.phoneCalls.sockets.count == 1)
    }
}

struct PhoneCallParsingTests {
    @Test func socketFramesParseLikeFlutter() {
        #expect(PhoneCallSocketEvent.parse("ping") == nil)
        let segments = PhoneCallSocketEvent.parse(#"[{"id":"s1","text":"Hi","is_user":true,"start":0.5,"end":1.0}]"#)
        #expect(segments == .segments([LiveSegment(id: "s1", text: "Hi", speaker: nil, speakerID: nil, isUser: true, start: 0.5, end: 1)]))
        let translating = #"{"type":"translating","segments":[{"id":"s1","translations":[{"lang":"en","text":"Hello"}]}]}"#
        #expect(PhoneCallSocketEvent.parse(translating) == .translations(["s1": ["Hello"]]))
        #expect(PhoneCallSocketEvent.parse(#"{"type":"service_status","status":"ready"}"#) == .status("ready"))
    }

    @Test func errorBodiesCarryTheReason() {
        #expect(PhoneCallErrorDetail(body: #"{"detail":"Phone number already verified"}"#) == .message("Phone number already verified"))
        #expect(PhoneCallErrorDetail(body: #"{"detail":{"error":"phone_call_quota_exceeded","monthly_limit":3}}"#)
            == .quotaExceeded(monthlyLimit: 3))
        #expect(PhoneCallErrorDetail(body: "Internal Server Error") == nil)
    }
}
