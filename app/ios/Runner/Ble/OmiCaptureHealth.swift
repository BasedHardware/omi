import Foundation

/// Ingress evidence, not a durability claim. The native owner survives Flutter
/// stalls, but no timer can execute while iOS has suspended or killed this process.
final class OmiCaptureHealth {
    enum Action { case repairSubscription, reconnect }
    enum ExhaustionPolicy { case keepLink }
    enum Phase: String { case inactive, unverified, flowing, repairing, reconnecting, quiet, actionRequired }

    enum Policy {
        static let evidenceLifetime: TimeInterval = 30
        static let repairGrace: TimeInterval = 10
        static let operationTimeout: TimeInterval = 15
        static let reconnectTimeout: TimeInterval = 45
        static let stableAudioToRearm: TimeInterval = 60
        static let minimumRecoveryInterval: TimeInterval = 6 * 60 * 60
        static let exhaustion: ExhaustionPolicy = .keepLink
        static let silenceAfterFreshSubscriptionIsFailure = false
        // One subscription repair and at most ONE physical reconnect per episode.
        // A quiet room cannot replenish this budget, even across launches. Only
        // 60s of continuous audio AND six hours since the last attempt can rearm
        // it. This deliberately trades fast repeated repair for battery life.
    }

    struct Record: Codable {
        var spent = false
        var reconnectSpent = false
        var attemptedAt: TimeInterval?
        var unverifiedSince: TimeInterval?
        var outcome = "none"
    }

    private(set) var record: Record
    private(set) var phase: Phase = .inactive
    private(set) var generation = UUID().uuidString
    private(set) var subscriptionConfirmed = false
    private(set) var lastAudioAt: TimeInterval?
    private(set) var reason = "inactive"
    private var authorized = false
    private var connected = false
    private var fresh = false
    private var hadAudio = false
    private var deadline: TimeInterval?
    private var stableSince: TimeInterval?
    private let persist: (Record) -> Bool

    init(record: Record = Record(), persist: @escaping (Record) -> Bool) {
        self.record = record
        self.persist = persist
    }

    func authorize(_ value: Bool, now: TimeInterval) {
        guard authorized != value else { return }
        authorized = value
        lastAudioAt = nil
        stableSince = nil
        if value {
            unverify("capture_authorized", now: now)
            // Relaunching a restored link cannot buy another full grace period.
            deadline = (fresh ? now : record.unverifiedSince ?? now) + Policy.evidenceLifetime
        } else {
            phase = .inactive
            reason = "capture_denied"
            deadline = nil
            record.unverifiedSince = nil
            _ = persist(record)
        }
    }

    func ready(fresh: Bool, now: TimeInterval) {
        // Readiness replay can never replay evidence or extend a recovery deadline.
        let previousPhase = phase
        let previousDeadline = deadline
        generation = UUID().uuidString
        connected = true
        self.fresh = fresh
        subscriptionConfirmed = false
        lastAudioAt = nil
        stableSince = nil
        hadAudio = false
        if authorized {
            unverify(fresh ? "fresh_link" : "restored_or_replayed", now: now)
            deadline = fresh ? now + Policy.evidenceLifetime : previousDeadline ?? now + Policy.evidenceLifetime
            if !fresh && (previousPhase == .repairing || previousPhase == .reconnecting) {
                phase = previousPhase
            }
        }
    }

    func subscribed(_ confirmed: Bool, now: TimeInterval) {
        subscriptionConfirmed = confirmed
        guard phase != .actionRequired else { return }
        if confirmed && fresh && record.spent && phase != .repairing && phase != .reconnecting {
            record.outcome = "fresh_subscription_confirmed"
            _ = persist(record)
        }
        if !confirmed {
            lastAudioAt = nil
            stableSince = nil
            if authorized && phase != .reconnecting && phase != .repairing {
                unverify("subscription_failed", now: now)
                deadline = now
            }
        }
    }

    func audio(now: TimeInterval) {
        guard authorized, connected, subscriptionConfirmed, phase != .reconnecting else { return }
        if let previous = lastAudioAt, now - previous > Policy.evidenceLifetime { stableSince = nil }
        stableSince = stableSince ?? now
        lastAudioAt = now
        hadAudio = true
        phase = .flowing
        reason = "audio_observed"
        deadline = now + Policy.evidenceLifetime
        if record.unverifiedSince != nil {
            record.unverifiedSince = nil
            record.outcome = "audio_observed"
            _ = persist(record)
        }
        if record.spent, let start = stableSince, let attempt = record.attemptedAt,
           now - start >= Policy.stableAudioToRearm, now - attempt >= Policy.minimumRecoveryInterval {
            var next = record
            next.spent = false
            next.reconnectSpent = false
            if persist(next) { record = next }
        }
    }

