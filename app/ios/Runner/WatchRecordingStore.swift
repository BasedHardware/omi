import Foundation
import CryptoKit

/// Durable custody for Watch audio, independent of the live transcript channel.
/// Files use the existing native batch wire format; operations are serialized below.
struct WatchRecordingMetadata: Codable, Equatable {
    let version: Int
    let sessionID: String
    let segment: Int
    let startedAt: Int64
    let ownerUID: String

    var fileName: String {
        "audio_omibatchwatch\(sessionID)s\(segment)_pcm16_16000_1_fs160_\(startedAt).bin"
    }

    var isValid: Bool {
        version == 1 && sessionID.count == 32 && sessionID.allSatisfy { $0.isHexDigit && $0.isASCII }
            && segment >= 0 && startedAt > 0 && !ownerUID.isEmpty && ownerUID.utf8.count <= 256
    }
}

enum WatchRecordingError: Error {
    case invalidMetadata, storageFull, invalidAudio, wrongOwner, conflictingReceipt
}

final class WatchRecordingStore: @unchecked Sendable {
    private struct Tail: Codable { let offset: UInt64; let bytes: Data }
    static let frameBytes = 320 // 10 ms, 16 kHz mono PCM16
    static let maxFrames = 6_000 // one minute, bounded transfer and memory
    let directory: URL
    private(set) var recoveryFailures = 0
    private let hasSpace: () -> Bool
    private let lock = NSRecursiveLock()
    private var metadata: WatchRecordingMetadata?
    private var writer: FileHandle?
    private var frames = 0
    private var totalFrames = 0
    private var remainder = Data()
    private var start: Int64 = 0
    private var segment = 0
    private var sessionID = ""
    private var ownerUID = ""
    private var lastSync: TimeInterval = -.infinity

    init(directory: URL, hasSpace: (() -> Bool)? = nil) throws {
        self.directory = directory
        self.hasSpace = hasSpace ?? {
            let attributes = try? FileManager.default.attributesOfFileSystem(forPath: directory.path)
            return (attributes?[.systemFreeSize] as? NSNumber)?.int64Value ?? 0 > 200 * 1024 * 1024
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try recoverInterruptedSegments()
    }

    deinit { try? writer?.close() }

    static func writeDurably(_ bytes: Data, to url: URL) throws {
        try bytes.write(to: url, options: .atomic)
        let handle = try FileHandle(forWritingTo: url)
        defer { try? handle.close() }
        try handle.synchronize()
    }

    @discardableResult
    func begin(ownerUID: String, startedAt: Int64) throws -> String {
        lock.lock(); defer { lock.unlock() }
        try finish()
        guard !ownerUID.isEmpty, ownerUID.utf8.count <= 256, startedAt > 0 else {
            throw WatchRecordingError.invalidMetadata
        }
        self.ownerUID = ownerUID
        start = startedAt
        sessionID = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        segment = 0
        totalFrames = 0
        remainder = Data()
        lastSync = -.infinity
        return sessionID
    }

    /// Writes precede live routing. Fsync bounds power-loss exposure to 1.5 seconds;
    /// finalize always syncs before a file becomes transferable.
    func append(_ pcm: Data, sessionID expectedSession: String? = nil) throws {
        lock.lock(); defer { lock.unlock() }
        // FileHandle/Data bridging can autorelease buffers on the audio thread.
        // Drain each callback rather than retaining a session worth of writes.
        try autoreleasepool {
            guard !ownerUID.isEmpty, pcm.count % 2 == 0 else { throw WatchRecordingError.invalidAudio }
            if let expectedSession, expectedSession != sessionID { throw WatchRecordingError.invalidMetadata }
            let uptime = ProcessInfo.processInfo.systemUptime
            if uptime - lastSync >= 1.5, !hasSpace() { throw WatchRecordingError.storageFull }
            remainder.append(pcm)
            while remainder.count >= Self.frameBytes {
                if writer == nil { try open() }
                var length = UInt32(Self.frameBytes).littleEndian
                var encoded = withUnsafeBytes(of: &length) { Data($0) }
                encoded.append(remainder.prefix(Self.frameBytes))
                guard let writer else { throw WatchRecordingError.storageFull }
                try writer.write(contentsOf: encoded)
                remainder.removeFirst(Self.frameBytes)
                frames += 1
                totalFrames += 1
                if frames == Self.maxFrames { try seal() }
            }
            // Data.removeFirst advances a slice; it can retain every consumed
            // byte in its backing allocation. Copy only the <320-byte tail.
            remainder = remainder.withUnsafeBytes { Data($0) }
            // Persist the sub-frame tail too: process death must not lose up to 10 ms.
            if !remainder.isEmpty, writer == nil { try open() }
            if uptime - lastSync >= 1.5 {
                try writer?.synchronize()
                if let metadata, let writer {
                    try Self.writeDurably(JSONEncoder().encode(Tail(offset: try writer.offset(), bytes: remainder)), to: tailURL(metadata))
                }
                lastSync = uptime
            }
        }
    }

    func finish() throws {
        lock.lock(); defer { lock.unlock() }
        if !remainder.isEmpty {
            if writer == nil { try open() }
            var length = UInt32(Self.frameBytes).littleEndian
            var frame = withUnsafeBytes(of: &length) { Data($0) }
            frame.append(remainder)
            frame.append(Data(count: Self.frameBytes - remainder.count))
            guard let writer else { throw WatchRecordingError.storageFull }
            try writer.write(contentsOf: frame)
            frames += 1
            totalFrames += 1
            remainder = Data()
        }
        try seal()
        ownerUID = ""
    }

    func pending() throws -> [(URL, WatchRecordingMetadata)] {
        lock.lock(); defer { lock.unlock() }
        return try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "bin" }
            .compactMap { url in
                guard let metadata = try? Self.readMetadata(url), metadata.isValid,
                      metadata.fileName == url.lastPathComponent else { return nil }
                return (url, metadata)
            }.sorted { $0.0.lastPathComponent < $1.0.lastPathComponent }
    }

