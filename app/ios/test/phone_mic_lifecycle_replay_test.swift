import AVFoundation
import Foundation

// PhoneMic native lifecycle replay harness (SCA-491 / C5).
//
// Replays the canonical `phone-mic-native-events/v1` vectors from
// app/test/fixtures/phone_mic_native_events through the PRODUCTION
// PhoneMicController + PhoneMicEventEmitter, with only OS audio/permission/
// session I/O faked (PhoneMicControllerSeams). The oracle is strict sequence
// equality against the vector (minus the stale-stimulus steps, which must be
// DROPPED) plus explicit negative assertions, so a broken epoch gate, session
// adoption, or terminal cleanup fails the run instead of passing vacuously.
//
// Compiled by ios/test/phone_mic_lifecycle_replay_test.rb together with the
// production sources and a stub of the Pigeon contract types extracted from
// the generated file at test time (drift-guarded by the extraction itself).

// MARK: - Fakes

struct RecordedDelivery {
    enum Kind { case frame, state, error, progress }
    let kind: Kind
    let sessionId: Int64
    var state: String?
    var frame: Data?
    var code: String?
    var message: String?
    var seconds: Double?
}

final class RecordingSink: PhoneMicEventSink, @unchecked Sendable {
    private let lock = NSLock()
    private var _deliveries: [RecordedDelivery] = []
    var deliveries: [RecordedDelivery] {
        lock.lock(); defer { lock.unlock() }
        return _deliveries
    }

    private func record(_ delivery: RecordedDelivery) {
        lock.lock(); defer { lock.unlock() }
        _deliveries.append(delivery)
    }

    func onAudioFrame(pcm16leMono16k: Data, sessionId: Int64) {
        record(RecordedDelivery(kind: .frame, sessionId: sessionId, state: nil, frame: pcm16leMono16k, code: nil, message: nil, seconds: nil))
    }

    func onStateChanged(state: PhoneMicCaptureState, sessionId: Int64) {
        record(RecordedDelivery(kind: .state, sessionId: sessionId, state: state.name, frame: nil, code: nil, message: nil, seconds: nil))
    }

    func onCaptureError(code: String, message: String, sessionId: Int64) {
        record(RecordedDelivery(kind: .error, sessionId: sessionId, state: nil, frame: nil, code: code, message: message, seconds: nil))
    }

    func onBatchProgress(capturedSeconds: Double, sessionId: Int64) {
        record(RecordedDelivery(kind: .progress, sessionId: sessionId, state: nil, frame: nil, code: nil, message: nil, seconds: capturedSeconds))
    }
}

extension PhoneMicCaptureState {
    var name: String {
        switch self {
        case .idle: return "idle"
        case .starting: return "starting"
        case .running: return "running"
        case .interrupted: return "interrupted"
        case .rebuilding: return "rebuilding"
        @unknown default: return "unknown"
        }
    }
}

final class FakeEngine: PhoneMicEngineControlling {
    let onConvertedData: (Data, UInt64) -> Void
    /// While > 0, startEngine() throws (consumed one per attempt).
    var startFailuresRemaining: Int

    init(onConvertedData: @escaping (Data, UInt64) -> Void, startFailuresRemaining: Int = 0) {
        self.onConvertedData = onConvertedData
        self.startFailuresRemaining = startFailuresRemaining
    }

    var isRunning: Bool { true }
    var audioEngineForMonitor: AVAudioEngine? { nil }

    func buildAndInstallTap(epoch: UInt64) throws {}

    func startEngine() throws {
        if startFailuresRemaining > 0 {
            startFailuresRemaining -= 1
            throw NSError(domain: "FakeEngine", code: 1, userInfo: [NSLocalizedDescriptionKey: "simulated engine start failure"])
        }
    }

    func teardown() {}

    /// Emit a converted frame exactly like the real tap pipeline would.
    func emitConverted(_ data: Data, epoch: UInt64) {
        onConvertedData(data, epoch)
    }
}

final class FakeMonitor: PhoneMicInterruptionSource {
    let queue: DispatchQueue
    let handler: (PhoneMicInterruptionSignal) -> Void

