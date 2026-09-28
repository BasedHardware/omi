import Foundation
import CoreSpotlight
import CryptoKit

/// The two Runner flavors share an App Group, so every persisted Siri value
/// needs a bundle-specific name even when its account uid is the same.
struct SiriStorageNamespace {
    static let current = SiriStorageNamespace(bundleID: Bundle.main.bundleIdentifier ?? "com.omi.unknown")
    let bundleID: String
    var snapshotFileName: String { "siri-index-snapshot-\(bundleID).json" }
    var ownerKey: String { "\(bundleID).siri.snapshot.owner" }
    var pendingWipeOwnersKey: String { "\(bundleID).siri.pending.wipe.owners" }
    var generationKey: String { "\(bundleID).siri.session.generation" }
    var enabledKey: String { "\(bundleID).siri.index.enabled" }
    var pendingRouteKey: String { "\(bundleID).siri.pending.route" }
    var sessionConfigKey: String { "\(bundleID).siri.session.config" }
    var telemetryKey: String { "\(bundleID).siri.telemetry.pending" }
    var keychainService: String { "com.omi.siri.session.\(bundleID)" }
    var keychainAccount: String { "firebase-id-token.\(bundleID)" }
    func indexName(for uid: String) -> String {
        let digest = SHA256.hash(data: Data(uid.utf8)).prefix(12)
            .map { String(format: "%02x", $0) }.joined()
        return "omi.siri.\(bundleID).\(digest)"
    }
}

enum SiriStorageLocation {
    static func container(groupURL: URL?, appSupportURL: URL) -> URL {
        groupURL ?? appSupportURL.appendingPathComponent("SiriIndex", isDirectory: true)
    }
}

/// Only the fields approved for Apple's on-device index are kept here.
#if compiler(>=6.4)
final class SiriSnapshotStore {
    static let shared = SiriSnapshotStore()
    private let lock = NSLock()
    private let defaults = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12") ?? .standard
    private let container = SiriStorageLocation.container(
        groupURL: FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.friend-app-with-wearable.ios12"),
        appSupportURL: FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory)
    private let namespace = SiriStorageNamespace.current
    private var ownerKey: String { namespace.ownerKey }
    private var pendingWipeOwnersKey: String { namespace.pendingWipeOwnersKey }
    private var generationKey: String { namespace.generationKey }
    private var enabledKey: String { namespace.enabledKey }
    private var routeKey: String { namespace.pendingRouteKey }

