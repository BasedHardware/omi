import ActivityKit
import Flutter
import UIKit

@available(iOS 16.1, *)
@MainActor
final class LiveActivityManager {
    private let channel: FlutterMethodChannel
    private var ready = false
    private var ownerId: String?
    private var enabled = true
    private var latest: (String, OmiCaptureAttributes.ContentState, Bool)?
    private var activity: Activity<OmiCaptureAttributes>?
    private var suppressedRecordingId: String?
    /// Cards swiped away stay away for that recording and that kind of card.
    private var dismissedCards: Set<String> = []
    /// Actions whose intent is still waiting for Flutter's reply. The card that owns the tapped
    /// button stays until the reply, even when the action makes capture healthy again.
    private var actionsInFlight = 0
    /// When the latest recording entered its current status; connecting and unverified
    /// count as one, since both mean the pendant has not been heard yet.
    private var statusClock: (id: String, status: String, since: Date)?
    private var delivery: Task<Void, Never>?
    private var foregroundObserver: NSObjectProtocol?

    init(messenger: FlutterBinaryMessenger) {
        channel = FlutterMethodChannel(name: "com.omi.ios/liveActivity", binaryMessenger: messenger)
        enabled = UserDefaults.standard.object(forKey: "omi.captureLiveActivityEnabled") as? Bool ?? true
        channel.setMethodCallHandler { [weak self] call, result in
            Task { @MainActor in self?.handle(call, result: result) }
        }
        foregroundObserver = NotificationCenter.default.addObserver(
            forName: UIApplication.didBecomeActiveNotification, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.enqueue { [weak self] in await self?.reconcile() }
            }
        }
        // A card alive at launch was left by a process that was killed or crashed. Its
        // recording died with it (ids are never reused), so it closes before anything else.
        enqueue { [weak self] in await self?.endAll(immediate: true) }
    }

    /// The app is terminating, so nothing will update the card again: close it and the
    /// island now instead of leaving them to go stale. Termination waits briefly for it.
    nonisolated static func endAllBeforeTermination() {
        let done = DispatchSemaphore(value: 0)
        Task.detached {
            for activity in Activity<OmiCaptureAttributes>.activities {
                if #available(iOS 16.2, *) {
                    await activity.end(nil, dismissalPolicy: .immediate)
                } else {
                    await activity.end(using: nil, dismissalPolicy: .immediate)
                }
            }
            done.signal()
        }
        _ = done.wait(timeout: .now() + 2)
    }

    private func enqueue(_ operation: @escaping @MainActor () async -> Void) {
        let previous = delivery
        delivery = Task { @MainActor in
            await previous?.value
            await operation()
        }
    }

    private func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "ready":
            guard let owner = call.arguments as? String, !owner.isEmpty else {
                result(FlutterError(code: "invalid", message: "Missing capture owner", details: nil)); return
            }
            enqueue { [weak self] in
                guard let self else { result(nil); return }
                self.ownerId = owner
                self.latest = nil
                self.ready = true
                if #available(iOS 17.0, *) {
                    OmiCaptureActionDispatcher.handler = { [weak self] id, revision, action in
                        guard let self else { throw CaptureActionError.unavailable }
                        try await self.perform(id: id, revision: revision, action: action)
                    }
                }
                result(nil)
            }
        case "availability":
            result(["supported": true, "authorized": ActivityAuthorizationInfo().areActivitiesEnabled])
        case "setEnabled":
            guard let value = call.arguments as? Bool else {
                result(FlutterError(code: "invalid", message: "Expected enabled preference", details: nil)); return
            }
            enqueue { [weak self] in
                guard let self else { result(nil); return }
                self.enabled = value
                try? SafeDefaults.store(.bool(value), forKey: "omi.captureLiveActivityEnabled")
                if value { self.suppressedRecordingId = nil }
                await self.reconcile()
                result(nil)
            }
        case "publish":
            guard let values = call.arguments as? [String: Any],
                  let id = values["recordingId"] as? String,
                  let active = values["active"] as? Bool,
                  let enabled = values["enabled"] as? Bool,
                  let owner = values["ownerId"] as? String else {
                result(FlutterError(code: "invalid", message: "Invalid capture snapshot", details: nil)); return
            }
            do {
                let data = try SafeJSON.data(withJSONObject: values)
                let state = try JSONDecoder().decode(OmiCaptureAttributes.ContentState.self, from: data)
                guard state.startedAt.isFinite, state.elapsed >= 0 else { throw CaptureActionError.unavailable }
                enqueue { [weak self] in
                    guard let self else { result(nil); return }
                    guard self.ownerId == owner else { result(nil); return }
                    self.enabled = enabled
                    self.latest = (id, state, active)
                    await self.reconcile()
                    result(nil)
                }
            } catch {
                result(FlutterError(code: "invalid", message: "Invalid capture state", details: nil))
            }
        case "detach":
            guard let owner = call.arguments as? String, ownerId == owner else { result(nil); return }
            ready = false
            if #available(iOS 17.0, *) { OmiCaptureActionDispatcher.handler = nil }
            enqueue { [weak self] in
                guard let self, self.ownerId == owner else { result(nil); return }
                await self.endAll(immediate: true)
                self.latest = nil
                self.ownerId = nil
                result(nil)
            }
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    private func reconcile() async {
        // Whether this process records is known only from the owner's snapshot; wait for it.
        guard ready, let (id, published, active) = latest else { return }
        if let current = activity, current.activityState == .dismissed {
            dismissedCards.insert(Self.cardKey(current.attributes.recordingId, current.contentState.notice))
            activity = nil
        }
        guard enabled, active, !id.isEmpty, ActivityAuthorizationInfo().areActivitiesEnabled else {
            await endAll(immediate: !enabled)
            return
        }
        if let suppressedRecordingId, suppressedRecordingId != id { self.suppressedRecordingId = nil }
        dismissedCards = dismissedCards.filter { $0.hasPrefix(id + "|") }
        // Healthy pendant capture is the default and shows nothing; see CapturePresentationPolicy.
        let since = statusSince(id: id, status: published.status)
        let battery = Self.pendantBattery()
        var state = published
        switch CapturePresentationPolicy.decide(status: state.status, source: state.source,
                                                statusAge: Date().timeIntervalSince(since), battery: battery) {
        case .hidden:
            // perform() reconciles again once the tapped intent has its reply.
            if actionsInFlight == 0 { await endAll(immediate: true) }
            return
        case .recording:
            state.notice = nil
        case .notice(let notice):
            state.notice = notice.rawValue
            state.noticeSince = since.timeIntervalSince1970
            state.pendantBattery = battery
        }
        let card = Self.cardKey(id, state.notice)
        if let current = activity, current.contentState.notice != state.notice {
            // A different kind of card is a new card, so a swipe on one never hides another.
            await end(current, immediate: true)
            activity = nil
        }
        for existing in Activity<OmiCaptureAttributes>.activities {
            if existing.attributes.recordingId != id {
                await end(existing, immediate: true)
            } else if activity == nil && existing.activityState != .ended && existing.activityState != .dismissed
                        && existing.contentState.notice == state.notice {
                activity = existing
            } else if existing.id != activity?.id {
                await end(existing, immediate: true)
            }
        }
        if let current = activity,
           current.attributes.recordingId != id || current.activityState == .ended {
            await end(current, immediate: true)
            activity = nil
        }
        if let activity {
            await update(activity, state: state)
        } else if suppressedRecordingId != id && !dismissedCards.contains(card)
                    && UIApplication.shared.applicationState == .active {
            do {
                if #available(iOS 16.2, *) {
                    activity = try Activity.request(attributes: OmiCaptureAttributes(recordingId: id),
                        content: ActivityContent(state: state, staleDate: Self.staleDate(for: state)), pushType: nil)
                } else {
                    activity = try Activity.request(attributes: OmiCaptureAttributes(recordingId: id),
                        contentState: state, pushType: nil)
                }
            } catch {
                NSLog("[LiveActivity] Start unavailable: %@", String(describing: error))
            }
        }
    }

    private func statusSince(id: String, status: String) -> Date {
        let group = ["connecting", "unverified"].contains(status) ? "unheard" : status
        if let clock = statusClock, clock.id == id, clock.status == group { return clock.since }
        let now = Date()
        statusClock = (id, group, now)
        return now
    }

    private static func cardKey(_ id: String, _ notice: String?) -> String { "\(id)|\(notice ?? "recording")" }

    /// The pendant battery the Home Screen widget shows (AppDelegate's battery channel), when the
    /// pendant is connected and not charging. Only Omi pendants report charging, so other
    /// wearables never show this card. Unknown readings are -1.
    private static func pendantBattery() -> Int? {
        guard let defaults = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12"),
              defaults.string(forKey: "widget_device_type") == "omi",
              defaults.bool(forKey: "widget_is_connected"), !defaults.bool(forKey: "widget_is_charging"),
              let level = defaults.object(forKey: "widget_battery_level") as? Int, level >= 0 else { return nil }
        return level
    }

    /// A live card goes stale when Omi stops refreshing it. A stopped one does not: iOS may suspend
    /// Omi while the mic is off, and Start must stay on the card. If Omi is killed meanwhile, its
    /// next launch, including one from a tap on this card, closes the card.
    private static func staleDate(for state: OmiCaptureAttributes.ContentState) -> Date? {
        state.status == "paused" ? nil : Date().addingTimeInterval(90)
    }

    private func update(_ activity: Activity<OmiCaptureAttributes>, state: OmiCaptureAttributes.ContentState) async {
        if #available(iOS 16.2, *) {
            await activity.update(ActivityContent(state: state, staleDate: Self.staleDate(for: state)))
        } else {
            await activity.update(using: state)
        }
    }

    private func end(_ activity: Activity<OmiCaptureAttributes>, immediate: Bool) async {
        guard activity.activityState != .dismissed,
              immediate || activity.activityState != .ended else { return }
        var final = activity.contentState
        if !final.paused && final.status != "ended" {
            let elapsed = CheckedIntegerConversion.int(Date().timeIntervalSince1970 - final.startedAt)
            final.elapsed = max(0, elapsed ?? final.elapsed)
        }
        final.status = "ended"
        final.busy = false
        final.canPause = false
        final.canFinish = false
        // Give the finished content a brief fade before the OS closes it. This
        // happens after capture ends; disabling the feature still dismisses at once.
        let policy: ActivityUIDismissalPolicy = immediate ? .immediate : .after(Date().addingTimeInterval(0.25))
        if #available(iOS 16.2, *) {
            await activity.end(ActivityContent(state: final, staleDate: nil), dismissalPolicy: policy)
        } else {
            await activity.end(using: final, dismissalPolicy: policy)
        }
    }

    private func endAll(immediate: Bool) async {
        for item in Activity<OmiCaptureAttributes>.activities { await end(item, immediate: immediate) }
        activity = nil
    }

    private func perform(id: String, revision: Int, action: String) async throws {
        guard ready, enabled, let (current, state, active) = latest,
              active, current == id, state.conversationRevision == revision else {
            throw CaptureActionError.unavailable
        }
        // End with nothing to save only closes the card; the recording is not touched.
        if action == "close" {
            closeCard(for: id)
            return
        }
        let backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "Omi recording action")
        actionsInFlight += 1
        defer {
            actionsInFlight -= 1
            enqueue { [weak self] in await self?.reconcile() }
            if backgroundTask != .invalid { UIApplication.shared.endBackgroundTask(backgroundTask) }
        }
        do {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                // Fails the tap if Flutter never answers; cancelled by the reply.
                let reply = CaptureIntentReply(continuation, timeoutNanoseconds: 20_000_000_000)
                channel.invokeMethod("action", arguments: [
                    "recordingId": id, "conversationRevision": revision,
                    "action": action
                ]) { result in
                    Task { @MainActor in
                        if result is FlutterError || (result as AnyObject?) === FlutterMethodNotImplemented || result == nil {
                            reply.finish(CaptureActionError.unavailable)
                        } else {
                            reply.finish(nil)
                        }
                    }
                }
            }
        } catch {
            enqueue { [weak self] in
                guard let self, let (current, state, active) = self.latest, current == id,
                      state.conversationRevision == revision else { return }
                var failed = state
                failed.actionFailed = true
                failed.busy = false
                self.latest = (current, failed, active)
                await self.reconcile()
            }
            throw error
        }
        if action == "finish" { closeCard(for: id) }
    }

    /// End closes the card after its brief exit transition. A pendant keeps listening, so the
    /// card stays closed for the rest of this recording, as when it is swiped away.
    private func closeCard(for id: String) {
        enqueue { [weak self] in
            guard let self else { return }
            self.suppressedRecordingId = id
            if let current = self.activity, current.attributes.recordingId == id {
                await self.end(current, immediate: false)
                self.activity = nil
            }
        }
    }
}

/// Resumes an action's continuation exactly once: with Flutter's reply, or
/// with a failure when the timeout fires first. The first to arrive cancels
/// the other. The timer holds the reply strongly so a missing Flutter reply
/// can never leave the continuation (and the tapped button) waiting forever.
@MainActor
private final class CaptureIntentReply {
    private var continuation: CheckedContinuation<Void, Error>?
    private var timeout: Task<Void, Never>?

    init(_ continuation: CheckedContinuation<Void, Error>, timeoutNanoseconds: UInt64) {
        self.continuation = continuation
        timeout = Task { @MainActor in
            try? await Task.sleep(nanoseconds: timeoutNanoseconds)
            guard !Task.isCancelled else { return }
            self.finish(CaptureActionError.unavailable)
        }
    }

    func finish(_ error: Error?) {
        guard let continuation else { return }
        self.continuation = nil
        timeout?.cancel()
        timeout = nil
        if let error { continuation.resume(throwing: error) } else { continuation.resume() }
    }
}
