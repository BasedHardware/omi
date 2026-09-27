import AppIntents
import CoreSpotlight
import CryptoKit
import Foundation

// Core Spotlight documents ordinary index operations as thread safe. This
// integration never enters its separate manual batch mode, which has a stricter
// single-thread rule. The SDK has not annotated CSSearchableIndex as Sendable.
extension CSSearchableIndex: @unchecked @retroactive Sendable {}

/// A memory returned by `.notes.createNote` is also a Notes schema entity.
enum SiriMemoryIndexRepresentation: Sendable, Equatable {
  case custom, note
}

/// Owns the per-account Spotlight index. All public entry points are safe to call
/// repeatedly; the preference and owner are checked before any content is sent.
@available(macOS 15.4, *)
actor SiriIndexer {
  static let shared = SiriIndexer()
  nonisolated static func supportsSpotlightIndexing(_ version: OperatingSystemVersion) -> Bool {
    version.majorVersion >= 27
  }

  @available(macOS 27, *)
  nonisolated static func deleteMemoryRepresentations(
    ids: [String],
    using delete: @Sendable (SiriMemoryIndexRepresentation, [String]) async throws -> Void
  ) async throws {
    for chunk in ids.chunkedSiriIndex(200) {
      try await delete(.custom, chunk)
      try await delete(.note, chunk)
    }
  }

  @available(macOS 27, *)
  nonisolated private static func deleteMemoryRepresentations(ids: [String], from index: CSSearchableIndex) async throws
  {
    try await Self.deleteMemoryRepresentations(ids: ids) { representation, chunk in
      switch representation {
      case .custom: try await index.deleteAppEntities(identifiedBy: chunk, ofType: MemoryEntity.self)
      case .note: try await index.deleteAppEntities(identifiedBy: chunk, ofType: ConversationEntity.self)
      }
    }
  }
  private let ownerKey = "siriIndexedOwnerID"
  private var indexedOwner: String?
  private var activeOperations = 0
  private var idleWaiters: [CheckedContinuation<Void, Never>] = []
  private var transitionInProgress = false
  private var transitionWaiters: [CheckedContinuation<Void, Never>] = []
  private var indexedMemoryExpirations: [String: Date] = [:]
  private var indexedConversationCutoffs: [String: Date] = [:]
  private var indexedTaskCutoffs: [String: Date] = [:]
  private var memoryExpiryTimer: Task<Void, Never>?
  private var rebuildRetryTask: Task<Void, Never>?
  private var rebuildRetryAttempt = 0

  nonisolated static func rebuildRetryDelay(attempt: Int) -> Int {
    min(5 * (1 << min(max(attempt, 0), 6)), 300)
  }

  /// Keep the existing Spotlight index until every local projection succeeds.
  func prepareThenReplace<Value>(
    prepare: () async throws -> Value,
    replace: (Value) async throws -> Void
  ) async throws {
    let value = try await prepare()
    try await replace(value)
  }

  private func cancelRebuildRetry() {
    rebuildRetryTask?.cancel()
    rebuildRetryTask = nil
    rebuildRetryAttempt = 0
  }

  private func scheduleRebuildRetry(owner: String) {
    let delay = Self.rebuildRetryDelay(attempt: rebuildRetryAttempt)
    rebuildRetryAttempt += 1
    rebuildRetryTask?.cancel()
    rebuildRetryTask = Task { [weak self] in
      try? await Task.sleep(for: .seconds(delay))
      guard !Task.isCancelled, RuntimeOwnerIdentity.currentOwnerId() == owner else { return }
      do { try await self?.rebuild() } catch {
        log("Siri index rebuild retry pending: \(error.localizedDescription)")
      }
    }
  }

  private init() {
    indexedOwner = UserDefaults.standard.string(forKey: ownerKey)
  }

  nonisolated static func indexName(bundleID: String, owner: String) -> String {
    let digest = SHA256.hash(data: Data(owner.utf8))
    let suffix = digest.prefix(16).map { String(format: "%02x", $0) }.joined()
    return "omi.siri.\(bundleID).\(suffix)"
  }

  nonisolated private func index(for owner: String) -> CSSearchableIndex {
    CSSearchableIndex(
      name: Self.indexName(bundleID: Bundle.main.bundleIdentifier ?? "com.omi.desktop.unknown", owner: owner))
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
    indexedConversationCutoffs.removeAll()
    indexedTaskCutoffs.removeAll()
  }

  private func scheduleNextMemoryExpiry(owner: String) {
    memoryExpiryTimer?.cancel()
    guard
      let next = SiriIndexScope.nextCutoff(
        Array(indexedMemoryExpirations.values) + Array(indexedConversationCutoffs.values)
          + Array(indexedTaskCutoffs.values))
    else {
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
    guard #available(macOS 27, *) else { return }
    let now = Date()
    let next = SiriIndexScope.nextCutoff(
      Array(indexedMemoryExpirations.values) + Array(indexedConversationCutoffs.values)
        + Array(indexedTaskCutoffs.values))
    guard next.map({ $0 <= now }) == true else {
      scheduleNextMemoryExpiry(owner: expectedOwner)
      return
    }
    if indexedConversationCutoffs.values.contains(where: { $0 <= now })
      || indexedTaskCutoffs.values.contains(where: { $0 <= now })
    {
      do { try await rebuild(now: now) } catch {
        log("Siri age cutoff rebuild pending retry: \(error.localizedDescription)")
      }
      return
    }
    do {
      guard let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
      defer { finishOperation() }
      let due = try await SiriMemoryExpirySweep.deleteDue(indexedMemoryExpirations, now: now) { ids in
        try await Self.deleteMemoryRepresentations(ids: ids, from: index)
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
          cancelRebuildRetry()
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
    guard Self.supportsSpotlightIndexing(ProcessInfo.processInfo.operatingSystemVersion), #available(macOS 27, *) else {
      // A pre-27 build may have left a legacy custom-memory index behind.
      // The persisted owner is removed only after Spotlight confirms deletion.
      if indexedOwner != nil { try await wipe() }
      return
    }
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
      cancelRebuildRetry()
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
    indexedConversationCutoffs.removeValue(forKey: id)
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  func deleteConversations(ids: [String], expectedOwner: String) async throws {
    guard !ids.isEmpty, let index = try await operationIndex(expectedOwner: expectedOwner), #available(macOS 27, *)
    else { return }
    defer { finishOperation() }
    for chunk in ids.chunkedSiriIndex(200) {
      try await index.deleteAppEntities(identifiedBy: chunk, ofType: ConversationEntity.self)
    }
    for id in ids { indexedConversationCutoffs.removeValue(forKey: id) }
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  func deleteMemory(id: String, expectedOwner: String) async throws {
    guard #available(macOS 27, *) else { return }
    guard let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    try await Self.deleteMemoryRepresentations(ids: [id], from: index)
    indexedMemoryExpirations.removeValue(forKey: id)
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  func deleteMemories(ids: [String], expectedOwner: String) async throws {
    guard #available(macOS 27, *) else { return }
    guard !ids.isEmpty, let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    try await Self.deleteMemoryRepresentations(ids: ids, from: index)
    for id in ids { indexedMemoryExpirations.removeValue(forKey: id) }
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  func deleteTask(id: String, expectedOwner: String) async throws {
    guard let index = try await operationIndex(expectedOwner: expectedOwner), #available(macOS 27, *) else { return }
    defer { finishOperation() }
    try await index.deleteAppEntities(identifiedBy: [id], ofType: TaskEntity.self)
    indexedTaskCutoffs.removeValue(forKey: id)
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  func deleteTasks(ids: [String], expectedOwner: String) async throws {
    guard !ids.isEmpty, let index = try await operationIndex(expectedOwner: expectedOwner), #available(macOS 27, *)
    else { return }
    defer { finishOperation() }
    for chunk in ids.chunkedSiriIndex(200) {
      try await index.deleteAppEntities(identifiedBy: chunk, ofType: TaskEntity.self)
    }
    for id in ids { indexedTaskCutoffs.removeValue(forKey: id) }
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  /// Resolve the requested IDs after acquiring the owner operation slot. A
  /// query that fetched before a local delete must never restore that row
  /// after its delete operation has finished.
  @available(macOS 27, *)
  func reindexConversations(ids: [String], expectedOwner: String) async throws {
    let ids = Array(Set(ids.filter { !$0.isEmpty }))
    guard !ids.isEmpty, let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    let resolved = try await ConversationEntityQuery().entities(for: ids)
    let noteIDs = resolved.filter { $0.folder?.id == "memories" }.map(\.id)
    let noteRecords = try await MemoryStorage.shared.getSiriMemoryRecords(backendIds: noteIDs)
    var validNotes: [String: MemoryRecord] = [:]
    for record in noteRecords where SiriIndexScope.memory(record, now: Date()) {
      if let id = record.backendId { validNotes[id] = record }
    }
    let entities = resolved.filter { $0.folder?.id != "memories" || validNotes[$0.id] != nil }
    let present = Set(entities.map(\.id))
    for chunk in ids.filter({ !present.contains($0) }).chunkedSiriIndex(200) {
      try await index.deleteAppEntities(identifiedBy: chunk, ofType: ConversationEntity.self)
    }
    for chunk in entities.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
    for entity in entities {
      if entity.folder?.id == "memories", let record = validNotes[entity.id] {
        indexedMemoryExpirations[entity.id] = SiriIndexScope.memoryNextCutoff(
          expiresAt: record.expiresAt, invalidAt: record.siriLedgerMetadata["invalid_at"])
      } else {
        indexedConversationCutoffs[entity.id] = entity.creationDate?.addingTimeInterval(
          SiriIndexScope.conversationAge)
      }
    }
    for id in ids where !present.contains(id) {
      indexedConversationCutoffs.removeValue(forKey: id)
      indexedMemoryExpirations.removeValue(forKey: id)
    }
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  @available(macOS 27, *)
  func reindexMemories(ids: [String], expectedOwner: String) async throws {
    let ids = Array(Set(ids.filter { !$0.isEmpty }))
    guard !ids.isEmpty, let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    let records = try await MemoryStorage.shared.getSiriMemoryRecords(backendIds: ids)
    let projection = Self.projectMemoryRepresentations(records, now: Date())
    let present = Set(projection.custom.map(\.id))
    try await Self.deleteMemoryRepresentations(ids: ids.filter { !present.contains($0) }, from: index)
    for chunk in projection.custom.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
    for chunk in projection.notes.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
    for entity in projection.custom { indexedMemoryExpirations[entity.id] = entity.eligibilityCutoff }
    for id in ids where !present.contains(id) { indexedMemoryExpirations.removeValue(forKey: id) }
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  @available(macOS 27, *)
  func reindexTasks(ids: [String], expectedOwner: String) async throws {
    let ids = Array(Set(ids.filter { !$0.isEmpty }))
    guard !ids.isEmpty, let index = try await operationIndex(expectedOwner: expectedOwner) else { return }
    defer { finishOperation() }
    let entities = try await TaskEntityQuery().entities(for: ids)
    let present = Set(entities.map(\.id))
    for chunk in ids.filter({ !present.contains($0) }).chunkedSiriIndex(200) {
      try await index.deleteAppEntities(identifiedBy: chunk, ofType: TaskEntity.self)
    }
    for chunk in entities.chunkedSiriIndex(200) { try await index.indexAppEntities(chunk, priority: 0) }
    for entity in entities {
      indexedTaskCutoffs[entity.id] =
        entity.isCompleted
        ? entity.completionDate?.addingTimeInterval(SiriIndexScope.completedTaskAge) : nil
    }
    for id in ids where !present.contains(id) { indexedTaskCutoffs.removeValue(forKey: id) }
    scheduleNextMemoryExpiry(owner: expectedOwner)
  }

  @available(macOS 27, *)
  struct MemoryProjection {
    let custom: [MemoryEntity]
    let notes: [ConversationEntity]
  }

  @available(macOS 27, *)
  nonisolated static func projectMemoryRepresentations(_ records: [MemoryRecord], now: Date) -> MemoryProjection {
    let eligible = records.filter { SiriIndexScope.memory($0, now: now) }
    return MemoryProjection(custom: eligible.map(MemoryEntity.init), notes: eligible.map(ConversationEntity.init))
  }

  @available(macOS 27, *)
  private struct RebuildProjection {
    let conversations: [ConversationEntity]
    let memories: [MemoryEntity]
    let memoryNotes: [ConversationEntity]
    let tasks: [TaskEntity]
    var count: Int { 3 + conversations.count + memories.count + memoryNotes.count + tasks.count }
  }

  @available(macOS 27, *)
  private func loadRebuildProjection(now: Date) async throws -> RebuildProjection {
    let records = try await TranscriptionStorage.shared.getSiriEligibleSessions(
      limit: SiriIndexScope.conversationLimit,
      since: now.addingTimeInterval(-SiriIndexScope.conversationAge))
    let conversations = SiriIndexScope.eligibleConversations(records, now: now).map(ConversationEntity.init)
    let memories = try await MemoryStorage.shared.getSiriMemoryCandidates()
    let selectedMemories = SiriIndexScope.capped(
      memories.filter { SiriIndexScope.memory($0, now: now) }, at: SiriIndexScope.memoryLimit
    )
    let memoryProjection = Self.projectMemoryRepresentations(selectedMemories, now: now)
    let tasks = try await ActionItemStorage.shared.getAllLocalActionItems()
    var taskEntities: [TaskEntity] = []
    for task in tasks where !task.id.hasPrefix("local_") && !task.isRetired {
      guard let record = try await ActionItemStorage.shared.getActionItemByBackendId(task.id),
        SiriIndexScope.task(record, now: now)
      else { continue }
      taskEntities.append(TaskEntity(record))
    }
    return RebuildProjection(
      conversations: conversations, memories: memoryProjection.custom,
      memoryNotes: memoryProjection.notes, tasks: taskEntities)
  }

  func rebuild(now: Date = Date()) async throws {
    guard Self.supportsSpotlightIndexing(ProcessInfo.processInfo.operatingSystemVersion), #available(macOS 27, *) else {
      if indexedOwner != nil { try await wipe() }
      return
    }
    let started = Date()
    guard let index = try await operationIndex() else { return }
    defer { finishOperation() }
    var count = 0
    do {
      try await prepareThenReplace(prepare: { try await loadRebuildProjection(now: now) }) { projection in
        count = projection.count
        try await index.deleteAllSearchableItems()
        try await index.indexAppEntities([OmiFolderEntity.conversations, .memories], priority: 0)
        try await index.indexAppEntities([OmiListEntity.omi], priority: 0)
        for chunk in projection.conversations.chunkedSiriIndex(200) {
          try await index.indexAppEntities(chunk, priority: 0)
        }
        for chunk in projection.memories.chunkedSiriIndex(200) {
          try await index.indexAppEntities(chunk, priority: 0)
        }
        for chunk in projection.memoryNotes.chunkedSiriIndex(200) {
          try await index.indexAppEntities(chunk, priority: 0)
        }
        for chunk in projection.tasks.chunkedSiriIndex(200) {
          try await index.indexAppEntities(chunk, priority: 0)
        }
        resetMemoryExpirations()
        for entity in projection.conversations {
          indexedConversationCutoffs[entity.id] = entity.creationDate?.addingTimeInterval(
            SiriIndexScope.conversationAge)
        }
        for entity in projection.memories { indexedMemoryExpirations[entity.id] = entity.eligibilityCutoff }
        for entity in projection.tasks {
          indexedTaskCutoffs[entity.id] =
            entity.isCompleted
            ? entity.completionDate?.addingTimeInterval(SiriIndexScope.completedTaskAge) : nil
        }
      }
      if let indexedOwner { scheduleNextMemoryExpiry(owner: indexedOwner) }
      cancelRebuildRetry()
      await PostHogManager.shared.track(
        "Siri Index Rebuilt",
        properties: [
          "platform": "macos", "entity_counts": count,
          "duration_ms": Int(Date().timeIntervalSince(started) * 1_000), "outcome": "ok",
        ])
    } catch {
      if let indexedOwner { scheduleRebuildRetry(owner: indexedOwner) }
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
