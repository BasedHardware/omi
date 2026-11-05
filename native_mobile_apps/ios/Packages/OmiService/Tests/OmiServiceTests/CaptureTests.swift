import Foundation
import OmiCore
import OmiDevice
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

final class FakePhoneEngine: PhoneCaptureEngine, @unchecked Sendable {
    let pcm: (AsyncStream<Data>, AsyncStream<Data>.Continuation) = AsyncStream.makeStream()
    let transcript: (AsyncStream<(segment: LiveSegment, isFinal: Bool)>, AsyncStream<(segment: LiveSegment, isFinal: Bool)>.Continuation)
        = AsyncStream.makeStream()
    private(set) var stopped = false
    private(set) var isRunning = false

    func start(transcribeOnDevice: Bool) async throws -> PhoneCaptureStreams {
        isRunning = true
        return PhoneCaptureStreams(
            pcm16: pcm.0, level: AsyncStream { $0.finish() }, transcript: transcribeOnDevice ? transcript.0 : nil
        )
    }

    func stop() {
        stopped = true
        isRunning = false
        pcm.1.finish()
        transcript.1.finish()
    }
}

final class FakeDriver: DeviceDriving, @unchecked Sendable {
    let stream: (AsyncStream<OmiDeviceManager.Event>, AsyncStream<OmiDeviceManager.Event>.Continuation) = AsyncStream.makeStream()
    var events: AsyncStream<OmiDeviceManager.Event> {
        stream.0
    }

    private(set) var connected: [UUID] = []
    func startScan() {}
    func stopScan() {}
    func connect(_ id: UUID) {
        connected.append(id)
    }

    func disconnect() {}
    func readBattery() {}
}

final class FakeDeviceTranscription: DeviceTranscriptionEngine, @unchecked Sendable {
    let stream: (AsyncStream<(segment: LiveSegment, isFinal: Bool)>, AsyncStream<(segment: LiveSegment, isFinal: Bool)>.Continuation)
        = AsyncStream.makeStream()
    private(set) var fedBytes = 0
    private let lock = NSLock()

    func start() async throws -> DeviceTranscription {
        DeviceTranscription(feed: { [weak self] frame in self?.lock.withLock { self?.fedBytes += frame.count } }, transcript: stream.0)
    }

    func stop() {
        stream.1.finish()
    }
}

@MainActor
struct CaptureStoreTests {
    func make(
        _ api: FakeAPIClient,
        _ engine: FakePhoneEngine,
        onDevice: Bool,
        device: FakeDeviceTranscription = FakeDeviceTranscription()
    ) -> CaptureStore {
        CaptureStore(
            api: api, engine: engine, deviceEngine: device, preferences: freshPreferences(),
            defaultOnDevice: onDevice, userID: { "alice" }
        )
    }

    func settle() async throws {
        try await Task.sleep(for: .milliseconds(30))
    }

