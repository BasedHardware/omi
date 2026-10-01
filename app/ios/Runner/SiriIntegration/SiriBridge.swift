#if compiler(>=6.4)
import Foundation
import Flutter
import UIKit
import AppIntents
import FirebaseAuth
import FirebaseCore

/// Native Shortcuts link embedded in Flutter Settings. Apple's button opens
/// this app's Shortcuts page, including the per-app Siri enable switch.
@available(iOS 16.0, *)
final class OmiShortcutsButtonFactory: NSObject, FlutterPlatformViewFactory {
    func create(withFrame frame: CGRect, viewIdentifier viewId: Int64, arguments args: Any?) -> FlutterPlatformView {
        OmiShortcutsButton(frame: frame)
    }
}

@available(iOS 16.0, *)
private final class OmiShortcutsButton: NSObject, FlutterPlatformView {
    private let button: ShortcutsUIButton

    init(frame: CGRect) {
        button = ShortcutsUIButton(style: .automatic)
        button.frame = frame
        button.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        super.init()
    }

    func view() -> UIView { button }
}

enum SiriListeningFailure: Error {
    case deviceAlreadyListening
    case recordingOff
    case micDenied
    case nothingToStop
    case capturePaused
    case unavailable

    init(pigeonCode: String) {
        switch pigeonCode {
        case "device_already_listening": self = .deviceAlreadyListening
        case "recording_off": self = .recordingOff
        case "mic_permission_denied": self = .micDenied
        case "nothing_to_stop": self = .nothingToStop
        case "capture_paused": self = .capturePaused
        default: self = .unavailable
        }
    }

    func spokenDialog(starting: Bool) -> String {
        switch self {
        case .deviceAlreadyListening: "Omi is already listening from your device."
        case .recordingOff: "Turn on audio recording in Omi first."
        case .micDenied: "Allow microphone access in Omi first."
        case .nothingToStop: "Omi isn't listening right now."
        case .capturePaused: "Omi is paused. Open Omi to resume."
        case .unavailable: starting ? "Open Omi to start listening." : "Open Omi to stop listening."
        }
    }
}

final class SiriBridge: SiriIndexApi {
    static let shared = SiriBridge()
    private var events: SiriEventsApi?
    private var currentActivity: NSUserActivity?
    #if OMI_SIRI_PROBE
    var routeDeliveryProbe: ((String, @escaping (Bool) -> Void) -> Void)?
    #endif

    func retryPendingWipeOnLaunch() {
        #if OMI_SIRI_PROBE
        if SiriDebugProbe.spotlightModeActive { return }
        #endif
        Task {
            do {
                if try await SiriSnapshotStore.shared.maintainOnLaunch() {
                    NSLog("[SiriIndex] Pending account wipe retried successfully on launch")
                }
            } catch {
                NSLog("[SiriIndex] Pending account wipe will retry on the next launch: %@", String(describing: error))
            }
        }
    }

    func installNativeAuthFence() {
        #if OMI_SIRI_PROBE
        if SiriDebugProbe.spotlightModeActive { return }
        let arguments = ProcessInfo.processInfo.arguments
        // The ordinary no-engine probe deliberately binds a fake Siri UID
        // without a Firebase user. The separate Auth-emulator probe exercises
        // the real listener, so keep the synthetic fixture isolated from it.
        if arguments.contains("-omi-siri-probe") &&
            !arguments.contains("-omi-siri-probe-auth-seed") &&
            !arguments.contains("-omi-siri-probe-auth-verify") { return }
        if arguments.contains("-omi-siri-probe-auth-gate") { return }
        #endif
        SiriNativeAuthFence.shared.install()
    }