    init(queue: DispatchQueue, handler: @escaping (PhoneMicInterruptionSignal) -> Void) {
        self.queue = queue
        self.handler = handler
    }

    func fire(_ signal: PhoneMicInterruptionSignal) {
        queue.async { self.handler(signal) }
    }

    func startObserving() {}
    func stopObserving() {}
    func bindEngine(_ engine: AVAudioEngine?) {}
}

final class FakePermission: PhoneMicPermissionChecking {
    var status: PhoneMicPermissionStatus
    var requestResult: Bool
    init(status: PhoneMicPermissionStatus, requestResult: Bool = true) {
        self.status = status
        self.requestResult = requestResult
    }

    func current() -> PhoneMicPermissionStatus { status }
    func request(_ completion: @escaping (Bool) -> Void) {
        // Mirror the OS: the prompt resolves on a background thread.
        DispatchQueue.global().async { completion(self.requestResult) }
    }
}

// MARK: - Harness

struct VectorEvent {
    let kind: String
    let sessionId: Int64
    let state: String?
    let frame: Data?
}

struct Vector {
    let id: String
    let startSessionId: Int64
    let events: [VectorEvent]
}

final class ReplayWorld {
    let sink = RecordingSink()
    let monitorBox = MonitorBox()
    let engineBox = EngineBox()

    final class MonitorBox {
        var monitor: FakeMonitor?
    }

    final class EngineBox {
        var engines: [FakeEngine] = []
        var startFailures = 0
    }

    func makeController(permission: FakePermission) -> PhoneMicController {
        let sink = self.sink
        let monitorBox = self.monitorBox
        let engineBox = self.engineBox
        return PhoneMicController(environment: PhoneMicControllerEnvironment(
            sink: sink,
            permission: permission,
            configureSession: {},
            describeRoute: { "harness-route" },
            makeMonitor: { controlQueue, onSignal in
                let monitor = FakeMonitor(queue: controlQueue, handler: onSignal)
                monitorBox.monitor = monitor
                return monitor
            },
            makeEngine: { _, onConvertedData, _ in
                let engine = FakeEngine(onConvertedData: onConvertedData, startFailuresRemaining: engineBox.startFailures)
                engineBox.engines.append(engine)
                return engine
            },
            batchDirectory: { nil },
            batchAutoMarker: { false },
            makeEncoder: { nil },
            makeWriter: { _, _ in fatalError("stream-mode vectors never build a batch writer") }
        ))
    }
}

func drainMain(seconds: Double) {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        RunLoop.main.run(until: Date().addingTimeInterval(0.02))
    }
}
func waitUntil(_ condition: @escaping () -> Bool, timeout: Double = 5.0, _ label: String) {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition() && Date() < deadline {
        RunLoop.main.run(until: Date().addingTimeInterval(0.02))
    }
    precondition(condition(), "timed out waiting for \(label)")
}

func loadVectors() -> [String: Vector] {
    let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent() // app/ios/test
    let fixturesDir = here.deletingLastPathComponent() // app/ios
        .deletingLastPathComponent() // app
        .appendingPathComponent("test/fixtures/phone_mic_native_events")
    var vectors: [String: Vector] = [:]
    for url in (try! FileManager.default.contentsOfDirectory(at: fixturesDir, includingPropertiesForKeys: nil)) where url.pathExtension == "json" {
        let doc = try! JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        let id = doc["id"] as! String
        precondition((doc["schema_version"] as? String) == "phone-mic-native-events/v1", "\(id): wrong schema")
        let events = (doc["events"] as! [[String: Any]]).map { raw -> VectorEvent in
            VectorEvent(
                kind: raw["kind"] as! String,
                sessionId: raw["session_id"] as! Int64,
                state: raw["state"] as? String,
                frame: (raw["pcm_frame_base64"] as? String).flatMap { Data(base64Encoded: $0) }
            )
        }
        vectors[id] = Vector(id: id, startSessionId: doc["start_session_id"] as! Int64, events: events)
    }
    precondition(vectors.count == 8, "expected the canonical 8 vectors, found \(vectors.count)")
    return vectors
}

