import AppIntents
import CoreSpotlight
import CryptoKit
import Foundation

// Core Spotlight documents ordinary index operations as thread safe. This
// integration never enters its separate manual batch mode, which has a stricter
// single-thread rule. The SDK has not annotated CSSearchableIndex as Sendable.
extension CSSearchableIndex: @unchecked @retroactive Sendable {}

/// Owns the per-account Spotlight index. All public entry points are safe to call
/// repeatedly; the preference and owner are checked before any content is sent.
@available(macOS 15.4, *)
actor SiriIndexer {
  static let shared = SiriIndexer()
  private let ownerKey = "siriIndexedOwnerID"
  private var indexedOwner: String?
  private var activeOperations = 0
  private var idleWaiters: [CheckedContinuation<Void, Never>] = []
  private var transitionInProgress = false
  private var transitionWaiters: [CheckedContinuation<Void, Never>] = []
  private var indexedMemoryExpirations: [String: Date] = [:]
  private var memoryExpiryTimer: Task<Void, Never>?

  private init() {
    indexedOwner = UserDefaults.standard.string(forKey: ownerKey)
  }

  nonisolated private func index(for owner: String) -> CSSearchableIndex {
    let digest = SHA256.hash(data: Data(owner.utf8))
    let suffix = digest.prefix(16).map { String(format: "%02x", $0) }.joined()
    return CSSearchableIndex(name: "omi.siri.\(suffix)")
  }

  private func awaitTransition() async {
    while transitionInProgress {
      await withCheckedContinuation { transitionWaiters.append($0) }
    }
  }

  private func acquireTransition() async {
    while true {
      await awaitTransition()
      if !transitionInProgress {
        transitionInProgress = true
        return
      }
    }
  }

  private func awaitIdle() async {
    if activeOperations > 0 {
      await withCheckedContinuation { idleWaiters.append($0) }
    }
  }

  private func finishOperation() {
    activeOperations -= 1
    if activeOperations == 0 {
      let waiters = idleWaiters
      idleWaiters.removeAll()
      for waiter in waiters { waiter.resume() }
    }
  }

  private func finishTransition() {
    transitionInProgress = false
    let waiters = transitionWaiters
    transitionWaiters.removeAll()
    for waiter in waiters { waiter.resume() }
  }

  private func resetMemoryExpirations() {
    memoryExpiryTimer?.cancel()
    memoryExpiryTimer = nil
    indexedMemoryExpirations.removeAll()
  }

  private func scheduleNextMemoryExpiry(owner: String) {
    memoryExpiryTimer?.cancel()
    guard let next = SiriMemoryExpirySweep.nextExpiry(indexedMemoryExpirations) else {
      memoryExpiryTimer = nil
      return
    }
    // Recheck within an hour if the wall clock moves or the machine sleeps.
    let delay = min(max(next.timeIntervalSinceNow, 0), 3_600)
    memoryExpiryTimer = Task { [weak self] in
      try? await Task.sleep(for: .seconds(delay))
      guard !Task.isCancelled else { return }
      await self?.expireDueMemories(expectedOwner: owner)
    }
  }

  private func expireDueMemories(expectedOwner: String) async {
    let now = Date()
    guard SiriMemoryExpirySweep.nextExpiry(indexedMemoryExpirations).map({ $0 <= now }) == true else {
      scheduleNextMemoryExpiry(owner: expectedOwner)
      return
    }
    do {
      guard let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
      defer { finishOperation() }
      let due = try await SiriMemoryExpirySweep.deleteDue(indexedMemoryExpirations, now: now) { ids in
        for chunk in ids.chunkedSiriIndex(200) {
          try await index.deleteAppEntities(identifiedBy: chunk, ofType: MemoryEntity.self)
        }
      }
      for id in due { indexedMemoryExpirations.removeValue(forKey: id) }
      scheduleNextMemoryExpiry(owner: expectedOwner)
    } catch {
      log("Siri memory expiry deletion pending retry: \(error.localizedDescription)")
      memoryExpiryTimer?.cancel()
      memoryExpiryTimer = Task { [weak self] in
        try? await Task.sleep(for: .seconds(5))
        guard !Task.isCancelled else { return }
        await self?.expireDueMemories(expectedOwner: expectedOwner)
      }
    }
  }

  private func operationIndex(expectedOwner: String? = nil) async throws -> CSSearchableIndex? {
    while true {
      await awaitTransition()
      if transitionInProgress { continue }
      let current = RuntimeOwnerIdentity.currentOwnerId()
      if indexedOwner != current {
        transitionInProgress = true
        await awaitIdle()
        do {
          indexedOwner = try await SiriIndexOwnerFence.transition(from: indexedOwner, to: current) { owner in
            try await self.index(for: owner).deleteAllSearchableItems()
          }
          resetMemoryExpirations()
          UserDefaults.standard.set(current, forKey: ownerKey)
          finishTransition()
        } catch {
          finishTransition()
          throw error
        }
        continue
      }
      if activeOperations > 0 {
        await awaitIdle()
        continue
      }
      guard SiriIntegrationSettings.isEnabled, let current, !current.isEmpty,
        expectedOwner == nil || expectedOwner == current
      else { return nil }
      activeOperations += 1
      return index(for: current)
    }
  }

  func preferenceOrOwnerChanged() async throws {
    if !SiriIntegrationSettings.isEnabled {
      try await wipe()
      return
    }
    try await rebuild()
  }

  func wipe() async throws {
    await acquireTransition()
    await awaitIdle()
    do {
      if let indexedOwner { try await index(for: indexedOwner).deleteAllSearchableItems() }
      resetMemoryExpirations()
      indexedOwner = nil
      UserDefaults.standard.removeObject(forKey: ownerKey)
      finishTransition()
    } catch {
      finishTransition()
      throw error
    }
  }

  func deleteConversation(id: String, expectedOwner: String) async throws {
    guard let index = try await operationIndex(expectedOwner: expectedOwner), #available(macOS 27, *) else { return }
    defer { finishOperation() }
    try await index.deleteAppEntities(identifiedBy: [id], ofType: ConversationEntity.self)
  }

  func deleteMemory(id: String, expectedOwner: String) async throws {
    guard let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    try await index.deleteAppEntities(identifiedBy: [id], ofType: MemoryEntity.self)
    indexedMemoryExpirations.removeValue(forKey: id)
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  func deleteMemories(ids: [String], expectedOwner: String) async throws {
    guard !ids.isEmpty, let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    for chunk in ids.chunkedSiriIndex(200) {
      try await index.deleteAppEntities(identifiedBy: chunk, ofType: MemoryEntity.self)
    }
    for id in ids { indexedMemoryExpirations.removeValue(forKey: id) }
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  func deleteTask(id: String, expectedOwner: String) async throws {
    guard let index = try await operationIndex(expectedOwner: expectedOwner), #available(macOS 27, *) else { return }
    defer { finishOperation() }
    try await index.deleteAppEntities(identifiedBy: [id], ofType: TaskEntity.self)
  }

  func deleteTasks(ids: [String], expectedOwner: String) async throws {
    guard !ids.isEmpty, let index = try await operationIndex(expectedOwner: expectedOwner), #available(macOS 27, *)
    else { return }
    defer { finishOperation() }
    for chunk in ids.chunkedSiriIndex(200) {
      try await index.deleteAppEntities(identifiedBy: chunk, ofType: TaskEntity.self)
    }
  }

  @available(macOS 27, *)
  func indexConversations(_ entities: [ConversationEntity], expectedOwner: String) async throws {
    guard let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    for chunk in entities.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
  }

  func indexMemories(_ entities: [MemoryEntity], expectedOwner: String) async throws {
    guard let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    for chunk in entities.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
    for entity in entities { indexedMemoryExpirations[entity.id] = entity.expiresAt }
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  @available(macOS 27, *)
  func indexTasks(_ entities: [TaskEntity], expectedOwner: String) async throws {
    guard let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    for chunk in entities.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
  }

  func rebuild(now: Date = Date()) async throws {
    let started = Date()
    guard let index = try await operationIndex() else { return }
    defer { finishOperation() }
    var count = 0
    do {
      try await index.deleteAllSearchableItems()
      resetMemoryExpirations()
      if #available(macOS 27, *) {
        try await index.indexAppEntities([OmiFolderEntity.conversations, .memories], priority: 0)
        try await index.indexAppEntities([OmiListEntity.omi], priority: 0)
        count += 3
        let records = try await TranscriptionStorage.shared.getSiriEligibleSessions(
          limit: SiriIndexScope.conversationLimit,
          since: now.addingTimeInterval(-SiriIndexScope.conversationAge))
        let entities = SiriIndexScope.capped(
          records.filter { SiriIndexScope.conversation($0, now: now) },
          at: SiriIndexScope.conversationLimit
        ).map(ConversationEntity.init)
        for chunk in entities.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
        count += entities.count
      }

      let memories = try await MemoryStorage.shared.getLocalMemories(
        limit: SiriIndexScope.memoryLimit, backendOnly: true, expiresAfter: now)
      let memoryEntities = memories.map(MemoryEntity.init)
      for chunk in memoryEntities.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
      for entity in memoryEntities { indexedMemoryExpirations[entity.id] = entity.expiresAt }
      if let indexedOwner { scheduleNextMemoryExpiry(owner: indexedOwner) }
      count += memoryEntities.count

      if #available(macOS 27, *) {
        let tasks = try await ActionItemStorage.shared.getAllLocalActionItems()
        var taskEntities: [TaskEntity] = []
        for task in tasks
        where !task.id.hasPrefix("local_") && !task.isRetired
          && SiriIndexScope.task(
            backendId: task.id, deleted: false, completed: task.completed,
            completedAt: task.completedAt, taskStatus: task.taskStatus, now: now)
        {
          guard let record = try await ActionItemStorage.shared.getActionItemByBackendId(task.id),
            SiriIndexScope.task(
              backendId: record.backendId, deleted: record.deleted,
              completed: record.completed, completedAt: record.completedAt,
              taskStatus: record.taskStatus, now: now)
          else { continue }
          taskEntities.append(TaskEntity(record))
        }
        for chunk in taskEntities.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
        count += taskEntities.count
      }
      await PostHogManager.shared.track(
        "Siri Index Rebuilt",
        properties: [
          "platform": "macos", "entity_counts": count,
          "duration_ms": Int(Date().timeIntervalSince(started) * 1_000), "outcome": "ok",
        ])
    } catch {
      await PostHogManager.shared.track(
        "Siri Index Rebuilt",
        properties: [
          "platform": "macos", "entity_counts": count,
          "duration_ms": Int(Date().timeIntervalSince(started) * 1_000), "outcome": "server",
        ])
      throw error
    }
  }
}

enum SiriIndexOwnerFence {
  static func transition(
    from previous: String?, to current: String?,
    wipe: @Sendable (String) async throws -> Void
  ) async throws -> String? {
    if previous != current, let previous { try await wipe(previous) }
    return current
  }
}

extension Array {
  fileprivate func chunkedSiriIndex(_ size: Int) -> [[Element]] {
    stride(from: 0, to: count, by: size).map { Array(self[$0..<Swift.min($0 + size, count)]) }
  }
}
