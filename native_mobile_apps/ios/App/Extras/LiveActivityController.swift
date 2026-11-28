@preconcurrency import ActivityKit
import Foundation
import OmiExtras
import os
import UIKit

/// Keeps one Live Activity per kind (a recording, a task Omi works on) in step with what the app
/// wants shown. Updates are throttled for ActivityKit's budget; every operation runs in order.
@MainActor
final class LiveActivityController {
    typealias Kind = OmiActivityAttributes.Kind
    typealias State = OmiActivityAttributes.ContentState

    /// How long a finished run stays on the Lock Screen.
    static let finishedLinger: TimeInterval = 5 * 60
    /// The recording card's exit: Finished fades out, then the system closes the card (Flutter's 0.25 s).
    static let endedLinger: TimeInterval = 0.25
    private static let log = Logger(subsystem: "omi", category: "live-activity")

    private struct Slot {
        var activity: Activity<OmiActivityAttributes>?
        /// What should be shown; nil ends the activity.
        var desired: State?
        /// What the activity shows now.
        var sent: State?
        var throttle = ActivityUpdateThrottle()
        var retry: Task<Void, Never>?
        /// Re-sends a live recording's content before it turns stale (`ContentState.staleDate`).
        var heartbeat: Task<Void, Never>?
        /// The card the user swiped away; it is not brought back for the same recording or run.
        var dismissedID: String?
    }

    /// Only queued operations touch a slot, so a slot never changes across their awaits.
    private var slots: [Kind: Slot] = [.capture: Slot(), .agent: Slot()]
    /// What should be shown per kind; nil ends the activity. Set right away, read by the queue.
    private var desired: [Kind: State] = [:]
    /// How to end: the final content and how long it lingers on the Lock Screen.
    private var endings: [Kind: (state: State, linger: TimeInterval)] = [:]
    private var queue: Task<Void, Never>?
    private var observers: [any NSObjectProtocol] = []

    init() {
        // A card alive at launch belongs to a process that was killed; its recording ended with it.
        enqueue { await Self.endAll() }
        let center = NotificationCenter.default
        // Starting a Live Activity needs the app in front; a recording that began in the
        // background (the Omi reconnecting) gets its card now.
        let active = UIApplication.didBecomeActiveNotification
        let becameActive = center.addObserver(forName: active, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.reconcileAll() }
        }
        observers.append(becameActive)
        observers.append(center.addObserver(forName: UIApplication.willTerminateNotification, object: nil, queue: .main) { _ in
            Self.endAllBeforeTermination()
        })
    }

    /// Shows `state` for `kind`, or ends its activity when nil (immediately).
    func show(_ state: State?, for kind: Kind) {
        guard desired[kind] != state else { return }
        desired[kind] = state
        if state != nil { endings[kind] = nil }
        enqueue { [weak self] in await self?.reconcile(kind) }
    }

    /// Ends `kind` with a last state that stays on the Lock Screen for `linger` seconds.
    func finish(_ kind: Kind, with state: State, linger: TimeInterval) {
        desired[kind] = nil
        endings[kind] = (state, linger)
        enqueue { [weak self] in await self?.reconcile(kind) }
    }

    private func reconcileAll() {
        for kind in slots.keys {
            enqueue { [weak self] in await self?.reconcile(kind) }
        }
    }

    private func enqueue(_ operation: @escaping @MainActor () async -> Void) {
        let previous = queue
        queue = Task { @MainActor in
            await previous?.value
            await operation()
        }
    }

    private func reconcile(_ kind: Kind) async {
        guard var slot = slots[kind] else { return }
        defer { slots[kind] = slot }
        slot.retry?.cancel()
        slot.retry = nil
        if let activity = slot.activity, activity.activityState == .dismissed || activity.activityState == .ended {
            if activity.activityState == .dismissed { slot.dismissedID = slot.sent?.id }
            slot.activity = nil
            slot.sent = nil
        }
        guard let desired = desired[kind] else {
            await end(&slot, ending: endings.removeValue(forKey: kind))
            return
        }
        if let dismissed = slot.dismissedID, dismissed == desired.id { return }
        slot.dismissedID = nil
        guard let activity = slot.activity else {
            start(desired, kind: kind, in: &slot)
            return
        }
        guard desired != slot.sent else { return }
        let urgent = slot.sent.map { !desired.isRoutineChange(from: $0) } ?? true
        switch slot.throttle.decide(urgent: urgent, at: .now) {
        case .send:
            await activity.update(ActivityContent(state: desired, staleDate: desired.staleDate(now: .now)))
            slot.sent = desired
            slot.throttle.didSend(at: .now)
            scheduleHeartbeat(kind, in: &slot)
        case let .wait(delay):
            slot.retry = Task { @MainActor [weak self] in
                try? await Task.sleep(for: .seconds(delay))
                guard !Task.isCancelled else { return }
                self?.enqueue { [weak self] in await self?.reconcile(kind) }
            }
        }
    }

    private func start(_ state: State, kind: Kind, in slot: inout Slot) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled, UIApplication.shared.applicationState == .active else { return }
        // A finished run still lingering makes way for the new one.
        for stale in Activity<OmiActivityAttributes>.activities where stale.attributes.kind == kind {
            Task { await stale.end(nil, dismissalPolicy: .immediate) }
        }
        do {
            slot.activity = try Activity.request(
                attributes: OmiActivityAttributes(kind: kind),
                content: ActivityContent(state: state, staleDate: state.staleDate(now: .now)),
                pushType: nil
            )
            slot.sent = state
            slot.throttle.didSend(at: .now)
            scheduleHeartbeat(kind, in: &slot)
        } catch {
            Self.log.error("Live Activity unavailable: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// While the content can go stale, re-send it before it does: the card turns stale (and says to
    /// open Omi) only once Omi stopped refreshing it.
    private func scheduleHeartbeat(_ kind: Kind, in slot: inout Slot) {
        slot.heartbeat?.cancel()
        slot.heartbeat = nil
        guard slot.sent?.staleDate(now: .now) != nil else { return }
        slot.heartbeat = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(State.heartbeat))
            guard !Task.isCancelled else { return }
            self?.enqueue { [weak self] in await self?.refresh(kind) }
        }
    }

    private func refresh(_ kind: Kind) async {
        guard var slot = slots[kind] else { return }
        defer { slots[kind] = slot }
        guard let activity = slot.activity, activity.activityState == .active, let sent = slot.sent else { return }
        await activity.update(ActivityContent(state: sent, staleDate: sent.staleDate(now: .now)))
        scheduleHeartbeat(kind, in: &slot)
    }

    private func end(_ slot: inout Slot, ending: (state: State, linger: TimeInterval)?) async {
        defer {
            slot.heartbeat?.cancel()
            slot.heartbeat = nil
            slot.activity = nil
            slot.sent = nil
            slot.throttle.reset()
        }
        guard let activity = slot.activity else { return }
        if let (state, linger) = ending {
            await activity.end(ActivityContent(state: state, staleDate: nil), dismissalPolicy: .after(.now.addingTimeInterval(linger)))
        } else {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
    }

    private static func endAll() async {
        for activity in Activity<OmiActivityAttributes>.activities {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
    }

    /// Nothing will update the cards after termination; close them now (termination waits briefly).
    private nonisolated static func endAllBeforeTermination() {
        let done = DispatchSemaphore(value: 0)
        Task.detached {
            await endAll()
            done.signal()
        }
        _ = done.wait(timeout: .now() + 2)
    }
}
