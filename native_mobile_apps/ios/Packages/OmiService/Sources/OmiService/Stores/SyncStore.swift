import Foundation
import Observation
import OmiDevice
import OmiNetwork

/// The connected Omi as offline sync sees it (real: `DeviceStore`).
@MainActor
public protocol StorageLink: AnyObject {
    /// The connected Omi's id; nil while none is connected.
    var storageDeviceID: String? { get }
    var codec: OmiGATT.Codec? { get }
    func sendStorage(_ command: OmiStorage.Command)
}

/// Offline sync: what the Omi recorded while the phone was away reaches the backend on its own.
///
/// Whenever an Omi with storage is connected: ask how much it holds (INFO), read it in batches
/// alongside live audio (the firmware shares its send queue between both), write each recording to
/// disk, then let the Omi free what is safely on disk (ADVANCE). Recordings upload to
/// `v2/sync-local-files` and are deleted once the backend's job completes. The file queue and
/// the saved position survive disconnects and relaunches.
///
/// Firmware without the custody contract frees records itself as they are delivered over
/// Bluetooth, so audio is written to disk as it arrives, not at the end of a batch.
@MainActor
@Observable
public final class SyncStore {
    public enum Status: Equatable, Sendable {
        /// No Omi with offline storage seen yet.
        case hidden
        case waiting(seconds: Int)
        case syncing(progress: Double)
        case synced
    }

    public private(set) var status: Status = .hidden
    /// The Omi's storage as last read (used and free bytes); `nil` before the first read.
    public private(set) var deviceStorage: OmiStorage.Status?
    /// Recordings saved here and not yet processed by the backend, oldest first.
    public private(set) var recordings: [PendingRecording] = []

    public var hasPending: Bool {
        switch status {
        case .waiting, .syncing: true
        case .hidden, .synced: false
        }
    }

    @ObservationIgnored public weak var link: (any StorageLink)?

    enum Phase: Equatable {
        case idle
        case awaitingInfo
        /// Records `start ..< start + received` arrived in this batch; `end` is the Omi's write position.
        case reading(start: UInt64, received: UInt64, end: UInt64, ringID: UInt64?)
    }

    @ObservationIgnored private(set) var phase: Phase = .idle
    let api: any APIClientProtocol
    let files: OfflineRecordings
    private let batchRecords: UInt32
    let retryDelay: Duration
    private let stallTimeout: Duration
    /// The signed-in account; recordings are tagged with it and uploaded only to it.
    @ObservationIgnored let userID: () -> String?
    @ObservationIgnored private var storageReady = false
    @ObservationIgnored private var reassembler = OmiStorage.Reassembler()
    @ObservationIgnored private var lastActivity = ContinuousClock.now
    @ObservationIgnored private var restartsLeft = 3
    @ObservationIgnored var uploading = false
    @ObservationIgnored var progress: (done: Double, total: Double)?
    @ObservationIgnored var retryTask: Task<Void, Never>?
    @ObservationIgnored private var watchdogTask: Task<Void, Never>?
    @ObservationIgnored private var restartTask: Task<Void, Never>?
    /// The phone-mic file being written (`SyncStore+Phone.swift`).
    @ObservationIgnored var phoneFile: PhoneAudioFile?
    /// The kept copy of live audio being written (Store audio on phone).
    @ObservationIgnored var keptFile: PhoneAudioFile?
    /// Background runtime held while a transfer runs (`TransferLease`); nil in tests and the local
    /// harness, where there is no app to be suspended.
    @ObservationIgnored public var lease: TransferLease?
    /// Whether the device read in progress took the lease (the read goes on in batches, so this
    /// keeps the take and the give-back paired).
    @ObservationIgnored private var holdsLease = false

    public init(
        api: any APIClientProtocol,
        directory: URL,
        batchRecords: UInt32 = 600,
        retryDelay: Duration = .seconds(30),
        stallTimeout: Duration = .seconds(15),
        userID: @escaping () -> String? = { nil }
    ) {
        self.api = api
        self.userID = userID
        files = OfflineRecordings(directory: directory)
        self.batchRecords = batchRecords
        self.retryDelay = retryDelay
        self.stallTimeout = stallTimeout
        refresh()
    }

    /// `Application Support/OfflineSync`, excluded from backups.
    public static var defaultDirectory: URL {
        var url = URL.applicationSupportDirectory.appending(path: "OfflineSync", directoryHint: .isDirectory)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try? url.setResourceValues(values)
        return url
    }

    /// App launch (signed in): uploads whatever is still waiting.
    public func start() {
        uploadSoon()
    }

    func uploadSoon() {
        Task { await uploadPending() }
    }

    public func handle(_ event: OmiStorage.Event) {
        lastActivity = .now
        switch event {
        case .ready:
            storageReady = true
            restartsLeft = 3
            begin()
        case let .status(status):
            deviceStorage = status
            if phase == .idle { files.update { $0.devicePending = UInt64(status.unreadRecords); $0.known = true } }
            refresh()
        case let .notification(notification):
            handle(notification)
        }
    }

    /// The codec arrived after storage was ready.
    public func codecKnown() {
        begin()
    }

    public func deviceDisconnected() {
        storageReady = false
        if case let .reading(start, received, _, ringID) = phase {
            // Whatever arrived is safe on disk; custody firmware is told on the next connect.
            files.closeOpen()
            files.update { $0.durableSeq = start + received; $0.ringID = ringID }
        }
        stopTransfer()
        uploadSoon()
    }

    private func begin() {
        guard storageReady, phase == .idle, link?.storageDeviceID != nil, link?.codec != nil else { return }
        phase = .awaitingInfo
        link?.sendStorage(.info)
        watch()
    }

