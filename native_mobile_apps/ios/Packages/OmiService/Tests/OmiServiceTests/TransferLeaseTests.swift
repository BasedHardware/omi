import Foundation
import OmiCore
import OmiDevice
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// The background grant around a transfer: the app asks iOS for extra runtime while the Omi is
/// read or a file is uploaded, and hands it back when the last transfer is done.
@MainActor
struct TransferLeaseTests {
    /// A lease over a fake app: `begins` counts the grants taken, `ends` the ones handed back.
    @MainActor
    final class Fake {
        var begins = 0
        var ends = 0
        var admit = true
        private(set) var expire: (() -> Void)?

        func makeLease(log: DebugLog? = nil) -> TransferLease {
            TransferLease(
                begin: { expiration in
                    self.begins += 1
                    guard self.admit else { return false }
                    self.expire = expiration
                    return true
                },
                end: { self.ends += 1 },
                log: log
            )
        }
    }

    @Test func oneGrantCoversEveryTransferRunningAtOnce() {
        let app = Fake()
        let lease = app.makeLease()
        lease.acquire()
        lease.acquire()
        #expect(app.begins == 1)
        #expect(lease.isHeld)
        // The first transfer is done; the second one still needs the app awake.
        lease.release()
        #expect(app.ends == 0)
        lease.release()
        #expect(app.ends == 1)
        #expect(!lease.isHeld)
    }

    @Test func aReleasedLeaseAsksAgainForTheNextTransfer() {
        let app = Fake()
        let lease = app.makeLease()
        lease.acquire()
        lease.release()
        lease.acquire()
        #expect(app.begins == 2)
        lease.release()
        #expect(app.ends == 2)
    }

    @Test func aRefusedGrantLeavesTheCountBalanced() {
        let app = Fake()
        app.admit = false
        let lease = app.makeLease()
        lease.acquire()
        #expect(app.begins == 1)
        #expect(!lease.isHeld)
        // Nothing was taken, so the transfers that come after it cannot hand back more than that.
        lease.release()
        #expect(app.ends == 0)
        app.admit = true
        lease.acquire()
        #expect(app.begins == 2)
        #expect(lease.isHeld)
    }

    /// iOS takes the time back: whatever was running stops, the grant is gone, and the release the
    /// transfers call on their way out does not end it a second time.
    @Test func theSystemTakingTheTimeBackEndsTheGrantOnce() async {
        let app = Fake()
        let lease = app.makeLease()
        lease.acquire()
        lease.acquire()
        app.expire?()
        #expect(app.ends == 1)
        #expect(!lease.isHeld)
        lease.release()
        lease.release()
        #expect(app.ends == 1)
    }

    @Test func releasesWithoutAnAcquireDoNothing() {
        let app = Fake()
        let lease = app.makeLease()
        lease.release()
        #expect(app.ends == 0)
    }
}

/// The lease as the sync actually takes it: held while the Omi is read or a file uploads, given
/// back when the transfer ends, and never stacked up per batch or per concurrent transfer.
@MainActor
struct SyncTransferLeaseTests {
    static let start: UInt32 = 1_760_000_000

    /// What the app would have asked iOS for, and handed back.
    @MainActor
    final class Counting {
        var begins = 0
        var ends = 0
    }

