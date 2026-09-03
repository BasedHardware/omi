import Foundation

/// Automation-harness transcript snapshots (`main_chat_snapshot`,
/// `wait_main_chat_idle`, floating variants). Read-only projections of the
/// canonical timeline, including per-message metadata presence and the
/// served-model attribution the Response Context popover displays.
extension ChatProvider {

  /// Snapshot for `main_chat_snapshot` / `wait_main_chat_idle` harness actions.
  func automationMainChatSnapshot(limit: Int) -> [String: String] {
    automationChatSnapshot(limit: limit)
  }

  /// Snapshot for the floating-bar chat. It intentionally returns the same
  /// canonical Omi chat timeline as main chat so typed notch, PTT, and
  /// spawned-agent links can be verified from either surface.
  func automationFloatingChatSnapshot(limit: Int) -> [String: String] {
    automationChatSnapshot(limit: limit)
  }

  func automationChatSnapshot(limit: Int) -> [String: String] {
    let boundedLimit = max(1, limit)
    let runtimeChatId = mainChatRuntimeChatId(sessionId: currentSessionId)
    let rows: [[String: String]] = messages.suffix(boundedLimit).map { message in
      [
        "id": message.id,
        "role": message.sender == .user ? "user" : "assistant",
        "text": message.copyableText,
        "raw_text": message.text,
        "streaming": message.isStreaming ? "true" : "false",
        "content_blocks_json": ChatContentBlockCodec.encode(message.contentBlocks) ?? "[]",
        "resources_json": ChatResource.encodeResourcesForPersistence(message.displayResources) ?? "[]",
        "has_metadata": message.metadata != nil ? "true" : "false",
        "models_used": message.metadata?.modelsUsed.joined(separator: ",") ?? "",
      ]
    }
    let messagesJSON: String
    if let data = try? JSONSerialization.data(withJSONObject: rows),
      let encoded = String(data: data, encoding: .utf8)
    {
      messagesJSON = encoded
    } else {
      messagesJSON = "[]"
    }
    var detail: [String: String] = [
      "chat_session_id": currentSessionId ?? "",
      "runtime_chat_id": runtimeChatId,
      "is_sending": isSending ? "true" : "false",
      "is_streaming": messages.contains(where: { $0.isStreaming }) ? "true" : "false",
      "message_count": "\(messages.count)",
      "messages_json": messagesJSON,
    ]
    if let lastAssistant = messages.last(where: { $0.sender != .user })?.copyableText {
      detail["last_assistant_text"] = lastAssistant
    }
    if let ownerId = runtimeOwnerId {
      detail["owner_id"] = ownerId
    }
    let hasStructuredError = currentError != nil
    let hasLegacyError = !(errorMessage?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
    detail["has_error"] = (hasStructuredError || hasLegacyError) ? "true" : "false"
    if let errorMessage, !errorMessage.isEmpty {
      detail["error_message"] = errorMessage
    }
    if let currentError {
      detail["current_error"] = String(describing: currentError)
    }
    return detail
  }
}
