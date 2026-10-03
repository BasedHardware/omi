import Foundation

/// One native ingress owner per pendant. All callbacks run on the BLE/main queue.
final class OmiBleCaptureSession {
    let health: OmiCaptureHealth
    private let now: () -> TimeInterval
    private let permitted: () -> Bool
    private let linkAvailable: () -> Bool
    private let repair: (@escaping (Bool) -> Void) -> Void
    private let reconnect: (@escaping (Bool) -> Void) -> Void
    private let publish: ([String: Any]) -> Void
    private var timer: Timer?
    private var active = false
    private var revision = 0
    private var lastPublishedAt: TimeInterval = 0
    private var lastPhase: OmiCaptureHealth.Phase = .inactive
    var isAuthorized: Bool { active && permitted() }

    init(
        health: OmiCaptureHealth,
        now: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 },
        permitted: @escaping () -> Bool,
        linkAvailable: @escaping () -> Bool = { true },
        repair: @escaping (@escaping (Bool) -> Void) -> Void,
        reconnect: @escaping (@escaping (Bool) -> Void) -> Void,
        publish: @escaping ([String: Any]) -> Void
    ) {
        self.health = health
        self.now = now
        self.permitted = permitted
        self.linkAvailable = linkAvailable
        self.repair = repair
        self.reconnect = reconnect
        self.publish = publish
    }

    func authorize(_ active: Bool) {
        if self.active != active { revision += 1 }
        self.active = active
        health.authorize(active && permitted(), now: now())
        if !active {
            timer?.invalidate()
            timer = nil
        } else if timer == nil {
            timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.tick() }
        }
        emit()
    }

    @discardableResult
    func ready(fresh: Bool, recovery: OmiCaptureReconnect? = nil) -> Bool {
        let finished = recovery?.stage == .finished
        if finished && recovery?.adoptLateConnection(fresh: fresh) != true {
            emit()
            return false
        }
        health.ready(fresh: fresh, now: now())
        emit()
        return finished
    }

    func subscribed(_ confirmed: Bool) {
        health.subscribed(confirmed, now: now())
        emit()
    }

    func audio() {
        guard active && permitted() else { return }
        health.audio(now: now())
        if health.phase != lastPhase || now() - lastPublishedAt >= 5 { emit() }
    }

    func disconnected(recovering: Bool) {
        health.disconnected(recovering: recovering, now: now())
        emit()
    }

    func reconnectTransaction(connected: @escaping () -> Bool, connect: @escaping () -> Void,
                              reportLink: @escaping (Bool) -> Void,
                              completion: @escaping (Bool) -> Void) -> OmiCaptureReconnect {
        OmiCaptureReconnect(connected: connected, authorized: { [weak self] in self?.isAuthorized == true },
            connect: connect, reconcile: { [weak self] connected, recovering in
                // Dart invalidates ingress on link callbacks. Publish reconciled
                // health afterwards so a terminal failure remains visible.
                reportLink(connected)
                if !connected { self?.disconnected(recovering: recovering) }
            }, completion: completion)
    }

    func tick() {
        health.authorize(active && permitted(), now: now())
        guard linkAvailable() else { emit(); return }
        let token = revision
        let action = health.tick(now: now())
        emit()
        switch action {
        case .repairSubscription:
            repair { [weak self] success in
                guard let self, self.revision == token, self.active && self.permitted() else { return }
                self.health.repairCompleted(success: success, now: self.now())
                self.emit()
            }
        case .reconnect:
            reconnect { [weak self] success in
                guard let self, self.revision == token, self.active && self.permitted() else { return }
                self.health.reconnectCompleted(success: success, now: self.now())
                if !success {
                    switch OmiCaptureHealth.Policy.exhaustion {
                    case .keepLink: break // No deliberate disconnect to force firmware flash storage.
                    }
                }
                self.emit()
            }
        case nil: break
        }
    }

    func emit() {
        lastPublishedAt = now()
        lastPhase = health.phase
        publish(health.snapshot(now: lastPublishedAt))
    }

    deinit { timer?.invalidate() }
}

/// The budget write is synchronous and atomic, before any recovery side effect.
/// Unlike a cached preference, a failed write can refuse the radio operation.
enum OmiCaptureHealthStore {
    static func url(_ uuid: String, directory: URL? = nil) -> URL? {
        guard let root = directory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first,
              UUID(uuidString: uuid) != nil else { return nil }
        return root.appendingPathComponent("capture-health").appendingPathComponent(uuid + ".json")
    }