    private struct Snapshot: Codable {
        var eligibilityVersion: Int? = nil
        var ownerUid: String? = nil
        var conversations: [String: Conversation] = [:]
        var memories: [String: Memory] = [:]
        var tasks: [String: Task] = [:]
    }
    private struct Conversation: Codable {
        let id: String; let title: String; let summary: String
        let startedAtMs: Int64; let updatedAtMs: Int64
    }
    private struct Memory: Codable { let id: String; let content: String; let createdAtMs: Int64; let expiresAtMs: Int64? }
    private struct Task: Codable {
        let id: String; let title: String; let completed: Bool
        let createdAtMs: Int64; let dueAtMs: Int64?; let completedAtMs: Int64?
    }
    private var snapshot: Snapshot
    private var transitionGeneration: Int64?
    private var authResolutionPending = false
    private var expiryTask: _Concurrency.Task<Void, Never>?
    #if OMI_SIRI_PROBE
    var simulateIndexDeleteFailure = false
    var simulateSnapshotPersistFailureOnce = false
    var simulateMarkerFlushFailureOnce = false
    private(set) var probeFullRebuildCount = 0
    #endif
    private var file: URL { container.appendingPathComponent(namespace.snapshotFileName) }
    private func serialized<T>(_ operation: () async throws -> T) async rethrows -> T {
        if SiriSnapshotQueueContext.active { return try await operation() }
        return try await SiriSpotlightGate.shared.run {
            try await SiriSnapshotQueueContext.$active.withValue(true) {
                try await operation()
            }
        }
    }
    private init() {
        try? FileManager.default.createDirectory(at: container, withIntermediateDirectories: true)
        snapshot = (try? Data(contentsOf: container.appendingPathComponent(SiriStorageNamespace.current.snapshotFileName)))
            .flatMap { try? JSONDecoder().decode(Snapshot.self, from: $0) } ?? Snapshot()
        // Older snapshots did not retain the memory layer. Their rows cannot
        // prove archive eligibility, so drop them before launch maintenance
        // rebuilds Spotlight; Flutter will republish active rows.
        if snapshot.eligibilityVersion != 1 {
            snapshot.memories.removeAll()
            snapshot.eligibilityVersion = 1
            try? persist()
        }
    }
    var enabled: Bool { defaults.object(forKey: enabledKey) as? Bool ?? true }
    var owner: String? { defaults.string(forKey: ownerKey) }
    func generationForOwner(_ uid: String) -> Int64? {
        lock.lock(); defer { lock.unlock() }
        let sessionOwner = SiriSession.shared.currentConfig()?.uid
        guard !uid.isEmpty, owner == uid, snapshot.ownerUid == uid,
              transitionGeneration == nil, !authResolutionPending,
              (defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).isEmpty,
              (sessionOwner == nil || sessionOwner == uid) else { return nil }
        return defaults.object(forKey: generationKey) as? Int64 ?? 0
    }
    var indexName: String? {
        guard let owner else { return nil }
        return indexName(for: owner)
    }
    private func indexName(for uid: String) -> String {
        namespace.indexName(for: uid)
    }
    private func accountOwnerLocked() -> Bool {
        guard let uid = snapshot.ownerUid, !uid.isEmpty else { return false }
        return owner == uid && SiriSession.shared.currentConfig()?.uid == uid &&
            SiriSession.shared.hasMirroredToken() && SiriSession.shared.hasCurrentFirebaseOwner(uid) &&
            transitionGeneration == nil && !authResolutionPending &&
            (defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).isEmpty
    }
    /// While Firebase waits for protected Keychain data, deny Siri reads and
    /// writes without deleting a possibly valid account's persisted index.
    func setAuthResolutionPending(_ pending: Bool) {
        lock.lock(); defer { lock.unlock() }
        authResolutionPending = pending
    }
    private func validOwnerLocked() -> Bool { enabled && accountOwnerLocked() }
    private static let conversationAgeMs: Int64 = 180 * 86_400_000
    private static let completedTaskAgeMs: Int64 = 30 * 86_400_000
    private func eligible(_ row: Conversation, now: Int64) -> Bool {
        !row.id.isEmpty && row.startedAtMs > now - Self.conversationAgeMs
    }
    private func eligible(_ row: Memory, now: Int64) -> Bool {
        !row.id.isEmpty && (row.expiresAtMs == nil || row.expiresAtMs! > now)
    }
    private func eligible(_ row: Task, now: Int64) -> Bool {
        !row.id.isEmpty && (!row.completed || (row.completedAtMs ?? 0) > now - Self.completedTaskAgeMs)
    }
    private func nextCutoffLocked() -> Int64? {
        let deadlines = snapshot.conversations.values.map { $0.startedAtMs + Self.conversationAgeMs }
            + snapshot.memories.values.compactMap(\.expiresAtMs)
            + snapshot.tasks.values.compactMap { $0.completed ? $0.completedAtMs.map { $0 + Self.completedTaskAgeMs } : nil }
        return deadlines.min()
    }
    private func generationMatchesLocked(_ generation: Int64) -> Bool {
        (defaults.object(forKey: generationKey) as? Int64 ?? 0) == generation
    }
    private func requireValidOwner(_ expectedUid: String? = nil) throws {
        guard let uid = expectedUid ?? owner else { throw SiriSession.Failure.auth }
        _ = try SiriSession.shared.requireFirebaseOwner(uid)
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked(), expectedUid == nil || snapshot.ownerUid == expectedUid else {
            throw SiriSession.Failure.auth
        }
    }
    private func persist() throws {
        #if OMI_SIRI_PROBE
        if simulateSnapshotPersistFailureOnce {
            simulateSnapshotPersistFailureOnce = false
            throw CocoaError(.fileWriteUnknown)
        }
        #endif
        try JSONEncoder().encode(snapshot).write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: file.path)
    }
    private func mutate(_ update: () -> Void) throws {
        lock.lock(); defer { lock.unlock() }
        update()
        try persist()
    }
    private func mutateForOwner(_ uid: String, generation: Int64? = nil, _ update: () -> Void) throws {
        lock.lock(); defer { lock.unlock() }
        guard accountOwnerLocked(), snapshot.ownerUid == uid,
              generation.map(generationMatchesLocked) ?? true,
              transitionGeneration == nil,
              (defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).isEmpty else {
            throw SiriSession.Failure.auth
        }
        update()
        try persist()
    }

    /// A native intent can finish with no Flutter engine. Commit its confirmed
    /// response under the same owner generation that authorized the request.
    func applyConfirmedMemory(id: String, content: String, owner: SiriSession.Config) async throws {
        try await serialized {
            try SiriSession.shared.validateOwner(owner)
            guard !id.isEmpty else { throw SiriSession.Failure.server }
            try mutateForOwner(owner.uid, generation: owner.generation ?? 0) {
                snapshot.memories[id] = Memory(id: id, content: content,
                    createdAtMs: Int64(Date().timeIntervalSince1970 * 1000), expiresAtMs: nil)
            }
            if enabled {
                do { try await applyIncremental(type: "memory", ids: [id], uid: owner.uid) }
                catch { NSLog("[SiriIndex] Confirmed memory index deferred: %@", String(describing: error)); scheduleIndexRetry() }
            }

        }
    }

    func applyConfirmedTask(id: String, title: String, completed: Bool, dueAt: Date?,
                            owner: SiriSession.Config) async throws {
        try await serialized {
            try SiriSession.shared.validateOwner(owner)
            guard !id.isEmpty else { throw SiriSession.Failure.server }
            let now = Int64(Date().timeIntervalSince1970 * 1000)
            try mutateForOwner(owner.uid, generation: owner.generation ?? 0) {
                let existing = snapshot.tasks[id]
                snapshot.tasks[id] = Task(id: id, title: title, completed: completed,
                    createdAtMs: existing?.createdAtMs ?? now,
                    dueAtMs: dueAt.map { Int64($0.timeIntervalSince1970 * 1000) } ?? existing?.dueAtMs,
                    completedAtMs: completed ? now : nil)
            }
            if enabled {
                do { try await applyIncremental(type: "task", ids: [id], uid: owner.uid) }
                catch { NSLog("[SiriIndex] Confirmed task index deferred: %@", String(describing: error)); scheduleIndexRetry() }
            }

        }
    }
    private func cancelExpiryTask() {
        lock.lock(); defer { lock.unlock() }
        expiryTask?.cancel()
        expiryTask = nil
    }
    #if OMI_SIRI_PROBE
    func simulateTerminatedExpiryTimer() { cancelExpiryTask() }
    func probeSimulateColdLaunchWithoutMarker() {
        lock.lock(); defer { lock.unlock() }
        defaults.removeObject(forKey: pendingWipeOwnersKey)
        _ = defaults.synchronize()
        transitionGeneration = nil
    }
    func probeStoredEntity(type: String, id: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        switch type {
        case "conversation": return snapshot.conversations[id] != nil
        case "memory": return snapshot.memories[id] != nil
        case "task": return snapshot.tasks[id] != nil
        default: return false
        }
    }
    func probePersistedEntity(type: String, id: String) -> Bool {
        guard let data = try? Data(contentsOf: file),
              let stored = try? JSONDecoder().decode(Snapshot.self, from: data) else { return false }
        switch type {
        case "memory": return stored.memories[id] != nil
        case "task": return stored.tasks[id] != nil
        case "conversation": return stored.conversations[id] != nil
        default: return false
        }
    }
    #endif
    /// Keep a live Runner's index fresh at the next expiry. A 24 hour cap also
    /// checks long-lived records without retaining an unbounded sleep.
    private func scheduleNextExpiry() {
        lock.lock(); defer { lock.unlock() }
        expiryTask?.cancel()
        expiryTask = nil
        guard validOwnerLocked() else { return }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        guard let next = nextCutoffLocked() else { return }
        let delayMs = UInt64(min(max(next - now + 50, 50), 24 * 60 * 60 * 1000))
        expiryTask = _Concurrency.Task.detached { [weak self] in
            try? await _Concurrency.Task.sleep(nanoseconds: delayMs * 1_000_000)
            guard !_Concurrency.Task.isCancelled else { return }
            await self?.rebuildAfterTimer()
        }
    }
    private func rebuildAfterTimer() async {
        do { try await rebuildIndex() }
        catch {
            NSLog("[SiriIndex] Expiry rebuild failed; retrying: %@", String(describing: error))
            scheduleIndexRetry()
        }
    }
    private func scheduleIndexRetry() {
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return }
        expiryTask?.cancel()
        expiryTask = _Concurrency.Task.detached { [weak self] in
            try? await _Concurrency.Task.sleep(nanoseconds: 30_000_000_000)
            guard !_Concurrency.Task.isCancelled else { return }
            await self?.rebuildAfterTimer()
        }
    }
    /// A backend-confirmed intent must succeed even when the local cache write
    /// fails. Retry only while the same account generation still owns it.
    func scheduleConfirmedRepair(owner: SiriSession.Config) {
        guard generationForOwner(owner.uid) == (owner.generation ?? 0) else { return }
        scheduleIndexRetry()
    }

    func bind(uid: String, generation: Int64? = nil) async throws {
        try await serialized {
            guard !uid.isEmpty else { throw SiriSession.Failure.auth }
            lock.lock()
            let snapshotOwner = snapshot.ownerUid
            let pendingWipe = !(defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).isEmpty
            let accepted = generation.map(generationMatchesLocked) ?? true
            let transitioning = transitionGeneration != nil
            lock.unlock()
            guard accepted, (!transitioning || pendingWipe) else { throw SiriSession.Failure.auth }
            if snapshotOwner != uid || owner != uid || pendingWipe { try await wipe(expectedGeneration: generation) }
            lock.lock(); defer { lock.unlock() }
            guard (generation.map(generationMatchesLocked) ?? true), transitionGeneration == nil,
                  (defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).isEmpty else {
                throw SiriSession.Failure.auth
            }
            snapshot.ownerUid = uid
            try persist()
            defaults.set(uid, forKey: ownerKey)

        }
    }
    func publishSession(_ config: SiriSessionConfig) async throws {
        try await serialized {
            try await bind(uid: config.uid, generation: config.generation)
            lock.lock(); defer { lock.unlock() }
            guard generationMatchesLocked(config.generation), transitionGeneration == nil,
                  (defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).isEmpty,
                  snapshot.ownerUid == config.uid,
                  owner == config.uid else { throw SiriSession.Failure.auth }
            try SiriSession.shared.publish(config)
            authResolutionPending = false

        }
    }
    func wipeForAccountTransition() async throws -> Int64 {
        return try await serialized {
            lock.lock()
            let next = (defaults.object(forKey: generationKey) as? Int64 ?? 0) + 1
            defaults.set(next, forKey: generationKey)
            transitionGeneration = next
            lock.unlock()
            try await wipe(expectedGeneration: next)
            return next

        }
    }
    /// This fast privacy fence bypasses the Spotlight serialization gate.
    /// Each operation runs even if another fails; the queued wipe follows via
    /// the auth callback. Token absence and the hydrated Firebase owner check
    /// each deny a cold engine-free launch independently of the marker.
    func prepareForSignOut() {
        let tokenRemoved = SiriSession.shared.revokeMirroredTokenForSignOut()
        if !tokenRemoved { NSLog("[SiriIndex] Sign-out token revocation failed; attempting durable marker") }
        lock.lock()
        let owners = Set([owner, snapshot.ownerUid, SiriSession.shared.currentConfig()?.uid].compactMap { $0 })
            .union(defaults.stringArray(forKey: pendingWipeOwnersKey) ?? [])
        defaults.set(Array(owners), forKey: pendingWipeOwnersKey)
        #if OMI_SIRI_PROBE
        let markerPersisted: Bool
        if simulateMarkerFlushFailureOnce {
            simulateMarkerFlushFailureOnce = false
            defaults.removeObject(forKey: pendingWipeOwnersKey)
            _ = defaults.synchronize()
            markerPersisted = false
        } else { markerPersisted = defaults.synchronize() }
        #else
        let markerPersisted = defaults.synchronize()
        #endif
        if !markerPersisted { NSLog("[SiriIndex] Sign-out pending-wipe marker flush failed") }
        let next = (defaults.object(forKey: generationKey) as? Int64 ?? 0) + 1
        defaults.set(next, forKey: generationKey)
        transitionGeneration = next
        defaults.removeObject(forKey: routeKey)
        if !defaults.synchronize() { NSLog("[SiriIndex] Sign-out generation flush failed") }
        lock.unlock()
        // A publisher already inside the owner lock may have mirrored a token
        // after the first deletion. Revoke it again after fencing that writer.
        if !SiriSession.shared.revokeMirroredTokenForSignOut() {
            NSLog("[SiriIndex] Sign-out post-fence token revocation failed")
        }
        if !tokenRemoved || !markerPersisted {
            // The process fence is still active. On a future launch, every
            // Siri read also checks Firebase's persisted currentUser.
            NSLog("[SiriIndex] Sign-out persistence incomplete; Firebase owner check remains required")
        }
    }
    func retryPendingWipe() async throws -> Bool {
        return try await serialized {
            lock.lock()
            let pending = !(defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).isEmpty
            let generation = defaults.object(forKey: generationKey) as? Int64 ?? 0
            lock.unlock()
            guard pending else { return false }
            try await wipe(expectedGeneration: generation)
            return true

        }
    }
    func maintainOnLaunch() async throws -> Bool {
        return try await serialized {
            let retriedWipe = try await retryPendingWipe()
            // setEnabled(false) persists the preference before Spotlight deletion.
            // A failed delete must be retried even though rebuilding is disabled.
            if !enabled {
                try await removeIndex()
            } else if let uid = owner, generationForOwner(uid) != nil {
                try await rebuildIndex()
            }
            return retriedWipe

        }
    }
    func setEnabled(_ value: Bool) async throws {
        try await serialized {
            defaults.set(value, forKey: enabledKey)
            if !value {
                cancelExpiryTask()
                try await removeIndex()
            }
            else { try await rebuildIndex() }

        }
    }
    func wipe(expectedGeneration: Int64? = nil) async throws {
        try await serialized {
            cancelExpiryTask()
            lock.lock()
            guard expectedGeneration.map(generationMatchesLocked) ?? true else {
                lock.unlock()
                throw SiriSession.Failure.auth
            }
            let owners = Set([owner, snapshot.ownerUid, SiriSession.shared.currentConfig()?.uid].compactMap { $0 })
                .union(defaults.stringArray(forKey: pendingWipeOwnersKey) ?? [])
            defaults.set(Array(owners), forKey: pendingWipeOwnersKey)
            snapshot = Snapshot()
            let persistence: Result<Void, Error>
            do { try persist(); persistence = .success(()) }
            catch { persistence = .failure(error) }
            defaults.removeObject(forKey: ownerKey)
            defaults.removeObject(forKey: routeKey)
            SiriSession.shared.clear()
            lock.unlock()
            try persistence.get()
            try await removeIndex(owners: owners)
            lock.lock()
            let remaining = Set(defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).subtracting(owners)
            if remaining.isEmpty { defaults.removeObject(forKey: pendingWipeOwnersKey) }
            else { defaults.set(Array(remaining), forKey: pendingWipeOwnersKey) }
            if expectedGeneration == nil || transitionGeneration == expectedGeneration { transitionGeneration = nil }
            lock.unlock()

        }
    }
    private func removeIndex(owners explicitOwners: Set<String>? = nil) async throws {
        lock.lock(); let snapshotOwner = snapshot.ownerUid; lock.unlock()
        let owners = explicitOwners ?? Set([owner, snapshotOwner, SiriSession.shared.currentConfig()?.uid].compactMap { $0 })
        try await serialized {
            #if OMI_SIRI_PROBE
            if simulateIndexDeleteFailure { throw SiriSession.Failure.server }
            #endif
            for uid in owners {
                try await CSSearchableIndex(name: indexName(for: uid)).deleteAllSearchableItems()
            }
        }
    }
    func upsert(_ values: [SiriConversation], uid: String) async throws {
        try await serialized {
            var evicted: [String] = []
            try mutateForOwner(uid) {
            for value in values where !value.id.isEmpty {
                snapshot.conversations[value.id] = Conversation(id: value.id, title: value.title,
                    summary: value.summary, startedAtMs: value.startedAtMs, updatedAtMs: value.updatedAtMs)
            }
            let now = Int64(Date().timeIntervalSince1970 * 1000)
            let newest = snapshot.conversations.values.filter { eligible($0, now: now) }
                .sorted { $0.startedAtMs > $1.startedAtMs }.prefix(2000)
            let keep = Set(newest.map(\.id))
            evicted = snapshot.conversations.keys.filter { !keep.contains($0) }
            snapshot.conversations = snapshot.conversations.filter { keep.contains($0.key) }
            }
            try await applyIncremental(type: "conversation", ids: values.map(\.id) + evicted, uid: uid)

        }
    }
    /// A successful owner-wide or newest-page fetch is authoritative only for
    /// its covered window. The oldest row on a nonfinal page is excluded so
    /// timestamp ties at the page boundary cannot delete unseen records.
    func reconcile(_ values: [SiriConversation], uid: String, coveredAfterMs: Int64?) async throws {
        try await serialized {
            try mutateForOwner(uid) {
                let keep = Set(values.map(\.id))
                snapshot.conversations = snapshot.conversations.filter { id, row in
                    keep.contains(id) || (coveredAfterMs.map { row.startedAtMs <= $0 } ?? false)
                }
                for value in values where !value.id.isEmpty {
                    snapshot.conversations[value.id] = Conversation(id: value.id, title: value.title,
                        summary: value.summary, startedAtMs: value.startedAtMs, updatedAtMs: value.updatedAtMs)
                }
            }
            if enabled { try await rebuildIndex() }

        }
    }
    func upsert(_ values: [SiriMemory], uid: String) async throws {
        try await serialized {
            var evicted: [String] = []
            try mutateForOwner(uid) {
            for value in values where !value.id.isEmpty {
                snapshot.memories[value.id] = Memory(id: value.id, content: value.content, createdAtMs: value.createdAtMs, expiresAtMs: value.expiresAtMs)
            }
            let now = Int64(Date().timeIntervalSince1970 * 1000)
            let newest = snapshot.memories.values.filter { eligible($0, now: now) }
                .sorted { $0.createdAtMs > $1.createdAtMs }.prefix(5000)
            let keep = Set(newest.map(\.id))
            evicted = snapshot.memories.keys.filter { !keep.contains($0) }
            snapshot.memories = snapshot.memories.filter { keep.contains($0.key) }
            }
            try await applyIncremental(type: "memory", ids: values.map(\.id) + evicted, uid: uid)

        }
    }
    /// Called only after the entire unfiltered memory traversal succeeds.
    func reconcile(_ values: [SiriMemory], uid: String) async throws {
        try await serialized {
            try mutateForOwner(uid) {
                let keep = Set(values.map(\.id))
                snapshot.memories = snapshot.memories.filter { keep.contains($0.key) }
                for value in values where !value.id.isEmpty {
                    snapshot.memories[value.id] = Memory(id: value.id, content: value.content,
                        createdAtMs: value.createdAtMs, expiresAtMs: value.expiresAtMs)
                }
            }
            if enabled { try await rebuildIndex() }

        }
    }
    func upsert(_ values: [SiriTask], uid: String) async throws {
        try await serialized {
            try mutateForOwner(uid) {
            for value in values where !value.id.isEmpty {
                snapshot.tasks[value.id] = Task(id: value.id, title: value.title, completed: value.completed,
                    createdAtMs: value.createdAtMs, dueAtMs: value.dueAtMs, completedAtMs: value.completedAtMs)
            }
            }
            try await applyIncremental(type: "task", ids: values.map(\.id), uid: uid)

        }
    }
    /// A complete active-only task list cannot speak for completed rows.
    func reconcile(_ values: [SiriTask], uid: String, includeCompleted: Bool) async throws {
        try await serialized {
            try mutateForOwner(uid) {
                let keep = Set(values.map(\.id))
                snapshot.tasks = snapshot.tasks.filter { id, row in
                    keep.contains(id) || (!includeCompleted && row.completed)
                }
                for value in values where !value.id.isEmpty {
                    snapshot.tasks[value.id] = Task(id: value.id, title: value.title, completed: value.completed,
                        createdAtMs: value.createdAtMs, dueAtMs: value.dueAtMs, completedAtMs: value.completedAtMs)
                }
            }
            if enabled { try await rebuildIndex() }

        }
    }
    func delete(type: String, ids: [String], uid: String) async throws {
        try await serialized {
            try mutateForOwner(uid) {
            for id in ids {
                switch type {
                case "conversation": snapshot.conversations.removeValue(forKey: id)
                case "memory": snapshot.memories.removeValue(forKey: id)
                case "task": snapshot.tasks.removeValue(forKey: id)
                default: break
                }
            }
            }
            try await applyIncremental(type: type, ids: ids, uid: uid)

        }
    }
    func pendingRoute() -> String? {
        let route = defaults.string(forKey: routeKey)
        defaults.removeObject(forKey: routeKey)
        return route
    }
    func setPendingRoute(_ route: String) { defaults.set(route, forKey: routeKey) }
    func clearPendingRoute(ifMatching route: String) {
        lock.lock(); defer { lock.unlock() }
        if defaults.string(forKey: routeKey) == route { defaults.removeObject(forKey: routeKey) }
    }
    func allowsDonation(uid: String) -> Bool {
        do { _ = try SiriSession.shared.requireFirebaseOwner(uid) }
        catch { return false }
        lock.lock(); defer { lock.unlock() }
        return validOwnerLocked() && snapshot.ownerUid == uid
    }

    /// Open intents remain usable with indexing OFF, but a stale entity must
    /// never navigate under a different owner or after leaving index scope.
    func containsCurrentEntity(type: String, id: String) -> Bool {
        guard let uid = owner else { return false }
        do { _ = try SiriSession.shared.requireFirebaseOwner(uid) }
        catch { return false }
        lock.lock(); defer { lock.unlock() }
        guard !id.isEmpty, accountOwnerLocked(), transitionGeneration == nil,
              (defaults.stringArray(forKey: pendingWipeOwnersKey) ?? []).isEmpty else { return false }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        switch type {
        case "conversation":
            return snapshot.conversations[id].map { eligible($0, now: now) } ?? false
        case "memory":
            return snapshot.memories[id].map { eligible($0, now: now) } ?? false
        case "task":
            return snapshot.tasks[id].map { eligible($0, now: now) } ?? false
        default: return false
        }
    }

    @available(iOS 27.0, *)
    func conversations(ids: [String]?) -> [ConversationEntity] {
        guard let uid = owner else { return [] }
        do { _ = try SiriSession.shared.requireFirebaseOwner(uid) }
        catch { return [] }
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return [] }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let selected = snapshot.conversations.values.filter {
            eligible($0, now: now) && (ids == nil || ids!.contains($0.id))
        }
        return selected.map { ConversationEntity(id: $0.id, name: $0.title, content: $0.summary,
            creationDate: Date(timeIntervalSince1970: Double($0.startedAtMs) / 1000),
            modificationDate: Date(timeIntervalSince1970: Double($0.updatedAtMs) / 1000)) }
    }
    @available(iOS 27.0, *)
    func memoryNotes(ids: [String]?) -> [ConversationEntity] {
        guard let uid = owner else { return [] }
        do { _ = try SiriSession.shared.requireFirebaseOwner(uid) }
        catch { return [] }
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return [] }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        return snapshot.memories.values.filter { (ids == nil || ids!.contains($0.id)) && eligible($0, now: now) }.map {
            ConversationEntity(memoryId: $0.id, content: $0.content,
                creationDate: Date(timeIntervalSince1970: Double($0.createdAtMs) / 1000))
        }
    }
    @available(iOS 27.0, *)
    func memories(ids: [String]?) -> [MemoryEntity] {
        guard let uid = owner else { return [] }
        do { _ = try SiriSession.shared.requireFirebaseOwner(uid) }
        catch { return [] }
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return [] }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        return snapshot.memories.values.filter { (ids == nil || ids!.contains($0.id)) && eligible($0, now: now) }.map {
            MemoryEntity(id: $0.id, content: $0.content,
                creationDate: Date(timeIntervalSince1970: Double($0.createdAtMs) / 1000)) }
    }
    @available(iOS 27.0, *)
    func tasks(ids: [String]?) -> [TaskEntity] {
        guard let uid = owner else { return [] }
        do { _ = try SiriSession.shared.requireFirebaseOwner(uid) }
        catch { return [] }
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return [] }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        return snapshot.tasks.values.filter {
            (ids == nil || ids!.contains($0.id)) && eligible($0, now: now)
        }.map {
            TaskEntity(id: $0.id, title: $0.title, isCompleted: $0.completed,
                creationDate: Date(timeIntervalSince1970: Double($0.createdAtMs) / 1000),
                dueDate: $0.dueAtMs.map { Date(timeIntervalSince1970: Double($0) / 1000) },
                completionDate: $0.completedAtMs.map { Date(timeIntervalSince1970: Double($0) / 1000) }) }
    }
    /// System callbacks use the same owner gate as mutations and wipes.
    func reindex(type: String, ids: [String], expectedUid: String) async throws {
        try await serialized {
            guard enabled, #available(iOS 27.0, *) else { return }
            try requireValidOwner(expectedUid)
            #if OMI_SIRI_PROBE
            await SiriReindexProbeGate.shared.pauseIfArmed()
            #endif
            try await applyIncremental(type: type, ids: ids, uid: expectedUid)
        }
    }

    /// Incremental mutations never empty the owner's whole index.
    @available(iOS 27.0, *)
    private func deleteMemoryRepresentations(ids: [String], from index: CSSearchableIndex) async throws {
        guard !ids.isEmpty else { return }
        try await index.deleteAppEntities(identifiedBy: ids, ofType: MemoryEntity.self)
        try await index.deleteAppEntities(identifiedBy: ids, ofType: ConversationEntity.self)
    }

    private func applyIncremental(type: String, ids: [String], uid: String) async throws {
        guard enabled, #available(iOS 27.0, *) else { return }
        try requireValidOwner(uid)
        let ids = Array(Set(ids.filter { !$0.isEmpty }))
        guard !ids.isEmpty else { return }
        let index = CSSearchableIndex(name: indexName(for: uid))
        do {
            switch type {
            case "conversation":
                let entities = conversations(ids: ids) + memoryNotes(ids: ids)
                let present = Set(entities.map(\.id))
                let removed = ids.filter { !present.contains($0) }
                if !removed.isEmpty {
                    try await index.deleteAppEntities(identifiedBy: removed, ofType: ConversationEntity.self)
                }
                try requireValidOwner(uid)
                if !entities.isEmpty { try await index.indexAppEntities(entities, priority: 0) }
            case "memory":
                let entities = memories(ids: ids)
                let present = Set(entities.map(\.id))
                let removed = ids.filter { !present.contains($0) }
                try await deleteMemoryRepresentations(ids: removed, from: index)
                try requireValidOwner(uid)
                if !entities.isEmpty { try await index.indexAppEntities(entities, priority: 0) }
                // A memory can also be represented as a Notes schema entity.
                // Reindex may create that entry, so every memory mutation must
                // update or remove it under the same owner gate.
                let notes = conversations(ids: ids) + memoryNotes(ids: ids)
                try requireValidOwner(uid)
                if !notes.isEmpty { try await index.indexAppEntities(notes, priority: 0) }
            case "task":
                let entities = tasks(ids: ids)
                let present = Set(entities.map(\.id))
                let removed = ids.filter { !present.contains($0) }
                if !removed.isEmpty {
                    try await index.deleteAppEntities(identifiedBy: removed, ofType: TaskEntity.self)
                }
                try requireValidOwner(uid)
                if !entities.isEmpty { try await index.indexAppEntities(entities, priority: 0) }
            default: return
            }
            try requireValidOwner(uid)
            scheduleNextExpiry()
        } catch {
            scheduleIndexRetry()
            throw error
        }
    }
    func rebuildIndex() async throws {
        try await serialized {
            #if OMI_SIRI_PROBE
            probeFullRebuildCount += 1
            #endif
            let started = Date()
            guard #available(iOS 27.0, *) else { return }
            try requireValidOwner()
            guard let uid = owner, let indexName else { throw SiriSession.Failure.auth }
            let now = Int64(Date().timeIntervalSince1970 * 1000)
            try mutateForOwner(uid) {
                snapshot.conversations = snapshot.conversations.filter { eligible($0.value, now: now) }
                let newest = snapshot.conversations.values.sorted { $0.startedAtMs > $1.startedAtMs }.prefix(2000)
                snapshot.conversations = Dictionary(uniqueKeysWithValues: newest.map { ($0.id, $0) })
                snapshot.memories = snapshot.memories.filter { eligible($0.value, now: now) }
                let memories = snapshot.memories.values.sorted { $0.createdAtMs > $1.createdAtMs }.prefix(5000)
                snapshot.memories = Dictionary(uniqueKeysWithValues: memories.map { ($0.id, $0) })
                snapshot.tasks = snapshot.tasks.filter { eligible($0.value, now: now) }
            }
            lock.lock()
            let count = snapshot.conversations.count + 2 * snapshot.memories.count + snapshot.tasks.count + 3
            lock.unlock()
            // Resolve the owner-fenced snapshot before replacing Spotlight.
            let conversationEntities = conversations(ids: nil)
            let memoryEntities = memories(ids: nil)
            let memoryNoteEntities = memoryNotes(ids: nil)
            let taskEntities = tasks(ids: nil)
            do {
            try await serialized {
                try requireValidOwner(uid)
                let index = CSSearchableIndex(name: indexName)
                try await index.deleteAllSearchableItems()
                try requireValidOwner(uid)
                try await index.indexAppEntities([OmiFolderEntity.conversations, OmiFolderEntity.memories], priority: 0)
                try requireValidOwner(uid)
                try await index.indexAppEntities([OmiListEntity.omi], priority: 0)
                try requireValidOwner(uid)
                try await index.indexAppEntities(conversationEntities, priority: 0)
                try requireValidOwner(uid)
                try await index.indexAppEntities(memoryEntities, priority: 0)
                try requireValidOwner(uid)
                try await index.indexAppEntities(memoryNoteEntities, priority: 0)
                try requireValidOwner(uid)
                try await index.indexAppEntities(taskEntities, priority: 0)
                try requireValidOwner(uid)
            }
            scheduleNextExpiry()
            SiriTelemetry.index(outcome: "ok", started: started, count: count)
            } catch {
                SiriTelemetry.index(outcome: SiriTelemetry.outcome(error), started: started, count: count)
                throw error
            }

        }
    }
}

/// Serializes the whole snapshot mutation and its Spotlight write. Reentrant
/// calls inside an operation stay on the same turn of the queue.
private enum SiriSnapshotQueueContext {
    @TaskLocal static var active = false
}

/// Serializes Spotlight writes, including a wipe racing an in-flight rebuild.
private actor SiriSpotlightGate {
    static let shared = SiriSpotlightGate()
    private var busy = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func run<T>(_ operation: () async throws -> T) async rethrows -> T {
        if busy {
            await withCheckedContinuation { waiters.append($0) }
        } else { busy = true }
        defer {
            if waiters.isEmpty { busy = false }
            else { waiters.removeFirst().resume() }
        }
        return try await operation()
    }
}
#endif
