import Foundation

/// Bridges committed local store mutations to Spotlight without making a cache
/// write depend on a best-effort system index write.
enum SiriIndexHooks {
  static func rebuild() {
    guard #available(macOS 15.4, *) else { return }
    Task {
      do { try await SiriIndexer.shared.rebuild() } catch {
        log("Siri index rebuild deferred: \(error.localizedDescription)")
      }
    }
  }

  static func memoryChanged(_ id: String) {
    guard #available(macOS 15.4, *) else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    Task {
      do {
        let entities = try await MemoryEntityQuery().entities(for: [id])
        if entities.isEmpty {
          try await SiriIndexer.shared.deleteMemory(id: id, expectedOwner: owner)
        } else {
          try await SiriIndexer.shared.indexMemories(entities, expectedOwner: owner)
        }
      } catch { log("Siri memory index deferred: \(error.localizedDescription)") }
    }
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
    guard #available(macOS 27, *) else { return }
    guard let owner = RuntimeOwnerIdentity.currentOwnerId() else { return }
    Task {
      do {
        let entities = try await ConversationEntityQuery().entities(for: [id])
        if entities.isEmpty {
          try await SiriIndexer.shared.deleteConversation(id: id, expectedOwner: owner)
        } else {
          try await SiriIndexer.shared.indexConversations(entities, expectedOwner: owner)
        }
      } catch { log("Siri conversation index deferred: \(error.localizedDescription)") }
    }
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
    Task {
      do {
        let entities = try await TaskEntityQuery().entities(for: ids)
        try await SiriIndexer.shared.indexTasks(entities, expectedOwner: owner)
        let current = Set(entities.map(\.id))
        for id in ids where !current.contains(id) {
          try await SiriIndexer.shared.deleteTask(id: id, expectedOwner: owner)
        }
      } catch { log("Siri task index deferred: \(error.localizedDescription)") }
    }
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