func stateDelivery(_ state: String, _ sessionId: Int64) -> RecordedDelivery {
    RecordedDelivery(kind: .state, sessionId: sessionId, state: state, frame: nil, code: nil, message: nil, seconds: nil)
}

func frameDelivery(_ data: Data, _ sessionId: Int64) -> RecordedDelivery {
    RecordedDelivery(kind: .frame, sessionId: sessionId, state: nil, frame: data, code: nil, message: nil, seconds: nil)
}

/// Delivered == vector minus the stale-stimulus indices, in order, byte-identical frames.
func assertDeliveriesMatch(_ vector: Vector, staleIndices: Set<Int>, _ delivered: [RecordedDelivery], label: String) {
    let expected: [RecordedDelivery] = vector.events.enumerated().compactMap { index, event in
        guard !staleIndices.contains(index) else { return nil }
        switch event.kind {
        case "stateChanged":
            return stateDelivery(event.state!, event.sessionId)
        case "audioFrame":
            return frameDelivery(event.frame!, event.sessionId)
        default:
            preconditionFailure("\(vector.id): unexpected kind \(event.kind) in expectation")
        }
    }
    guard delivered.count == expected.count else {
        preconditionFailure("\(label): delivered \(delivered.count) events, expected \(expected.count)\n" +
            "delivered: \(delivered.map { "\($0.kind)@\($0.sessionId):\($0.state ?? "")" })\n" +
            "expected: \(expected.map { "\($0.kind)@\($0.sessionId):\($0.state ?? "")" })")
    }
    for (got, want) in zip(delivered, expected) {
        precondition(got.kind == want.kind && got.sessionId == want.sessionId && got.state == want.state && got.frame == want.frame,
            "\(label): delivery mismatch\n got: \(got.kind) sid \(got.sessionId) state \(got.state ?? "-") frameBytes \(got.frame?.count ?? 0)\nwant: \(want.kind) sid \(want.sessionId) state \(want.state ?? "-") frameBytes \(want.frame?.count ?? 0)")
    }
    if !staleIndices.isEmpty {
        // Oracle detection proof: an ungated emitter would deliver the stale
        // steps too, and this exact comparator would then fail on the count
        // above. State it explicitly so a "pass" can never hide a delivered
        // stale frame.
        precondition(delivered.count == vector.events.count - staleIndices.count,
            "\(label): stale steps leaked into delivery")
    }
}

func assertNoFrameAfterIdle(_ delivered: [RecordedDelivery], label: String) {
    if let idleAt = delivered.lastIndex(where: { $0.kind == .state && $0.state == "idle" }) {
        precondition(!delivered[(idleAt + 1)...].contains { $0.kind == .frame },
            "\(label): a frame was delivered after the terminal idle event")
    }
}

func start(_ controller: PhoneMicController, _ sessionId: Int64) -> Result<Void, Error> {
    let box = ResultBox()
    controller.start(mode: .stream, sessionId: sessionId) { box.result = $0 }
    waitUntil({ box.result != nil }, "start completion (sid \(sessionId))")
    drainMain(seconds: 0.05)
    return box.result!
}

final class ResultBox {
    var result: Result<Void, Error>?
}

func stop(_ controller: PhoneMicController) {
    let box = FlagBox()
    controller.stop { box.done = true }
    waitUntil({ box.done }, "stop completion")
    drainMain(seconds: 0.05)
}

final class FlagBox {
    var done = false
}

func waitForState(_ sink: RecordingSink, _ state: String, label: String) {
    waitUntil({ sink.deliveries.contains { $0.kind == .state && $0.state == state } }, label)
    drainMain(seconds: 0.05)
}

func frameBytes(_ vector: Vector, _ index: Int) -> Data {
    vector.events[index].frame!
}

