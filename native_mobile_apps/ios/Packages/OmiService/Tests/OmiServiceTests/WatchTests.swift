import Foundation
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// WatchConnectivity stand-in: tests push the watch's messages and read what the iPhone sent back.
final class FakeWatchLink: WatchLink, @unchecked Sendable {
    let stream: (AsyncStream<WatchMessage>, AsyncStream<WatchMessage>.Continuation) = AsyncStream.makeStream()
    var messages: AsyncStream<WatchMessage> {
        stream.0
    }

    private let lock = NSLock()
    private var _sent: [WatchMessage] = []
    private var _states: [WatchPhoneState] = []
    var sent: [WatchMessage] {
        lock.withLock { _sent }
    }

    var states: [WatchPhoneState] {
        lock.withLock { _states }
    }

    /// The watch sends one dictionary; the iPhone sees what WatchConnectivity would deliver.
    func receive(_ payload: [String: Any]) {
        if let message = WatchMessage(payload: payload) { stream.1.yield(message) }
    }

    func send(_ message: WatchMessage) {
        lock.withLock { _sent.append(message) }
    }

    func updateState(_ state: WatchPhoneState) {
        lock.withLock { _states.append(state) }
    }
}

struct WatchMessageTests {
    @Test func decodesTheFlutterWatchAppsDictionaries() {
        let pcm = Data(repeating: 3, count: 48000)
        let chunk: [String: Any] = [
            "method": "sendAudioChunk", "audioChunk": pcm, "chunkIndex": NSNumber(value: 4),
            "isLast": NSNumber(value: false), "sampleRate": NSNumber(value: 16000.0),
        ]
        #expect(WatchMessage(payload: chunk) == .audioChunk(WatchAudioChunk(data: pcm, index: 4, isLast: false)))
        #expect(WatchMessage(payload: ["method": "startRecording"]) == .startRecording)
        #expect(WatchMessage(payload: ["method": "stopRecording"]) == .stopRecording(reason: nil))
        // The watch reports `batteryLevel * 100` as a Float.
        let battery: [String: Any] = ["method": "batteryUpdate", "batteryLevel": Float(85), "batteryState": 2]
        #expect(WatchMessage(payload: battery) == .batteryUpdate(level: 85, state: 2))
        let info: [String: Any] = [
            "method": "watchInfoUpdate", "name": "Anna's Watch", "model": "Watch",
            "systemVersion": "11.2", "localizedModel": "Apple Watch",
        ]
        #expect(WatchMessage(payload: info) == .watchInfoUpdate(WatchInfo(
            name: "Anna's Watch", model: "Watch", systemVersion: "11.2", localizedModel: "Apple Watch"
        )))
    }

    @Test func rejectsUnknownOrIncompleteMessages() {
        #expect(WatchMessage(payload: ["method": "somethingNew"]) == nil)
        #expect(WatchMessage(payload: ["audioChunk": Data()]) == nil)
        #expect(WatchMessage(payload: ["method": "sendAudioChunk", "chunkIndex": 1]) == nil)
    }

    @Test func everyMessageSurvivesTheRoundTrip() {
        let messages: [WatchMessage] = [
            .startRecording, .stopRecording(reason: nil), .stopRecording(reason: .busy),
            .audioChunk(WatchAudioChunk(data: Data([1, 2, 3, 4]), index: 2, isLast: true)),
            .recordingError("Microphone permission denied"), .requestMicrophonePermission,
            .microphonePermissionResult(granted: true), .requestBattery, .batteryUpdate(level: 40, state: 1),
            .requestWatchInfo, .watchInfoUpdate(WatchInfo(name: "W", model: "M", systemVersion: "11", localizedModel: "L")),
        ]
        for message in messages {
            #expect(WatchMessage(payload: message.payload) == message)
        }
        #expect(WatchMessage.stopRecording(reason: nil).payload.count == 1)
        let state = WatchPhoneState(capture: .omi, omiBattery: 72)
        #expect(WatchPhoneState(payload: state.payload) == state)
        #expect(WatchPhoneState(payload: WatchPhoneState(capture: .idle, omiBattery: nil).payload)?.omiBattery == nil)
    }
}

@MainActor
struct WatchStoreTests {
    final class Harness {
        let api = FakeAPIClient()
        let link = FakeWatchLink()
        let engine = FakePhoneEngine()
        let capture: CaptureStore
        let store: WatchStore
        var signedIn: Bool? = true
        var omiBattery: Int?

        @MainActor init(signInWait: Duration = .milliseconds(200)) {
            capture = CaptureStore(
                api: api, engine: engine, deviceEngine: FakeDeviceTranscription(), preferences: freshPreferences(),
                defaultOnDevice: false, userID: { "alice" }
            )
            var harness: Harness?
            store = WatchStore(
                link: link, capture: capture,
                isSignedIn: { harness?.signedIn }, omiBattery: { harness?.omiBattery },
                signInWait: signInWait
            )
            harness = self
            store.start()
        }
    }