    func make(
        _ api: FakeAPIClient, _ link: FakeStorageLink, _ counting: Counting, batch: UInt32 = 600,
        retryDelay: Duration = .milliseconds(40)
    ) -> SyncStore {
        let directory = FileManager.default.temporaryDirectory.appending(path: "lease-sync-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let sync = SyncStore(api: api, directory: directory, batchRecords: batch, retryDelay: retryDelay, userID: { "alice" })
        sync.link = link
        sync.lease = TransferLease(
            begin: { _ in counting.begins += 1; return true },
            end: { counting.ends += 1 }
        )
        return sync
    }

    /// One firmware record: a big-endian timestamp, then `frames` 80-byte Opus frames packed as
    /// `[size][frame]` inside the fixed payload.
    func record(_ timestamp: UInt32, frames: Int = 5) -> Data {
        var payload = [UInt8](repeating: 0, count: OmiStorage.payloadSize)
        for index in 0 ..< frames {
            payload[index * 81] = 80
            for byte in 1 ... 80 { payload[index * 81 + byte] = 0xA0 }
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

    func settle(until condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    /// A read that spans three batches: the app stays awake across all of them, and the grant goes
    /// back once, when the Omi has nothing left to send.
    @Test func aReadHoldsOneGrantAcrossItsBatches() {
        let counting = Counting()
        let link = FakeStorageLink()
        let sync = make(FakeAPIClient(), link, counting, batch: 2)
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 3))))
        #expect(counting.begins == 1)
        deliver([record(Self.start), record(Self.start)], to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 2)))
        #expect(counting.begins == 1, "the next batch is the same transfer, not a new one")
        deliver([record(Self.start + 1)], to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 3)))
        #expect(sync.phase == .idle)
        #expect(counting.begins == 1)
        #expect(counting.ends == 1)
    }

    /// The link drops mid-read: the grant goes back with the transfer, and the read that starts
    /// again after the reconnect takes a fresh one.
    @Test func aDroppedLinkHandsTheGrantBack() {
        let counting = Counting()
        let link = FakeStorageLink()
        let sync = make(FakeAPIClient(), link, counting, batch: 2)
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 3))))
        #expect(counting.begins == 1)
        sync.deviceDisconnected()
        #expect(counting.ends == 1)
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 3))))
        #expect(counting.begins == 2)
    }

    /// Files going out hold the grant as well, and the app is free to be suspended again once the
    /// queue is empty.
    @Test func anUploadHoldsTheGrantWhileItSends() async throws {
        let counting = Counting()
        let api = FakeAPIClient()
        // The store's `link` is weak: the test keeps it alive.
        let link = FakeStorageLink()
        let sync = make(api, link, counting)
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 1))))
        deliver([record(Self.start)], to: sync)
        sync.handle(.notification(.done(status: 0, nextSeq: 1)))
        try await settle { api.syncBackend.uploads.count == 1 && counting.ends == 2 }
        #expect(counting.begins == 2, "the read asked first, the upload after it")
        #expect(counting.ends == 2)
    }

    /// A recording that closes while the Omi is still being read goes up right away, and the app
    /// stays awake for it: the read's grant is still held, so the upload takes no second one, and
    /// it is handed back only once both are done.
    @Test func anUploadDuringAReadSharesTheGrant() async throws {
        let counting = Counting()
        let api = FakeAPIClient()
        let link = FakeStorageLink()
        // The retry that a still-queued job schedules would take grants of its own; park it.
        let sync = make(api, link, counting, batch: 10, retryDelay: .seconds(60))
        let gate = Gate()
        api.syncBackend.uploadGate = { await gate.hold() }
        sync.handle(.ready)
        sync.handle(.notification(.info(OmiStorage.Info(readSeq: 0, writeSeq: 3))))
        #expect(counting.begins == 1)
        // The last record is ten minutes later: that closes the recording the first two opened, and
        // the closed file goes up without waiting for the Omi to be finished.
        deliver([record(Self.start), record(Self.start), record(Self.start + 600)], to: sync)
        #expect(sync.phase != .idle)
        await gate.entered()
        #expect(counting.begins == 1, "the read already holds the app awake, so the upload takes nothing")
        sync.handle(.notification(.done(status: 0, nextSeq: 3)))
        #expect(sync.phase == .idle)
        #expect(counting.ends == 0, "the app stays awake while the upload is still running")
        gate.open()
        try await settle { counting.ends == 1 }
        #expect(counting.ends == 1, "and it is handed back once both are done")
        #expect(counting.begins == 1, "one grant was taken, so exactly one is handed back")
    }

    /// A transfer parked mid-request, so a test can look at the app while it is in flight.
    @MainActor
    final class Gate {
        private var held: CheckedContinuation<Void, Never>?
        private var waiter: CheckedContinuation<Void, Never>?
        private var isEntered = false

        /// Parks the first transfer that arrives; the ones after it go straight through, so the
        /// test only ever has to open the gate once.
        func hold() async {
            guard !isEntered else { return }
            isEntered = true
            waiter?.resume()
            waiter = nil
            await withCheckedContinuation { held = $0 }
        }

        func entered() async {
            guard !isEntered else { return }
            await withCheckedContinuation { waiter = $0 }
        }

        func open() {
            held?.resume()
            held = nil
        }
    }
}
