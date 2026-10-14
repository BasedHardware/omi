import Foundation
import OmiCore
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

/// A conversation left open (app closed, Omi or socket gone) is finalized before the next socket,
/// a dropped Omi socket resumes the same recording, and Omi audio without a socket is held.
@MainActor
struct CaptureLifecycleTests {
    func make(_ api: FakeAPIClient, preferences: Preferences = freshPreferences()) -> CaptureStore {
        CaptureStore(
            api: api, engine: FakePhoneEngine(), deviceEngine: FakeDeviceTranscription(), preferences: preferences,
            defaultOnDevice: false, userID: { "alice" }
        )
    }

    func settle(until condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    /// The backend's copy of a conversation the last socket recorded into.
    func leftover(_ api: FakeAPIClient, id: String = "c-old", status: Conversation.Status = .inProgress, words: Bool = true) {
        var conversation = Fixtures.conversation(id: id, title: "", minutesAgo: 30)
        conversation.status = status
        let line = ConversationDetail.Line(id: 0, speaker: "You", isUser: true, text: "We ship on Friday.", start: 0)
        api.conversationExtras.details[id] = ConversationDetail(
            conversation: conversation,
            summaryActionItems: [],
            transcript: words ? [line] : []
        )
    }

    func leftOpen(_ id: String = "c-old") -> Preferences {
        let preferences = freshPreferences()
        preferences.set(id, for: .captureOpenConversation)
        return preferences
    }

    // MARK: Remembering the open conversation

    @Test func theSocketsConversationIsRememberedUntilTheRecordingEnds() async throws {
        let preferences = freshPreferences()
        let api = FakeAPIClient()
        let capture = make(api, preferences: preferences)
        await capture.startDevice(codec: .opusFS320)
        api.liveChannel.emit(.conversationStarted(id: "c1"))
        try await settle { preferences.string(.captureOpenConversation) == "c1" }
        #expect(preferences.string(.captureOpenConversation) == "c1")
        // The Omi going away does not end it: the next start does.
        capture.deviceDisconnected()
        #expect(preferences.string(.captureOpenConversation) == "c1")
        await capture.startDevice(codec: .opusFS320)
        await capture.stop()
        #expect(api.finalizeCalls == 1)
        #expect(preferences.string(.captureOpenConversation) == nil)
    }

    @Test func aConversationTheServerFinalizedIsForgotten() async throws {
        let preferences = freshPreferences()
        let api = FakeAPIClient()
        let capture = make(api, preferences: preferences)
        await capture.startDevice(codec: .opusFS320)
        api.liveChannel.emit(.conversationStarted(id: "c1"))
        api.liveChannel.emit(.processingStarted(conversationID: "c1"))
        api.liveChannel.emit(.conversationStarted(id: "c2"))
        try await settle { preferences.string(.captureOpenConversation) == "c2" }
        api.liveChannel.emit(.conversationCreated(id: "c2"))
        try await settle { preferences.string(.captureOpenConversation) == nil }
        #expect(preferences.string(.captureOpenConversation) == nil)
    }

    // MARK: Finalizing it at the next start

    @Test func aConversationLeftOpenIsFinalizedBeforeTheNextSocketOpens() async {
        let preferences = leftOpen()
        let api = FakeAPIClient()
        leftover(api)
        var refreshed = false
        let capture = make(api, preferences: preferences)
        capture.onConversationFinished = { refreshed = true }
        await capture.startDevice(codec: .opusFS320)
        #expect(api.listenBackend.calls == ["finalize:c-old", "listen"])
        #expect(api.finalizeCalls == 0)
        #expect(refreshed)
        #expect(capture.isLive)
        #expect(preferences.string(.captureOpenConversation) == nil)
    }

    @Test func thePhoneAndTheWatchFinalizeItToo() async {
        let starts: [@MainActor (CaptureStore) async -> Void] = [{ await $0.startPhone() }, { await $0.startWatch() }]
        for start in starts {
            let api = FakeAPIClient()
            leftover(api)
            let capture = make(api, preferences: leftOpen())
            await start(capture)
            #expect(api.listenBackend.calls == ["finalize:c-old", "listen"])
        }
    }

    @Test func emptyFinishedOrMissingConversationsAreLeftToTheBackend() async {
        let setUps: [@MainActor (FakeAPIClient) -> Void] = [{ leftover($0, words: false) }, { leftover($0, status: .completed) }, { _ in }]
        for setUp in setUps {
            let api = FakeAPIClient()
            setUp(api)
            let preferences = leftOpen()
            let capture = make(api, preferences: preferences)
            await capture.startDevice(codec: .opusFS320)
            #expect(api.listenBackend.calls == ["listen"])
            #expect(api.finalizeCalls == 0)
            #expect(preferences.string(.captureOpenConversation) == nil)
        }
    }

    /// A backend without the durable finalization worker (the local harness) answers 503: the
    /// in-progress endpoint is used, but only while it would finalize this very conversation.
    @Test func withoutADurableWorkerOnlyTheNewestInProgressIsFinalized() async {
        for newest in ["c-old", "c-other"] {
            let api = FakeAPIClient()
            leftover(api)
            api.listenBackend.finalizeError = .http(status: 503, body: "")
            api.placesAndHealth.inProgressConversationID = newest
            let capture = make(api, preferences: leftOpen())
            await capture.startDevice(codec: .opusFS320)
            let expected = newest == "c-old" ? ["finalize:c-old", "finalizeInProgress", "listen"] : ["finalize:c-old", "listen"]
            #expect(api.listenBackend.calls == expected)
            #expect(capture.isLive)
        }
    }

    @Test func aFailedFinalizeIsRetriedAtTheNextStart() async {
        let api = FakeAPIClient()
        leftover(api)
        api.listenBackend.finalizeError = .http(status: 429, body: "")
        let preferences = leftOpen()
        let capture = make(api, preferences: preferences)
        await capture.startDevice(codec: .opusFS320)
        #expect(capture.isLive)
        #expect(preferences.string(.captureOpenConversation) == "c-old")
    }

    @Test func anUncheckedConversationStaysRemembered() async {
        let preferences = leftOpen()
        let capture = make(FakeAPIClient(error: .transport("offline")), preferences: preferences)
        await capture.startPhone()
        #expect(preferences.string(.captureOpenConversation) == "c-old")
    }

    // MARK: Omi audio without a socket

    @Test func omiAudioWhileTheSocketOpensReachesIt() async throws {
        let api = FakeAPIClient()
        api.listenBackend.openDelay = .milliseconds(150)
        let capture = make(api)
        let start = Task { await capture.startDevice(codec: .opusFS320) }
        try await settle { capture.phase == .starting }
        for _ in 0 ..< 3 {
            capture.ingestDeviceAudio(Data(repeating: 1, count: 80))
        }
        #expect(api.liveChannel.audioBytes == 0)
        await start.value
        #expect(api.liveChannel.audioMessages == 3)
        #expect(api.liveChannel.audioBytes == 240)
    }

    @Test func mutedOrIdleOmiAudioIsNotHeld() async throws {
        let api = FakeAPIClient()
        api.listenBackend.openDelay = .milliseconds(100)
        let capture = make(api)
        capture.isDeviceMuted = true
        let start = Task { await capture.startDevice(codec: .opusFS320) }
        try await settle { capture.phase == .starting }
        capture.ingestDeviceAudio(Data(repeating: 1, count: 80))
        await start.value
        capture.isDeviceMuted = false
        await capture.stop()
        capture.ingestDeviceAudio(Data(repeating: 1, count: 80))
        #expect(capture.heldDeviceAudio.isEmpty)
        #expect(api.liveChannel.audioBytes == 0)
    }

    // MARK: A dropped Omi socket

    @Test func aDroppedOmiSocketReopensWithTheSameRecordingID() async throws {
        let api = FakeAPIClient()
        let capture = make(api)
        capture.deviceReconnectDelays = [.milliseconds(50)]
        await capture.startDevice(codec: .opusFS320)
        api.liveChannel.emit(.status("disconnected: The network connection was lost."))
        try await settle { capture.reconnectingDevice }
        // Audio meanwhile is held and sent first once the socket is back.
        capture.ingestDeviceAudio(Data(repeating: 1, count: 80))
        try await settle { api.listenOptions.count == 2 && !capture.reconnectingDevice }
        #expect(api.listenOptions.count == 2)
        #expect(api.listenOptions[0].clientConversationID == api.listenOptions[1].clientConversationID)
        #expect(capture.isLive)
        #expect(api.liveChannel.audioBytes == 80)
        #expect(api.finalizeCalls == 0)
    }

    @Test func stoppingEndsTheReconnect() async throws {
        let api = FakeAPIClient()
        let capture = make(api)
        capture.deviceReconnectDelays = [.milliseconds(80)]
        await capture.startDevice(codec: .opusFS320)
        api.liveChannel.emit(.status("disconnected: lost"))
        try await settle { capture.reconnectingDevice }
        await capture.stop()
        try await Task.sleep(for: .milliseconds(200))
        #expect(api.listenOptions.count == 1)
        #expect(!capture.isLive)
        #expect(api.finalizeCalls == 1)
    }

    @Test func eachRecordingGetsItsOwnID() async {
        let api = FakeAPIClient()
        let capture = make(api)
        await capture.startDevice(codec: .opusFS320)
        await capture.endDeviceConversation()
        #expect(api.listenOptions.count == 2)
        #expect(api.listenOptions[0].clientConversationID != api.listenOptions[1].clientConversationID)
    }
}