    /// Waits until the condition holds (or two seconds pass): the stores react on their own tasks,
    /// so a fixed sleep is too short when the whole suite runs in parallel.
    func settle(until condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    @Test func phoneCaptureStreamsAudioAndFinalizes() async throws {
        let api = FakeAPIClient()
        let engine = FakePhoneEngine()
        let capture = make(api, engine, onDevice: false)
        var finished = false
        capture.onConversationFinished = { finished = true }
        await capture.startPhone()
        #expect(capture.isLive)
        engine.pcm.1.yield(Data(repeating: 1, count: 640))
        api.liveChannel.emit(.segments([LiveSegment(
            id: "s1",
            text: "Hello Anna",
            speaker: nil,
            speakerID: 0,
            isUser: true,
            start: 0,
            end: 1
        )]))
        try await settle { api.liveChannel.audioBytes == 640 && capture.transcriptText == "Hello Anna" }
        #expect(api.liveChannel.audioBytes == 640)
        #expect(capture.transcriptText == "Hello Anna")
        await capture.stop()
        #expect(engine.stopped)
        #expect(api.liveChannel.closed)
        #expect(api.finalizeCalls == 1)
        #expect(capture.lastConversationID == "c-new")
        #expect(finished)
    }

    @Test func serverModeShowsTheIPhonesWordsUntilTheServerCatchesUp() async throws {
        let api = FakeAPIClient()
        let engine = FakePhoneEngine()
        let capture = make(api, engine, onDevice: false)
        await capture.startPhone()
        // The recognizer's words show right away as the live line, final or not…
        let local = LiveSegment(id: "o1", text: "Hello there", speaker: "SPEAKER_00", speakerID: 0, isUser: true, start: 0, end: 2)
        engine.transcript.1.yield((local, true))
        try await settle { capture.partial?.text == "Hello there" }
        #expect(capture.partial?.text == "Hello there")
        // …but never become the transcript or reach the server.
        #expect(capture.segments.isEmpty)
        #expect(api.liveChannel.suggested.isEmpty)
        // The server's segment replaces the preview.
        api.liveChannel.emit(.segments([
            LiveSegment(id: "s1", text: "Hello there.", speaker: nil, speakerID: 0, isUser: true, start: 0, end: 2),
        ]))
        try await settle { capture.partial == nil }
        #expect(capture.transcriptText == "Hello there.")
        #expect(capture.partial == nil)
    }

    @Test func thePreviewNeverRepeatsWhatTheServerAlreadyShows() async throws {
        let api = FakeAPIClient()
        let engine = FakePhoneEngine()
        let capture = make(api, engine, onDevice: false)
        await capture.startPhone()
        func local(_ text: String) -> LiveSegment {
            LiveSegment(id: "o1", text: text, speaker: "SPEAKER_00", speakerID: 0, isUser: true, start: 0, end: 4)
        }
        engine.transcript.1.yield((local("Hello there how are"), false))
        try await settle { capture.partial?.text == "Hello there how are" }
        let served = LiveSegment(
            id: "s1", text: "Hello there.", speaker: nil, speakerID: 0, isUser: true, start: 0, end: 1
        )
        api.liveChannel.emit(.segments([served]))
        try await settle { capture.partial?.text == "how are" }
        // The recognizer repeats its whole line; only the words after the server's show.
        engine.transcript.1.yield((local("Hello there how are you today"), false))
        try await settle { capture.partial?.text == "how are you today" }
        #expect(capture.transcriptText == "Hello there. how are you today")
    }

    @Test func onDeviceModeSendsSuggestedTranscript() async throws {
        let api = FakeAPIClient()
        let engine = FakePhoneEngine()
        let capture = make(api, engine, onDevice: true)
        await capture.startPhone()
        let partial = LiveSegment(id: "o1", text: "Hello", speaker: "SPEAKER_00", speakerID: 0, isUser: true, start: 0, end: 1)
        let final = LiveSegment(id: "o1", text: "Hello there", speaker: "SPEAKER_00", speakerID: 0, isUser: true, start: 0, end: 2)
        engine.transcript.1.yield((partial, false))
        try await settle { capture.partial?.text == "Hello" }
        #expect(capture.partial?.text == "Hello")
        engine.transcript.1.yield((final, true))
        // Server echoes are ignored on-device (the local transcript is the truth).
        api.liveChannel.emit(.segments([LiveSegment(id: "x", text: "echo", speaker: nil, speakerID: 0, isUser: true, start: 0, end: 2)]))
        try await settle { !api.liveChannel.suggested.isEmpty }
        try await settle()
        #expect(capture.transcriptText == "Hello there")
        #expect(api.liveChannel.suggested.map(\.text) == ["Hello there"])
    }

    @Test func wearableAudioIsTranscribedOnDevice() async throws {
        let api = FakeAPIClient()
        let device = FakeDeviceTranscription()
        let capture = make(api, FakePhoneEngine(), onDevice: true, device: device)
        await capture.startDevice(codec: .opusFS320)
        capture.ingestDeviceAudio(Data(repeating: 7, count: 80))
        device.stream.1.yield((
            LiveSegment(id: "d1", text: "From the wearable", speaker: nil, speakerID: 0, isUser: true, start: 0, end: 1),
            true
        ))
        try await settle()
        #expect(api.liveChannel.audioBytes == 80)
        #expect(device.fedBytes == 80)
        #expect(capture.transcriptText == "From the wearable")
        #expect(api.liveChannel.suggested.map(\.text) == ["From the wearable"])
    }

    @Test func doubleTapFinalizesAndKeepsListening() async {
        let api = FakeAPIClient()
        let capture = make(api, FakePhoneEngine(), onDevice: false)
        var finished = 0
        capture.onConversationFinished = { finished += 1 }
        await capture.startDevice(codec: .opusFS320)
        capture.ingestDeviceAudio(Data(repeating: 7, count: 80))
        await capture.endDeviceConversation()
        #expect(api.finalizeCalls == 1)
        #expect(finished == 1)
        #expect(capture.isLive)
        #expect(capture.source == .device)
        // The still-connected Omi's audio flows into the next conversation.
        capture.ingestDeviceAudio(Data(repeating: 7, count: 40))
        #expect(api.liveChannel.audioBytes == 120)
    }

    @Test func doubleTapWithoutDeviceCaptureDoesNothing() async {
        let api = FakeAPIClient()
        let capture = make(api, FakePhoneEngine(), onDevice: false)
        await capture.startPhone()
        await capture.endDeviceConversation()
        #expect(api.finalizeCalls == 0)
        await capture.stop()
        await capture.startDevice(codec: .opusFS320)
        capture.deviceDisconnected()
        await capture.endDeviceConversation()
        #expect(api.finalizeCalls == 1)
        #expect(!capture.isLive)
    }

    @Test func serverFinalizationEventRefreshes() async throws {
        let api = FakeAPIClient()
        let capture = make(api, FakePhoneEngine(), onDevice: false)
        var finished = 0
        capture.onConversationFinished = { finished += 1 }
        await capture.startPhone()
        api.liveChannel.emit(.conversationCreated(id: "c42"))
        try await settle { finished == 1 }
        #expect(capture.lastConversationID == "c42")
        #expect(finished == 1)
    }
}

@MainActor
struct DeviceStoreTests {
    @Test func reconnectsDevicePairedInFlutterBuild() {
        let prefs = freshPreferences()
        let id = UUID()
        prefs.set(#"{"name":"Omi","id":"\#(id.uuidString)","type":"omi","rssi":-50}"#, for: .btDevice)
        let driver = FakeDriver()
        let devices = DeviceStore(makeDriver: { driver }, preferences: prefs)
        #expect(devices.paired?.name == "Omi")
        devices.start()
        #expect(driver.connected == [id])
    }

    @Test func noPairedDeviceMeansNoBluetoothPrompt() {
        var created = false
        let devices = DeviceStore(makeDriver: { created = true; return FakeDriver() }, preferences: freshPreferences())
        devices.start()
        #expect(!created)
    }

    @Test func connectionLifecycle() {
        let prefs = freshPreferences()
        let devices = DeviceStore(makeDriver: { FakeDriver() }, preferences: prefs)
        var readyCodec: OmiGATT.Codec?
        var audio = 0
        devices.onReady = { readyCodec = $0 }
        devices.onAudio = { audio += $0.count }
        let id = UUID()
        devices.handle(.connected(id: id, name: "Omi DevKit"))
        devices.handle(.battery(83))
        devices.handle(.codec(.opusFS320))
        devices.handle(.audio(Data(repeating: 0, count: 80)))
        devices.handle(.info(model: "Omi CV 1", firmware: "2.0.10", manufacturer: "Based Hardware"))
        #expect(devices.connection == .connected)
        #expect(devices.battery == 83)
        #expect(readyCodec == .opusFS320)
        #expect(audio == 80)
        #expect(PairedDevice.decode(prefs.string(.btDevice))?.firmwareRevision == "2.0.10")
        devices.forget()
        #expect(prefs.string(.btDevice) == nil)
    }

    func pairedStore(
        _ driver: FakeDriver,
        connectTimeout: Duration = .seconds(15),
        retryDelay: Duration = .milliseconds(10)
    ) -> (DeviceStore, UUID) {
        let prefs = freshPreferences()
        let id = UUID()
        prefs.set(PairedDevice(id: id.uuidString, name: "Omi").encoded, for: .btDevice)
        let devices = DeviceStore(makeDriver: { driver }, preferences: prefs, connectTimeout: connectTimeout, retryDelay: retryDelay)
        return (devices, id)
    }

    /// Cold start: the connect from `start()` lands before CoreBluetooth is powered on.
    @Test func connectsAgainOnceBluetoothIsReady() {
        let driver = FakeDriver()
        let (devices, id) = pairedStore(driver)
        devices.start()
        devices.handle(.bluetooth(.unknown))
        #expect(driver.connected == [id])
        devices.handle(.bluetooth(.ready))
        #expect(driver.connected == [id, id])
        devices.handle(.connected(id: id, name: "Omi"))
        devices.handle(.bluetooth(.ready))
        #expect(driver.connected == [id, id])
    }

    @Test func bluetoothOffDropsTheLinkAndOnReconnects() {
        let driver = FakeDriver()
        let (devices, id) = pairedStore(driver)
        var disconnects = 0
        devices.onDisconnect = { disconnects += 1 }
        devices.handle(.connected(id: id, name: "Omi"))
        devices.handle(.bluetooth(.poweredOff))
        #expect(devices.connection == .disconnected)
        #expect(disconnects == 1)
        #expect(driver.connected.isEmpty)
        devices.handle(.bluetooth(.ready))
        #expect(driver.connected == [id])
    }

    @Test func reconnectsRightAwayAfterTheLinkDrops() {
        let driver = FakeDriver()
        let (devices, id) = pairedStore(driver)
        var disconnects = 0
        devices.onDisconnect = { disconnects += 1 }
        devices.handle(.connected(id: id, name: "Omi"))
        devices.handle(.disconnected(id: id, error: nil))
        #expect(devices.connection == .disconnected)
        #expect(disconnects == 1)
        #expect(driver.connected == [id])
    }

    /// Polls instead of a fixed sleep: the suite runs in parallel and timers drift under load.
    func eventually(_ condition: () -> Bool) async throws {
        for _ in 0 ..< 200 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    @Test func failedAttemptsAreSpacedOutAndCapped() async throws {
        let driver = FakeDriver()
        let (devices, id) = pairedStore(driver)
        for attempt in 1 ... 3 {
            devices.handle(.connecting(id))
            devices.handle(.disconnected(id: id, error: "Connection failed"))
            #expect(driver.connected.count == attempt - 1)
            try await eventually { driver.connected.count == attempt }
        }
        devices.handle(.connecting(id))
        devices.handle(.disconnected(id: id, error: "Connection failed"))
        try await Task.sleep(for: .milliseconds(50))
        #expect(driver.connected.count == 3)
        // "Try again" starts over.
        devices.start()
        #expect(driver.connected.count == 4)
    }

    @Test func longConnectAttemptReadsAsNotConnected() async throws {
        let driver = FakeDriver()
        let (devices, id) = pairedStore(driver, connectTimeout: .milliseconds(10))
        devices.handle(.connecting(id))
        #expect(devices.connection == .connecting)
        try await eventually { devices.connection == .disconnected }
        #expect(devices.connection == .disconnected)
        // CoreBluetooth kept waiting; the Omi coming into range still connects.
        devices.handle(.connected(id: id, name: "Omi"))
        #expect(devices.connection == .connected)
    }

    @Test func ignoresThePreviousDeviceLettingGo() {
        let driver = FakeDriver()
        let (devices, id) = pairedStore(driver)
        devices.handle(.connecting(id))
        devices.handle(.disconnected(id: UUID(), error: nil))
        #expect(devices.connection == .connecting)
        #expect(driver.connected.isEmpty)
    }

    @Test func doubleTapEndsTheConversation() {
        let devices = DeviceStore(makeDriver: { FakeDriver() }, preferences: freshPreferences())
        var taps = 0
        devices.onDoubleTap = { taps += 1 }
        // Firmware sends `int[2]`, little-endian: 1 tap, 2 double tap, 3 long press.
        devices.handle(.button(Data([1, 0, 0, 0, 0, 0, 0, 0])))
        devices.handle(.button(Data([3, 0, 0, 0, 0, 0, 0, 0])))
        devices.handle(.button(Data([2])))
        #expect(taps == 0)
        devices.handle(.button(Data([2, 0, 0, 0, 0, 0, 0, 0])))
        #expect(taps == 1)
    }
}
