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

  /// Direct memory writes are limited to a typed main/floating desktop chat
  /// turn whose user text contains an affirmative save request. Runtime
  /// surfaces such as voice, task chat, onboarding, delegated work, and
  /// background runs fail closed because they cannot establish that intent.
  nonisolated static func isExplicitMemorySaveIntent(
    userText: String?,
    surfaceKind: String?
  ) -> Bool {
    guard let surfaceKind, ["main_chat", "floating_chat"].contains(surfaceKind) else { return false }
    guard let userText else { return false }
    let text = userText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !text.isEmpty else { return false }

    // Keep this validator aligned with the runtime external-surface policy:
    // negations, recall questions, and assistant-authored suggestions are not
    // authorization for a write.
    let negativePattern =
      #"(?:\b(?:don't|do not|never|no longer|without)\b[^.!?]{0,96}\b(?:remember|save|store|keep)\b|\b(?:remember|save|store|keep)\b[^.!?]{0,96}\b(?:not|never)\b)"#
    guard text.range(of: negativePattern, options: .regularExpression) == nil else { return false }
    let questionPattern =
      #"^\s*(?:should|would|could|can|do|did|why|what)\b[^.!?]*\b(?:remember|save|store|keep)\b[^.!?]*\?\s*$"#
    guard text.range(of: questionPattern, options: .regularExpression) == nil else { return false }

    let directCommandPattern = #"^(?:hey\s+)?(?:please\s+)?(?:remember|save|store|keep)\b"#
    let sentenceCommandPattern = #"(?:^|[.!?,;]\s+)(?:please\s+)?(?:remember|save|store|keep)\b"#
    let delegatedCommandPattern = #"\b(?:want|need|ask)\s+(?:you\s+)?to\s+(?:please\s+)?(?:remember|save|store|keep)\b"#
    let anaphoricCommandPattern =
      #"\b(?:remember|save|store|keep)\s+(?:this|that|it|my|our|the following)\b"#
    let hasCommand =
      text.range(of: directCommandPattern, options: .regularExpression) != nil
      || text.range(of: sentenceCommandPattern, options: .regularExpression) != nil
      || text.range(of: delegatedCommandPattern, options: .regularExpression) != nil
      || text.range(of: anaphoricCommandPattern, options: .regularExpression) != nil
    guard hasCommand else { return false }
    return text.range(
      of: #"\b(?:i|we|you|they)\s+(?:remember|save|store|keep)\b"#,
      options: .regularExpression) == nil
  }

  nonisolated static func isMemoryContentUserSupplied(content: String, userText: String?) -> Bool {
    guard let userText else { return false }
    let normalizedContent = normalizeMemoryText(content)
    let normalizedUserText = normalizeMemoryText(userText)
    guard !normalizedContent.isEmpty, !normalizedUserText.isEmpty else { return false }
    return " \(normalizedUserText) ".contains(" \(normalizedContent) ")
  }

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

  static func executeCreateMemory(
    _ arguments: [String: Any],
    originatingUserText: String?,
    originatingSurface: AgentSurfaceReference?,
    originatingClientScope: String?,
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    api: APIClient
  ) async -> String {
    guard
      isExplicitMemorySaveIntent(
        userText: originatingUserText,
        surfaceKind: originatingSurface?.surfaceKind),
      originatingClientScope == nil
    else {
      return [
        #"{"ok":false,"error":{"code":"explicit_user_intent_required","message":"Memory writes require "#,
        #"an explicit typed request to remember or save something."}}"#,
      ].joined()
    }
    guard let input = memoryCreationInput(arguments) else {
      return [
        #"{"ok":false,"error":{"code":"invalid_memory_content","message":"content must be 1-1000 "#,
        #"non-whitespace characters."}}"#,
      ].joined()
    }
    guard isMemoryContentUserSupplied(content: input.content, userText: originatingUserText) else {
      return [
        #"{"ok":false,"error":{"code":"memory_content_not_user_supplied","message":"Memory content must appear in "#,
        #"the current typed user request."}}"#,
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