    func attach(messenger: FlutterBinaryMessenger) {
        events = SiriEventsApi(binaryMessenger: messenger)
        SiriIndexApiSetup.setUp(binaryMessenger: messenger, api: self)
    }
    private func complete(_ work: @escaping () async throws -> Void,
                          completion: @escaping (Result<Void, Error>) -> Void) {
        Task {
            do { try await work(); completion(.success(())) }
            catch { completion(.failure(error)) }
        }
    }
    func upsertConversations(uid: String, conversations: [SiriConversation], completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.upsert(conversations, uid: uid) }, completion: completion)
    }
    func reconcileConversations(uid: String, conversations: [SiriConversation], coveredAfterMs: Int64?,
                                completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.reconcile(conversations, uid: uid,
            coveredAfterMs: coveredAfterMs) }, completion: completion)
    }
    func upsertMemories(uid: String, memories: [SiriMemory], completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.upsert(memories, uid: uid) }, completion: completion)
    }
    func reconcileMemories(uid: String, memories: [SiriMemory], completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.reconcile(memories, uid: uid) }, completion: completion)
    }
    func upsertTasks(uid: String, tasks: [SiriTask], completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.upsert(tasks, uid: uid) }, completion: completion)
    }
    func reconcileTasks(uid: String, tasks: [SiriTask], includeCompleted: Bool,
                        completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.reconcile(tasks, uid: uid,
            includeCompleted: includeCompleted) }, completion: completion)
    }
    func deleteEntities(uid: String, type: String, ids: [String], completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.delete(type: type, ids: ids, uid: uid) }, completion: completion)
    }
    func repairOwnerIndex(uid: String, completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.repairOwnerIndex(uid: uid) }, completion: completion)
    }
    func wipe(completion: @escaping (Result<Int64, Error>) -> Void) {
        Task {
            do { completion(.success(try await SiriSnapshotStore.shared.wipeForAccountTransition())) }
            catch { completion(.failure(error)) }
        }
    }
    func prepareForSignOut(completion: @escaping (Result<Void, Error>) -> Void) {
        SiriSnapshotStore.shared.prepareForSignOut()
        completion(.success(()))
    }
    func generationForOwner(uid: String, completion: @escaping (Result<Int64?, Error>) -> Void) {
        completion(.success(SiriSnapshotStore.shared.generationForOwner(uid)))
    }
    func setEnabled(enabled: Bool, completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.setEnabled(enabled) }, completion: completion)
    }
    func publishSessionConfig(config: SiriSessionConfig, completion: @escaping (Result<Void, Error>) -> Void) {
        complete({ try await SiriSnapshotStore.shared.publishSession(config) }, completion: completion)
    }
    func setCurrentScreen(route: String, entityId: String?) throws {
        currentActivity?.resignCurrent()
        currentActivity?.invalidate()
        currentActivity = nil
        guard let entityId, !entityId.isEmpty, #available(iOS 27.0, *) else { return }
        let activity = NSUserActivity(activityType: "com.omi.siri.viewing")
        activity.title = "Viewing in Omi"
        if route.hasPrefix("/conversation/") {
            activity.appEntityIdentifier = EntityIdentifier(for: ConversationEntity.self, identifier: entityId)
        } else if route.hasPrefix("/memory/") {
            activity.appEntityIdentifier = EntityIdentifier(for: MemoryEntity.self, identifier: entityId)
        } else { return }
        activity.isEligibleForSearch = true
        let sceneWindow = UIApplication.shared.connectedScenes
            .compactMap { ($0 as? UIWindowScene)?.keyWindow }.first
        sceneWindow?.rootViewController?.userActivity = activity
        currentActivity = activity
        activity.becomeCurrent()
    }
    func takePendingRoute() throws -> SiriPendingRoute? { SiriSnapshotStore.shared.pendingRoute() }
    func finishPendingRoute(route: String, uid: String, generation: Int64, delivered: Bool) throws {
        SiriSnapshotStore.shared.finishPendingRoute(route: route, uid: uid,
                                                    generation: generation, delivered: delivered)
    }
    func isEnabled() throws -> Bool { SiriSnapshotStore.shared.enabled }
    func takeTelemetry() throws -> [SiriTelemetryRecord] { SiriTelemetry.take() }
    /// This target is compiled by the Siri toolchain (compiler(>=6.4)), so the
    /// omi/shortcuts_button platform view is registered and App Shortcuts ship.
    func appShortcutsAvailable() throws -> Bool { true }
    func donateAction(uid: String, type: String, id: String, completion: @escaping (Result<Void, Error>) -> Void) {
        complete({
            guard SiriSnapshotStore.shared.allowsDonation(uid: uid), !id.isEmpty,
                  ["memory", "task", "conversation"].contains(type) else { throw SiriSession.Failure.auth }
            if #available(iOS 26.0, *) {
                var intent = OmiUiActivityIntent()
                intent.kind = type
                intent.id = id
                _ = try await intent.donate()
            }
        }, completion: completion)
    }

    func memoryCreated(_ id: String) { events?.memoryCreated(id: id) { _ in } }
    func taskChanged(_ id: String) { events?.taskChanged(id: id) { _ in } }
    static func entityRoute(kind: String, id: String) -> String {
        let encodedID = id.addingPercentEncoding(
            withAllowedCharacters: CharacterSet.urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
        return "omi://\(kind)/\(encodedID)"
    }
    @discardableResult
    func navigate(_ route: String, entryPath: String = "unknown") -> Bool {
        let appRoute = route.hasPrefix("omi://") ? "/" + String(route.dropFirst(6)) : route
        let started = Date()
        let claim = SiriSnapshotStore.shared.claimPendingRoute(appRoute, entryPath: entryPath, started: started)
        let pending: SiriPendingRoute
        switch claim {
        case .accepted(let route): pending = route
        case .duplicate:
            if entryPath != "unknown" {
                SiriTelemetry.intent("open", outcome: "ok", started: started, entryPath: entryPath)
            }
            return true
        case .rejected:
            if entryPath != "unknown" {
                SiriTelemetry.intent("open", outcome: "auth", started: started, entryPath: entryPath)
            }
            return false
        }
        let acknowledged: (Bool) -> Void = { delivered in
            SiriSnapshotStore.shared.finishPendingRoute(route: appRoute, uid: pending.uid,
                generation: pending.generation, delivered: delivered)
        }
        #if OMI_SIRI_PROBE
        if let routeDeliveryProbe {
            routeDeliveryProbe(appRoute, acknowledged)
            return true
        }
        #endif
        events?.openRoute(route: appRoute, uid: pending.uid, generation: pending.generation) { result in
            switch result {
            case .success(let delivered): acknowledged(delivered)
            case .failure: acknowledged(false)
            }
        }
        return true
    }
    func setListening(_ enabled: Bool) async throws {
        guard let events else { throw SiriSession.Failure.server }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            events.setListening(enabled: enabled) { result in
                switch result {
                case .success: continuation.resume()
                case .failure(let error): continuation.resume(throwing: SiriListeningFailure(pigeonCode: error.code))
                }
            }
        }
    }
}

