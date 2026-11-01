import Foundation
import Darwin

@main
struct WatchRecordingStoreHarness {
    static func check(_ value: Bool) { precondition(value) }
    static func rejected(_ body: () throws -> Void) {
        do { try body(); preconditionFailure("expected rejection") } catch {}
    }

    static func payload(_ url: URL) throws -> Data {
        let bytes = try Data(contentsOf: url)
        var result = Data()
        for index in stride(from: 0, to: bytes.count, by: 324) { result.append(bytes[(index + 4)..<(index + 324)]) }
        return result
    }

    static func main() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let watch = root.appendingPathComponent("watch")
        let phone = root.appendingPathComponent("phone")
        let store = try WatchRecordingStore(directory: watch, hasSpace: { true })
        let scenario = CommandLine.arguments[1]
        if scenario == "bounded_writer" {
            try store.begin(ownerUID: "user-a", startedAt: 1720000000)
            let chunk = Data(repeating: 37, count: 47998)
            // 90 minutes of audio callbacks; no caller-owned autorelease pool.
            // Foundation bridging must not retain the ~175 MB of written data.
            for _ in 0..<3600 { try store.append(chunk) }
            try store.finish()
            var usage = rusage()
            check(getrusage(RUSAGE_SELF, &usage) == 0)
            precondition(usage.ru_maxrss < 128 * 1024 * 1024, "writer retained buffers: \(usage.ru_maxrss) bytes")
            check(try store.pending().count == 90)
            for (url, metadata) in try store.pending() {
                check(try WatchRecordingStore.validatedFrameCount(url) > 0)
                try store.acknowledge(fileName: metadata.fileName, digest: WatchRecordingStore.digest(url))
            }
            try store.pruneAcknowledged(excluding: [])
            check(try store.pending().isEmpty)
            check(getrusage(RUSAGE_SELF, &usage) == 0)
            precondition(usage.ru_maxrss < 128 * 1024 * 1024, "receipt cleanup retained buffers: \(usage.ru_maxrss) bytes")
        } else if scenario == "transfer_queue" {
            let files = (0..<12).map { index -> (URL, WatchRecordingMetadata) in
                let metadata = WatchRecordingMetadata(version: 1, sessionID: String(repeating: "a", count: 32),
                    segment: index, startedAt: 1720000000 + Int64(index), ownerUID: index < 6 ? "old-user" : "user-a")
                return (watch.appendingPathComponent(metadata.fileName), metadata)
            }
            let first = WatchRecoveryTransferQueue.candidates(files, ownerUID: "user-a", inFlight: [], attempts: [:], uptime: 100)
            check(first.map { $0.1.segment } == [6, 7, 8, 9])
            let next = WatchRecoveryTransferQueue.candidates(files, ownerUID: "user-a",
                inFlight: [first[0].0.lastPathComponent], attempts: [first[1].0.lastPathComponent: 90], uptime: 100)
            check(next.map { $0.1.segment } == [8, 9, 10])
            let retry = WatchRecoveryTransferQueue.candidates(files, ownerUID: "user-a",
                inFlight: [], attempts: [first[1].0.lastPathComponent: 90], uptime: 150)
            check(retry.map { $0.1.segment } == [6, 8, 9, 10])
            check(WatchRecoveryTransferQueue.candidates([files[7]], ownerUID: "user-a",
                inFlight: [], attempts: [files[7].0.lastPathComponent: 90], uptime: 150).count == 1)
            let attempted = Dictionary(uniqueKeysWithValues: first.map { ($0.0.lastPathComponent, TimeInterval(100)) })
            let fairRetry = WatchRecoveryTransferQueue.candidates(files, ownerUID: "user-a",
                inFlight: [], attempts: attempted, uptime: 160)
            check(fairRetry.map { $0.1.segment } == [10, 11, 6, 7])
            check(WatchRecoveryTransferQueue.candidates(files, ownerUID: "", inFlight: [], attempts: [:], uptime: 100).isEmpty)
            check(WatchRecoveryTransferQueue.candidates(files, ownerUID: "user-a",
                inFlight: Set(first.map { $0.0.lastPathComponent }), attempts: [:], uptime: 100).isEmpty)
        } else if ["damaged_partial", "conflicting_partial", "oversized_partial"].contains(scenario) {
            let location = root.appendingPathComponent("interrupted")
            var interrupted: WatchRecordingStore? = try WatchRecordingStore(directory: location, hasSpace: { true })
            try interrupted!.begin(ownerUID: "user-a", startedAt: 1720000000)
            try interrupted!.append(Data(repeating: 23, count: 640))
            interrupted = nil
            let part = try FileManager.default.contentsOfDirectory(at: location, includingPropertiesForKeys: nil).first { $0.pathExtension == "part" }!
            if scenario == "damaged_partial" {
                var bytes = try Data(contentsOf: part)
                bytes[0] = 255
                try bytes.write(to: part)
            } else if scenario == "conflicting_partial" {
                var bytes = try Data(contentsOf: part)
                bytes[4] = 99
                try bytes.write(to: part.deletingPathExtension())
            } else {
                let handle = try FileHandle(forWritingTo: part)
                try handle.truncate(atOffset: UInt64((WatchRecordingStore.maxFrames + 1) * 324))
                try handle.close()
            }
            let original = try WatchRecordingStore.digest(part)
            let recovered = try WatchRecordingStore(directory: location, hasSpace: { true })
            check(recovered.recoveryFailures == 1)
            check(try WatchRecordingStore.digest(part) == original)
            try recovered.begin(ownerUID: "user-a", startedAt: 1720000100)
            try recovered.append(Data(repeating: 7, count: 320))
            try recovered.finish()
            let healthy = try recovered.pending().filter { $0.1.startedAt == 1720000100 }
            check(healthy.count == 1)
            check(try payload(healthy[0].0) == Data(repeating: 7, count: 320))
            let restarted = try WatchRecordingStore(directory: location, hasSpace: { true })
            check(restarted.recoveryFailures == 1)
            check(try restarted.pending().contains { $0.1.startedAt == 1720000100 })
        } else if scenario == "unbound" {
            rejected { try store.begin(ownerUID: "", startedAt: 1720000000) }
        } else if scenario == "restart_tail" {
            var interrupted: WatchRecordingStore? = try WatchRecordingStore(directory: root.appendingPathComponent("restart"), hasSpace: { true })
            let location = interrupted!.directory
            try interrupted!.begin(ownerUID: "user-a", startedAt: 1720000000)
            try interrupted!.append(Data(repeating: 23, count: 642))
            interrupted = nil
            let part = try FileManager.default.contentsOfDirectory(at: location, includingPropertiesForKeys: nil).first { $0.pathExtension == "part" }!
            let torn = try FileHandle(forWritingTo: part)
            try torn.seekToEnd()
            try torn.write(contentsOf: Data([0x40, 0x01]))
            try torn.close()
            let recovered = try WatchRecordingStore(directory: location, hasSpace: { true })
            let files = try recovered.pending()
            check(files.count == 1)
            check(try WatchRecordingStore.validatedFrameCount(files[0].0) == 3)
            let audio = try payload(files[0].0)
            check(audio.prefix(642) == Data(repeating: 23, count: 642))
            check(audio.suffix(318) == Data(count: 318))
            check(FileManager.default.fileExists(atPath: part.appendingPathExtension("torn").path))
        } else if scenario == "stale_session" {
            let old = try store.begin(ownerUID: "user-a", startedAt: 1720000000)
            try store.append(Data(count: 320), sessionID: old)
            let current = try store.begin(ownerUID: "user-a", startedAt: 1720000001)
            rejected { try store.append(Data(count: 320), sessionID: old) }
            try store.append(Data(repeating: 7, count: 320), sessionID: current)
            try store.finish()
            let files = try store.pending()
            check(files.count == 2)
            check(try files.reduce(0) { try $0 + WatchRecordingStore.validatedFrameCount($1.0) } == 2)
        } else if scenario == "storage_full" {
            let full = try WatchRecordingStore(directory: root.appendingPathComponent("full"), hasSpace: { false })
            try full.begin(ownerUID: "user-a", startedAt: 1720000000)
            rejected { try full.append(Data(count: 320)) }
            check(try full.pending().isEmpty)
        } else {
            try store.begin(ownerUID: "user-a", startedAt: 1720000000)
            let input = Data((0..<32000).map { UInt8($0 % 251) })
            try store.append(input)
            try store.append(Data([1, 2]))
            try store.finish()
            let (url, metadata) = try store.pending()[0]
            if scenario == "roundtrip" {
                check(try WatchRecordingStore.validatedFrameCount(url) == 101)
                var expected = input
                expected.append(contentsOf: [1, 2])
                expected.append(Data(count: 318))
                check(try payload(url) == expected)
                let digest = try WatchRecordingInbox.receive(url, metadata: metadata, directory: phone, ownerUID: "user-a")
                check(digest == (try WatchRecordingStore.digest(url)))
                check(try payload(phone.appendingPathComponent(metadata.fileName)) == expected)
            } else if scenario == "custody" {
                try store.pruneAcknowledged(excluding: [])
                check(try store.pending().count == 1)
                try store.acknowledge(fileName: metadata.fileName, digest: "wrong")
                try store.pruneAcknowledged(excluding: [])
                check(try store.pending().count == 1)
                let digest = try WatchRecordingInbox.receive(url, metadata: metadata, directory: phone, ownerUID: "user-a")
                try store.acknowledge(fileName: metadata.fileName, digest: digest)
                try store.pruneAcknowledged(excluding: [metadata.fileName])
                check(try store.pending().count == 1)
                try store.pruneAcknowledged(excluding: [])
                check(try store.pending().isEmpty)
            } else if scenario == "wrong_owner" {
                rejected { _ = try WatchRecordingInbox.receive(url, metadata: metadata, directory: phone, ownerUID: "user-b") }
                check(try store.pending().count == 1)
                check(!FileManager.default.fileExists(atPath: phone.appendingPathComponent(metadata.fileName).path))
            } else if scenario == "receipt_after_delete" {
                let digest = try WatchRecordingInbox.receive(url, metadata: metadata, directory: phone, ownerUID: "user-a")
                try FileManager.default.removeItem(at: phone.appendingPathComponent(metadata.fileName))
                let retry = try WatchRecordingInbox.receive(url, metadata: metadata, directory: phone, ownerUID: "user-a")
                check(retry == digest)
                check(!FileManager.default.fileExists(atPath: phone.appendingPathComponent(metadata.fileName).path))
            } else if scenario == "conflicting_retry" {
                _ = try WatchRecordingInbox.receive(url, metadata: metadata, directory: phone, ownerUID: "user-a")
                var bytes = try Data(contentsOf: url)
                bytes[4] = bytes[4] ^ 255
                let different = root.appendingPathComponent("different")
                try bytes.write(to: different)
                rejected { _ = try WatchRecordingInbox.receive(different, metadata: metadata, directory: phone, ownerUID: "user-a") }
                check(try payload(phone.appendingPathComponent(metadata.fileName)) == payload(url))
            } else if scenario == "corrupt_audio" {
                try Data([0x40, 1, 0]).write(to: root.appendingPathComponent("bad"))
                rejected { _ = try WatchRecordingInbox.receive(root.appendingPathComponent("bad"), metadata: metadata, directory: phone, ownerUID: "user-a") }
            } else if scenario == "invalid_metadata" {
                let bad = WatchRecordingMetadata(version: 1, sessionID: "../../outside", segment: 0, startedAt: 1, ownerUID: "user-a")
                rejected { _ = try WatchRecordingInbox.receive(url, metadata: bad, directory: phone, ownerUID: "user-a") }
            } else if scenario == "out_of_order_rotation" {
                try store.begin(ownerUID: "user-a", startedAt: 1720000001)
                let minute = Data(repeating: 37, count: 16000 * 2 * 61)
                for offset in stride(from: 0, to: minute.count, by: 48000) {
                    try store.append(minute.subdata(in: offset..<min(minute.count, offset + 48000)))
                }
                try store.finish()
                let segments = try store.pending().filter { $0.1.startedAt >= 1720000001 }
                check(segments.count == 2)
                for (file, info) in segments.reversed() {
                    _ = try WatchRecordingInbox.receive(file, metadata: info, directory: phone, ownerUID: "user-a")
                }
                let sorted = segments.sorted { $0.1.segment < $1.1.segment }
                var recovered = Data()
                for (file, info) in sorted {
                    check(info.startedAt == 1720000001 + Int64(info.segment * 60))
                    recovered.append(try payload(file))
                }
                check(recovered == minute)
            } else { preconditionFailure("unknown scenario") }
        }
        print("ok: \(scenario)")
    }
}