    private func handle(_ notification: OmiStorage.Notification) {
        switch notification {
        case let .info(info) where phase == .awaitingInfo:
            received(info)
        case let .readBegin(start, _):
            guard case let .reading(expected, 0, _, _) = phase, start != expected else { return }
            restart()
        case let .data(bytes):
            guard case .reading = phase else { return }
            ingest(bytes)
        case let .done(status, nextSeq):
            finishBatch(status: status, nextSeq: nextSeq)
        case let .ack(status) where status != OmiStorage.AckStatus.ok && status != OmiStorage.AckStatus.seqOutOfRange:
            // Storage not ready (SD remounting) or a refused read: ask again shortly.
            if phase != .idle { restart() }
        default:
            break
        }
    }

    private func received(_ info: OmiStorage.Info) {
        var start = info.readSeq
        let saved = files.state
        // Custody firmware frees only on ADVANCE: skip what an interrupted sync already saved.
        if let ringID = info.ringID, saved.ringID == ringID, let durable = saved.durableSeq, durable > start, durable <= info.writeSeq {
            link?.sendStorage(.advance(to: durable))
            start = durable
        }
        files.update { state in
            state.devicePending = info.writeSeq > start ? info.writeSeq - start : 0
            state.known = true
            // A position saved for another ring means nothing here.
            if state.ringID != info.ringID { state.durableSeq = nil }
            state.ringID = info.ringID
        }
        guard start < info.writeSeq else {
            stopTransfer()
            uploadSoon()
            return
        }
        beginProgress()
        read(from: start, end: info.writeSeq, ringID: info.ringID)
    }

    private func read(from start: UInt64, end: UInt64, ringID: UInt64?) {
        takeLease()
        reassembler = OmiStorage.Reassembler()
        phase = .reading(start: start, received: 0, end: end, ringID: ringID)
        link?.sendStorage(.read(start: start, count: UInt32(min(UInt64(batchRecords), end - start))))
        refresh()
    }

    private func ingest(_ bytes: Data) {
        guard case let .reading(start, received, end, ringID) = phase,
              let deviceID = link?.storageDeviceID, let codec = link?.codec else { return }
        let records = reassembler.append(bytes)
        var closed = false
        for record in records {
            closed = files.append(record, deviceID: deviceID, codec: codec, owner: userID(), now: Date()) || closed
        }
        phase = .reading(start: start, received: received + UInt64(records.count), end: end, ringID: ringID)
        progress?.done += Double(records.count) * files.state.secondsPerRecord
        if closed { uploadSoon() }
        refresh()
    }

    private func finishBatch(status: UInt8, nextSeq: UInt64) {
        guard case let .reading(start, received, end, ringID) = phase else { return }
        files.sync()
        guard status == OmiStorage.AckStatus.ok, nextSeq == start + received, reassembler.pendingBytes == 0 else {
            // Out of step: keep what is on disk, free nothing, read again from the Omi's position.
            restart()
            return
        }
        link?.sendStorage(.advance(to: nextSeq))
        files.update { $0.durableSeq = nextSeq; $0.ringID = ringID; $0.devicePending = end > nextSeq ? end - nextSeq : 0 }
        if nextSeq < end, received > 0 {
            read(from: nextSeq, end: end, ringID: ringID)
        } else {
            files.closeOpen()
            stopTransfer()
            uploadSoon()
        }
    }

    /// Stops the transfer and asks the Omi where it stands again (a few times per connection).
    private func restart() {
        link?.sendStorage(.stop)
        files.closeOpen()
        stopTransfer()
        guard restartsLeft > 0 else { return }
        restartsLeft -= 1
        restartTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(2))
            guard !Task.isCancelled else { return }
            self?.begin()
        }
    }

    private func stopTransfer() {
        phase = .idle
        releaseLease()
        watchdogTask?.cancel()
        refresh()
    }

    /// The read is about to ask the Omi for a batch: it needs the app to stay awake for it. The
    /// batches of one read share one take, so a fresh batch in the middle does not stack up.
    private func takeLease() {
        guard !holdsLease else { return }
        holdsLease = true
        lease?.acquire()
    }

    private func releaseLease() {
        guard holdsLease else { return }
        holdsLease = false
        lease?.release()
    }

    /// No reply for `stallTimeout`: the transfer is stuck.
    private func watch() {
        watchdogTask?.cancel()
        watchdogTask = Task { [weak self, stallTimeout] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(250))
                guard let self, phase != .idle else { return }
                if ContinuousClock.now - lastActivity > stallTimeout {
                    restart()
                    return
                }
            }
        }
    }

    // MARK: Status

    private var waitingSeconds: Double {
        let recordings = files.state.recordings.filter { $0.jobID == nil && $0.manual != true && !$0.isKept }.reduce(0) { $0 + $1.seconds }
        return recordings + (files.state.open?.seconds ?? 0) + Double(files.state.devicePending) * files.state.secondsPerRecord
    }

    func refresh() {
        let active = phase != .idle || uploading
        if !active { progress = nil }
        let next: Status = if active, let progress {
            .syncing(progress: min(0.99, progress.done / max(progress.total, 1)))
        } else if waitingSeconds >= 1 {
            .waiting(seconds: Int(waitingSeconds.rounded()))
        } else if files.state.known || !files.state.recordings.isEmpty {
            .synced
        } else {
            .hidden
        }
        if next != status { status = next }
        if files.state.recordings != recordings { recordings = files.state.recordings }
    }
}

public extension SyncStore {
    /// Deletes a recording that is waiting here (it never reaches the backend).
    func delete(_ filename: String) {
        files.remove(filename)
        refresh()
    }
}
