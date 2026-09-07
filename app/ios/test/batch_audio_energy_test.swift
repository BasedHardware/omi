import Foundation

// Stub only the Flutter delivery boundary; compile and execute the real writers.
final class OmiBleManager {
    static let shared = OmiBleManager()
    var flutterApi: TestFlutterApi?
}
final class TestFlutterApi {
    func onBatchRecordingFinalized(fileName: String, completion: (Bool) -> Void) {}
}
final class CountingDefaults: UserDefaults {
    var locationReads = 0
    override func string(forKey key: String) -> String? {
        if key == "flutter.phoneBatchGeolocation" { locationReads += 1 }
        return super.string(forKey: key)
    }
}

@main
struct BatchAudioEnergyTests {
    static func check(_ condition: Bool) { precondition(condition) }

    static func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    static func main() throws {
        try testFrameWrites()
        try testConfigChanges()
        try testLocationSnapshot()
        print("PASS: single writes, partial failures, config changes, and location lifecycle")
    }

    static func testFrameWrites() throws {
        let dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        var writes: [Data] = []
        var tearAt: Int?
        let writer = BaseBatchAudioWriter(tag: "test", queueLabel: "test", recoveryPrefix: "test_", writeData: { fh, data in
            writes.append(data)
            if let tearAt {
                try fh.write(contentsOf: data.prefix(tearAt))
                throw NSError(domain: "injected-write-failure", code: 1)
            }
            try fh.write(contentsOf: data)
        })
        try writer.queue.sync {
            precondition(!writer.writeFramesLocked([Data([1])]))
            precondition(writer.openLocked(dirPath: dir.path, fileName: "test_normal.bin.part", startSec: 1, nowMs: 0))
            let frames = [Data([0xaa, 0xbb]), Data(), Data(repeating: 0xcc, count: 320)]
            precondition(writer.writeFramesLocked(frames))
            precondition(writes.count == frames.count) // old code performed two writes per frame
            precondition(writes[0] == Data([2, 0, 0, 0, 0xaa, 0xbb]))
            precondition(writes[1] == Data([0, 0, 0, 0]))
            precondition(writes[2].prefix(4) == Data([0x40, 1, 0, 0]))
            precondition(writer.currentFrames == 3 && writer.currentBytes == 334)
            let expected = writes.reduce(into: Data()) { $0.append($1) }
            check(try Data(contentsOf: dir.appendingPathComponent("test_normal.bin.part")) == expected)
            precondition(writer.fsyncLocked())
            writer.closeCurrentLocked("test")
            check(try Data(contentsOf: dir.appendingPathComponent("test_normal.bin")) == expected)

            // Fail inside the header, at its boundary, and inside the payload.
            // Every failure must publish only the previously completed frame.
            for offset in [0, 2, 4, 5] {
                tearAt = nil
                let name = "test_torn_\(offset).bin"
                precondition(writer.openLocked(dirPath: dir.path, fileName: name + ".part", startSec: 2, nowMs: 0))
                precondition(writer.writeFramesLocked([Data([0x11])]))
                tearAt = offset
                precondition(!writer.writeFramesLocked([Data([0x22, 0x33]), Data([0x44])]))
                precondition(!writer.isOpen)
                check(try Data(contentsOf: dir.appendingPathComponent(name)) == Data([1, 0, 0, 0, 0x11]))
                precondition(!FileManager.default.fileExists(atPath: dir.appendingPathComponent(name + ".part").path))
            }
            // Failure in the first frame leaves no ingestable placeholder.
            tearAt = 5 // inject the failure explicitly; don't rely on loop leftovers
            precondition(writer.openLocked(dirPath: dir.path, fileName: "test_empty.bin.part", startSec: 3, nowMs: 0))
            precondition(!writer.writeFramesLocked([Data([1, 2])]))
            precondition(!FileManager.default.fileExists(atPath: dir.appendingPathComponent("test_empty.bin").path))
        }
    }

