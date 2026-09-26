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
        try testCapturePolicyFixture()
        try testCapturePolicyAdmission()
        try testProcessMuteLatch()
        try testRevisionRetiresQueuedBleWrites()
        try testPhoneWriterPolicyAcrossRestart()
        try testConfigChanges()
        try testLocationSnapshot()
        print("PASS: capture policy, revision retirement, single writes, partial failures, config changes, and location lifecycle")
    }

    private struct CapturePolicyFixture: Decodable {
        let name: String
        let policy: String?
        let deviceMuted: Bool
        let batchMuted: Bool
        let expectedMuted: Bool
        let expectedRevision: Int64
    }

    private struct CapturePolicyFixtureEnvelope: Decodable {
        let cases: [CapturePolicyFixture]
    }

    /// The same fixture drives the native iOS parser as the Flutter and
    /// Android implementations. The parent test harness owns the fixture at
    /// app/test/fixtures/capture_policy.json; keep this test tolerant while a
    /// checkout is being bootstrapped before that shared file is present.
    static func testCapturePolicyFixture() throws {
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // ios/test
            .deletingLastPathComponent() // ios
            .deletingLastPathComponent() // app
            .appendingPathComponent("test/fixtures/capture_policy.json")
        guard FileManager.default.fileExists(atPath: fixtureURL.path) else { return }
        let fixtures = try JSONDecoder().decode(CapturePolicyFixtureEnvelope.self, from: Data(contentsOf: fixtureURL)).cases
        let suite = "omi.capture.policy.fixture.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        for fixture in fixtures {
            defaults.removeObject(forKey: CaptureAdmissionPolicy.defaultsKey)
            defaults.set(fixture.deviceMuted, forKey: "flutter.deviceMuted")
            defaults.set(fixture.batchMuted, forKey: "flutter.batchMuted")
            if let policy = fixture.policy {
                defaults.set(policy, forKey: CaptureAdmissionPolicy.defaultsKey)
            }
            let actual = CaptureAdmissionPolicy.load(from: defaults)
            precondition(actual.muted == fixture.expectedMuted, fixture.name)
            precondition(actual.revision == fixture.expectedRevision, fixture.name)
        }
    }

    static func testCapturePolicyAdmission() throws {
        let suite = "omi.capture.policy.admission.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        // A missing canonical value preserves the legacy mute behavior while
        // keeping the initial revision stable.
        defaults.set(false, forKey: "flutter.deviceMuted")
        defaults.set(false, forKey: "flutter.batchMuted")
        var policy = CaptureAdmissionPolicy.load(from: defaults)
        precondition(!policy.muted && policy.revision == 0)
        defaults.set(true, forKey: "flutter.deviceMuted")
        policy = CaptureAdmissionPolicy.load(from: defaults)
        precondition(policy.muted && policy.revision == 0)
        defaults.set(false, forKey: "flutter.deviceMuted")
        defaults.set(true, forKey: "flutter.batchMuted")
        policy = CaptureAdmissionPolicy.load(from: defaults)
        precondition(policy.muted && policy.revision == 0)

        // Canonical state supersedes both legacy booleans. Invalid canonical
        // state remains fail-closed even when the legacy flags are clear.
        defaults.set("{\"version\":1,\"revision\":7,\"muted\":false}", forKey: CaptureAdmissionPolicy.defaultsKey)
        policy = CaptureAdmissionPolicy.load(from: defaults)
        precondition(!policy.muted && policy.revision == 7)
        defaults.set("{\"version\":1,\"revision\":8,\"muted\":true}", forKey: CaptureAdmissionPolicy.defaultsKey)
        policy = CaptureAdmissionPolicy.load(from: defaults)
        precondition(policy.muted && policy.revision == 8)
        defaults.set("{\"version\":2,\"revision\":9,\"muted\":false}", forKey: CaptureAdmissionPolicy.defaultsKey)
        policy = CaptureAdmissionPolicy.load(from: defaults)
        precondition(policy.muted && policy.revision == 0)
        defaults.set("{broken", forKey: CaptureAdmissionPolicy.defaultsKey)
        policy = CaptureAdmissionPolicy.load(from: defaults)
        precondition(policy.muted && policy.revision == 0)
    }

    static func testProcessMuteLatch() throws {
        CaptureAdmissionPolicy.resetProcessLatchForTesting()
        defer { CaptureAdmissionPolicy.resetProcessLatchForTesting() }
        precondition(CaptureAdmissionPolicy.currentProcessRevision() == 0)
        precondition(CaptureAdmissionPolicy.channelRevision(NSNumber(value: Int32(1))) == 1)
        precondition(CaptureAdmissionPolicy.channelRevision(NSNumber(value: Int64(2))) == 2)
        precondition(CaptureAdmissionPolicy.channelRevision(NSNumber(value: true)) == nil)
        let suite = "omi.capture.policy.latch.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        defaults.set("{\"version\":1,\"revision\":1,\"muted\":false}", forKey: CaptureAdmissionPolicy.defaultsKey)
        precondition(!CaptureAdmissionPolicy.load(from: defaults).muted)

        // The native mute takes effect before the durable write and remains in
        // force while the old unmuted preference is still visible.
        precondition(CaptureAdmissionPolicy.applyProcessUpdate(muted: true, revision: 2, defaults: defaults) == .applied)
        precondition(CaptureAdmissionPolicy.currentProcessRevision() == 2)
        precondition(CaptureAdmissionPolicy.load(from: defaults).muted)
        precondition(CaptureAdmissionPolicy.applyProcessUpdate(muted: false, revision: 2, defaults: defaults) == .persistenceNotReady)

        // Persisting a mute does not release the latch. Only a matching
        // persisted unmute can do that.
        defaults.set("{\"version\":1,\"revision\":2,\"muted\":true}", forKey: CaptureAdmissionPolicy.defaultsKey)
        precondition(CaptureAdmissionPolicy.applyProcessUpdate(muted: false, revision: 2, defaults: defaults) == .persistenceNotReady)
        defaults.set("{\"version\":1,\"revision\":2,\"muted\":false}", forKey: CaptureAdmissionPolicy.defaultsKey)
        precondition(CaptureAdmissionPolicy.applyProcessUpdate(muted: false, revision: 2, defaults: defaults) == .applied)
        precondition(!CaptureAdmissionPolicy.load(from: defaults).muted)
        if case .stale(let currentRevision) = CaptureAdmissionPolicy.applyProcessUpdate(muted: true, revision: 1, defaults: defaults) {
            precondition(currentRevision == 2)
        } else {
            preconditionFailure("stale native policy revision was accepted")
        }

        // A malformed or muted durable value still denies capture when the
        // process latch is clear; the latch never authorizes audio by itself.
        defaults.set("broken", forKey: CaptureAdmissionPolicy.defaultsKey)
        precondition(CaptureAdmissionPolicy.load(from: defaults).muted)
    }

    /// Exercise the real BLE batch writer at both policy boundaries. The
    /// second packet is queued while revision 4 is current, then retired when
    /// revision 5 arrives before the writer queue drains.
    static func testRevisionRetiresQueuedBleWrites() throws {
        let dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let suite = "omi.capture.policy.writer.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let writer = OmiBatchAudioWriter(defaults: defaults)
        defaults.set(true, forKey: "flutter.batchModeEnabled")
        defaults.set(dir.path, forKey: "flutter.batchAudioDir")
        defaults.set("{\"deviceId\":\"device\",\"serviceUuid\":\"service\",\"characteristicUuid\":\"char\"}", forKey: "flutter.nativeBleStreamConfig")

        func policy(_ revision: Int, muted: Bool) {
            defaults.set(
                "{\"version\":1,\"revision\":\(revision),\"muted\":\(muted ? "true" : "false")}",
                forKey: CaptureAdmissionPolicy.defaultsKey
            )
        }
        func enqueue(_ byte: UInt8) {
            precondition(writer.handle(
                peripheralUuid: "device", serviceUuid: "service", characteristicUuid: "char",
                value: Data([0, 0, 0, byte])
            ))
        }

        // Work admitted under revision 1 must be retired after mute revision 2
        // arrives, even though the BLE callback already returned to its caller.
        policy(1, muted: false)
        enqueue(0x11)
        policy(2, muted: true)
        writer.queue.sync {}
        precondition((try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil).isEmpty) == true)
        defaults.set(false, forKey: "flutter.batchModeEnabled")
        precondition(!writer.handle(
            peripheralUuid: "device", serviceUuid: "service", characteristicUuid: "char", value: Data([0, 0, 0, 0x12])
        ))
        writer.queue.sync {}
        defaults.set(true, forKey: "flutter.batchModeEnabled")
        // Re-enabling batch mode while muted remains safe: the native writer
        // consumes the configured characteristic but creates no file.
        enqueue(0x13)
        writer.queue.sync {}
        precondition((try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil).isEmpty) == true)

        // An unmuted packet writes normally. A revision-only transition retires
        // queued work too, while the current revision remains unmuted.
        policy(3, muted: false)
        enqueue(0x22)
        writer.queue.sync {}
        policy(4, muted: false)
        enqueue(0x33)
        policy(5, muted: false)
        writer.queue.sync {}
        policy(5, muted: false)
        enqueue(0x44)
        writer.queue.sync {}

        // Mute remains authoritative while batch mode is alive; unmute under a
        // new revision resumes the same open file without admitting 0x55.
        policy(6, muted: true)
        enqueue(0x55)
        writer.queue.sync {}
        policy(7, muted: false)
        enqueue(0x66)
        writer.queue.sync {}
        defaults.set(false, forKey: "flutter.batchModeEnabled")
        precondition(!writer.handle(
            peripheralUuid: "device", serviceUuid: "service", characteristicUuid: "char", value: Data([0, 0, 0, 0x77])
        ))
        writer.queue.sync {}

        let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)
        let finalized = files.filter { $0.path.hasSuffix(".bin") }
        precondition(finalized.count == 1)
        let actual = try Data(contentsOf: finalized[0])
        check(actual == Data([
            1, 0, 0, 0, 0x22,
            1, 0, 0, 0, 0x44,
            1, 0, 0, 0, 0x66,
        ]))
    }

    static func testPhoneWriterPolicyAcrossRestart() throws {
        let dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let suite = "omi.capture.policy.phone.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let queue = DispatchQueue(label: "test.phone.policy")
        let packets = [Data([0x01, 0x02])]

        // Generic device mute is honored by the phone batch sink while the
        // canonical policy has not yet been introduced.
        defaults.set(true, forKey: "flutter.deviceMuted")
        let firstWriter = PhoneMicBatchAudioWriter(dir: dir.path, queue: queue, defaults: defaults)
        queue.sync {
            firstWriter.append(opusPackets: packets, marker: "omibatchphone")
        }
        precondition((try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil).isEmpty) == true)

        // A canonical mute survives construction of a replacement writer (the
        // app-restart boundary) and blocks already-produced opus packets.
        defaults.set("{\"version\":1,\"revision\":9,\"muted\":true}", forKey: CaptureAdmissionPolicy.defaultsKey)
        let restartedWriter = PhoneMicBatchAudioWriter(dir: dir.path, queue: queue, defaults: defaults)
        queue.sync {
            restartedWriter.append(opusPackets: packets, marker: "omibatchphone")
        }
        precondition((try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil).isEmpty) == true)

        defaults.set("{\"version\":1,\"revision\":10,\"muted\":false}", forKey: CaptureAdmissionPolicy.defaultsKey)
        queue.sync {
            restartedWriter.append(opusPackets: packets, marker: "omibatchphone")
            restartedWriter.closeNowLocked("test")
        }
        let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)
        let finalized = files.filter { $0.path.hasSuffix(".bin") }
        precondition(finalized.count == 1)
        check(try Data(contentsOf: finalized[0]) == Data([2, 0, 0, 0, 0x01, 0x02]))
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
