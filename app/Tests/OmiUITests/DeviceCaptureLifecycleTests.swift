import Combine
import Foundation
import OmiKit
import XCTest

@testable import OmiUI

private func packetJournalEntries(_ entries: [String]) -> [String] {
    entries.filter { entry in
        guard
            let parts = (try? JSONSerialization.jsonObject(with: Data(entry.utf8))) as? [String],
            parts.count == 2
        else { return false }
        return parts[0] == "p"
    }
}

@MainActor
final class DeviceCaptureLifecycleTests: XCTestCase {
    func testCaptureDoesNotAcceptAudioWithoutBackendTransport() async {
        let deviceTransport = ScriptedDeviceTransport()
        let store = AppStore(
            services: AppServices(devices: deviceTransport))

        await store.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))

        XCTAssertEqual(store.captureStage, .failed)
        XCTAssertEqual(
            store.deviceErrorCopy,
            "Audio recording is unavailable because the backend transport is not configured."
        )
        XCTAssertNil(store.runtime.captureMachine)

        await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        XCTAssertEqual(store.captureStage, .failed)
        XCTAssertNil(store.runtime.captureMachine)
    }

    func testCaptureLimitStopsOversizedPacketBeforeItEntersMemory() async {
        let deviceTransport = ScriptedDeviceTransport()
        let backend = ScriptedDeviceSessionBackend()
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: backend))

        await store.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))
        let oversized = DeviceAudioPacket(
            deviceId: "omi-1", connectionId: "link-1",
            raw: [UInt8](repeating: 0, count: recordingJournalMaxBytes + 1),
            receivedAtMs: 1_050)

        await store.ingestAudioPacket(oversized)

        XCTAssertEqual(store.captureStage, .failed)
        XCTAssertEqual(store.runtime.captureMachine?.byteCount, 0)
        XCTAssertEqual(
            store.deviceErrorCopy,
            "Recording reached its capture limit. Disconnect your Omi to save audio already received."
        )
    }

    func testBackendWithoutJournalUploadsCaptureOnDisconnect() async throws {
        let deviceTransport = ScriptedDeviceTransport()
        let backend = ScriptedDeviceSessionBackend()
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: backend))

        await store.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))
        for index in 0...deviceSessionMaxBatchPackets {
            await store.ingestAudioPacket(
                audioPacket(connectionId: "link-1", index: UInt16(index)))
        }
        XCTAssertEqual(store.captureStage, .active)

        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value

        XCTAssertNil(store.deviceErrorCopy)
        let requests = await backend.snapshot()
        XCTAssertEqual(
            requests.map(\.path),
            [
                "/v1/device-sessions",
                "/v1/device-sessions/session-1/audio",
                "/v1/device-sessions/session-1/audio",
                "/v1/device-sessions/session-1/complete",
            ])
        let openBody = try XCTUnwrap(requests[0].body)
        let open = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(openBody.utf8)) as? [String: Any])
        XCTAssertEqual(open["deviceId"] as? String, "omi-1")
        XCTAssertEqual((open["capturedAtMs"] as? NSNumber)?.int64Value, 1_050)

        let firstAudioBody = try XCTUnwrap(requests[1].body)
        let firstAudio = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(firstAudioBody.utf8)) as? [String: Any])
        let firstChunks = try XCTUnwrap(firstAudio["chunks"] as? [[String: Any]])
        XCTAssertEqual(firstChunks.count, deviceSessionMaxBatchPackets)
        XCTAssertEqual(
            firstChunks.compactMap { $0["chunkIndex"] as? Int },
            Array(0..<deviceSessionMaxBatchPackets))

        let secondAudioBody = try XCTUnwrap(requests[2].body)
        let secondAudio = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(secondAudioBody.utf8)) as? [String: Any])
        let secondChunks = try XCTUnwrap(secondAudio["chunks"] as? [[String: Any]])
        XCTAssertEqual(secondChunks.count, 1)
        XCTAssertEqual(secondChunks.first?["chunkIndex"] as? Int, deviceSessionMaxBatchPackets)
        XCTAssertEqual(
            secondChunks.compactMap { $0["bytesBase64"] as? String }
                .compactMap { Data(base64Encoded: $0) },
            [Data([1, 2, 3])])
    }

    func testDirectDeviceSessionHttpFailureIsVisibleAfterDisconnect() async {
        let deviceTransport = ScriptedDeviceTransport()
        let backend = ScriptedDeviceSessionBackend(failureStatus: 503)
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: backend))

        await store.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))
        await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value

        XCTAssertEqual(
            store.deviceErrorCopy,
            "Audio was captured, but the recording could not be saved. Check your connection and try again."
        )
    }

    func testStaleConnectionCannotChangeCaptureAndDisconnectJournalsAudio() async throws {
        let deviceTransport = ScriptedDeviceTransport()
        let journal = CaptureJournalTransport()
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: journal))
        let device = DiscoveredDevice(id: "omi-1", name: "NotePin")

        await store.connect(device)
        XCTAssertEqual(store.connectedDeviceName, "NotePin")
        XCTAssertEqual(store.captureStage, .waiting)

        await store.ingestAudioPacket(audioPacket(connectionId: "old-link", index: 0))
        XCTAssertEqual(store.captureStage, .waiting)

        store.applyConnectionEvent(
            DeviceConnectionEvent(
                deviceId: device.id, connectionId: "old-link", phase: .connected,
                info: BleDeviceInfo(model: "Stale model")))
        store.applyConnectionEvent(
            DeviceConnectionEvent(
                deviceId: device.id, connectionId: "old-link", phase: .disconnected))
        XCTAssertEqual(store.connectedDeviceName, "NotePin")
        XCTAssertEqual(store.connectedDeviceInfo, nil)
        XCTAssertEqual(store.captureStage, .waiting)

        store.applyConnectionEvent(
            DeviceConnectionEvent(
                deviceId: device.id, connectionId: "link-1", phase: .connected,
                info: BleDeviceInfo(model: "Updated NotePin")))
        XCTAssertEqual(store.connectedDeviceInfo?.model, "Updated NotePin")

        await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        XCTAssertEqual(store.captureStage, .active)
        let journaledBeforeDisconnect = await journal.snapshot()
        XCTAssertEqual(packetJournalEntries(journaledBeforeDisconnect.entries).count, 1)

        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value

        XCTAssertEqual(store.connectedDeviceName, nil)
        XCTAssertEqual(store.captureStage, .idle)
        XCTAssertEqual(deviceTransport.disconnectedDeviceIDs(), [device.id])

        store.applyConnectionEvent(
            DeviceConnectionEvent(
                deviceId: device.id, connectionId: "link-1", phase: .connected,
                info: BleDeviceInfo(model: "Retired connection")))
        await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 1))
        XCTAssertEqual(store.connectedDeviceName, nil)
        XCTAssertEqual(store.captureStage, .idle)

        let saved = await journal.snapshot()
        XCTAssertEqual(saved.input?.deviceId, device.id)
        XCTAssertEqual(saved.input?.deviceName, device.name)
        XCTAssertEqual(saved.input?.codec, 0)
        XCTAssertEqual(saved.input?.capturedAtMs, 1_050)
        XCTAssertEqual(packetJournalEntries(saved.entries).count, 1)
        XCTAssertNil(store.deviceErrorCopy)
        let packet = try XCTUnwrap(
            JSONSerialization.jsonObject(
                with: Data(try XCTUnwrap(packetJournalEntries(saved.entries).first).utf8))
                as? [String])
        XCTAssertEqual(packet, ["p", Data([1, 2, 3]).base64EncodedString()])
    }

    func testRetiredLinkEventsCannotCloseReconnectedCapture() async throws {
        let deviceTransport = ScriptedDeviceTransport()
        let journal = CaptureJournalTransport()
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: journal))
        let device = DiscoveredDevice(id: "omi-1", name: "NotePin")

        await store.connect(device)
        await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        XCTAssertEqual(store.captureStage, .active)

        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value
        XCTAssertEqual(store.captureStage, .idle)

        await store.connect(device)
        XCTAssertEqual(store.connectedDeviceName, "NotePin")
        XCTAssertEqual(store.captureStage, .waiting)

        store.applyConnectionEvent(
            DeviceConnectionEvent(
                deviceId: device.id, connectionId: "link-1", phase: .disconnected))
        XCTAssertEqual(store.connectedDeviceName, "NotePin")
        XCTAssertEqual(store.captureStage, .waiting)

        store.applyConnectionEvent(
            DeviceConnectionEvent(
                deviceId: device.id, connectionId: "link-1", phase: .connected,
                info: BleDeviceInfo(model: "Retired NotePin")))
        await store.ingestAudioPacket(
            audioPacket(connectionId: "link-1", index: 1, payload: [4, 5, 6]))
        XCTAssertEqual(store.connectedDeviceName, "NotePin")
        XCTAssertNil(store.connectedDeviceInfo)
        XCTAssertEqual(store.captureStage, .waiting)

        await store.ingestAudioPacket(
            audioPacket(connectionId: "link-2", index: 2, payload: [7, 8, 9]))
        XCTAssertEqual(store.captureStage, .active)
        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value

        XCTAssertEqual(deviceTransport.disconnectedDeviceIDs(), [device.id, device.id])
        let saved = await journal.snapshot()
        let packetEntries = packetJournalEntries(saved.entries)
        XCTAssertEqual(packetEntries.count, 2)
        let packets = try packetEntries.map { entry in
            try XCTUnwrap(JSONSerialization.jsonObject(with: Data(entry.utf8)) as? [String])
        }
        XCTAssertEqual(
            packets.map { $0[1] },
            [Data([1, 2, 3]).base64EncodedString(), Data([7, 8, 9]).base64EncodedString()])
    }

    func testReconnectWaitsForDisconnectedCaptureIngressToFinish() async throws {
        let deviceTransport = ScriptedDeviceTransport()
        let journal = CaptureJournalTransport()
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: journal))
        let device = DiscoveredDevice(id: "omi-1", name: "NotePin")

        await store.connect(device)
        await journal.pauseNextJournalCreation()
        let ingress = Task { @MainActor in
            await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        }
        await journal.waitUntilJournalCreationStarts()

        store.applyConnectionEvent(
            DeviceConnectionEvent(
                deviceId: device.id, connectionId: "link-1", phase: .disconnected))
        let reconnect = Task { @MainActor in await store.connect(device) }
        var busySubscription: AnyCancellable?
        let busy = deviceBusyChangedExpectation(store, cancellable: &busySubscription)
        await fulfillment(of: [busy], timeout: 1)
        busySubscription?.cancel()

        XCTAssertTrue(store.deviceBusy)
        XCTAssertEqual(deviceTransport.connectionAttemptCount(), 1)
        XCTAssertNil(store.connectedDeviceName)

        await journal.resumeJournalCreation()
        await ingress.value
        await reconnect.value

        XCTAssertEqual(deviceTransport.connectionAttemptCount(), 2)
        XCTAssertEqual(store.connectedDeviceName, "NotePin")
        XCTAssertEqual(store.captureStage, .waiting)
        await store.ingestAudioPacket(audioPacket(connectionId: "link-2", index: 1))
        XCTAssertEqual(store.captureStage, .active)
        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value
    }

    private func deviceBusyChangedExpectation(
        _ store: AppStore, cancellable: inout AnyCancellable?
    ) -> XCTestExpectation {
        let expectation = expectation(description: "reconnect waits for capture finalization")
        cancellable = store.$deviceBusy.dropFirst().first(where: { $0 }).sink { _ in
            expectation.fulfill()
        }
        return expectation
    }

    func testFailedJournalUploadReplaysAfterStoreRecreation() async throws {
        let vault = CaptureJournalVault()
        let journal = CaptureJournalTransport(vault: vault, failFirstAudioRequest: true)
        let deviceTransport = ScriptedDeviceTransport()
        let firstStore = AppStore(
            services: AppServices(devices: deviceTransport, transport: journal))

        await firstStore.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))
        await firstStore.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        await firstStore.disconnectDevice()
        await firstStore.runtime.streamTasks.last?.value

        XCTAssertTrue(firstStore.deviceErrorCopy?.contains("retained on this device") == true)
        let retainedJournals = try await journal.listRecordingJournals()
        let retained = try XCTUnwrap(retainedJournals.first)
        XCTAssertEqual(retained.sessionId, "00000000-0000-4000-8000-000000000001")
        let retainedJournal = try await journal.readRecordingJournal(handle: retained.handle)
        XCTAssertEqual(try restoreRecording(retainedJournal).acknowledged, 0)

        let reopenedStore = AppStore(services: AppServices(transport: journal))
        reopenedStore.onboardingRequired = false
        reopenedStore.returningUser = false
        await reopenedStore.recoverRecordingJournals()

        let recoveredJournals = try await journal.listRecordingJournals()
        XCTAssertTrue(recoveredJournals.isEmpty)
        XCTAssertNil(reopenedStore.deviceErrorCopy)
        let requests = await journal.requestPaths()
        XCTAssertEqual(requests.filter { $0 == "/v1/device-sessions" }.count, 1)
        XCTAssertEqual(requests.filter { $0.hasSuffix("/audio") }.count, 2)
        XCTAssertEqual(requests.filter { $0.hasSuffix("/complete") }.count, 1)
    }

    func testJournalRecoveryCannotCrossAccountPartitions() async throws {
        let vault = CaptureJournalVault()
        let accountA = CaptureJournalTransport(
            owner: "account-a", vault: vault, failFirstAudioRequest: true)
        let firstStore = AppStore(
            services: AppServices(devices: ScriptedDeviceTransport(), transport: accountA))
        await firstStore.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))
        await firstStore.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        await firstStore.disconnectDevice()
        await firstStore.runtime.streamTasks.last?.value
        let accountAJournals = try await accountA.listRecordingJournals()
        let savedForA = try XCTUnwrap(accountAJournals.first)

        let accountB = CaptureJournalTransport(owner: "account-b", vault: vault)
        let secondStore = AppStore(services: AppServices(transport: accountB))
        secondStore.onboardingRequired = false
        secondStore.returningUser = false
        await secondStore.recoverRecordingJournals()

        let accountBJournals = try await accountB.listRecordingJournals()
        XCTAssertTrue(accountBJournals.isEmpty)
        do {
            _ = try await accountB.readRecordingJournal(handle: savedForA.handle)
            XCTFail("Another account must not read the journal handle")
        } catch {
            XCTAssertEqual(error as? JournalFailure, .foreignHandle)
        }
        do {
            _ = try await accountB.requestRecordingJournal(
                handle: savedForA.handle,
                request: BackendRequest(method: .POST, path: "/v1/device-sessions"))
            XCTFail("Another account must not issue a backend request through the journal")
        } catch {
            XCTAssertEqual(error as? JournalFailure, .foreignHandle)
        }
        let accountAHandles = try await accountA.listRecordingJournals().map(\.handle)
        XCTAssertEqual(accountAHandles, [savedForA.handle])
        let accountBRequests = await accountB.requestPaths()
        XCTAssertTrue(accountBRequests.isEmpty)
    }

    func testJournalCreationFailureIsVisibleAfterDisconnect() async {
        let deviceTransport = ScriptedDeviceTransport()
        let journal = CaptureJournalTransport(failure: .create)
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: journal))

        await store.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))
        await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value

        XCTAssertEqual(
            store.deviceErrorCopy,
            "A captured audio packet could not be saved. Disconnect your Omi to preserve audio already journaled."
        )
    }

    func testJournalAppendFailureIsVisibleAfterDisconnect() async {
        let deviceTransport = ScriptedDeviceTransport()
        let journal = CaptureJournalTransport(failure: .append)
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: journal))

        await store.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))
        await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value

        XCTAssertEqual(
            store.deviceErrorCopy,
            "A captured audio packet could not be saved. Disconnect your Omi to preserve audio already journaled."
        )
    }

    func testJournalAppendAcknowledgementMismatchIsVisibleAfterDisconnect() async {
        let deviceTransport = ScriptedDeviceTransport()
        let journal = CaptureJournalTransport(failure: .acknowledgement)
        let store = AppStore(
            services: AppServices(devices: deviceTransport, transport: journal))

        await store.connect(DiscoveredDevice(id: "omi-1", name: "NotePin"))
        await store.ingestAudioPacket(audioPacket(connectionId: "link-1", index: 0))
        await store.disconnectDevice()
        await store.runtime.streamTasks.last?.value

        XCTAssertEqual(
            store.deviceErrorCopy,
            "A captured audio packet could not be saved. Disconnect your Omi to preserve audio already journaled."
        )
    }

    private func audioPacket(
        connectionId: String, index: UInt16, payload: [UInt8] = [1, 2, 3]
    ) -> DeviceAudioPacket {
        let crc = Policy.packetChecksum(payload)
        let raw =
            [UInt8(index & 0xFF), UInt8(index >> 8), 0xAA, 0x55] + payload + [
                UInt8((crc >> 24) & 0xFF), UInt8((crc >> 16) & 0xFF),
                UInt8((crc >> 8) & 0xFF), UInt8(crc & 0xFF),
            ]
        return DeviceAudioPacket(
            deviceId: "omi-1", connectionId: connectionId, raw: raw, receivedAtMs: 1_050)
    }
}