/// Observes the native Auth instance used by FlutterFire. This remains active
/// when a Pigeon request fails before it reaches Runner, and while no Flutter
/// engine exists. It never waits for Spotlight work before revoking Siri access.
private final class SiriNativeAuthFence {
    static let shared = SiriNativeAuthFence()
    private var listener: NSObjectProtocol?

    func install() {
        guard listener == nil else { return }
        if FirebaseApp.app() == nil { FirebaseApp.configure() }
        let auth = Auth.auth()
        listener = auth.addStateDidChangeListener { [weak self] auth, _ in
            self?.reconcile(auth)
        }
        // FirebaseAuth's first listener callback is asynchronous on main and
        // can observe nil before its saved user is loaded. Its currentUser
        // getter synchronizes with the SDK's global work queue, where saved
        // user hydration was enqueued at Auth initialization (Auth.swift in
        // the linked FirebaseAuth SDK). Resolve it before launch reindexing.
        reconcile(auth)
    }

    private func reconcile(_ auth: Auth) {
        let uid = auth.currentUser?.uid
        guard let owner = SiriSession.shared.currentConfig()?.uid ?? SiriSnapshotStore.shared.owner else {
            SiriSnapshotStore.shared.setAuthResolutionPending(false)
            return
        }
        if uid == owner {
            SiriSnapshotStore.shared.setAuthResolutionPending(false)
            return
        }
        if uid == nil && !UIApplication.shared.isProtectedDataAvailable {
            // Keychain hydration may resume after unlock. Deny current-process
            // Siri without durably destroying a still-signed-in owner's index.
            SiriSnapshotStore.shared.setAuthResolutionPending(true)
            return
        }
        SiriSnapshotStore.shared.prepareForSignOut()
    }
}

/// A bounded, account-scoped outbox for engine-free intent and index metrics.
/// Records have enums/counts/durations only; user content never enters defaults.
enum SiriTelemetry {
    private static let defaults = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12")
    private static let key = SiriStorageNamespace.current.telemetryKey
    private static let lock = NSLock()