    /// An OS transfer completion alone is not a receipt from the iPhone's durable inbox.
    func acknowledge(fileName: String, digest: String) throws {
        lock.lock(); defer { lock.unlock() }
        guard !fileName.contains("/"), !fileName.contains("\\") else { return }
        let url = directory.appendingPathComponent(fileName)
        guard FileManager.default.fileExists(atPath: url.path), try Self.digest(url) == digest else { return }
        try Self.writeDurably(Data(digest.utf8), to: url.appendingPathExtension("ack"))
    }

    func pruneAcknowledged(excluding inFlight: Set<String>) throws {
        lock.lock(); defer { lock.unlock() }
        for (url, _) in try pending() where !inFlight.contains(url.lastPathComponent) {
            let ack = url.appendingPathExtension("ack")
            guard let digest = try? String(contentsOf: ack, encoding: .utf8), try Self.digest(url) == digest else { continue }
            try FileManager.default.removeItem(at: url)
            try? FileManager.default.removeItem(at: url.appendingPathExtension("watch.json"))
            try? FileManager.default.removeItem(at: ack)
        }
    }

    static func readMetadata(_ url: URL) throws -> WatchRecordingMetadata {
        try JSONDecoder().decode(WatchRecordingMetadata.self, from: Data(contentsOf: url.appendingPathExtension("watch.json")))
    }