private actor ScriptedDeviceSessionBackend: BackendTransport {
    private let failureStatus: Int?
    private var requests: [BackendRequest] = []
    private var capturedAtMs: Int64?
    private var deviceId = "omi-1"
    private var deviceName: String? = "NotePin"
    private var codec = 0
    private var chunkCount = 0
    private var byteCount = 0
    private let sessionId = "session-1"

    init(failureStatus: Int? = nil) {
        self.failureStatus = failureStatus
    }

    func snapshot() -> [BackendRequest] { requests }

    func request(_ request: BackendRequest) async throws -> BackendResponse {
        requests.append(request)
        if let failureStatus {
            return BackendResponse(id: request.id, status: failureStatus, body: nil)
        }
        if request.path == "/v1/device-sessions" {
            let payload = try parseBody(request.body)
            capturedAtMs = (payload["capturedAtMs"] as? NSNumber)?.int64Value
            deviceId = payload["deviceId"] as? String ?? ""
            deviceName = payload["deviceName"] as? String
            codec = (payload["codec"] as? NSNumber)?.intValue ?? -1
            return try response(request, state: "open")
        }
        if request.path.hasSuffix("/audio") {
            let payload = try parseBody(request.body)
            guard let chunks = payload["chunks"] as? [[String: Any]] else {
                throw ScriptedBackendError.invalidRequest
            }
            chunkCount += chunks.count
            byteCount += chunks.compactMap { $0["bytesBase64"] as? String }
                .compactMap { Data(base64Encoded: $0) }.reduce(0) { $0 + $1.count }
            return try response(request, state: "open")
        }
        if request.path.hasSuffix("/complete") {
            return try response(request, state: "complete")
        }
        return BackendResponse(id: request.id, status: 404, body: nil)
    }

    func generationEvents(
        generationId: String, lastEventId: String?,
        onFrame: @escaping @Sendable (String) -> Void
    ) async throws -> BackendResponse {
        BackendResponse(id: generationId, status: 200, body: nil)
    }

    func cancelGenerationEvents(generationId: String) async {}
    func createWriteId() async throws -> String { "write-id" }
    func createRecordingId() async throws -> String { "123e4567-e89b-42d3-a456-426614174000" }
    func apiContract() async -> APIContract? { .canonical }
    func softwarePlane() async -> SoftwarePlane? { .new }
    func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane? { plane }
    func stampedBackendOrigin() async -> String? { nil }

    private func parseBody(_ body: String?) throws -> [String: Any] {
        guard let body,
            let payload = try JSONSerialization.jsonObject(with: Data(body.utf8)) as? [String: Any]
        else { throw ScriptedBackendError.invalidRequest }
        return payload
    }

    private func response(_ request: BackendRequest, state: String) throws -> BackendResponse {
        let session: [String: Any] = [
            "id": sessionId,
            "capturedAtMs": capturedAtMs.map { NSNumber(value: $0) as Any } ?? NSNull(),
            "deviceId": deviceId,
            "deviceName": deviceName.map { $0 as Any } ?? NSNull(),
            "codec": codec,
            "state": state,
            "byteCount": byteCount,
            "chunkCount": chunkCount,
            "startedAt": 1_050,
            "endedAt": state == "complete" ? 2_050 as Any : NSNull(),
        ]
        let data = try JSONSerialization.data(withJSONObject: ["session": session])
        return BackendResponse(
            id: request.id, status: 200, body: String(decoding: data, as: UTF8.self))
    }
}

