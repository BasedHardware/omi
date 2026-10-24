import Foundation
import OmiCore
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct OnboardingButtonAndWatchTests {
    func make(onboarded: Bool = false, watchPaired: Bool = false) -> (OnboardingStore, Preferences) {
        let prefs = freshPreferences(onboarded: onboarded)
        let store = OnboardingStore(api: FakeAPIClient(), preferences: prefs, watchPaired: { watchPaired }, updateDisplayName: { _ in })
        return (store, prefs)
    }

    @Test func theOmiPathTeachesTheButton() {
        let (store, _) = make()
        store.hasOmi = true
        store.step = .voice
        store.next()
        #expect(store.step == .askOmi)
        store.next()
        #expect(store.step == .voiceReply)
        store.next()
        #expect(store.step == .doublePress)
        store.next()
        #expect(store.step == .permissions)
        store.hasOmi = false
        #expect(!store.path.contains(.askOmi) && !store.path.contains(.voiceReply) && !store.path.contains(.doublePress))
    }

    @Test func theWatchStepNeedsAPairedWatch() {
        #expect(!make().0.path.contains(.watch))
        let (store, _) = make(watchPaired: true)
        store.hasOmi = false
        store.step = .voice
        store.next()
        #expect(store.step == .watch)
    }

    /// First run: spoken replies start off until picked; a replay shows the saved choice.
    @Test func voiceReplyStartsOffOnTheFirstRun() {
        let (first, prefs) = make()
        prefs.set(2, for: .voiceResponseMode)
        first.showVoiceReply()
        #expect(first.voiceReplyMode == .off)
        #expect(prefs.integer(.voiceResponseMode, default: 1) == 0)
        first.chooseVoiceReply(.headphonesOnly)
        first.showVoiceReply()
        #expect(first.voiceReplyMode == .headphonesOnly)
        #expect(prefs.integer(.voiceResponseMode, default: 0) == 1)

        let (replay, replayPrefs) = make(onboarded: true)
        replayPrefs.set(2, for: .voiceResponseMode)
        replay.showVoiceReply()
        #expect(replay.voiceReplyMode == .always)
    }
}

@MainActor
struct WatchPermissionTests {
    func make(_ link: FakeWatchLink) -> WatchStore {
        let api = FakeAPIClient()
        let capture = CaptureStore(
            api: api, engine: FakePhoneEngine(), deviceEngine: FakeDeviceTranscription(), preferences: freshPreferences(),
            defaultOnDevice: false, userID: { "alice" }
        )
        return WatchStore(link: link, capture: capture, isSignedIn: { true }, omiBattery: { nil })
    }

    @Test func theWatchAsksForItsMicrophoneAndAnswers() async {
        let link = FakeWatchLink()
        let watch = make(link)
        watch.requestMicrophone()
        #expect(link.sent == [.requestMicrophonePermission])
        #expect(watch.isRequestingMicrophone)
        await watch.handle(.microphonePermissionResult(granted: true))
        #expect(watch.microphoneGranted == true)
        #expect(!watch.isRequestingMicrophone)
        #expect(!watch.isWatchPaired)
    }

    @Test func aWatchThatNeverAnswersStopsTheWait() async throws {
        let watch = make(FakeWatchLink())
        watch.requestMicrophone(answerWait: .milliseconds(20))
        try await waitUntil { !watch.isRequestingMicrophone }
        #expect(!watch.isRequestingMicrophone)
        #expect(watch.microphoneGranted == nil)
    }
}

@MainActor
struct DiagnosticsReportTests {
    @Test func sendingReturnsTheTicket() async throws {
        let api = FakeAPIClient()
        let devices = DeviceStore(makeDriver: { FakeDriver() }, preferences: freshPreferences())
        let environment = DeviceDiagnosticsLog.Environment(appVersion: "1", appBuild: "1", osVersion: "26", phoneModel: "x")
        let report = DiagnosticsReportStore(api: api, devices: devices, environment: environment)
        await report.send()
        #expect(report.phase == .sent(ticket: "A1B2C3D4E5F6"))
        let sent = try #require(api.diagnosticsUploads.bundles.first)
        let object = try JSONSerialization.jsonObject(with: sent) as? [String: Any]
        #expect(object?["schema_version"] as? Int == 2)
        report.dismiss()
        api.fail(with: .http(status: 500, body: ""))
        await report.send()
        #expect(report.phase == .failed)
    }
}