@main
struct Harness {
    static func main() {
        let vectors = loadVectors()

        // 1. start-running: starting, running, two frames under the live epoch.
        do {
            let world = ReplayWorld()
            let controller = world.makeController(permission: FakePermission(status: .granted))
            let vector = vectors["phone-mic-start-running"]!
            let result = start(controller, vector.startSessionId)
            guard case .success = result else { preconditionFailure("start-running: start must succeed") }
            let engine = world.engineBox.engines[0]
            engine.emitConverted(frameBytes(vector, 2), epoch: 1)
            engine.emitConverted(frameBytes(vector, 3), epoch: 1)
            drainMain(seconds: 0.1)
            assertDeliveriesMatch(vector, staleIndices: [], world.sink.deliveries, label: "start-running")
        }

        // 2. interruption-resume: interrupt, resume (probe once), frame under the new epoch.
        do {
            let world = ReplayWorld()
            let controller = world.makeController(permission: FakePermission(status: .granted))
            let vector = vectors["phone-mic-interruption-resume"]!
            start(controller, vector.startSessionId)
            world.engineBox.engines[0].emitConverted(frameBytes(vector, 2), epoch: 1)
            drainMain(seconds: 0.05)
            world.monitorBox.monitor!.fire(.interruptionBegan)
            waitForState(world.sink, "interrupted", label: "interruption-resume: interrupted")
            world.monitorBox.monitor!.fire(.interruptionEnded(shouldResume: false))
            waitForState(world.sink, "running", label: "interruption-resume: resume probe")
            precondition(world.engineBox.engines.count == 2, "resume must rebuild a fresh engine")
            world.engineBox.engines[1].emitConverted(frameBytes(vector, 5), epoch: 2)
            drainMain(seconds: 0.05)
            stop(controller)
            assertDeliveriesMatch(vector, staleIndices: [], world.sink.deliveries, label: "interruption-resume")
            assertNoFrameAfterIdle(world.sink.deliveries, label: "interruption-resume")
        }

        // 3. rebuild: route change rebuilds the engine under a fresh epoch.
        do {
            let world = ReplayWorld()
            let controller = world.makeController(permission: FakePermission(status: .granted))
            let vector = vectors["phone-mic-rebuild"]!
            start(controller, vector.startSessionId)
            world.engineBox.engines[0].emitConverted(frameBytes(vector, 2), epoch: 1)
            drainMain(seconds: 0.05)
            world.monitorBox.monitor!.fire(.routeChanged(reasonDescription: "3"))
            waitForState(world.sink, "rebuilding", label: "rebuild: rebuilding")
            waitForState(world.sink, "running", label: "rebuild: back to running")
            precondition(world.engineBox.engines.count == 2, "rebuild must build a fresh engine")
            world.engineBox.engines[1].emitConverted(frameBytes(vector, 5), epoch: 2)
            drainMain(seconds: 0.05)
            stop(controller)
            assertDeliveriesMatch(vector, staleIndices: [], world.sink.deliveries, label: "rebuild")
            assertNoFrameAfterIdle(world.sink.deliveries, label: "rebuild")
        }

        // 4. stale-event: the OLD engine's sink fires across the rebuild — must be dropped.
        do {
            let world = ReplayWorld()
            let controller = world.makeController(permission: FakePermission(status: .granted))
            let vector = vectors["phone-mic-stale-event"]!
            start(controller, vector.startSessionId)
            world.engineBox.engines[0].emitConverted(frameBytes(vector, 2), epoch: 1)
            drainMain(seconds: 0.05)
            world.monitorBox.monitor!.fire(.routeChanged(reasonDescription: "3"))
            waitForState(world.sink, "running", label: "stale-event: rebuilt and running")
            // Stale stimulus: frame from the pre-rebuild epoch, delivered late.
            world.engineBox.engines[0].emitConverted(frameBytes(vector, 4), epoch: 1)
            // Fresh frame under the new epoch is delivered normally.
            world.engineBox.engines[1].emitConverted(frameBytes(vector, 6), epoch: 2)
            drainMain(seconds: 0.05)
            stop(controller)
            // Vector index 4 is the stale frame (between rebuilding and running).
            assertDeliveriesMatch(vector, staleIndices: [4], world.sink.deliveries, label: "stale-event")
            assertNoFrameAfterIdle(world.sink.deliveries, label: "stale-event")
        }

        // 5. idle-stop: stop resolves idle; a late frame from the dead epoch never lands.
        do {
            let world = ReplayWorld()
            let controller = world.makeController(permission: FakePermission(status: .granted))
            let vector = vectors["phone-mic-idle-stop"]!
            start(controller, vector.startSessionId)
            world.engineBox.engines[0].emitConverted(frameBytes(vector, 2), epoch: 1)
            drainMain(seconds: 0.05)
            stop(controller)
            // Terminal-cleanup stimulus: the trailing vector frame after idle.
            world.engineBox.engines[0].emitConverted(frameBytes(vector, 4), epoch: 1)
            drainMain(seconds: 0.1)
            assertDeliveriesMatch(vector, staleIndices: [4], world.sink.deliveries, label: "idle-stop")
            assertNoFrameAfterIdle(world.sink.deliveries, label: "idle-stop")
        }

        // 6. start-error-permission: denied permission fails start with the exact code.
        do {
            let world = ReplayWorld()
            let controller = world.makeController(permission: FakePermission(status: .denied))
            let vector = vectors["phone-mic-start-error-permission"]!
            let result = start(controller, vector.startSessionId)
            guard case .failure(let error) = result,
                  let pigeon = error as? PhoneMicPigeonError, pigeon.code == "permission_denied"
            else { preconditionFailure("start-error-permission: expected permission_denied, got \(String(describing: result))") }
            assertDeliveriesMatch(vector, staleIndices: [], world.sink.deliveries, label: "start-error-permission")
        }

        // 7. start-error-engine: bring-up failure exhausts the retry budget, then fails.
        do {
            let world = ReplayWorld()
            world.engineBox.startFailures = 3 // initial attempt + 2 retries all fail
            let controller = world.makeController(permission: FakePermission(status: .granted))
            let vector = vectors["phone-mic-start-error-engine"]!
            let box = ResultBox()
            controller.start(mode: .stream, sessionId: vector.startSessionId) { box.result = $0 }
            waitUntil({ box.result != nil }, timeout: 5.0, "engine failure to exhaust retries")
            guard case .failure(let error) = box.result!,
                  let pigeon = error as? PhoneMicPigeonError, pigeon.code == "engine_start_failed"
            else { preconditionFailure("start-error-engine: expected engine_start_failed, got \(String(describing: box.result))") }
            precondition(world.engineBox.engines.count == 3, "the retry policy must attempt exactly 1+2 bring-ups")
            drainMain(seconds: 0.1)
            assertDeliveriesMatch(vector, staleIndices: [], world.sink.deliveries, label: "start-error-engine")
        }

        // 8. session-adoption: a second start() onto a live session adopts the
        //    new id, re-emits running, and the NEXT engine bakes it into frames;
        //    frames from the pre-adoption engine keep their original id.
        do {
            let world = ReplayWorld()
            let controller = world.makeController(permission: FakePermission(status: .granted))
            let vector = vectors["phone-mic-session-adoption"]!
            let original = vector.startSessionId
            let adopted = original + 16
            let first = start(controller, original)
            guard case .success = first else { preconditionFailure("adoption: first start must succeed") }
            world.engineBox.engines[0].emitConverted(frameBytes(vector, 2), epoch: 1)
            drainMain(seconds: 0.05)
            let second = start(controller, adopted)
            guard case .success = second else { preconditionFailure("adoption: second start must piggyback successfully") }
            // Frame from the pre-adoption engine sink: keeps the original id.
            world.engineBox.engines[0].emitConverted(frameBytes(vector, 4), epoch: 1)
            drainMain(seconds: 0.05)
            // Rebuild: rebuilding/running carry the adopted id; the new engine bakes it.
            world.monitorBox.monitor!.fire(.routeChanged(reasonDescription: "3"))
            waitForState(world.sink, "running", label: "adoption: rebuilt under the adopted id")
            world.engineBox.engines[1].emitConverted(frameBytes(vector, 7), epoch: 2)
            drainMain(seconds: 0.05)
            stop(controller)
            assertDeliveriesMatch(vector, staleIndices: [], world.sink.deliveries, label: "session-adoption")
        }

        print("phone-mic lifecycle replay: all 8 canonical vectors passed (stale/terminal-cleanup drops verified)")
    }
}
