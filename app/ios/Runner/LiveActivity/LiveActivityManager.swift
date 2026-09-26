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
                UserDefaults.standard.set(value, forKey: "omi.captureLiveActivityEnabled")
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
                let data = try JSONSerialization.data(withJSONObject: values)
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
        // A launch is not proof that capture ended. Wait for the owner snapshot.
        guard ready, let (id, state, active) = latest else { return }
        if let current = activity, current.activityState == .dismissed {
            suppressedRecordingId = current.attributes.recordingId
            activity = nil
        }
        guard enabled, active, !id.isEmpty, ActivityAuthorizationInfo().areActivitiesEnabled else {
            await endAll(immediate: !enabled)
            return
        }
        if let suppressedRecordingId, suppressedRecordingId != id { self.suppressedRecordingId = nil }
        for existing in Activity<OmiCaptureAttributes>.activities {
            if existing.attributes.recordingId != id {
                await end(existing, immediate: true)
            } else if activity == nil && existing.activityState != .ended && existing.activityState != .dismissed {
                activity = existing
            } else if let activity, existing.id != activity.id {
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
        } else if suppressedRecordingId != id && UIApplication.shared.applicationState == .active {
            do {
                if #available(iOS 16.2, *) {
                    activity = try Activity.request(attributes: OmiCaptureAttributes(recordingId: id),
                        content: ActivityContent(state: state, staleDate: Date().addingTimeInterval(90)), pushType: nil)
                } else {
                    activity = try Activity.request(attributes: OmiCaptureAttributes(recordingId: id),
                        contentState: state, pushType: nil)
                }
            } catch {
                NSLog("[LiveActivity] Start unavailable: %@", String(describing: error))
            }
        }
    }

    private func update(_ activity: Activity<OmiCaptureAttributes>, state: OmiCaptureAttributes.ContentState) async {
        if #available(iOS 16.2, *) {
            await activity.update(ActivityContent(state: state, staleDate: Date().addingTimeInterval(90)))
        } else {
            await activity.update(using: state)
        }
    }

    private func end(_ activity: Activity<OmiCaptureAttributes>, immediate: Bool) async {
        guard activity.activityState != .dismissed,
              immediate || activity.activityState != .ended else { return }
        var final = activity.contentState
        if !final.paused && final.status != "ended" {
            final.elapsed = max(0, Int(Date().timeIntervalSince1970 - final.startedAt))
        }
        final.status = "ended"
        final.busy = false
        final.canPause = false
        final.canFinish = false
        let policy: ActivityUIDismissalPolicy = immediate ? .immediate : .after(Date().addingTimeInterval(5))
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
        let backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "Omi recording action")
        defer {
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
