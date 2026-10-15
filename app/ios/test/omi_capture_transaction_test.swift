import Foundation

@main
struct CaptureTransactionTest {
    static func main() throws {
        precondition(!OmiCaptureReconnect.acceptsDownCallback(currentOwner: false, connected: false))
        precondition(!OmiCaptureReconnect.acceptsDownCallback(currentOwner: true, connected: true))
        precondition(OmiCaptureReconnect.acceptsDownCallback(currentOwner: true, connected: false))
        for scenario in ["cancel_before_disconnect", "cancel_during_connect", "failed_connect"] {
            var connected = true
            var authorized = true
            var connects = 0
            var outcomes: [Bool] = []
            var reconciled: [Bool] = []
            let transaction = OmiCaptureReconnect(
                connected: { connected }, authorized: { authorized },
                connect: { connects += 1 }, reconcile: { connected, _ in reconciled.append(connected) },
                completion: { outcomes.append($0) })
            connected = false // cancelPeripheralConnection changes actual link state
            if scenario == "cancel_before_disconnect" {
                authorized = false
                transaction.finish(false)
            }
            transaction.didDisconnect(pairingLost: false)
            precondition(connects == (scenario == "cancel_before_disconnect" ? 0 : 1))
            if scenario == "cancel_during_connect" { authorized = false }
            transaction.finish(false)
            precondition(outcomes == [false] && reconciled.last == false)
            var subscriptions = 0
            transaction.ready(fresh: true) { _ in subscriptions += 1 }
            precondition(subscriptions == 0)
        }

        // A stale subscription completion must not complete a replacement.
        var oldDone: ((Bool) -> Void)?
        var connected = false
        var oldOutcomes: [Bool] = []
        let old = OmiCaptureReconnect(connected: { connected }, authorized: { true },
            connect: {}, reconcile: { _, _ in }, completion: { oldOutcomes.append($0) })
        old.didDisconnect(pairingLost: false)
        connected = true
        old.ready(fresh: true) { oldDone = $0 }
        old.finish(false)
        var currentOutcomes: [Bool] = []
        let current = OmiCaptureReconnect(connected: { connected }, authorized: { true },
            connect: {}, reconcile: { _, _ in }, completion: { currentOutcomes.append($0) })
        oldDone?(true)
        precondition(oldOutcomes == [false] && currentOutcomes.isEmpty)
        current.didDisconnect(pairingLost: false)
        current.ready(fresh: false) { _ in preconditionFailure("cached services are not reset readiness") }
        current.ready(fresh: true) { $0(true) }
        precondition(currentOutcomes == [true])
        connected = false
        current.didDisconnect(pairingLost: false)
        current.finish(false)
        precondition(current.result == true && currentOutcomes == [true])

        // Compose the exact session/transaction wiring used by the manager:
        // timeout -> late radio callback must retain terminal health and never
        // issue another connect. Resume has its own bounded settlement.
        for lateFailure in [false, true] {
            var time: Double = 0
            var radioConnected = true
            var connects = 0
            var downs = 0
            var deliveries: [String] = []
            var transaction: OmiCaptureReconnect?
            var session: OmiBleCaptureSession!
            let health = OmiCaptureHealth(persist: { _ in true })
            session = OmiBleCaptureSession(health: health, now: { time }, permitted: { true },
                repair: { $0(false) },
                reconnect: { done in
                    transaction = session.reconnectTransaction(connected: { radioConnected },
                        connect: { connects += 1 },
                        reportLink: { if !$0 { downs += 1; deliveries.append("disconnected") } }, completion: done)
                }, publish: { deliveries.append("health:" + ($0["phase"] as! String)) })
            session.ready(fresh: false)
            session.authorize(true)
            time = 30
            session.tick()
            session.tick()
            let reset = transaction!
            precondition(health.phase == .reconnecting)
            // Simulate the manager's 45-second reset deadline before any down callback.
            time += OmiCaptureHealth.Policy.reconnectTimeout
            reset.finish(false)
            precondition(reset.result == false && health.phase == .actionRequired)
            let reason = health.reason
            var expiry: (() -> Void)?
            var resumes: [Bool] = []
            reset.requestResume(settled: false, schedule: { delay, task in
                precondition(delay == OmiCaptureHealth.Policy.operationTimeout)
                expiry = task
            }, completion: { resumes.append($0) })
            expiry?() // no callback: Resume must settle, retaining the tombstone
            precondition(resumes == [false] && reset.stage == .finished)
            radioConnected = false
            session.subscribed(false) // manager cleanup settles outstanding CCCD requests
            if lateFailure { reset.finish(false) }
            else { reset.didDisconnect(pairingLost: false) }
            reset.settleResume(true)
            precondition(deliveries.last == "health:actionRequired")
            session.tick()
            precondition(health.phase == .actionRequired && health.reason == reason)
            precondition(reset.result == false && connects == 0 && downs > 0 && resumes == [false])

            // A new explicit request can settle and establish a real connection.
            reset.requestResume(settled: true, schedule: { _, _ in preconditionFailure("already down") }) {
                precondition($0)
                connects += 1
            }
            precondition(connects == 1)
            session.authorize(false)
        }

        // A connection can succeed after its reset deadline. Drive the same
        // readiness/adoption decision as the manager, not a copied condition.
        do {
            var time: Double = 0
            var radioConnected = true
            var connects = 0
            var outcomes: [Bool] = []
            var transaction: OmiCaptureReconnect?
            var session: OmiBleCaptureSession!
            let health = OmiCaptureHealth(persist: { _ in true })
            session = OmiBleCaptureSession(health: health, now: { time }, permitted: { true },
                repair: { $0(false) },
                reconnect: { done in
                    transaction = session.reconnectTransaction(connected: { radioConnected },
                        connect: { connects += 1 }, reportLink: { _ in },
                        completion: { outcomes.append($0); done($0) })
                }, publish: { _ in })
            session.ready(fresh: false)
            session.authorize(true)
            time = 30
            session.tick()
            session.tick()
            let reset = transaction!
            radioConnected = false
            reset.didDisconnect(pairingLost: false)
            precondition(connects == 1 && reset.stage == .connecting)
            time += OmiCaptureHealth.Policy.reconnectTimeout
            reset.finish(false)
            precondition(health.phase == .actionRequired && outcomes == [false])
            let attemptedAt = health.record.attemptedAt
            let generation = health.generation
            var resumeExpiry: (() -> Void)?
            var resumeEffects = 0
            reset.requestResume(settled: false, schedule: { _, task in resumeExpiry = task }) { _ in
                resumeEffects += 1
            }
            // Cached replay cannot settle the failed transaction.
            precondition(!session.ready(fresh: false, recovery: transaction))
            precondition(health.phase == .actionRequired)
            radioConnected = true
            if session.ready(fresh: true, recovery: transaction) { transaction = nil }
            precondition(transaction == nil && health.phase == .unverified)
            precondition(health.generation != generation)
            session.audio() // readiness alone is not audio-path proof
            precondition(health.phase == .unverified)
            session.subscribed(true)
            session.audio()
            precondition(health.phase == .flowing && health.lastAudioAt == time)
            precondition(health.snapshot(now: time)["phase"] as? String == "flowing")
            precondition(health.record.spent && health.record.reconnectSpent)
            precondition(health.record.attemptedAt == attemptedAt)
            resumeExpiry?()
            reset.finish(true)
            precondition(reset.result == false && outcomes == [false])
            precondition(resumeEffects == 0 && connects == 1)
            time += 1
            session.tick()
            precondition(health.phase == .flowing && connects == 1)
            session.authorize(false)
        }

        // Resume pending when a late callback arrives settles exactly once.
        var settlementExpiry: (() -> Void)?
        var resumeResults: [Bool] = []
        old.requestResume(settled: false, schedule: { _, task in settlementExpiry = task }) { resumeResults.append($0) }
        old.didDisconnect(pairingLost: false)
        old.settleResume(true)
        settlementExpiry?()
        precondition(resumeResults == [true] && old.result == false)

        // Native storage progress survives session/engine replacement and
        // expires even if Dart stalls on INFO, READ or STOP forever.
        let progress = OmiCaptureStorageProgress()
        var time: Double = 0
        var effects = 0
        func makeSession() -> OmiBleCaptureSession {
            let session = OmiBleCaptureSession(health: OmiCaptureHealth(persist: { _ in true }),
                now: { time }, permitted: { true },
                linkAvailable: { !progress.isActive("pendant", now: time) },
                repair: { _ in effects += 1 }, reconnect: { _ in effects += 1 }, publish: { _ in })
            session.ready(fresh: false)
            session.authorize(true)
            session.subscribed(true)
            return session
        }
        var session = makeSession()
        for moment in [20.0, 49.0, 78.0] {
            time = moment
            progress.received("pendant", characteristic: OmiCaptureStorageProgress.characteristic, now: time)
            time += 1
            session.tick()
        }
        precondition(effects == 0 && !session.health.record.spent)
        session.authorize(false)
        session = makeSession() // replacing Flutter does not clear native progress
        time = 90
        session.tick()
        precondition(effects == 0)
        progress.received("pendant", characteristic: "read-control", now: time)
        progress.received("other-device", characteristic: OmiCaptureStorageProgress.characteristic, now: time)
        time = 120
        session.tick()
        precondition(effects == 1 && session.health.record.spent)
        session.authorize(false)
        // No storage notification at all cannot strand recovery either.
        effects = 0
        session = makeSession()
        time += 30
        session.tick()
        precondition(effects == 1)
        session.authorize(false)

        // Produce the trace consumed by the Dart bridge/transport regression.
        // These are actual policy and transaction outputs, not a copied model.
        var trace: [[String: Any]] = []
        var record = OmiCaptureHealth.Record()
        var radioConnected = true
        var generation = 0
        time = 0
        for launch in 0..<4 {
            trace.append(["event": "launch"])
            let health = OmiCaptureHealth(record: record) { record = $0; return true }
            var session: OmiBleCaptureSession!
            session = OmiBleCaptureSession(health: health, now: { time }, permitted: { true },
                repair: { done in trace.append(["event": "repair"]); done(true) },
                reconnect: { done in
                    trace.append(["event": "disconnect_requested"])
                    let reset = OmiCaptureReconnect(connected: { radioConnected }, authorized: { true },
                        connect: { trace.append(["event": "connect"]) },
                        reconcile: { connected, _ in
                            if !connected { trace.append(["event": "disconnected"]) }
                        }, completion: done)
                    radioConnected = false
                    reset.didDisconnect(pairingLost: false)
                    session.disconnected(recovering: true)
                    radioConnected = true
                    generation += 1
                    trace.append(["event": "ready"])
                    session.ready(fresh: true)
                    reset.ready(fresh: true) { subscribed in
                        session.subscribed(true)
                        subscribed(true)
                    }
                },
                publish: { snapshot in
                    var stable = snapshot
                    stable["generation"] = "connection-\(generation)"
                    trace.append(["event": "health", "snapshot": stable])
                })
            generation += 1
            trace.append(["event": "ready"])
            session.ready(fresh: false)
            session.authorize(true)
            session.subscribed(true)
            trace.append(["event": "read"]) // cached services and working reads
            time += 30
            session.tick()
            if launch == 1 { time += 30; session.tick() }
            // Simulate process death, not a user stop. Do not clear the persisted interval.
            session = nil
        }
        let data = try JSONSerialization.data(withJSONObject: trace, options: [.sortedKeys])
        print(String(data: data, encoding: .utf8)!)
    }
}