    static func load(_ uuid: String, directory: URL? = nil) -> OmiCaptureHealth.Record {
        guard let url = url(uuid, directory: directory) else { return .init(spent: true, reconnectSpent: true, attemptedAt: Date().timeIntervalSince1970, outcome: "budget_unreadable") }
        do {
            let data = try Data(contentsOf: url)
            return try JSONDecoder().decode(OmiCaptureHealth.Record.self, from: data)
        } catch let error as NSError where error.domain == NSCocoaErrorDomain && error.code == NSFileReadNoSuchFileError {
            return .init()
        } catch {
            // An unreadable budget must not buy another radio operation.
            let record = OmiCaptureHealth.Record(spent: true, reconnectSpent: true,
                attemptedAt: Date().timeIntervalSince1970, outcome: "budget_unreadable")
            _ = save(record, uuid: uuid, directory: directory)
            return record
        }
    }

    static func save(_ record: OmiCaptureHealth.Record, uuid: String, directory: URL? = nil) -> Bool {
        guard let url = url(uuid, directory: directory) else { return false }
        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try JSONEncoder().encode(record).write(to: url, options: .atomic)
            return true
        } catch { return false }
    }
}

/// Owns the reset transaction, including late callbacks after cancellation.
/// The manager supplies radio effects; tests drive these same transition points.
final class OmiCaptureReconnect {
    // CoreBluetooth can reuse a peripheral across connections. An old down
    // callback must not clean up a replacement that is already connected.
    static func acceptsDownCallback(currentOwner: Bool, connected: Bool) -> Bool {
        currentOwner && !connected
    }

    enum Stage { case disconnecting, connecting, subscribing, finished }
    let token = UUID()
    private(set) var stage: Stage = .disconnecting
    private(set) var disconnected = false
    private var completion: ((Bool) -> Void)?
    private let connected: () -> Bool
    private let authorized: () -> Bool
    private let connect: () -> Void
    private let reconcile: (Bool, Bool) -> Void
    private(set) var result: Bool?
    private var resumeCompletion: ((Bool) -> Void)?
    private var resumeRevision = 0

    init(connected: @escaping () -> Bool, authorized: @escaping () -> Bool,
         connect: @escaping () -> Void, reconcile: @escaping (Bool, Bool) -> Void,
         completion: @escaping (Bool) -> Void) {
        self.connected = connected
        self.authorized = authorized
        self.connect = connect
        self.reconcile = reconcile
        self.completion = completion
    }

    func didDisconnect(pairingLost: Bool) {
        let mayConnect = stage == .disconnecting && authorized() && !pairingLost
        disconnected = true
        // Link truth is delivered independently from capture intent.
        reconcile(false, stage != .finished)
        guard mayConnect else { finish(false); return }
        stage = .connecting
        connect()
    }

    func ready(fresh: Bool, subscribe: (@escaping (Bool) -> Void) -> Void) {
        guard stage == .connecting, disconnected, fresh else { return }
        guard authorized() else { finish(false); return }
        stage = .subscribing
        subscribe { [weak self] success in
            guard let self, self.stage == .subscribing else { return }
            self.finish(success && self.authorized())
        }
    }

    func adoptLateConnection(fresh: Bool) -> Bool {
        guard stage == .finished, disconnected, fresh, connected() else { return false }
        // Adopt physical success without rewriting the timed-out result or
        // running a pending Resume's connect effect a second time.
        resumeCompletion = nil
        resumeRevision += 1
        return true
    }

    func finish(_ success: Bool) {
        guard stage != .finished else { reconcile(connected(), false); return }
        stage = .finished
        result = success
        reconcile(connected(), false)
        let done = completion
        completion = nil
        done?(success)
    }
    // Explicit Resume may wait for the old cancellation callback, but only once
    // per request and for a bounded interval. Timeout keeps the tombstone so a
    // late callback cannot buy an automatic reconnect.
    func requestResume(settled: Bool, schedule: (TimeInterval, @escaping () -> Void) -> Void,
                       completion: @escaping (Bool) -> Void) {
        guard stage == .finished, resumeCompletion == nil else { return }
        resumeCompletion = completion
        resumeRevision += 1
        let revision = resumeRevision
        if settled { settleResume(true); return }
        schedule(OmiCaptureHealth.Policy.operationTimeout) { [weak self] in
            guard let self, self.resumeRevision == revision else { return }
            self.settleResume(false)
        }
    }

    func settleResume(_ settled: Bool) {
        let done = resumeCompletion
        resumeCompletion = nil
        done?(settled)
    }
}

/// Only observed storage notifications defer recovery. There is no engine-owned
/// lease to strand: reads, writes and STOP cannot extend this monotonic window.
final class OmiCaptureStorageProgress {
    static let window: TimeInterval = 30
    static let characteristic = "30295781-4301-eabd-2904-2849adfeae43"
    private var lastDataAt: [String: TimeInterval] = [:]

    func received(_ uuid: String, characteristic: String, now: TimeInterval) {
        guard characteristic.lowercased() == Self.characteristic else { return }
        lastDataAt[uuid] = now
    }

    func isActive(_ uuid: String, now: TimeInterval) -> Bool {
        guard let last = lastDataAt[uuid] else { return false }
        return now - last < Self.window
    }
}
