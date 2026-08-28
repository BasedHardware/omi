import Foundation

extension ChatToolExecutor {
  struct MemoryCreationInput: Equatable {
    let content: String
  }

  /// Normalize and bound the only user-controlled value accepted by the
  /// explicit chat memory write. Tier, durability, tags, and other lifecycle
  /// fields deliberately do not belong to this tool's input contract.
  nonisolated static func memoryCreationInput(_ arguments: [String: Any]) -> MemoryCreationInput? {
    guard let rawContent = arguments["content"] as? String else { return nil }
    let content = rawContent.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !content.isEmpty, content.count <= 1000 else { return nil }
    return MemoryCreationInput(content: content)
  }

  /// Memory writes belong to a typed desktop chat turn whose owner is present.
  /// Voice, task chat, onboarding, delegated work, and background runs fail
  /// closed: nothing there establishes that this user asked for a memory.
  /// Whether the turn actually asked for one is the model's judgment, stated in
  /// the tool description — this executor does not pattern-match the phrasing.
  nonisolated static func isTypedChatMemorySurface(_ surfaceKind: String?) -> Bool {
    guard let surfaceKind else { return false }
    return ["main_chat", "floating_chat"].contains(surfaceKind)
  }

  /// Fold whitespace and case so two phrasings of the same fact collapse to one
  /// batch entry.
  private nonisolated static func normalizeMemoryText(_ value: String) -> String {
    value
      .precomposedStringWithCompatibilityMapping
      .lowercased()
      .unicodeScalars
      .map { CharacterSet.alphanumerics.contains($0) ? String($0) : " " }
      .joined()
      .split(whereSeparator: \.isWhitespace)
      .joined(separator: " ")
  }

  /// Upper bound on one batch save. A document worth remembering is a few dozen
  /// facts; beyond that the model is dumping the source rather than distilling it.
  nonisolated static let memoriesCreationMaxFacts = 25

  /// Normalize the batch input the same way the single write normalizes
  /// `content`: trim, bound each fact, drop duplicates, and cap the batch.
  nonisolated static func memoriesCreationInput(_ arguments: [String: Any]) -> [String]? {
    guard let rawFacts = arguments["facts"] as? [Any] else { return nil }
    var seen = Set<String>()
    var facts: [String] = []
    for raw in rawFacts {
      guard let text = raw as? String else { continue }
      let fact = text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !fact.isEmpty, fact.count <= 1000 else { continue }
      guard seen.insert(normalizeMemoryText(fact)).inserted else { continue }
      facts.append(fact)
      if facts.count == memoriesCreationMaxFacts { break }
    }
    return facts.isEmpty ? nil : facts
  }