    func settle(until condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    @Test func watchRecordingStreamsIntoAnAppleWatchConversation() async throws {
        let h = Harness()
        var finished = false
        h.capture.onConversationFinished = { finished = true }
        h.link.receive(["method": "startRecording"])
        h.link.receive(WatchMessage.audioChunk(WatchAudioChunk(data: Data(repeating: 1, count: 48000), index: 0, isLast: false)).payload)
        try await settle { h.api.liveChannel.audioBytes == 48000 }
        #expect(h.capture.source == .watch)
        #expect(h.capture.isLive)
        #expect(h.api.listenOptions.map(\.source) == [.appleWatch])
        #expect(ListenSocket.Options.Source.appleWatch.rawValue == "apple_watch")
        #expect(h.api.listenOptions.first?.codec == .pcm16)
        #expect(h.api.listenOptions.first?.sampleRate == 16000)
        // 1.5 s chunk → fifteen 100 ms socket messages.
        #expect(h.api.liveChannel.audioMessages == 15)

        h.link.receive(WatchMessage.audioChunk(WatchAudioChunk(data: Data(), index: 1, isLast: true)).payload)
        h.link.receive(["method": "stopRecording"])
        try await settle { !h.capture.isLive && finished }
        #expect(h.api.finalizeCalls == 1)
        #expect(h.api.liveChannel.closed)
        #expect(finished)
        // The watch stopped itself; the iPhone does not echo a stop back.
        #expect(h.link.sent.isEmpty)
    }

    @Test func stoppingOnThePhoneStopsTheWatch() async throws {
        let h = Harness()
        h.link.receive(["method": "startRecording"])
        try await settle { h.capture.isLive }
        await h.capture.stop()
        #expect(h.link.sent == [.stopRecording(reason: nil)])
        #expect(h.api.finalizeCalls == 1)
    }

    @Test func audioOutsideAWatchRecordingIsDropped() async throws {
        let h = Harness()
        h.link.receive(WatchMessage.audioChunk(WatchAudioChunk(data: Data(repeating: 1, count: 3200), index: 7, isLast: false)).payload)
        h.link.receive(["method": "batteryUpdate", "batteryLevel": 55.4, "batteryState": 1])
        try await settle { h.store.battery != nil }
        #expect(h.store.battery == 55)
        #expect(h.api.listenOptions.isEmpty)
        #expect(h.api.liveChannel.audioBytes == 0)
    }

    @Test func phoneAlreadyRecordingRefusesTheWatch() async throws {
        let h = Harness()
        await h.capture.startPhone()
        h.link.receive(["method": "startRecording"])
        try await settle { !h.link.sent.isEmpty }
        #expect(h.link.sent == [.stopRecording(reason: .busy)])
        #expect(h.capture.source == .phone)
    }

    @Test func signedOutIPhoneRefusesTheWatch() async throws {
        let h = Harness(signInWait: .milliseconds(50))
        h.signedIn = false
        h.link.receive(["method": "startRecording"])
        try await settle { !h.link.sent.isEmpty }
        #expect(h.link.sent == [.stopRecording(reason: .signedOut)])
        #expect(!h.capture.isLive)
    }

    @Test func waitsForTheSessionToRestore() async throws {
        let h = Harness(signInWait: .seconds(2))
        h.signedIn = nil
        h.link.receive(["method": "startRecording"])
        try await Task.sleep(for: .milliseconds(80))
        #expect(!h.capture.isLive)
        h.signedIn = true
        try await settle { h.capture.isLive }
        #expect(h.capture.source == .watch)
        #expect(h.link.sent.isEmpty)
    }

    @Test func failedSocketTellsTheWatch() async throws {
        let h = Harness()
        h.api.fail(with: .transport("offline"))
        h.link.receive(["method": "startRecording"])
        try await settle { !h.link.sent.isEmpty }
        #expect(h.link.sent == [.stopRecording(reason: .failed)])
    }

    @Test func mirrorsCaptureAndOmiBatteryToTheWatch() async throws {
        let h = Harness()
        #expect(h.link.states == [WatchPhoneState(capture: .idle, omiBattery: nil)])
        h.link.receive(["method": "startRecording"])
        try await settle { h.link.states.last?.capture == .watch }
        #expect(h.link.states.last == WatchPhoneState(capture: .watch, omiBattery: nil))
        await h.capture.stop()
        try await settle { h.link.states.last?.capture == .idle }
        #expect(h.link.states.last?.capture == .idle)
    }
}