    func disconnected(recovering: Bool, now: TimeInterval) {
        connected = false
        subscriptionConfirmed = false
        lastAudioAt = nil
        stableSince = nil
        // A terminal recovery result survives late radio callbacks. Only a
        // new authorized attempt/readiness or real audio can supersede it.
        if authorized && phase != .actionRequired {
            unverify("disconnected", now: now)
            if recovering { phase = .reconnecting }
        }
        deadline = nil
    }

    func tick(now: TimeInterval) -> Action? {
        guard authorized, connected, let deadline, now >= deadline else { return nil }
        self.deadline = nil
        if phase == .repairing {
            return reserveReconnect(now: now)
        }
        if phase == .reconnecting || phase == .actionRequired { return nil }
        unverify("audio_evidence_expired", now: now)
        if subscriptionConfirmed && fresh && !hadAudio && !Policy.silenceAfterFreshSubscriptionIsFailure {
            phase = .quiet
            reason = "fresh_subscription_quiet"
            return nil
        }
        if record.spent {
            if !record.reconnectSpent { return reserveReconnect(now: now) }
            let recoveryCompleted = record.outcome == "fresh_subscription_confirmed" || record.outcome == "audio_observed"
            phase = subscriptionConfirmed && recoveryCompleted ? .quiet : .actionRequired
            reason = phase == .quiet ? "budget_spent_quiet" : "recovery_incomplete_budget_spent"
            return nil
        }
        var next = record
        next.spent = true
        next.attemptedAt = now
        next.outcome = "repair_subscription"
        // Reserve durably BEFORE any radio effect. A failed write fails closed.
        guard persist(next) else {
            phase = .actionRequired
            reason = "recovery_budget_write_failed"
            return nil
        }
        record = next
        phase = .repairing
        reason = "repair_subscription"
        self.deadline = now + 2 * Policy.operationTimeout + Policy.repairGrace
        return .repairSubscription
    }

    private func reserveReconnect(now: TimeInterval) -> Action? {
        var next = record
        next.reconnectSpent = true
        next.outcome = "fresh_connection_requested"
        guard persist(next) else {
            recoveryFailed("recovery_budget_write_failed", now: now)
            return nil
        }
        record = next
        phase = .reconnecting
        reason = next.outcome
        return .reconnect
    }

    func reconnectCompleted(success: Bool, now: TimeInterval) {
        guard authorized else { return }
        if success {
            record.outcome = "fresh_subscription_confirmed"
            _ = persist(record)
        } else {
            recoveryFailed("fresh_connection_failed", now: now)
        }
    }

    func repairCompleted(success: Bool, now: TimeInterval) {
        guard authorized, phase == .repairing else { return }
        subscriptionConfirmed = success
        reason = success ? "repair_confirmed" : "repair_failed"
        deadline = success ? now + Policy.repairGrace : now
    }

    func recoveryFailed(_ reason: String, now: TimeInterval) {
        guard authorized else { return }
        unverify(reason, now: now)
        phase = .actionRequired
        deadline = nil
        record.outcome = reason
        _ = persist(record)
    }

    func snapshot(now: TimeInterval) -> [String: Any] {
        [
            "phase": phase.rawValue, "generation": generation, "reason": reason,
            "observed_at_ms": Int64(now * 1000),
            "last_audio_at_ms": lastAudioAt.map { Int64($0 * 1000) } ?? 0,
            "valid_until_ms": lastAudioAt.map { Int64(($0 + Policy.evidenceLifetime) * 1000) } ?? 0,
            "unverified_since_ms": record.unverifiedSince.map { Int64($0 * 1000) } ?? 0,
            "subscription_confirmed": subscriptionConfirmed, "recovery_spent": record.spent,
            "recovery_outcome": record.outcome, "reconnect_spent": record.reconnectSpent,
            "keep_link_after_exhaustion": Policy.exhaustion == .keepLink,
        ]
    }

    private func unverify(_ reason: String, now: TimeInterval) {
        phase = .unverified
        self.reason = reason
        if record.unverifiedSince == nil {
            record.unverifiedSince = now
            _ = persist(record)
        }
    }
}