    static func outcome(_ error: Error) -> String {
        switch error {
        case SiriSession.Failure.auth: return "auth"
        case SiriSession.Failure.network: return "network"
        case SiriSession.Failure.rateLimited: return "rateLimited"
        case SiriSession.Failure.quota: return "quota"
        default: return "server"
        }
    }
    static func intent(_ name: String, outcome: String, started: Date, entryPath: String = "unknown") {
        append(kind: "intent", intent: name, outcome: outcome,
               latencyMs: CheckedIntegerConversion.int64(max(0, Date().timeIntervalSince(started) * 1000)) ?? 0,
               entityCounts: 0, entryPath: entryPath)
    }
    static func index(outcome: String, started: Date, count: Int) {
        append(kind: "index", intent: "", outcome: outcome,
               latencyMs: CheckedIntegerConversion.int64(max(0, Date().timeIntervalSince(started) * 1000)) ?? 0,
               entityCounts: Int64(count), entryPath: "unknown")
    }
    private static func append(kind: String, intent: String, outcome: String,
                               latencyMs: Int64, entityCounts: Int64, entryPath: String) {
        guard let defaults, let uid = SiriSession.shared.currentConfig()?.uid else { return }
        lock.lock(); defer { lock.unlock() }
        var rows = defaults.array(forKey: key) as? [[String: Any]] ?? []
        rows.append(["uid": uid, "kind": kind, "intent": intent, "outcome": outcome,
                     "latencyMs": latencyMs, "entityCounts": entityCounts, "entryPath": entryPath])
        let records: [[String: PlistValue]] = rows.suffix(100).map { row in
            var record: [String: PlistValue] = [:]
            record["uid"] = .string(row["uid"] as? String ?? "")
            record["kind"] = .string(row["kind"] as? String ?? "")
            record["intent"] = .string(row["intent"] as? String ?? "")
            record["outcome"] = .string(row["outcome"] as? String ?? "")
            record["latencyMs"] = .int64(row["latencyMs"] as? Int64 ?? 0)
            record["entityCounts"] = .int64(row["entityCounts"] as? Int64 ?? 0)
            record["entryPath"] = .string(row["entryPath"] as? String ?? "unknown")
            return record
        }
        try? SafeDefaults.setPlistRecords(records, forKey: key, in: defaults)
    }
    static func take() -> [SiriTelemetryRecord] {
        guard let defaults, let uid = SiriSession.shared.currentConfig()?.uid else { return [] }
        lock.lock(); defer { lock.unlock() }
        let rows = defaults.array(forKey: key) as? [[String: Any]] ?? []
        defaults.removeObject(forKey: key)
        return rows.compactMap { row in
            guard row["uid"] as? String == uid,
                  let kind = row["kind"] as? String,
                  let intent = row["intent"] as? String,
                  let outcome = row["outcome"] as? String,
                  let latency = (row["latencyMs"] as? NSNumber)?.int64Value,
                  let count = (row["entityCounts"] as? NSNumber)?.int64Value else { return nil }
            return SiriTelemetryRecord(kind: kind, intent: intent, outcome: outcome,
                                       latencyMs: latency, entityCounts: count,
                                       entryPath: row["entryPath"] as? String ?? "unknown")
        }
    }
}

#else
import Flutter
import Foundation

/// Xcode 26.6 required CI keeps the Pigeon channel registered while Siri is
/// unavailable. The Xcode 27 Codemagic build compiles the real bridge above.
final class SiriBridge: SiriIndexApi {
    static let shared = SiriBridge()
    func installNativeAuthFence() {}
    func retryPendingWipeOnLaunch() {}
    func attach(messenger: FlutterBinaryMessenger) {
        SiriIndexApiSetup.setUp(binaryMessenger: messenger, api: self)
    }
    func upsertConversations(uid: String, conversations: [SiriConversation], completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func reconcileConversations(uid: String, conversations: [SiriConversation], coveredAfterMs: Int64?, completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func upsertMemories(uid: String, memories: [SiriMemory], completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func reconcileMemories(uid: String, memories: [SiriMemory], completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func upsertTasks(uid: String, tasks: [SiriTask], completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func reconcileTasks(uid: String, tasks: [SiriTask], includeCompleted: Bool, completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func deleteEntities(uid: String, type: String, ids: [String], completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func repairOwnerIndex(uid: String, completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func wipe(completion: @escaping (Result<Int64, Error>) -> Void) { completion(.success(0)) }
    func prepareForSignOut(completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func generationForOwner(uid: String, completion: @escaping (Result<Int64?, Error>) -> Void) { completion(.success(nil)) }
    func setEnabled(enabled: Bool, completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func setCurrentScreen(route: String, entityId: String?) throws {}
    func publishSessionConfig(config: SiriSessionConfig, completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
    func takePendingRoute() throws -> SiriPendingRoute? { nil }
    func finishPendingRoute(route: String, uid: String, generation: Int64, delivered: Bool) throws {}
    func isEnabled() throws -> Bool { false }
    func takeTelemetry() throws -> [SiriTelemetryRecord] { [] }
    /// Stable-compiler fallback: the Siri toolchain did not compile this build,
    /// so omi/shortcuts_button is unregistered and Dart must not request it.
    func appShortcutsAvailable() throws -> Bool { false }
    func donateAction(uid: String, type: String, id: String, completion: @escaping (Result<Void, Error>) -> Void) { completion(.success(())) }
}
#endif
