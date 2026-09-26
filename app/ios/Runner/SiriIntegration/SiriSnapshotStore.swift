import Foundation
import CoreSpotlight
import CryptoKit

/// Only the fields approved for Apple's on-device index are kept here.
final class SiriSnapshotStore {
    static let shared = SiriSnapshotStore()
    private let lock = NSLock()
    private let defaults = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12")!
    private let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.friend-app-with-wearable.ios12")!
    private let ownerKey = "siri.snapshot.owner"
    private let enabledKey = "siri.index.enabled"
    private let routeKey = "siri.pending.route"

    private struct Snapshot: Codable {
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
    private var expiryTask: _Concurrency.Task<Void, Never>?
    private var file: URL { container.appendingPathComponent("siri-index-snapshot.json") }
    private init() {
        snapshot = (try? Data(contentsOf: container.appendingPathComponent("siri-index-snapshot.json")))
            .flatMap { try? JSONDecoder().decode(Snapshot.self, from: $0) } ?? Snapshot()
    }
    var enabled: Bool { defaults.object(forKey: enabledKey) as? Bool ?? true }
    var owner: String? { defaults.string(forKey: ownerKey) }
    var indexName: String? {
        guard let owner else { return nil }
        return indexName(for: owner)
    }
    private func indexName(for uid: String) -> String {
        let digest = SHA256.hash(data: Data(uid.utf8)).prefix(12).map { String(format: "%02x", $0) }.joined()
        return "omi.siri.\(digest)"
    }
    private func validOwnerLocked() -> Bool {
        guard enabled, let uid = snapshot.ownerUid, !uid.isEmpty else { return false }
        return owner == uid && SiriSession.shared.currentConfig()?.uid == uid
    }
    private func requireValidOwner(_ expectedUid: String? = nil) throws {
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked(), expectedUid == nil || snapshot.ownerUid == expectedUid else {
            throw SiriSession.Failure.auth
        }
    }
    private func persist() throws {
        try JSONEncoder().encode(snapshot).write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: file.path)
    }
    private func mutate(_ update: () -> Void) throws {
        lock.lock(); defer { lock.unlock() }
        update()
        try persist()
    }
    private func mutateForOwner(_ uid: String, _ update: () -> Void) throws {
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked(), snapshot.ownerUid == uid else { throw SiriSession.Failure.auth }
        update()
        try persist()
    }
    private func cancelExpiryTask() {
        lock.lock(); defer { lock.unlock() }
        expiryTask?.cancel()
        expiryTask = nil
    }
    /// Keep a live Runner's index fresh at the next expiry. A 24 hour cap also
    /// checks long-lived records without retaining an unbounded sleep.
    private func scheduleNextExpiry() {
        lock.lock(); defer { lock.unlock() }
        expiryTask?.cancel()
        expiryTask = nil
        guard validOwnerLocked() else { return }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        guard let next = snapshot.memories.values.compactMap(\.expiresAtMs).filter({ $0 > now }).min() else { return }
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

    func bind(uid: String) async throws {
        guard !uid.isEmpty else { throw SiriSession.Failure.auth }
        lock.lock(); let snapshotOwner = snapshot.ownerUid; lock.unlock()
        if snapshotOwner != uid || owner != uid { try await wipe() }
        try mutate { snapshot.ownerUid = uid }
        defaults.set(uid, forKey: ownerKey)
    }
    func setEnabled(_ value: Bool) async throws {
        defaults.set(value, forKey: enabledKey)
        if !value {
            cancelExpiryTask()
            try await removeIndex()
        }
        else { try await rebuildIndex() }
    }
    func wipe() async throws {
        cancelExpiryTask()
        lock.lock(); let snapshotOwner = snapshot.ownerUid; lock.unlock()
        let owners = Set([owner, snapshotOwner, SiriSession.shared.currentConfig()?.uid].compactMap { $0 })
        try mutate { snapshot = Snapshot() }
        defaults.removeObject(forKey: ownerKey)
        defaults.removeObject(forKey: routeKey)
        SiriSession.shared.clear()
        try await removeIndex(owners: owners)
    }
    private func removeIndex(owners explicitOwners: Set<String>? = nil) async throws {
        lock.lock(); let snapshotOwner = snapshot.ownerUid; lock.unlock()
        let owners = explicitOwners ?? Set([owner, snapshotOwner, SiriSession.shared.currentConfig()?.uid].compactMap { $0 })
        try await SiriSpotlightGate.shared.run {
            for uid in owners {
                try await CSSearchableIndex(name: indexName(for: uid)).deleteAllSearchableItems()
            }
        }
    }
    func upsert(_ values: [SiriConversation], uid: String) async throws {
        try mutateForOwner(uid) {
        for value in values where !value.id.isEmpty {
            snapshot.conversations[value.id] = Conversation(id: value.id, title: value.title,
                summary: value.summary, startedAtMs: value.startedAtMs, updatedAtMs: value.updatedAtMs)
        }
        }
        try await rebuildIndex()
    }
    func upsert(_ values: [SiriMemory], uid: String) async throws {
        try mutateForOwner(uid) {
        for value in values where !value.id.isEmpty {
            snapshot.memories[value.id] = Memory(id: value.id, content: value.content, createdAtMs: value.createdAtMs, expiresAtMs: value.expiresAtMs)
        }
        }
        try await rebuildIndex()
    }
    func upsert(_ values: [SiriTask], uid: String) async throws {
        try mutateForOwner(uid) {
        for value in values where !value.id.isEmpty {
            snapshot.tasks[value.id] = Task(id: value.id, title: value.title, completed: value.completed,
                createdAtMs: value.createdAtMs, dueAtMs: value.dueAtMs, completedAtMs: value.completedAtMs)
        }
        }
        try await rebuildIndex()
    }
    func delete(type: String, ids: [String], uid: String) async throws {
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
        // Removing first prevents a deleted item surviving an incremental index.
        try await removeIndex()
        try await rebuildIndex()
    }
    func pendingRoute() -> String? {
        let route = defaults.string(forKey: routeKey)
        defaults.removeObject(forKey: routeKey)
        return route
    }
    func setPendingRoute(_ route: String) { defaults.set(route, forKey: routeKey) }
    func allowsDonation(uid: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        return validOwnerLocked() && snapshot.ownerUid == uid
    }

    @available(iOS 27.0, *)
    func conversations(ids: [String]?) -> [ConversationEntity] {
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return [] }
        let selected = snapshot.conversations.values.filter { ids == nil || ids!.contains($0.id) }
        return selected.map { ConversationEntity(id: $0.id, name: $0.title, content: $0.summary,
            creationDate: Date(timeIntervalSince1970: Double($0.startedAtMs) / 1000),
            modificationDate: Date(timeIntervalSince1970: Double($0.updatedAtMs) / 1000)) }
    }
    @available(iOS 27.0, *)
    func memoryNotes(ids: [String]?) -> [ConversationEntity] {
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return [] }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        return snapshot.memories.values.filter { (ids == nil || ids!.contains($0.id)) && ($0.expiresAtMs == nil || $0.expiresAtMs! > now) }.map {
            ConversationEntity(memoryId: $0.id, content: $0.content,
                creationDate: Date(timeIntervalSince1970: Double($0.createdAtMs) / 1000))
        }
    }
    @available(iOS 27.0, *)
    func memories(ids: [String]?) -> [MemoryEntity] {
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return [] }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        return snapshot.memories.values.filter { (ids == nil || ids!.contains($0.id)) && ($0.expiresAtMs == nil || $0.expiresAtMs! > now) }.map {
            MemoryEntity(id: $0.id, content: $0.content,
                creationDate: Date(timeIntervalSince1970: Double($0.createdAtMs) / 1000)) }
    }
    @available(iOS 27.0, *)
    func tasks(ids: [String]?) -> [TaskEntity] {
        lock.lock(); defer { lock.unlock() }
        guard validOwnerLocked() else { return [] }
        return snapshot.tasks.values.filter { ids == nil || ids!.contains($0.id) }.map {
            TaskEntity(id: $0.id, title: $0.title, isCompleted: $0.completed,
                creationDate: Date(timeIntervalSince1970: Double($0.createdAtMs) / 1000),
                dueDate: $0.dueAtMs.map { Date(timeIntervalSince1970: Double($0) / 1000) },
                completionDate: $0.completedAtMs.map { Date(timeIntervalSince1970: Double($0) / 1000) }) }
    }
    func rebuildIndex() async throws {
        let started = Date()
        guard #available(iOS 27.0, *) else { return }
        try requireValidOwner()
        guard let uid = owner, let indexName else { throw SiriSession.Failure.auth }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        try mutateForOwner(uid) {
            snapshot.conversations = snapshot.conversations.filter { $0.value.startedAtMs > now - 180 * 86_400_000 }
            let newest = snapshot.conversations.values.sorted { $0.startedAtMs > $1.startedAtMs }.prefix(2000)
            snapshot.conversations = Dictionary(uniqueKeysWithValues: newest.map { ($0.id, $0) })
            snapshot.memories = snapshot.memories.filter { $0.value.expiresAtMs == nil || $0.value.expiresAtMs! > now }
            let memories = snapshot.memories.values.sorted { $0.createdAtMs > $1.createdAtMs }.prefix(5000)
            snapshot.memories = Dictionary(uniqueKeysWithValues: memories.map { ($0.id, $0) })
            snapshot.tasks = snapshot.tasks.filter { !$0.value.completed || ($0.value.completedAtMs ?? 0) > now - 30 * 86_400_000 }
        }
        lock.lock()
        let count = snapshot.conversations.count + snapshot.memories.count + snapshot.tasks.count + 3
        lock.unlock()
        do {
        try await SiriSpotlightGate.shared.run {
            try requireValidOwner(uid)
            let index = CSSearchableIndex(name: indexName)
            try await index.deleteAllSearchableItems()
            try requireValidOwner(uid)
            try await index.indexAppEntities([OmiFolderEntity.conversations, OmiFolderEntity.memories], priority: 0)
            try requireValidOwner(uid)
            try await index.indexAppEntities([OmiListEntity.omi], priority: 0)
            try requireValidOwner(uid)
            try await index.indexAppEntities(conversations(ids: nil), priority: 0)
            try requireValidOwner(uid)
            try await index.indexAppEntities(memories(ids: nil), priority: 0)
            try requireValidOwner(uid)
            try await index.indexAppEntities(tasks(ids: nil), priority: 0)
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