    static func digest(_ url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hash = SHA256()
        while true {
            let more = try autoreleasepool {
                guard let bytes = try handle.read(upToCount: 64 * 1024), !bytes.isEmpty else { return false }
                hash.update(data: bytes)
                return true
            }
            if !more { break }
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    /// Reject truncation and unexpected framing before accepting custody or publishing a file.
    static func validatedFrameCount(_ url: URL) throws -> Int {
        try autoreleasepool {
            let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
            guard size > 0, size <= Self.maxFrames * (Self.frameBytes + 4) else { throw WatchRecordingError.invalidAudio }
            let data = try Data(contentsOf: url, options: .mappedIfSafe)
            guard !data.isEmpty, data.count <= Self.maxFrames * (Self.frameBytes + 4),
                  data.count % (Self.frameBytes + 4) == 0 else { throw WatchRecordingError.invalidAudio }
            for offset in stride(from: 0, to: data.count, by: Self.frameBytes + 4) {
                guard Array(data[offset..<(offset + 4)]) == [0x40, 0x01, 0, 0] else { throw WatchRecordingError.invalidAudio }
            }
            return data.count / (Self.frameBytes + 4)
        }
    }

    private func open() throws {
        guard hasSpace() else { throw WatchRecordingError.storageFull }
        let value = WatchRecordingMetadata(version: 1, sessionID: sessionID, segment: segment,
                                           startedAt: start + Int64(totalFrames / 100), ownerUID: ownerUID)
        let url = directory.appendingPathComponent(value.fileName)
        try Self.writeDurably(JSONEncoder().encode(value), to: url.appendingPathExtension("watch.json"))
        guard FileManager.default.createFile(atPath: url.appendingPathExtension("part").path, contents: nil) else {
            throw WatchRecordingError.storageFull
        }
        metadata = value
        writer = try FileHandle(forWritingTo: url.appendingPathExtension("part"))
        frames = 0
    }

    private func tailURL(_ value: WatchRecordingMetadata) -> URL {
        directory.appendingPathComponent(value.fileName).appendingPathExtension("tail")
    }

    private func seal() throws {
        guard let writer, let metadata else { return }
        try writer.synchronize()
        try writer.close()
        self.writer = nil
        let url = directory.appendingPathComponent(metadata.fileName)
        if frames > 0 { try FileManager.default.moveItem(at: url.appendingPathExtension("part"), to: url) }
        try? FileManager.default.removeItem(at: tailURL(metadata))
        self.metadata = nil
        frames = 0
        segment += 1
    }

    private func recoverInterruptedSegments() throws {
        for part in try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
            where part.lastPathComponent.hasSuffix(".bin.part") {
            do { try autoreleasepool { try recoverInterruptedSegment(part) } }
            catch { recoveryFailures += 1 } // Preserve the original; other recordings must remain usable.
        }
    }

    private func recoverInterruptedSegment(_ part: URL) throws {
        let url = part.deletingPathExtension()
        let metadata = try Self.readMetadata(url)
        guard metadata.isValid, metadata.fileName == url.lastPathComponent else { throw WatchRecordingError.invalidMetadata }
        let size = try part.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size <= Self.maxFrames * (Self.frameBytes + 4) else { throw WatchRecordingError.invalidAudio }
        // A torn last frame is retained in the .part until the complete prefix is secured.
        var bytes = try Data(contentsOf: part)
        let complete = bytes.count / (Self.frameBytes + 4) * (Self.frameBytes + 4)
        bytes = bytes.prefix(complete)
        if let encoded = try? Data(contentsOf: tailURL(metadata)),
           let tail = try? JSONDecoder().decode(Tail.self, from: encoded), tail.offset == UInt64(complete),
           !tail.bytes.isEmpty, tail.bytes.count < Self.frameBytes, tail.bytes.count % 2 == 0 {
            bytes.append(contentsOf: [0x40, 0x01, 0, 0])
            bytes.append(tail.bytes)
            bytes.append(Data(count: Self.frameBytes - tail.bytes.count))
        }
        guard !bytes.isEmpty else { return }
        let recovered = url.appendingPathExtension("recovering")
        try bytes.write(to: recovered, options: .atomic)
        _ = try Self.validatedFrameCount(recovered)
        let handle = try FileHandle(forWritingTo: recovered)
        try handle.synchronize()
        try handle.close()
        if FileManager.default.fileExists(atPath: url.path) {
            // Never discard a partial merely because a different sealed copy exists.
            guard try Self.digest(url) == Self.digest(recovered) else { throw WatchRecordingError.conflictingReceipt }
            try FileManager.default.removeItem(at: recovered)
        } else { try FileManager.default.moveItem(at: recovered, to: url) }
        // Preserve a torn suffix for diagnostics rather than destroy original bytes.
        if complete < size {
            try FileManager.default.moveItem(at: part, to: part.appendingPathExtension("torn"))
        } else { try FileManager.default.removeItem(at: part) }
        try? FileManager.default.removeItem(at: tailURL(metadata))
    }
}

/// Do not repeatedly send another account's retained recordings ahead of the
/// current account. Retry timing uses uptime so a clock correction cannot stall it.
enum WatchRecoveryTransferQueue {
    static func candidates(_ files: [(URL, WatchRecordingMetadata)], ownerUID: String,
                           inFlight: Set<String>, attempts: [String: TimeInterval], uptime: TimeInterval) -> [(URL, WatchRecordingMetadata)] {
        guard !ownerUID.isEmpty else { return [] }
        return Array(files.filter { url, metadata in
            metadata.ownerUID == ownerUID && !inFlight.contains(url.lastPathComponent)
                && uptime - (attempts[url.lastPathComponent] ?? -.infinity) >= 60
        }.sorted { left, right in
            let leftAttempt = attempts[left.0.lastPathComponent] ?? -.infinity
            let rightAttempt = attempts[right.0.lastPathComponent] ?? -.infinity
            if leftAttempt != rightAttempt { return leftAttempt < rightAttempt }
            if left.1.startedAt != right.1.startedAt { return left.1.startedAt < right.1.startedAt }
            return left.0.lastPathComponent < right.0.lastPathComponent
        }.prefix(max(0, 4 - inFlight.count)))
    }
}

/// iPhone receipt journal outlives the audio file: retransmission cannot resurrect a
/// backup that the user already processed or deleted. A receipt precedes the Watch ACK.
enum WatchRecordingInbox {
    private struct Receipt: Codable { let metadata: WatchRecordingMetadata; let digest: String }
    private static let lock = NSLock()
    static func receive(_ source: URL, metadata: WatchRecordingMetadata, directory: URL, ownerUID: String) throws -> String {
        lock.lock(); defer { lock.unlock() }
        guard metadata.isValid else { throw WatchRecordingError.invalidMetadata }
        guard metadata.ownerUID == ownerUID else { throw WatchRecordingError.wrongOwner }
        _ = try WatchRecordingStore.validatedFrameCount(source)
        let digest = try WatchRecordingStore.digest(source)
        let receipts = directory.appendingPathComponent(".watch-receipts", isDirectory: true)
        try FileManager.default.createDirectory(at: receipts, withIntermediateDirectories: true)
        let receipt = receipts.appendingPathComponent(metadata.fileName)
        if FileManager.default.fileExists(atPath: receipt.path) {
            let existing = try JSONDecoder().decode(Receipt.self, from: Data(contentsOf: receipt))
            guard existing.digest == digest, existing.metadata == metadata else { throw WatchRecordingError.conflictingReceipt }
            return digest
        }
        let destination = directory.appendingPathComponent(metadata.fileName)
        // The owner sidecar is published before the discoverable .bin, never adopted
        // by whichever account happens to scan the documents directory next.
        if let existing = try? WatchRecordingStore.readMetadata(destination), existing != metadata {
            throw WatchRecordingError.conflictingReceipt
        }
        try WatchRecordingStore.writeDurably(JSONEncoder().encode(metadata), to: destination.appendingPathExtension("watch.json"))
        if FileManager.default.fileExists(atPath: destination.path) {
            guard try WatchRecordingStore.digest(destination) == digest else { throw WatchRecordingError.conflictingReceipt }
        } else {
            let temporary = destination.appendingPathExtension("incoming")
            try? FileManager.default.removeItem(at: temporary)
            try FileManager.default.copyItem(at: source, to: temporary)
            let handle = try FileHandle(forWritingTo: temporary)
            try handle.synchronize()
            try handle.close()
            try FileManager.default.moveItem(at: temporary, to: destination)
        }
        try WatchRecordingStore.writeDurably(JSONEncoder().encode(Receipt(metadata: metadata, digest: digest)), to: receipt)
        return digest
    }
}
