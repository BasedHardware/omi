import Foundation
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

/// Phone-mic offline buffering, Transcribe later and the recovery banner.
@MainActor
struct CaptureBufferingTests {
    let api = FakeAPIClient()
    let engine = FakePhoneEngine()
    let prefs = freshPreferences()
    let directory: URL

    init() {
        directory = FileManager.default.temporaryDirectory.appending(path: "phone-buffer-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    func make(_ sync: SyncStore) -> CaptureStore {
        let capture = CaptureStore(
            api: api, engine: engine, deviceEngine: FakeDeviceTranscription(), preferences: prefs,
            defaultOnDevice: false, userID: { "alice" }
        )
        capture.phoneBuffer = sync
        return capture
    }

    func makeSync() -> SyncStore {
        SyncStore(api: api, directory: directory, retryDelay: .milliseconds(40), userID: { "alice" })
    }

    func settle(until condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    @Test func aDroppedConnectionReopensTheSocketAndKeepsStreaming() async throws {
        let sync = makeSync()
        let capture = make(sync)
        capture.phoneReconnectDelays = [.milliseconds(300)]
        await capture.startPhone()
        engine.pcm.1.yield(Data(repeating: 1, count: 640))
        try await settle { api.liveChannel.audioBytes == 640 }
        api.liveChannel.emit(.status("disconnected: The network connection was lost."))
        try await settle { capture.isBuffering }
        #expect(capture.isLive)
        #expect(capture.recovery == .connectionLost)
        // The gap goes to the phone's file: the reconnect never costs words.
        engine.pcm.1.yield(Data(repeating: 2, count: 1000))
        try await settle { sync.phoneFile?.recording.frames == 3 }
        #expect(api.liveChannel.audioBytes == 640)
        // A second socket opens with the same recording id, and the file closes into the queue.
        try await settle { capture.recovery == nil }
        #expect(!capture.isBuffering)
        #expect(api.listenOptions.count == 2)
        #expect(api.listenOptions[1].clientConversationID == api.listenOptions[0].clientConversationID)
        #expect(sync.phoneRecordings.count == 1)
        // From here the recording streams again instead of waiting for the upload at the end.
        let streamedBefore = api.liveChannel.audioBytes
        engine.pcm.1.yield(Data(repeating: 3, count: 320))
        try await settle { api.liveChannel.audioBytes > streamedBefore }
        await capture.stop()
        try await settle { api.syncBackend.uploads.count == 1 }
        // What the socket missed uploads at the end, framed like every other phone file; what was
        // streamed before the drop is finalized with the conversation.
        let upload = try #require(api.syncBackend.uploads.first)
        #expect(upload.filename.hasPrefix("audio_phonemic_pcm16_16000_1_fs160_"))
        #expect(upload.data.count == 3 * (4 + 320))
        #expect(SyncStore.frames(in: upload.data).allSatisfy { $0.count == 320 })
        #expect(api.finalizeCalls == 1)
        #expect(prefs.string(.captureActiveSince) == nil)
    }

    @Test func aSocketThatStaysAwayKeepsRecordingToAFile() async throws {
        let sync = makeSync()
        let capture = make(sync)
        capture.phoneReconnectDelays = [.milliseconds(20)]
        await capture.startPhone()
        engine.pcm.1.yield(Data(repeating: 1, count: 640))
        try await settle { api.liveChannel.audioBytes == 640 }
        api.fail(with: .transport("offline"))
        api.liveChannel.emit(.status("disconnected: The network connection was lost."))
        try await settle { capture.isBuffering }
        engine.pcm.1.yield(Data(repeating: 2, count: 1000))
        try await settle { sync.phoneFile?.recording.frames == 3 }
        // Several retries pass with the socket still away: nothing else is streamed, the file keeps
        // the recording, and the banner stays up.
        try await Task.sleep(for: .milliseconds(200))
        #expect(capture.isLive)
        #expect(capture.isBuffering)
        #expect(capture.recovery == .connectionLost)
        #expect(api.liveChannel.audioBytes == 640)
        #expect(api.listenOptions.count == 1)
        await capture.stop()
        try await settle { api.syncBackend.uploads.count == 1 }
        #expect(api.finalizeCalls == 1)
        #expect(prefs.string(.captureActiveSince) == nil)
    }

    @Test func transcribeLaterOpensNoSocketAndWaitsForProcessNow() async throws {
        let sync = makeSync()
        let capture = make(sync)
        capture.transcribesLater = true
        await capture.startPhone()
        #expect(capture.isBuffering)
        #expect(api.listenOptions.isEmpty)
        engine.pcm.1.yield(Data(repeating: 4, count: 3200))
        try await settle { sync.phoneFile?.recording.frames == 10 }
        await capture.stop()
        #expect(api.finalizeCalls == 0)
        #expect(sync.phoneRecordings.count == 1)
        #expect(sync.phoneRecordings.first?.manual == true)
        #expect(sync.phoneRecordings.first?.filename.contains("_omibatchphone_") == true)
        await sync.uploadPending()
        #expect(api.syncBackend.uploads.isEmpty)
        // Waiting for the user is not "waiting to sync".
        #expect(!sync.hasPending)
        let file = try #require(sync.audioFile(for: sync.phoneRecordings[0].filename))
        #expect((try? Data(contentsOf: file))?.count == 44 + 3200)
        await sync.process(sync.phoneRecordings[0].filename)
        try await settle { api.syncBackend.uploads.count == 1 }
        #expect(api.syncBackend.uploads.count == 1)
    }

    @Test func withoutAConnectionAtTheStartThePhoneRecordsOffline() async throws {
        api.fail(with: .transport("offline"))
        let sync = makeSync()
        let capture = make(sync)
        await capture.startPhone()
        #expect(capture.isLive)
        #expect(capture.isBuffering)
        engine.pcm.1.yield(Data(repeating: 5, count: 640))
        try await settle { sync.phoneFile?.recording.frames == 2 }
        api.fail(with: nil)
        await capture.stop()
        try await settle { api.syncBackend.uploads.count == 1 }
        #expect(api.finalizeCalls == 0)
    }

    @Test func aRecordingFileSurvivesAnAppKill() async throws {
        let sync = makeSync()
        let capture = make(sync)
        capture.transcribesLater = true
        await capture.startPhone()
        engine.pcm.1.yield(Data(repeating: 6, count: 320 * 250))
        try await settle { sync.files.state.phoneOpen?.frames == 250 }
        // Relaunch without stopping: the file is adopted, the banner shows.
        let relaunched = makeSync()
        #expect(relaunched.phoneRecordings.first?.frames == 250)
        let next = CaptureStore(
            api: api, engine: FakePhoneEngine(), deviceEngine: FakeDeviceTranscription(), preferences: prefs,
            defaultOnDevice: false, userID: { "alice" }
        )
        guard case .interrupted = next.recovery else {
            Issue.record("expected the interrupted banner")
            return
        }
        next.dismissRecovery()
        #expect(next.recovery == nil)
        #expect(prefs.string(.captureActiveSince) == nil)
    }

    @Test func serverModelAndVADGateReachTheSocket() async {
        prefs.set(true, for: .vadGateEnabled)
        let capture = make(makeSync())
        capture.usesParakeet = true
        await capture.startPhone()
        #expect(api.listenOptions.last?.sttService == "parakeet")
        #expect(api.listenOptions.last?.vadGate == true)
        await capture.stop()
    }
}
