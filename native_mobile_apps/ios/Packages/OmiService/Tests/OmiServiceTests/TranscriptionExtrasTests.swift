import Foundation
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

/// Hands a custom provider's segments to capture (the real one: `CustomTranscriber`).
@MainActor
final class FakeCustomTranscriber: CustomTranscribing {
    let providerName: String
    private(set) var fedBytes = 0
    private(set) var stopped = false
    private var continuation: AsyncStream<LiveSegment>.Continuation?

    init(providerName: String) {
        self.providerName = providerName
    }

    func start() -> AsyncStream<LiveSegment> {
        let (stream, continuation) = AsyncStream.makeStream(of: LiveSegment.self)
        self.continuation = continuation
        return stream
    }

    func feed(_ pcm16: Data) {
        fedBytes += pcm16.count
    }

    func stop() {
        stopped = true
        continuation?.finish()
    }

    func emit(_ segment: LiveSegment) {
        continuation?.yield(segment)
    }
}

/// Custom STT, the plan's fallback to the iPhone, translations and Store audio on phone.
@MainActor
struct TranscriptionExtrasTests {
    let api = FakeAPIClient()
    let engine = FakePhoneEngine()
    let prefs = freshPreferences()
    let directory: URL

    init() {
        directory = FileManager.default.temporaryDirectory.appending(path: "extras-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    func make(device: FakeDeviceTranscription = FakeDeviceTranscription()) -> CaptureStore {
        CaptureStore(api: api, engine: engine, deviceEngine: device, preferences: prefs, defaultOnDevice: false, userID: { "alice" })
    }

    func settle(until condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    func segment(_ id: String, _ text: String) -> LiveSegment {
        LiveSegment(id: id, text: text, speaker: "SPEAKER_00", speakerID: 0, isUser: false, start: 0, end: 1)
    }

    // MARK: Custom provider

    @Test func aCustomProviderTranscribesAndTheSocketTakesItsWords() async throws {
        let secrets = InMemorySecretStore()
        let settings = CustomSTTSettings(preferences: prefs, secrets: secrets)
        settings.save(CustomSTTConfig(provider: .openai, apiKey: " sk-1 "))
        let capture = make()
        let fake = FakeCustomTranscriber(providerName: "openai")
        capture.customSTT = settings
        capture.makeCustomTranscriber = { _ in fake }
        await capture.startPhone()
        #expect(capture.transcriber == .custom("openai"))
        #expect(api.listenOptions.last?.clientTranscription == true)
        engine.pcm.1.yield(Data(repeating: 1, count: 640))
        try await settle { fake.fedBytes == 640 }
        #expect(api.liveChannel.audioBytes == 640)
        fake.emit(segment("c1", "From my provider"))
        try await settle { capture.transcriptText == "From my provider" }
        #expect(api.liveChannel.suggestedProviders == ["openai"])
        // Server segments (the echo of what the phone sent) do not replace the provider's.
        api.liveChannel.emit(.segments([segment("x", "server")]))
        await capture.stop()
        #expect(fake.stopped)
        #expect(capture.transcriptText == "From my provider")
    }

    @Test func theKeyLivesInTheKeychainAndFlutterJSONLosesIt() {
        prefs.set(#"{"provider":"deepgramLive","api_key":"dg-secret","language":"de","model":"nova-3"}"#, for: .customSttConfig)
        let secrets = InMemorySecretStore()
        let settings = CustomSTTSettings(preferences: prefs, secrets: secrets)
        #expect(settings.config == CustomSTTConfig(provider: .deepgramLive, apiKey: "dg-secret", model: "nova-3", language: "de"))
        #expect(secrets.secret(CustomSTTSettings.keyName) == "dg-secret")
        #expect(prefs.string(.customSttConfig)?.contains("dg-secret") == false)
        #expect(settings.isActive)
        settings.save(nil)
        #expect(settings.config == nil)
        #expect(secrets.secret(CustomSTTSettings.keyName) == nil)
        #expect(prefs.string(.customSttConfig) == nil)
    }

    @Test func flutterOnDeviceIsTheIPhoneAndUnknownProvidersReadAsOff() {
        prefs.set(#"{"provider":"onDeviceWhisper","language":"multi"}"#, for: .customSttConfig)
        #expect(CustomSTTSettings(preferences: prefs, secrets: InMemorySecretStore()).config == nil)
        #expect(prefs.bool(.onDeviceTranscription, default: false))
        // Signed out (the JSON is gone): a leftover key is removed too.
        let secrets = InMemorySecretStore()
        secrets.setSecret("old", for: CustomSTTSettings.keyName)
        prefs.set(nil as String?, for: .customSttConfig)
        _ = CustomSTTSettings(preferences: prefs, secrets: secrets)
        #expect(secrets.secret(CustomSTTSettings.keyName) == nil)
    }

    @Test func thePollingTranscriberSendsThreeSecondChunksAndOffsetsTheirTimes() async throws {
        let answer = Data(#"{"segments":[{"start":0.5,"end":1.0,"text":"chunk"}]}"#.utf8)
        let transport = FakeCustomSTTTransport(responses: [(Data("{}".utf8), 500), (answer, 200)])
        let log = DebugLog(preferences: nil, directory: directory)
        let transcriber = CustomTranscriber(
            config: CustomSTTConfig(provider: .openai, apiKey: "sk-secret"), transport: transport, log: log, interval: .seconds(60)
        )
        var received: [LiveSegment] = []
        let stream = transcriber.start()
        let reader = Task { for await segment in stream { received.append(segment) } }
        transcriber.feed(Data(count: 32000))
        await transcriber.flush() // 500: the audio waits for the next try
        await transcriber.flush()
        transcriber.feed(Data(count: 32000))
        await transcriber.flush()
        try await settle { received.count == 2 }
        #expect(transport.requests.count == 3)
        #expect(received.map(\.start) == [0.5, 1.5]) // the second second's chunk starts at 1 s
        #expect(log.entries.contains { $0.message.contains("HTTP 500") })
        #expect(!log.entries.contains { $0.message.contains("sk-secret") })
        transcriber.stop()
        reader.cancel()
    }

    @Test func deepgramStreamsAudioAndClosesTheStream() async throws {
        let transport = FakeCustomSTTTransport()
        let transcriber = CustomTranscriber(config: CustomSTTConfig(provider: .deepgramLive, apiKey: "dg"), transport: transport, log: nil)
        var received: [LiveSegment] = []
        let stream = transcriber.start()
        let reader = Task { for await segment in stream { received.append(segment) } }
        transcriber.feed(Data(count: 640))
        #expect(transport.socket.audioBytes == 640)
        let word = #"{"punctuated_word":"Hey","start":1,"end":1.2,"speaker":2}"#
        let results = #"{"type":"Results","is_final":true,"channel":{"alternatives":[{"transcript":"hey","words":["#
        transport.socket.emit(results + word + "]}]}}")
        try await settle { received.count == 1 }
        #expect(received.first?.text == "Hey")
        #expect(received.first?.speaker == "SPEAKER_02")
        transcriber.stop()
        #expect(transport.socket.texts == [#"{"type":"CloseStream"}"#])
        #expect(transport.socket.closed)
        reader.cancel()
    }

    // MARK: Plan

    @Test func noMinutesLeftStartsOnTheIPhone() async throws {
        api.transcriptionAllowance = .onDevice
        let capture = make()
        await capture.refreshTranscriptionAllowance()
        await capture.startPhone()
        #expect(capture.transcriber == .iPhone)
        #expect(capture.transcriptionNotice == .switchedToIPhone)
        #expect(api.listenOptions.last?.clientTranscription == true)
        await capture.stop()
        // Minutes are back: Omi transcribes the next recording.
        api.transcriptionAllowance = .managed
        await capture.refreshTranscriptionAllowance()
        await capture.startPhone()
        #expect(capture.transcriber == .omi)
        #expect(capture.transcriptionNotice == nil)
        await capture.stop()
    }

    @Test func aBlockedPlanKeepsTheAudioOnThePhone() async throws {
        api.transcriptionAllowance = .blocked
        let capture = make()
        let sync = SyncStore(api: api, directory: directory, userID: { "alice" })
        capture.phoneBuffer = sync
        await capture.refreshTranscriptionAllowance()
        await capture.startPhone()
        #expect(capture.isBuffering)
        #expect(capture.transcriptionNotice == .recordingOnly)
        #expect(api.listenOptions.isEmpty)
        await capture.stop()
    }

    @Test func runningOutMidRecordingSwitchesTheSessionToTheIPhone() async throws {
        let capture = make()
        await capture.startPhone()
        #expect(capture.transcriber == .omi)
        api.liveChannel.emit(.freemiumThreshold(remainingSeconds: 120, requiresOnDevice: true))
        try await settle { capture.transcriptionNotice == .minutesRunningLow(seconds: 120) }
        api.liveChannel.emit(.freemiumThreshold(remainingSeconds: 0, requiresOnDevice: true))
        try await settle { capture.transcriber == .iPhone }
        #expect(capture.transcriptionNotice == .switchedToIPhone)
        #expect(api.liveChannel.closeReasons == ["retry"])
        #expect(api.listenOptions.count == 2)
        #expect(api.listenOptions.last?.clientTranscription == true)
        // The recognizer's final words are now the transcript, sent to the new socket.
        engine.transcript.1.yield((segment: segment("p1", "Mine now"), isFinal: true))
        try await settle { capture.transcriptText == "Mine now" }
        #expect(api.liveChannel.suggestedProviders == ["apple_on_device"])
        #expect(capture.transcriptionAllowance == .onDevice)
        await capture.stop()
    }

    // MARK: Translation

    @Test func translationsJoinTheirSegments() async throws {
        let capture = make()
        await capture.startPhone()
        api.liveChannel.emit(.segments([segment("s1", "Hola")]))
        try await settle { capture.segments.count == 1 }
        var translated = segment("s1", "Hola")
        translated.translations = [LiveSegment.Translation(lang: "en", text: "Hello")]
        api.liveChannel.emit(.translated([translated, segment("unknown", "x")]))
        try await settle { !(capture.segments.first?.translations.isEmpty ?? true) }
        #expect(capture.segments.map(\.translations) == [[LiveSegment.Translation(lang: "en", text: "Hello")]])
        await capture.stop()
    }

    // MARK: Store audio on phone

    @Test func storeAudioOnPhoneKeepsALiveRecordingThatNeverUploads() async throws {
        prefs.set(true, for: .unlimitedLocalStorageEnabled)
        let capture = make()
        let sync = SyncStore(api: api, directory: directory, userID: { "alice" })
        capture.phoneBuffer = sync
        await capture.startPhone()
        engine.pcm.1.yield(Data(repeating: 4, count: 3200))
        try await settle { api.liveChannel.audioBytes == 3200 && sync.keptFile?.recording.frames == 10 }
        await capture.stop()
        try await settle { sync.recordings.count == 1 }
        let kept = try #require(sync.recordings.first)
        #expect(kept.isKept)
        #expect(kept.isPhone)
        #expect(kept.frames == 10)
        #expect(sync.status == .synced)
        await sync.uploadPending()
        await sync.process(kept.filename)
        #expect(api.syncBackend.uploads.isEmpty)
        #expect(sync.audioFile(for: kept.filename) != nil)
    }

    @Test func theOmisLiveAudioIsKeptAsOpusFrames() async throws {
        prefs.set(true, for: .unlimitedLocalStorageEnabled)
        let capture = make()
        let sync = SyncStore(api: api, directory: directory, userID: { "alice" })
        capture.phoneBuffer = sync
        await capture.startDevice(codec: .opusFS320)
        capture.ingestDeviceAudio(Data(repeating: 9, count: 40))
        capture.ingestDeviceAudio(Data(repeating: 8, count: 38))
        capture.deviceDisconnected()
        let kept = try #require(sync.recordings.first)
        #expect(kept.isKept)
        #expect(!kept.isPhone)
        #expect(kept.filename.contains("_opus_fs320_16000_1_fs320_"))
        let data = try Data(contentsOf: directory.appending(path: kept.filename))
        #expect(SyncStore.frames(in: data).map(\.count) == [40, 38])
    }

    @Test func offByDefaultNothingIsKept() async throws {
        let capture = make()
        let sync = SyncStore(api: api, directory: directory, userID: { "alice" })
        capture.phoneBuffer = sync
        await capture.startPhone()
        engine.pcm.1.yield(Data(repeating: 4, count: 640))
        try await settle { api.liveChannel.audioBytes == 640 }
        await capture.stop()
        #expect(sync.recordings.isEmpty)
    }

    // MARK: Background

    @Test func backgroundWorkUploadsThenRefreshesOnlyWhenSignedIn() async {
        var calls: [String] = []
        var signedIn = false
        let work = BackgroundWork(
            isSignedIn: { signedIn },
            uploadRecordings: { calls.append("upload") },
            refreshLists: { calls.append("refresh") }
        )
        #expect(await work.run(.refresh) == false)
        #expect(calls.isEmpty)
        signedIn = true
        #expect(await work.run(.processing))
        #expect(calls == ["upload", "refresh"])
    }
}