  /// A partial save is reported as one: the model must be able to tell the user
  /// how many of their facts actually landed.
  nonisolated static func memoriesCreationReceipt(
    savedIDs: [String],
    requestedCount: Int,
    failed: Bool
  ) -> String {
    var payload: [String: Any] = [
      "ok": true,
      "saved": true,
      "saved_count": savedIDs.count,
      "requested_count": requestedCount,
      "memory_ids": savedIDs,
      "message": "Memories saved; their lifecycle is managed by Omi.",
    ]
    if failed {
      payload["message"] =
        "Saved \(savedIDs.count) of \(requestedCount); the rest could not be saved. Tell the user what was kept."
    }
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return "{\"ok\":true,\"saved\":true,\"saved_count\":\(savedIDs.count)}"
    }
    return json
  }

  nonisolated static func memoryCreationReceipt(_ memory: ServerMemory) -> String {
    var payload: [String: Any] = [
      "ok": true,
      "saved": true,
      "memory_id": memory.id,
      "message": "Memory saved; its lifecycle is managed by Omi.",
    ]
    if memory.tierIsExplicit {
      payload["layer"] = memory.tier.rawValue
      if memory.tier == .shortTerm {
        payload["message"] = "Memory saved to short-term memory; its lifecycle is managed by Omi."
      }
    }
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else {
      return "{\"ok\":true,\"saved\":true,\"memory_id\":\"\(memory.id)\"}"
    }
    return json
  }

  nonisolated static func memorySaveStatusUnknownResult() -> String {
    [
      #"{"ok":false,"status":"unknown","error":{"code":"memory_save_status_unknown","message":"Memory save status is unknown; the request may have reached Omi. Check memories before retrying."}}"#
    ].joined()
  }

  private nonisolated static func memorySaveFailureResult() -> String {
    [
      #"{"ok":false,"saved":false,"status":"failed","error":{"code":"memory_unavailable","message":"Memory could not be saved."}}"#
    ].joined()
  }

  private nonisolated static func isDefiniteMemorySaveRejection(_ error: Error) -> Bool {
    if case APIError.unauthorized = error { return true }
    guard case APIError.httpError(let statusCode, _) = error else { return false }
    return (400..<500).contains(statusCode) && ![408, 409, 429].contains(statusCode)
  }

  /// A chat-tool write lands in the backend projection only; the memories page
  /// reads its own cache and would otherwise keep showing a list without it.
  private nonisolated static func announceMemoryWrite() {
    Task { @MainActor in
      NotificationCenter.default.post(name: .memoriesDidChange, object: nil)
    }
  }

  private nonisolated static func memorySurfaceRejection(
    surface: AgentSurfaceReference?,
    clientScope: String?
  ) -> String? {
    guard isTypedChatMemorySurface(surface?.surfaceKind), clientScope == nil else {
      return [
        #"{"ok":false,"error":{"code":"typed_chat_surface_required","message":"Memory writes are only "#,
        #"available in the user's own typed desktop chat."}}"#,
      ].joined()
    }
    return nil
  }

  static func executeCreateMemories(
    _ arguments: [String: Any],
    originatingSurface: AgentSurfaceReference?,
    originatingClientScope: String?,
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    api: APIClient
  ) async -> String {
    if let rejection = memorySurfaceRejection(
      surface: originatingSurface,
      clientScope: originatingClientScope)
    {
      return rejection
    }
    guard let facts = memoriesCreationInput(arguments) else {
      return [
        #"{"ok":false,"error":{"code":"invalid_memory_content","message":"facts must hold 1-"#,
        #"\#(memoriesCreationMaxFacts) non-empty items of at most 1000 characters."}}"#,
      ].joined()
    }
    guard
      let expectedOwnerID,
      let authorizationSnapshot,
      isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot)
    else { return authorizedOwnerChangedResult() }

    // Each fact goes through the single-memory endpoint. `/v3/memories/batch`
    // answers 503 for this write in production (backend#: chat batch save), and
    // a bounded chat save is a couple of dozen requests, not the thousands the
    // batch route exists to collapse.
    var savedIDs: [String] = []
    var lastError: Error?
    for fact in facts {
      guard isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else {
        return authorizedOwnerChangedResult()
      }
      do {
        // `.manual` is what marks a memory user-asserted on the backend, which
        // decides its authority in conflict resolution. These facts came from an
        // explicit save request, exactly like the single write's.
        let memory = try await api.createMemory(
          content: fact,
          visibility: "private",
          category: .manual,
          tags: [],
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot,
          allowsAuthRetry: false)
        savedIDs.append(memory.id)
      } catch {
        lastError = error
        log("Create memories tool failed on one fact: \(error.localizedDescription)")
        // Stop at the first failure: the rest would hit the same backend, and a
        // long retry storm buys nothing. What did save is still reported.
        break
      }
    }

    guard isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else {
      return authorizedOwnerChangedResult()
    }
    if !savedIDs.isEmpty {
      announceMemoryWrite()
      return memoriesCreationReceipt(
        savedIDs: savedIDs,
        requestedCount: facts.count,
        failed: lastError != nil)
    }
    guard let lastError else { return memorySaveFailureResult() }
    return isDefiniteMemorySaveRejection(lastError)
      ? memorySaveFailureResult()
      : memorySaveStatusUnknownResult()
  }

  static func executeCreateMemory(
    _ arguments: [String: Any],
    originatingSurface: AgentSurfaceReference?,
    originatingClientScope: String?,
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    api: APIClient
  ) async -> String {
    if let rejection = memorySurfaceRejection(
      surface: originatingSurface,
      clientScope: originatingClientScope)
    {
      return rejection
    }
    guard let input = memoryCreationInput(arguments) else {
      return [
        #"{"ok":false,"error":{"code":"invalid_memory_content","message":"content must be 1-1000 "#,
        #"non-whitespace characters."}}"#,
      ].joined()
    }
    guard
      let expectedOwnerID,
      let authorizationSnapshot,
      isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot)
    else { return authorizedOwnerChangedResult() }

    do {
      let memory = try await api.createMemory(
        content: input.content,
        visibility: "private",
        category: .manual,
        tags: [],
        expectedOwnerId: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot,
        allowsAuthRetry: false)
      guard isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else {
        return authorizedOwnerChangedResult()
      }
      announceMemoryWrite()
      return memoryCreationReceipt(memory)
    } catch {
      guard isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else {
        return authorizedOwnerChangedResult()
      }
      log("Create memory tool failed: \(error.localizedDescription)")
      return isDefiniteMemorySaveRejection(error)
        ? memorySaveFailureResult()
        : memorySaveStatusUnknownResult()
    }
  }
}
