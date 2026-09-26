import Foundation

enum SiriFailure: Error, Equatable {
  case auth, network, quota, rateLimited, server, cancelled, unsupported

  var outcome: String {
    switch self {
    case .auth: "auth"
    case .network: "network"
    case .quota: "quota"
    case .rateLimited: "rate_limited"
    case .server: "server"
    case .cancelled: "cancelled"
    case .unsupported: "server"
    }
  }

  func message(for action: String) -> String {
    let changed = action == "complete" ? "the task wasn't changed" : "nothing was saved"
    switch self {
    case .auth: return "Open Omi and sign in first."
    case .network:
      return action == "open" ? "I couldn't reach Omi to open that." : "I couldn't reach Omi, so \(changed)."
    case .quota: return "Your Omi limit has been reached, so \(changed)."
    case .rateLimited: return "Omi is receiving too many requests. Try again shortly."
    case .server:
      return action == "open"
        ? "Omi couldn't open that right now."
        : action == "complete" ? "Omi couldn't change the task right now." : "Omi couldn't save that right now."
    case .cancelled: return "The action was cancelled."
    case .unsupported:
      return action == "open"
        ? "That item is no longer available in Omi."
        : action == "complete" ? "Omi can only change task completion through Siri." : "Tell Omi what to save."
    }
  }

  static func classify(_ error: Error) -> SiriFailure {
    if let scoped = error as? SiriActionFailure { return scoped.failure }
    if let failure = error as? SiriFailure { return failure }
    if error is CancellationError { return .cancelled }
    if let error = error as? APIError {
      switch error {
      case .unauthorized: return .auth
      case .httpError(let status, _):
        switch status {
        case 401, 403: return .auth
        case 402: return .quota
        case 429: return .rateLimited
        default: return .server
        }
      case .syncRateLimited: return .rateLimited
      case .invalidResponse, .decodingError: return .server
      default: return .server
      }
    }
    if let error = error as? URLError {
      return error.code == .cancelled ? .cancelled : .network
    }
    return .server
  }
}

struct SiriActionFailure: LocalizedError, Equatable {
  let action: String
  let failure: SiriFailure
  var errorDescription: String? { failure.message(for: action) }
}

enum SiriIntentService {
  @TaskLocal static var memoryWriter: (@Sendable (String) async throws -> ServerMemory)?
  static func normalizedMemory(_ input: String) -> String {
    var value = input.trimmingCharacters(in: .whitespacesAndNewlines)
    if value.lowercased().hasPrefix("that ") {
      value = String(value.dropFirst(5)).trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return value
  }

  static func remember(_ input: String) async throws -> ServerMemory {
    try await remember(input, create: memoryWriter ?? liveCreateMemory)
  }

  /// The injected writer is also used by backend-free tests of the exact
  /// normalization and failure path used by RememberIntent.perform().
  static func remember(
    _ input: String,
    create: @Sendable (String) async throws -> ServerMemory
  ) async throws -> ServerMemory {
    let content = normalizedMemory(input)
    guard !content.isEmpty else { throw SiriActionFailure(action: "remember", failure: .unsupported) }
    do { return try await create(content) } catch {
      throw SiriActionFailure(action: "remember", failure: SiriFailure.classify(error))
    }
  }

  private static func liveCreateMemory(_ content: String) async throws -> ServerMemory {
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      throw SiriFailure.auth
    }
    let result = try await APIClient.shared.createMemory(
      content: content, visibility: "private", category: .manual, tags: ["siri"],
      expectedOwnerId: authorization.ownerID, authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw SiriFailure.cancelled }
    do { try await MemoryStorage.shared.syncServerMemory(result) } catch {
      log("Siri memory cache refresh deferred: \(error.localizedDescription)")
    }
    return result
  }

  static func completeTask(id: String) async throws -> TaskActionItem {
    try await completeTask(id: id, update: liveCompleteTask)
  }

  static func completeTask(
    id: String,
    update: @Sendable (String) async throws -> TaskActionItem
  ) async throws -> TaskActionItem {
    guard !id.hasPrefix("local_") else { throw SiriActionFailure(action: "complete", failure: .unsupported) }
    do { return try await update(id) } catch {
      throw SiriActionFailure(action: "complete", failure: SiriFailure.classify(error))
    }
  }

  private static func liveCompleteTask(_ id: String) async throws -> TaskActionItem {
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      throw SiriFailure.auth
    }
    let result = try await APIClient.shared.updateActionItem(
      id: id, completed: true, expectedOwnerId: authorization.ownerID,
      authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw SiriFailure.cancelled }
    do {
      try await ActionItemStorage.shared.syncTaskActionItems(
        [result],
        authorization: TasksStore.localMutationAuthorization(snapshot: authorization))
    } catch { log("Siri task cache refresh deferred: \(error.localizedDescription)") }
    return result
  }

  static func createTask(title: String, dueDate: Date?) async throws -> TaskActionItem {
    try await createTask(title: title, dueDate: dueDate, create: liveCreateTask)
  }

  static func createTask(
    title: String, dueDate: Date?,
    create: @Sendable (String, Date?) async throws -> TaskActionItem
  ) async throws -> TaskActionItem {
    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { throw SiriActionFailure(action: "create", failure: .unsupported) }
    do { return try await create(trimmed, dueDate) } catch {
      throw SiriActionFailure(action: "create", failure: SiriFailure.classify(error))
    }
  }

  private static func liveCreateTask(_ title: String, _ dueDate: Date?) async throws -> TaskActionItem {
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      throw SiriFailure.auth
    }
    let result = try await APIClient.shared.createActionItem(
      description: title, dueAt: dueDate, source: "siri",
      expectedOwnerId: authorization.ownerID, authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw SiriFailure.cancelled }
    do {
      try await ActionItemStorage.shared.syncTaskActionItems(
        [result],
        authorization: TasksStore.localMutationAuthorization(snapshot: authorization))
    } catch { log("Siri task cache refresh deferred: \(error.localizedDescription)") }
    return result
  }
}