private enum ScriptedBackendError: Error, Sendable {
    case invalidRequest
}

private final class ScriptedDeviceTransport: DeviceTransport, @unchecked Sendable {
    let bluetoothStates = AsyncStream<BluetoothState> { $0.finish() }
    let connectionEvents = AsyncStream<DeviceConnectionEvent> { $0.finish() }
    let audioPackets = AsyncStream<DeviceAudioPacket> { $0.finish() }

    private let disconnected = OmiKit.LockedBox<[String]>([])
    private let connectCount = OmiKit.LockedBox(0)

    func currentBluetoothState() async -> BluetoothState { .poweredOn }

    func startScan(durationSeconds: Int) async throws -> [DiscoveredDevice] {
        [DiscoveredDevice(id: "omi-1", name: "NotePin")]
    }

    func stopScan() async {}

    func connect(deviceId: String) async throws -> DeviceConnectionEvent {
        let sequence = connectCount.withLock { value in
            value += 1
            return value
        }
        return DeviceConnectionEvent(
            deviceId: deviceId, connectionId: "link-\(sequence)", phase: .connected)
    }

    func disconnect(deviceId: String) async {
        disconnected.withLock { $0.append(deviceId) }
    }

    func deviceInfo(deviceId: String) async -> BleDeviceInfo? { nil }

