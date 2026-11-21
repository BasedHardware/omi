import Foundation
import OmiAudio
import OmiCore
import OmiDevice
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// Answers `start` with fresh streams every time, so a test can see a recording come back to life.
final class ResumablePhoneEngine: PhoneCaptureEngine, @unchecked Sendable {
    private(set) var attempts = 0
    private(set) var starts = 0
    /// While false, `start` throws, like a microphone a call still holds.
    var canStart = true
    var isRunning = false

    func start(transcribeOnDevice _: Bool) async throws -> PhoneCaptureStreams {
        attempts += 1
        guard canStart else { throw CaptureFailure.engine("microphone not available") }
        let (pcm, _) = AsyncStream.makeStream(of: Data.self)
        starts += 1
        isRunning = true
        return PhoneCaptureStreams(pcm16: pcm, level: AsyncStream { $0.finish() }, transcript: nil)
    }

    func stop() {
        isRunning = false
    }
}

/// The OS signals, driven by hand.
@MainActor
final class FakeAudioSessionMonitor: AudioSessionMonitoring {
    private var handler: (@MainActor (AudioSessionEvent) -> Void)?
    private(set) var started = false
    private(set) var stopped = false

    func start(_ onEvent: @escaping @MainActor (AudioSessionEvent) -> Void) {
        started = true
        handler = onEvent
    }

    func stop() {
        stopped = true
        handler = nil
    }

    func send(_ event: AudioSessionEvent) {
        handler?(event)
    }
}

@MainActor
struct CaptureInterruptionTests {
    private func make(
        _ api: FakeAPIClient,
        _ engine: ResumablePhoneEngine,
        session: FakeAudioSessionMonitor,
        tick: Duration = .milliseconds(10)
    ) -> CaptureStore {
        CaptureStore(
            api: api, engine: engine, deviceEngine: FakeDeviceTranscription(), preferences: freshPreferences(),
            defaultOnDevice: false, userID: { "alice" }, healthTick: tick, audioSession: session
        )
    }

    /// Waits until the condition holds, or two seconds pass (the assertion after it reports the
    /// timeout). Always a state the store publishes, never an engine's own counter: a fake engine
    /// counts a start before the store's continuation has run, which made this flaky under load.
    private func settle(until condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    private func isMicrophoneTaken(_ notice: CaptureNotice?) -> Bool {
        if case .microphoneTaken = notice { return true }
        return false
    }

    @Test func aCallPausesCaptureAndSaysWhy() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()
        #expect(session.started)
        #expect(engine.starts == 1)

        session.send(.interrupted)
        #expect(isMicrophoneTaken(capture.notice))
        #expect(capture.isPaused)
        #expect(!engine.isRunning)
        // Still live: the conversation, the socket and the file all stay.
        #expect(capture.isLive)
    }

    @Test func captureComesBackWhenTheInterruptionEnds() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        session.send(.interrupted)
        #expect(capture.isPaused)
        session.send(.interruptionEnded(shouldResume: true))
        try await settle(until: { !capture.isPaused && capture.notice == nil })
        #expect(!capture.isPaused)
        #expect(capture.notice == nil)
        #expect(engine.starts >= 2)
    }

    /// iOS omits `shouldResume` when another app's audio ends the interruption, so the app probes
    /// anyway instead of leaving the recording silent for good.
    @Test func captureProbesEvenWithoutShouldResume() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        session.send(.interrupted)
        session.send(.interruptionEnded(shouldResume: false))
        try await settle(until: { !capture.isPaused && capture.notice == nil })
        #expect(!capture.isPaused)
        #expect(capture.notice == nil)
        #expect(engine.starts >= 2)
    }

    @Test func aMicrophoneThatStaysTakenKeepsTryingAndStaysVisible() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        engine.canStart = false
        session.send(.interrupted)
        session.send(.interruptionEnded(shouldResume: true))
        try await settle(until: { engine.attempts >= 3 })
        // Every probe was refused, and the recording is still there to be continued.
        #expect(capture.isLive)
        #expect(capture.isPaused)
        #expect(isMicrophoneTaken(capture.notice))

        engine.canStart = true
        try await settle(until: { !capture.isPaused })
        #expect(!capture.isPaused)
        #expect(capture.notice == nil)
    }

    @Test func aRouteWithoutAnInputPausesWithItsOwnReason() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        session.send(.routeChanged(input: nil))
        #expect(capture.notice == .inputGone)
        #expect(capture.isPaused)

        session.send(.routeChanged(input: "iPhone Microphone"))
        try await settle(until: { !capture.isPaused && capture.notice == nil })
        #expect(capture.notice == nil)
        #expect(!capture.isPaused)
        #expect(engine.starts >= 2)
    }

    /// The user's own pause is not the system's: no banner, and the app does not fight the user.
    @Test func aUserPauseClearsTheNoticeAndDoesNotRestart() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        capture.pause()
        try await Task.sleep(for: .milliseconds(60))
        #expect(engine.starts == 1)
        #expect(capture.notice == nil)

        await capture.resume()
        #expect(capture.notice == nil)
        #expect(!capture.isPaused)
        #expect(engine.starts == 2)
    }

    @Test func aResumeTheSystemRefusesStaysVisibleAndTriesAgain() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        capture.pause()
        engine.canStart = false
        await capture.resume()
        #expect(capture.isLive)
        #expect(capture.isPaused)
        #expect(isMicrophoneTaken(capture.notice))

        engine.canStart = true
        try await settle(until: { !capture.isPaused })
        #expect(!capture.isPaused)
    }

    /// A dead engine with no notification at all (competing audio stops the tap): the health loop
    /// is the only thing that can notice, and it takes the microphone back.
    @Test func aSilentlyDeadEngineIsTakenBack() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        engine.isRunning = false
        try await settle(until: { engine.isRunning && engine.starts >= 2 })
        #expect(engine.isRunning)
        #expect(capture.isLive)
        #expect(!capture.isPaused)
    }

    @Test func stoppingTheRecordingEndsTheHealthWatch() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        await capture.stop()
        #expect(session.stopped)
        let attempts = engine.attempts
        try await Task.sleep(for: .milliseconds(60))
        #expect(engine.attempts == attempts)
    }

    @Test func dismissingTheNoticeLeavesTheRecordingAlone() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startPhone()

        session.send(.interrupted)
        try await settle(until: { capture.notice != nil })
        capture.dismissNotice()
        #expect(capture.notice == nil)
        #expect(capture.isLive)
    }

    /// A failed start before the recording is live is still a failure: nothing is on disk yet.
    @Test func aFailedFirstStartStillFails() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        engine.canStart = false
        await capture.startPhone()
        if case .failed = capture.phase {} else { Issue.record("expected a failed capture, got \(capture.phase)") }
    }

    /// The Omi's audio arrives over Bluetooth and never uses the app's audio session.
    @Test func theWatchOfTheDeviceIgnoresSessionEvents() async throws {
        let api = FakeAPIClient()
        let engine = ResumablePhoneEngine()
        let session = FakeAudioSessionMonitor()
        let capture = make(api, engine, session: session)
        await capture.startDevice(codec: .opusFS320)
        session.send(.interrupted)
        #expect(capture.notice == nil)
        #expect(!session.started)
    }
}