    static func testConfigChanges() throws {
        let suite = "omi.batch.config.test.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var decodes = 0
        let writer = OmiBatchAudioWriter(defaults: defaults, decodeJSON: { data in
            decodes += 1
            return try JSONSerialization.jsonObject(with: data)
        })
        func config(_ device: String) -> String {
            "{\"deviceId\":\"\(device)\",\"serviceUuid\":\"SERVICE\",\"characteristicUuid\":\"CHAR\"}"
        }
        func handle(_ device: String = "DEVICE") -> Bool {
            // Header-only packets exercise routing without creating files.
            writer.handle(peripheralUuid: device, serviceUuid: "service", characteristicUuid: "char", value: Data([1, 2, 3]))
        }
        defaults.set(true, forKey: "flutter.batchModeEnabled")
        defaults.set("/unused", forKey: "flutter.batchAudioDir")
        defaults.set(config("device"), forKey: "flutter.nativeBleStreamConfig")
        for _ in 0..<1_000 { precondition(handle()) }
        precondition(decodes == 1)
        defaults.set(true, forKey: "flutter.batchMuted")
        defaults.set(true, forKey: "flutter.batchCutRequested")
        precondition(handle())
        precondition(defaults.bool(forKey: "flutter.batchCutRequested"))
        defaults.set(false, forKey: "flutter.batchMuted")
        precondition(handle())
        precondition(!defaults.bool(forKey: "flutter.batchCutRequested"))
        defaults.set(config("other"), forKey: "flutter.nativeBleStreamConfig")
        precondition(!handle() && handle("other") && decodes == 2)
        defaults.set("{broken", forKey: "flutter.nativeBleStreamConfig")
        for _ in 0..<10 { precondition(!handle()) }
        precondition(decodes == 3)
        defaults.set(config("device"), forKey: "flutter.nativeBleStreamConfig")
        precondition(handle() && decodes == 4)
        defaults.set("/other", forKey: "flutter.batchAudioDir")
        precondition(handle() && decodes == 5)
        defaults.set(false, forKey: "flutter.batchModeEnabled")
        precondition(!handle())
        defaults.set(true, forKey: "flutter.batchModeEnabled")
        precondition(handle())
        defaults.removeObject(forKey: "flutter.nativeBleStreamConfig")
        precondition(!handle())
        defaults.set(config("device"), forKey: "flutter.nativeBleStreamConfig")
        defaults.set("", forKey: "flutter.batchAudioDir")
        precondition(!handle())
        writer.queue.sync {} // drain disable finalization before teardown

        // Exercise real bytes after a cache hit, including mute and manual cut.
        let dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        defaults.set(dir.path, forKey: "flutter.batchAudioDir")
        precondition(handle()) // populate the exact config cache used by audio below
        let beforeAudioDecodes = decodes
        func audio(_ byte: UInt8) {
            precondition(writer.handle(peripheralUuid: "device", serviceUuid: "service", characteristicUuid: "char", value: Data([0, 0, 0, byte])))
            writer.queue.sync {}
        }
        audio(0x11)
        defaults.set(true, forKey: "flutter.batchMuted")
        audio(0x22)
        defaults.set(true, forKey: "flutter.batchCutRequested")
        defaults.set(false, forKey: "flutter.batchMuted")
        audio(0x33)
        precondition(decodes == beforeAudioDecodes)
        precondition(!defaults.bool(forKey: "flutter.batchCutRequested"))
        let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)
        let finalized = files.filter { $0.path.hasSuffix(".bin") }
        let active = files.filter { $0.path.hasSuffix(".bin.part") }
        precondition(finalized.count == 1 && active.count == 1)
        check(try Data(contentsOf: finalized[0]) == Data([1, 0, 0, 0, 0x11]))
        check(try Data(contentsOf: active[0]) == Data([1, 0, 0, 0, 0x33]))
        defaults.set(false, forKey: "flutter.batchModeEnabled")
        precondition(!handle())
        writer.queue.sync {}
    }

    static func testLocationSnapshot() throws {
        let dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let suite = "omi.batch.location.test.\(UUID().uuidString)"
        let defaults = CountingDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let queue = DispatchQueue(label: "test.phone")
        let writer = PhoneMicBatchAudioWriter(dir: dir.path, queue: queue, defaults: defaults)
        let location = "{\"latitude\":1,\"longitude\":2}"
        try queue.sync {
            func append() { writer.append(opusPackets: [Data([1, 2])], marker: "omibatchphone") }
            append() // no initial location: keep trying
            defaults.set("broken", forKey: "flutter.phoneBatchGeolocation")
            append()
            defaults.set(location, forKey: "flutter.phoneBatchGeolocation")
            // The audio handle stays valid across a directory rename, but the
            // sidecar path becomes temporarily unwritable. Restore it to prove
            // the phone writer does not latch failure and retries the next chunk.
            let relocated = dir.appendingPathExtension("temporarily-moved")
            try FileManager.default.moveItem(at: dir, to: relocated)
            append()
            let readsAfterFailure = defaults.locationReads
            try FileManager.default.moveItem(at: relocated, to: dir)
            append()
            precondition(defaults.locationReads == readsAfterFailure + 1)
            let readsAfterSave = defaults.locationReads
            defaults.set("{\"latitude\":3}", forKey: "flutter.phoneBatchGeolocation")
            for _ in 0..<100 { append() }
            precondition(defaults.locationReads == readsAfterSave)
            let sidecars = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil).filter { $0.path.hasSuffix(".geolocation.json") }
            precondition(sidecars.count == 1)
            check(try String(contentsOf: sidecars[0], encoding: .utf8) == location)
            writer.closeNowLocked("test")
            append() // new recording gets the new location and resets its latch
            precondition(defaults.locationReads > readsAfterSave)
            writer.closeNowLocked("test")

            // Existing snapshots are immutable, and failed writes remain retryable.
            let base = BaseBatchAudioWriter(tag: "test", queueLabel: "unused", recoveryPrefix: "test_")
            precondition(base.persistRecordingGeolocationSidecar(rawGeolocation: "{\"latitude\":9}", audioURL: URL(fileURLWithPath: String(sidecars[0].path.dropLast(".geolocation.json".count)))))
            // An existing snapshot wins even when the current preference is invalid:
            // the caller must latch instead of rereading defaults on every append.
            precondition(base.persistRecordingGeolocationSidecar(rawGeolocation: "broken", audioURL: URL(fileURLWithPath: String(sidecars[0].path.dropLast(".geolocation.json".count)))))
            precondition(base.persistRecordingGeolocationSidecar(rawGeolocation: nil, audioURL: URL(fileURLWithPath: String(sidecars[0].path.dropLast(".geolocation.json".count)))))
            check(try String(contentsOf: sidecars[0], encoding: .utf8) == location)
            let missingDir = dir.appendingPathComponent("missing")
            let audio = missingDir.appendingPathComponent("recording.bin")
            precondition(!base.persistRecordingGeolocationSidecar(rawGeolocation: location, audioURL: audio))
            try FileManager.default.createDirectory(at: missingDir, withIntermediateDirectories: true)
            precondition(base.persistRecordingGeolocationSidecar(rawGeolocation: location, audioURL: audio))
        }
    }
}
