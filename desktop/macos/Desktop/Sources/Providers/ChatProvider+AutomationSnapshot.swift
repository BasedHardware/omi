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

  /// The grounded follow-up question on the newest answer, or `nil` when it
  /// carries no chip. One reader for both the snapshot field and the
  /// `tap_chat_follow_up_chip` action, so a flow can never assert a chip the
  /// tap would then fail to find.
  func automationLastFollowUpQuestion() -> String? {
    guard let lastAssistant = messages.last(where: { $0.sender != .user }) else { return nil }
    return lastAssistant.contentBlocks.compactMap { block -> String? in
      if case .followUp(_, let text) = block { return text }
      return nil
    }.last
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
    if let lastAssistant = messages.last(where: { $0.sender != .user }) {
      detail["last_assistant_text"] = lastAssistant.copyableText
      // The grounded follow-up chip, projected out of the block list so a flow
      // can assert it without string-matching `messages_json`. The pair matters
      // more than either half: `last_assistant_text` is the visible prose and
      // excludes this block, so asserting both pins the tail as *moved* rather
      // than merely present — the exact defect the split exists to prevent.
      if let question = automationLastFollowUpQuestion() {
        detail["last_assistant_follow_up_question"] = question
      }
    }
    if let probe = streamingBuffer.tailProjectionProbe {
      // The half of the follow-up split that only exists while the answer is streaming. The chip's
      // question must never have been visible as prose, and the terminal answer overwrites the
      // streamed text, so `last_assistant_text` above cannot tell. `delimiter_seen` is asserted
      // alongside the leak count on purpose: without it a turn that produced no tail at all would
      // report zero leaks and read as a pass.
      detail["streaming_tail_projections"] = String(probe.projectionCount)
      detail["streaming_tail_delimiter_seen"] = probe.delimiterSeen ? "true" : "false"
      detail["streaming_tail_leaks"] = String(probe.leakCount)
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
