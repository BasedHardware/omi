import Foundation

/// Coalesces sync mutations into at most 200 ids per Spotlight write. A single
/// drain per owner also prevents overlapping cache reads during large syncs.
actor SiriIndexBatcher {
  enum Kind: Hashable, Sendable { case memory, conversation, task }
  private let process: @Sendable (String, Kind, [String]) async -> Void
  private var pending: [String: [Kind: Set<String>]] = [:]
  private var draining: Set<String> = []
  private var idleWaiters: [String: [CheckedContinuation<Void, Never>]] = [:]

  init(process: @escaping @Sendable (String, Kind, [String]) async -> Void) { self.process = process }

  func enqueue(owner: String, kind: Kind, ids: [String]) {
    guard !owner.isEmpty, !ids.isEmpty else { return }
    var work = pending[owner] ?? [:]
    work[kind, default: []].formUnion(ids.filter { !$0.isEmpty })
    pending[owner] = work
    guard draining.insert(owner).inserted else { return }
    Task { await drain(owner: owner) }
  }

  func waitUntilIdle(owner: String) async {
    guard draining.contains(owner) else { return }
    await withCheckedContinuation { idleWaiters[owner, default: []].append($0) }
  }

  private func drain(owner: String) async {
    while var work = pending[owner], let kind = work.keys.first(where: { !work[$0, default: []].isEmpty }) {
      var remaining = work[kind, default: []]
      let ids = Array(remaining.sorted().prefix(200))
      remaining.subtract(ids)
      if remaining.isEmpty { work.removeValue(forKey: kind) } else { work[kind] = remaining }
      pending[owner] = work.isEmpty ? nil : work
      await process(owner, kind, ids)
    }
    draining.remove(owner)
    for waiter in idleWaiters.removeValue(forKey: owner) ?? [] { waiter.resume() }
  }
}

/// Bridges committed local store mutations to Spotlight without making a cache
/// write depend on a best-effort system index write.
enum SiriIndexHooks {
  @available(macOS 15.4, *)
  private static let batcher = SiriIndexBatcher { owner, kind, ids in
    guard RuntimeOwnerIdentity.currentOwnerId() == owner else { return }
    do {
      switch kind {
      case .memory:
        let entities = try await MemoryEntityQuery().entities(for: ids)
        try await SiriIndexer.shared.indexMemories(entities, expectedOwner: owner)
        let present = Set(entities.map(\.id))
        let missing = ids.filter { !present.contains($0) }
        try await SiriIndexer.shared.deleteMemories(ids: missing, expectedOwner: owner)
      case .conversation:
        if #available(macOS 27, *) {
          let entities = try await ConversationEntityQuery().entities(for: ids)
          try await SiriIndexer.shared.indexConversations(entities, expectedOwner: owner)
          let present = Set(entities.map(\.id))
          try await SiriIndexer.shared.deleteConversations(
            ids: ids.filter { !present.contains($0) }, expectedOwner: owner)
        }
      case .task:
        if #available(macOS 27, *) {
          let entities = try await TaskEntityQuery().entities(for: ids)
          try await SiriIndexer.shared.indexTasks(entities, expectedOwner: owner)
          let present = Set(entities.map(\.id))
          try await SiriIndexer.shared.deleteTasks(ids: ids.filter { !present.contains($0) }, expectedOwner: owner)
        }
      }
    } catch { log("Siri \(kind) index batch deferred: \(error.localizedDescription)") }
  }

  static func rebuild() {
    guard #available(macOS 15.4, *) else { return }
    Task {
      do { try await SiriIndexer.shared.rebuild() } catch {
        log("Siri index rebuild deferred: \(error.localizedDescription)")
      }
    }
  }

  static func memoryChanged(_ id: String) {
    memoriesChanged([id])
  }

  static func memoriesChanged(_ ids: [String]) {
    guard #available(macOS 15.4, *) else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    Task { await batcher.enqueue(owner: owner, kind: .memory, ids: ids) }
  }

  static func memoryDeleted(_ id: String) async {
    guard #available(macOS 15.4, *) else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    _ = await memoryDeleted(id, using: { try await SiriIndexer.shared.deleteMemory(id: $0, expectedOwner: owner) })
  }

  static func memoriesDeleted(_ ids: [String]) async {
    guard #available(macOS 15.4, *), !ids.isEmpty else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    do { try await SiriIndexer.shared.deleteMemories(ids: ids, expectedOwner: owner) } catch {
      log("Siri memory batch deletion pending retry: \(error.localizedDescription)")
    }
  }

  @discardableResult
  static func memoryDeleted(
    _ id: String, using deletion: @Sendable (String) async throws -> Void
  ) async -> Bool {
    do {
      try await deletion(id)
      return true
    } catch {
      log("Siri memory deletion pending retry: \(error.localizedDescription)")
      return false
    }
  }

  static func conversationChanged(_ id: String) {
    conversationsChanged([id])
  }

  static func conversationsChanged(_ ids: [String]) {
    guard #available(macOS 27, *) else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    Task { await batcher.enqueue(owner: owner, kind: .conversation, ids: ids) }
  }

  static func conversationDeleted(_ id: String) async {
    guard #available(macOS 27, *) else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    do { try await SiriIndexer.shared.deleteConversation(id: id, expectedOwner: owner) } catch {
      log("Siri conversation deletion pending retry: \(error.localizedDescription)")
    }
  }

  static func tasksChanged(_ ids: [String]) {
    guard #available(macOS 27, *) else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    Task { await batcher.enqueue(owner: owner, kind: .task, ids: ids) }
  }

  static func taskDeleted(_ id: String) async {
    guard #available(macOS 27, *) else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    do { try await SiriIndexer.shared.deleteTask(id: id, expectedOwner: owner) } catch {
      log("Siri task deletion pending retry: \(error.localizedDescription)")
    }
  }

  static func tasksDeleted(_ ids: [String]) async {
    guard #available(macOS 27, *), !ids.isEmpty else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    do { try await SiriIndexer.shared.deleteTasks(ids: ids, expectedOwner: owner) } catch {
      log("Siri task batch deletion pending retry: \(error.localizedDescription)")
    }
  }

  static func ownerChanged() {
    guard #available(macOS 15.4, *) else { return }
    Task {
      do { try await SiriIndexer.shared.preferenceOrOwnerChanged() } catch {
        log("Siri index owner transition pending wipe retry: \(error.localizedDescription)")
      }
    }
  }
}
