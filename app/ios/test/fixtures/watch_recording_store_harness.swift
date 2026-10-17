import Foundation

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
        if scenario == "unbound" {
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