    func disconnectedDeviceIDs() -> [String] {
        disconnected.withLock { $0 }
    }

    func connectionAttemptCount() -> Int {
        connectCount.get()
    }
}

private actor CaptureJournalVault {
    private var journals: [String: [String: RecordingJournalRecord]] = [:]

    func create(owner: String, input: RecordingJournalInput) throws -> RecordingJournalRecord {
        let captureId = input.captureId
        if let existing = journals[owner]?[captureId] {
            guard
                existing.capturedAtMs == input.capturedAtMs
                    && existing.deviceId == input.deviceId
                    && existing.deviceName == input.deviceName
                    && existing.codec == input.codec
            else {
                throw JournalFailure.invalidCreateRetry
            }
            return existing
        }
        let journal = RecordingJournalRecord(
            capturedAtMs: input.capturedAtMs, handle: captureId, captureId: captureId,
            deviceId: input.deviceId, deviceName: input.deviceName, codec: input.codec,
            sessionId: nil, entries: [])
        journals[owner, default: [:]][captureId] = journal
        return journal
    }

    func list(owner: String) -> [RecordingJournalRecord] {
        guard let ownerJournals = journals[owner] else { return [] }
        return ownerJournals.values.sorted { $0.handle < $1.handle }
    }

    func read(owner: String, handle: String) throws -> RecordingJournalRecord {
        guard let journal = try ownedJournal(owner: owner, handle: handle) else {
            throw JournalFailure.missingHandle
        }
        return journal
    }

    func append(
        owner: String, handle: String, entry: String, expectedEntryCount: Int
    ) throws -> Int {
        guard var journal = try ownedJournal(owner: owner, handle: handle) else {
            throw JournalFailure.missingHandle
        }
        if journal.entries.count == expectedEntryCount {
            guard journal.entries.last == entry else {
                throw JournalFailure.invalidAppendSequence
            }
            return expectedEntryCount
        }
        guard journal.entries.count + 1 == expectedEntryCount else {
            throw JournalFailure.invalidAppendSequence
        }
        journal.entries.append(entry)
        journals[owner, default: [:]][handle] = journal
        return expectedEntryCount
    }

    func setSession(owner: String, handle: String, sessionId: String) throws {
        guard var journal = try ownedJournal(owner: owner, handle: handle) else {
            throw JournalFailure.missingHandle
        }
        journal.sessionId = sessionId
        journals[owner, default: [:]][handle] = journal
    }

    func remove(owner: String, handle: String) throws {
        _ = try read(owner: owner, handle: handle)
        journals[owner]?.removeValue(forKey: handle)
        if journals[owner]?.isEmpty == true { journals.removeValue(forKey: owner) }
    }

    private func ownedJournal(
        owner: String, handle: String
    ) throws -> RecordingJournalRecord? {
        guard let journal = journals[owner]?[handle] else {
            if journals.values.contains(where: { $0[handle] != nil }) {
                throw JournalFailure.foreignHandle
            }
            return nil
        }
        return journal
    }

}

