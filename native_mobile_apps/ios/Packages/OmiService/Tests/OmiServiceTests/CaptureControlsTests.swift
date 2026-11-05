import Foundation
import OmiDevice
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct CaptureControlsTests {
    func make(
        _ api: FakeAPIClient,
        _ engine: FakePhoneEngine = FakePhoneEngine(),
        preferences: Preferences = freshPreferences()
    ) -> CaptureStore {
        CaptureStore(
            api: api, engine: engine, deviceEngine: FakeDeviceTranscription(), preferences: preferences,
            defaultOnDevice: false, userID: { "alice" }
        )
    }

    /// Pause drops the Omi's audio but keeps the conversation (socket) open; resume sends again.
    @Test func pauseHoldsBackDeviceAudio() async {
        let api = FakeAPIClient()
        let capture = make(api)
        await capture.startDevice(codec: .opusFS320)
        capture.ingestDeviceAudio(Data(repeating: 1, count: 80))
        capture.pause()
        #expect(capture.isPaused)
        #expect(capture.isDeviceMuted)
        capture.ingestDeviceAudio(Data(repeating: 1, count: 80))
        #expect(api.liveChannel.audioBytes == 80)
        #expect(!api.liveChannel.closed)
        #expect(capture.isLive)
        await capture.resume()
        capture.ingestDeviceAudio(Data(repeating: 1, count: 40))
        #expect(api.liveChannel.audioBytes == 120)
        #expect(!capture.isDeviceMuted)
        #expect(api.finalizeCalls == 0)
    }

    /// The Omi's mute outlasts the conversation and the app (Flutter capture policy).
    @Test func muteCarriesIntoTheNextConversation() async {
        let prefs = freshPreferences()
        let api = FakeAPIClient()
        let capture = make(api, preferences: prefs)
        capture.isDeviceMuted = true
        await capture.startDevice(codec: .opusFS320)
        #expect(capture.isPaused)
        capture.ingestDeviceAudio(Data(repeating: 1, count: 80))
        #expect(api.liveChannel.audioBytes == 0)
        let relaunched = make(FakeAPIClient(), preferences: prefs)
        #expect(relaunched.isDeviceMuted)
        capture.isDeviceMuted = false
        #expect(!capture.isPaused)
        capture.ingestDeviceAudio(Data(repeating: 1, count: 80))
        #expect(api.liveChannel.audioBytes == 80)
    }

    /// Phone pause releases the microphone; the conversation stays open and is not muted for the Omi.
    @Test func phonePauseReleasesTheMicrophone() async {
        let api = FakeAPIClient()
        let engine = FakePhoneEngine()
        let capture = make(api, engine)
        await capture.startPhone()
        capture.pause()
        #expect(engine.stopped)
        #expect(capture.isPaused)
        #expect(!capture.isDeviceMuted)
        #expect(!api.liveChannel.closed)
        await capture.resume()
        #expect(!capture.isPaused)
        await capture.stop()
        #expect(api.finalizeCalls == 1)
    }

    @Test func starIsAppliedWhenTheConversationEnds() async {
        let api = FakeAPIClient()
        let capture = make(api)
        await capture.startDevice(codec: .opusFS320)
        capture.toggleStar()
        capture.toggleStar()
        #expect(!capture.starsConversation)
        capture.toggleStar()
        await capture.endDeviceConversation()
        #expect(api.deviceActions.starred.map(\.id) == ["c-new"])
        #expect(api.deviceActions.starred.first?.starred == true)
        #expect(!capture.starsConversation)
        await capture.endDeviceConversation()
        #expect(api.deviceActions.starred.count == 1)
    }

    @Test func conversationTimeoutGoesToTheListenSocket() async {
        let prefs = freshPreferences()
        let api = FakeAPIClient()
        let capture = make(api, preferences: prefs)
        #expect(capture.conversationTimeout == 120)
        capture.conversationTimeout = 600
        await capture.startDevice(codec: .opusFS320)
        await capture.stop()
        capture.conversationTimeout = -1
        await capture.startPhone()
        #expect(api.listenOptions.map(\.conversationTimeout) == [600, -1])
        #expect(prefs.integer(.conversationSilenceDuration, default: 0) == -1)
        #expect(CaptureStore.conversationTimeouts == [120, 300, 600, 1800, -1])
    }
}
