import Foundation
import OmiDevice
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
final class FakeStorageLink: StorageLink {
    var storageDeviceID: String? = "6F1D0C3A-1B2C-4D5E-8F90-123456789ABC"
    var codec: OmiGATT.Codec? = .opusFS320
    var sent: [OmiStorage.Command] = []

    func sendStorage(_ command: OmiStorage.Command) {
        sent.append(command)
    }
}

@MainActor
struct SyncStoreTests {
    static let start: UInt32 = 1_760_000_000

    func makeDirectory() -> URL {
        let url = FileManager.default.temporaryDirectory.appending(path: "offline-sync-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    /// `link` is weak in the store (the app's `DeviceStore` outlives it): tests keep it alive.
    func make(
        _ api: FakeAPIClient, _ link: FakeStorageLink, directory: URL, batch: UInt32 = 600,
        user: @escaping () -> String? = { "alice" }
    ) -> SyncStore {
        let sync = SyncStore(api: api, directory: directory, batchRecords: batch, retryDelay: .milliseconds(40), userID: user)
        sync.link = link
        return sync
    }

    /// One firmware record: timestamp, then `frames` 80-byte Opus frames packed `[size][frame]`.
    func record(_ timestamp: UInt32, frames: Int = 5, fill: UInt8 = 0xA0) -> Data {
        var payload = [UInt8](repeating: 0, count: OmiStorage.payloadSize)
        for index in 0 ..< frames {
            payload[index * 81] = 80
            for byte in 1 ... 80 { payload[index * 81 + byte] = fill }
        }
        let time = withUnsafeBytes(of: timestamp.bigEndian) { Data($0) }
        return time + Data(payload)
    }

    /// Feeds records the way BLE does: unaligned 243-byte data notifications.
    func deliver(_ records: [Data], to sync: SyncStore) {
        let stream = records.reduce(Data(), +)
        var offset = 0
        while offset < stream.count {
            sync.handle(.notification(.data(stream.subdata(in: offset ..< min(stream.count, offset + 243)))))
            offset += 243
        }
    }

    func eventually(_ condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    @Test func connectListDownloadUploadAck() async throws {
        let api = FakeAPIClient()
        let link = FakeStorageLink()
        let sync = make(api, link, directory: makeDirectory())
        #expect(sync.status == .hidden)
        sync.handle(.ready)
        #expect(link.sent == [.info])
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 10, writeSeq: 13))))
        #expect(link.sent.last == .read(start: 10, count: 3))
        guard case .syncing = sync.status else {
            Issue.record("expected syncing, got \(sync.status)")
            return
        }
        sync.handle(.notification(.readBegin(start: 10, count: 3)))
        deliver((0 ..< 3).map { record(Self.start + UInt32($0) / 10) }, to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 13)))
        #expect(link.sent.last == .advance(to: 13))
        try await eventually { api.syncBackend.uploads.count == 1 }
        let upload = try #require(api.syncBackend.uploads.first)
        #expect(upload.filename == "audio_6f1d0c3a1b2c4d5e8f90123456789abc_opus_fs320_16000_1_fs320_1760000000.bin")
        // [u32 LE length][frame] per frame: 15 frames of 80 bytes.
        #expect(upload.data.count == 15 * 84)
        #expect(upload.data.prefix(5) == Data([80, 0, 0, 0, 0xA0]))
        try await eventually { sync.status == .synced }
        #expect(sync.status == .synced)
        // The file stays until the backend's job completes.
        #expect(sync.files.state.recordings.count == 1)
        api.syncBackend.setJob("job-1", SyncJob(status: "completed"))
        try await eventually { sync.files.state.recordings.isEmpty }
        #expect(sync.files.state.recordings.isEmpty)
    }

    @Test func recordingsOnlyGoToTheAccountThatWasSignedIn() async throws {
        let api = FakeAPIClient()
        let link = FakeStorageLink()
        var user: String? = "alice"
        let sync = make(api, link, directory: makeDirectory(), user: { user })
        // Recorded while alice is signed in, then bob signs in before the upload.
        user = "bob"
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 10, writeSeq: 13))))
        sync.handle(.notification(.readBegin(start: 10, count: 3)))
        user = "alice"
        deliver((0 ..< 3).map { record(Self.start + UInt32($0) / 10) }, to: sync)
        user = "bob"
        sync.handle(.notification(.done(status: 0, nextSeq: 13)))
        try await Task.sleep(for: .milliseconds(150))
        #expect(api.syncBackend.uploads.isEmpty)
        #expect(sync.files.state.recordings.first?.owner == "alice")
        // Back on alice's account it goes up.
        user = "alice"
        await sync.uploadPending()
        #expect(api.syncBackend.uploads.count == 1)
    }

    @Test func readsInBatchesAndAdvancesAfterEach() {
        let link = FakeStorageLink()
        let sync = make(FakeAPIClient(), link, directory: makeDirectory(), batch: 2)
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 3))))
        #expect(link.sent.last == .read(start: 0, count: 2))
        deliver([record(Self.start), record(Self.start)], to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 2)))
        #expect(Array(link.sent.suffix(2)) == [.advance(to: 2), .read(start: 2, count: 1)])
        deliver([record(Self.start + 1)], to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 3)))
        #expect(link.sent.last == .advance(to: 3))
        #expect(sync.phase == .idle)
        #expect(sync.files.state.recordings.first?.frames == 15)
    }

    /// Custody firmware (ring id): the link drops mid-batch; after a relaunch the next connect
    /// frees what was saved and reads on from there.
    @Test func disconnectMidwayResumesAfterRelaunch() async throws {
        let directory = makeDirectory()
        let link = FakeStorageLink()
        let api = FakeAPIClient()
        api.syncBackend.failUploads([.transport("offline")])
        let sync = make(api, link, directory: directory)
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 5, ringID: 77))))
        deliver([record(Self.start), record(Self.start)], to: sync)
        sync.deviceDisconnected()
        #expect(sync.files.state.durableSeq == 2)
        #expect(sync.files.state.recordings.map(\.frames) == [10])

        let relaunched = make(FakeAPIClient(), link, directory: directory)
        #expect(relaunched.files.state.recordings.count == 1)
        link.sent = []
        relaunched.handle(.ready)
        relaunched.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 5, ringID: 77))))
        #expect(link.sent == [.info, .advance(to: 2), .read(start: 2, count: 3)])
    }

    /// A different ring (cleared or a new card) never reuses a saved position.
    @Test func otherRingStartsFromTheOmisPosition() {
        let directory = makeDirectory()
        let link = FakeStorageLink()
        let sync = make(FakeAPIClient(), link, directory: directory)
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 5, ringID: 77))))
        deliver([record(Self.start)], to: sync)
        sync.deviceDisconnected()
        link.sent = []
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 4, ringID: 78))))
        #expect(link.sent == [.info, .read(start: 0, count: 4)])
        #expect(sync.files.state.durableSeq == nil)
    }

    /// Killed while writing: the half-written frame is cut, the rest is queued for upload.
    @Test func relaunchRecoversTheOpenFile() throws {
        let directory = makeDirectory()
        let link = FakeStorageLink()
        let sync = make(FakeAPIClient(), link, directory: directory)
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 9))))
        deliver([record(Self.start)], to: sync)
        sync.files.sync()
        let open = try #require(sync.files.state.open)
        let handle = try FileHandle(forWritingTo: directory.appending(path: open.filename))
        try handle.seekToEnd()
        handle.write(Data([80, 0, 0, 0, 1, 2]))
        try handle.close()

        let relaunched = make(FakeAPIClient(), link, directory: directory)
        #expect(relaunched.files.state.open == nil)
        #expect(relaunched.files.state.recordings.map(\.frames) == [5])
        let size = try FileManager.default.attributesOfItem(atPath: directory.appending(path: open.filename).path)[.size] as? Int
        #expect(size == 5 * 84)
    }

    @Test func clockGapStartsANewRecording() {
        let link = FakeStorageLink()
        let sync = make(FakeAPIClient(), link, directory: makeDirectory())
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 3))))
        deliver([record(Self.start), record(Self.start), record(Self.start + 600)], to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 3)))
        #expect(sync.files.state.recordings.map(\.startedAt) == [Double(Self.start), Double(Self.start + 600)])
    }

    @Test func outOfStepBatchFreesNothing() {
        let link = FakeStorageLink()
        let sync = make(FakeAPIClient(), link, directory: makeDirectory())
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 3))))
        deliver([record(Self.start)], to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 3)))
        #expect(!link.sent.contains { if case .advance = $0 { true } else { false } })
        #expect(link.sent.last == .stop)
        #expect(sync.files.state.recordings.count == 1)
    }

    @Test func waitsForTheCodecAndAConnection() {
        let link = FakeStorageLink()
        link.codec = nil
        let sync = make(FakeAPIClient(), link, directory: makeDirectory())
        sync.handle(.ready)
        #expect(link.sent.isEmpty)
        link.codec = .opusFS320
        sync.codecKnown()
        #expect(link.sent == [.info])
    }

    @Test func failedUploadIsRetriedAndRefusedFileDropped() async throws {
        let api = FakeAPIClient()
        api.syncBackend.failUploads([.transport("offline"), .http(status: 422, body: "")])
        let link = FakeStorageLink()
        let sync = make(api, link, directory: makeDirectory())
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 2))))
        deliver([record(Self.start), record(Self.start + 600)], to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 2)))
        // First attempt fails offline and is retried; the retry of file 1 is refused (422) and dropped.
        try await eventually { api.syncBackend.uploads.count == 1 }
        #expect(api.syncBackend.uploads.first?.filename.hasSuffix("_1760000600.bin") == true)
        try await eventually { sync.files.state.recordings.count == 1 && sync.files.state.recordings.first?.jobID != nil }
        #expect(sync.files.state.recordings.count == 1)
    }

    @Test func waitingShowsMinutesLeftOnTheOmi() {
        let sync = make(FakeAPIClient(), FakeStorageLink(), directory: makeDirectory())
        let status = UInt32(0).littleEndianData + UInt32(1800).littleEndianData + UInt32(0).littleEndianData + UInt32(1).littleEndianData
        sync.handle(.status(OmiStorage.Status(status)!))
        #expect(sync.status == .waiting(seconds: 180))
        #expect(sync.hasPending)
    }
}