private struct CaptureJournalBackendSession {
    var id: String
    var capturedAtMs: Int64?
    var deviceId: String
    var deviceName: String?
    var codec: Int
    var state = "open"
    var byteCount = 0
    var chunkCount = 0
}

private actor CaptureJournalTransport: BackendTransport, RecordingJournalStoring {
    private let failure: JournalFailure?
    private let owner: String
    private let vault: CaptureJournalVault
    private var input: RecordingJournalInput?
    private var entries: [String] = []
    private var failFirstAudioRequest: Bool
    private var didFailFirstAudioRequest = false
    private var requestPathValues: [String] = []
    private var sessions: [String: CaptureJournalBackendSession] = [:]
    private var sessionSequence = 0
    private var pauseNextCreation = false
    private var creationStarted = false
    private var creationStartWaiter: CheckedContinuation<Void, Never>?
    private var creationRelease: CheckedContinuation<Void, Never>?

    init(
        owner: String = "account-a", vault: CaptureJournalVault? = nil,
        failure: JournalFailure? = nil, failFirstAudioRequest: Bool = false
    ) {
        self.owner = owner
        self.vault = vault ?? CaptureJournalVault()
        self.failure = failure
        self.failFirstAudioRequest = failFirstAudioRequest
    }

    func snapshot() -> (input: RecordingJournalInput?, entries: [String]) {
        (input, entries)
    }

    func request(_ request: BackendRequest) async throws -> BackendResponse {
        BackendResponse(id: request.id, status: 200, body: nil)
    }

    func generationEvents(
        generationId: String, lastEventId: String?,
        onFrame: @escaping @Sendable (String) -> Void
    ) async throws -> BackendResponse {
        BackendResponse(id: generationId, status: 200, body: nil)
    }

    func cancelGenerationEvents(generationId: String) async {}
    func createWriteId() async throws -> String { "write-id" }
    func createRecordingId() async throws -> String { "recording-id" }
    func apiContract() async -> APIContract? { .canonical }
    func softwarePlane() async -> SoftwarePlane? { .new }
    func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane? { plane }
    func stampedBackendOrigin() async -> String? { nil }

    func pauseNextJournalCreation() { pauseNextCreation = true }

    func waitUntilJournalCreationStarts() async {
        guard !creationStarted else { return }
        await withCheckedContinuation { continuation in
            creationStartWaiter = continuation
        }
    }

    func resumeJournalCreation() {
        creationRelease?.resume()
        creationRelease = nil
    }

    func requestPaths() -> [String] { requestPathValues }

    func createRecordingJournal(
        _ input: RecordingJournalInput
    ) async throws -> RecordingJournalRecord {
        if failure == .create { throw JournalFailure.create }
        if pauseNextCreation {
            pauseNextCreation = false
            await withCheckedContinuation { continuation in
                creationStarted = true
                creationStartWaiter?.resume()
                creationStartWaiter = nil
                creationRelease = continuation
            }
        }
        let journal = try await vault.create(owner: owner, input: input)
        self.input = input
        return journal
    }

    func listRecordingJournals() async throws -> [RecordingJournalRecord] {
        await vault.list(owner: owner)
    }

    func readRecordingJournal(handle: String) async throws -> RecordingJournalRecord {
        try await vault.read(owner: owner, handle: handle)
    }

    func appendRecordingJournal(
        handle: String, entry: String, expectedEntryCount: Int
    ) async throws -> Int {
        if failure == .append { throw JournalFailure.append }
        if failure == .acknowledgement { return 0 }
        entries.append(entry)
        return try await vault.append(
            owner: owner, handle: handle, entry: entry,
            expectedEntryCount: expectedEntryCount)
    }

    func requestRecordingJournal(
        handle: String, request: BackendRequest
    ) async throws -> BackendResponse {
        _ = try await vault.read(owner: owner, handle: handle)
        requestPathValues.append(request.path)

        if request.path == "/v1/device-sessions" {
            let payload = try parseBody(request.body)
            sessionSequence += 1
            let session = CaptureJournalBackendSession(
                id: "00000000-0000-4000-8000-00000000000\(sessionSequence)",
                capturedAtMs: (payload["capturedAtMs"] as? NSNumber)?.int64Value,
                deviceId: payload["deviceId"] as? String ?? "",
                deviceName: payload["deviceName"] as? String,
                codec: (payload["codec"] as? NSNumber)?.intValue ?? -1)
            sessions[session.id] = session
            try await vault.setSession(owner: owner, handle: handle, sessionId: session.id)
            return try response(request, session: session)
        }

        let pathParts = request.path.split(separator: "/")
        guard pathParts.count >= 4, pathParts[0] == "v1",
            pathParts[1] == "device-sessions",
            var session = sessions[String(pathParts[2])]
        else {
            return BackendResponse(id: request.id, status: 404, body: nil)
        }

        if pathParts.last == "audio" {
            if failFirstAudioRequest && !didFailFirstAudioRequest {
                didFailFirstAudioRequest = true
                return BackendResponse(id: request.id, status: 503, body: nil)
            }
            let payload = try parseBody(request.body)
            guard let chunks = payload["chunks"] as? [[String: Any]] else {
                throw ScriptedBackendError.invalidRequest
            }
            session.chunkCount += chunks.count
            session.byteCount += chunks.compactMap { $0["bytesBase64"] as? String }
                .compactMap { Data(base64Encoded: $0) }.reduce(0) { $0 + $1.count }
        } else if pathParts.last == "complete" {
            session.state = "complete"
        } else {
            return BackendResponse(id: request.id, status: 404, body: nil)
        }

        sessions[session.id] = session
        return try response(request, session: session)
    }

    func removeRecordingJournal(handle: String) async {
        try? await vault.remove(owner: owner, handle: handle)
    }

    private func parseBody(_ body: String?) throws -> [String: Any] {
        guard let body,
            let payload = try JSONSerialization.jsonObject(with: Data(body.utf8))
                as? [String: Any]
        else { throw ScriptedBackendError.invalidRequest }
        return payload
    }

    private func response(
        _ request: BackendRequest, session: CaptureJournalBackendSession
    ) throws -> BackendResponse {
        let body: [String: Any] = [
            "session": [
                "id": session.id,
                "capturedAtMs": session.capturedAtMs.map { NSNumber(value: $0) as Any }
                    ?? NSNull(),
                "deviceId": session.deviceId,
                "deviceName": session.deviceName.map { $0 as Any } ?? NSNull(),
                "codec": session.codec,
                "state": session.state,
                "byteCount": session.byteCount,
                "chunkCount": session.chunkCount,
                "startedAt": 1_050,
                "endedAt": session.state == "complete" ? 2_050 as Any : NSNull(),
            ] as [String: Any]
        ]
        let data = try JSONSerialization.data(withJSONObject: body)
        return BackendResponse(
            id: request.id, status: 200, body: String(decoding: data, as: UTF8.self))
    }
}

private enum JournalFailure: Error, Sendable, Equatable {
    case create
    case invalidCreateRetry
    case append
    case acknowledgement
    case invalidAppendSequence
    case foreignHandle
    case missingHandle
}
