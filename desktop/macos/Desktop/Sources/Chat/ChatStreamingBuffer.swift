import Foundation

final class ChatStreamingBuffer {
  private enum PendingSegment {
    case text(messageId: String, text: String)
    case thinking(messageId: String, text: String)

    var messageId: String {
      switch self {
      case .text(let messageId, _), .thinking(let messageId, _):
        return messageId
      }
    }
  }

  /// The raw, un-normalized text a streaming message has received so far.
  ///
  /// `normalizeText` is a *projection*, not an edit: it may legitimately withhold
  /// text it cannot yet classify — the follow-up tail marker arrives split across
  /// flushes, and the question after it must never appear in the transcript. Feeding
  /// a projection its own previous output destroys the evidence it needs on the next
  /// flush, so what was withheld once leaks token by token afterwards. The raw text
  /// is therefore accumulated here and the projection is only ever *written to* the
  /// message, never read back out of it.
  private struct RawAccumulator {
    var text: String = ""
    var blocks: [String: String] = [:]
  }

  private var pendingSegments: [PendingSegment] = []
  private var rawAccumulators: [String: RawAccumulator] = [:]
  private var flushWorkItem: DispatchWorkItem?
  private let flushInterval: TimeInterval

  init(flushInterval: TimeInterval) {
    self.flushInterval = flushInterval
  }

  func appendText(messageId: String, text: String, scheduleFlush: @escaping () -> Void) {
    appendSegment(.text(messageId: messageId, text: text))
    scheduleFlushIfNeeded(scheduleFlush)
  }

  func appendThinking(messageId: String, text: String, scheduleFlush: @escaping () -> Void) {
    appendSegment(.thinking(messageId: messageId, text: text))
    scheduleFlushIfNeeded(scheduleFlush)
  }

  func cancelPendingFlush() {
    flushWorkItem?.cancel()
    flushWorkItem = nil
  }

  /// Release the raw accumulator for a finished turn.
  ///
  /// Called when the authoritative terminal answer replaces the streamed text.
  /// Without this the map grows for the life of the session, and a message id
  /// that streams a second time would resume from the first turn's text.
  func finishStreaming(messageId: String) {
    rawAccumulators[messageId] = nil
  }

  /// Drop only the buffered deltas for a revoked turn. A newer turn may already
  /// share this buffer, so cancelling or flushing the whole queue would either
  /// lose its tokens or apply the stopped turn's late output.
  func discardPendingSegments(messageId: String) {
    pendingSegments.removeAll { $0.messageId == messageId }
    rawAccumulators[messageId] = nil
    if pendingSegments.isEmpty {
      cancelPendingFlush()
    }
  }

  func flush(
    messages: inout [ChatMessage],
    normalizeText: (_ message: ChatMessage, _ text: String) -> String = { _, text in text }
  ) {
    flushWorkItem?.cancel()
    flushWorkItem = nil

    let segments = pendingSegments
    pendingSegments = []

    for segment in segments {
      guard let index = messages.firstIndex(where: { $0.id == segment.messageId }) else { continue }
      switch segment {
      case .text(_, let text):
        appendTextSegment(text, to: &messages[index], normalizeText: normalizeText)
      case .thinking(_, let text):
        appendThinkingSegment(text, to: &messages[index])
      }
    }
  }

  @discardableResult
  func applyToolActivity(
    messageId: String,
    toolName: String,
    status: ToolCallStatus,
    toolUseId: String? = nil,
    input: [String: Any]? = nil,
    messages: inout [ChatMessage],
    normalizeText: (_ message: ChatMessage, _ text: String) -> String = { _, text in text }
  ) -> Int? {
    flush(messages: &messages, normalizeText: normalizeText)
    guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return nil }
    ToolCallBlockUpdater.applyToolActivity(
      to: &messages[index].contentBlocks,
      toolName: toolName,
      status: status,
      toolUseId: toolUseId,
      input: input
    )
    return index
  }

  @discardableResult
  func applyToolResult(
    messageId: String,
    toolUseId: String,
    name: String,
    output: String,
    messages: inout [ChatMessage],
    normalizeText: (_ message: ChatMessage, _ text: String) -> String = { _, text in text }
  ) -> Int? {
    flush(messages: &messages, normalizeText: normalizeText)
    guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return nil }
    ToolCallBlockUpdater.applyToolOutput(
      to: &messages[index].contentBlocks,
      toolUseId: toolUseId,
      name: name,
      output: output
    )
    return index
  }

  func completeRemainingToolCalls(
    messageId: String,
    terminalStatus: ToolCallStatus = .completed,
    messages: inout [ChatMessage],
    normalizeText: (_ message: ChatMessage, _ text: String) -> String = { _, text in text }
  ) {
    flush(messages: &messages, normalizeText: normalizeText)
    guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
    ToolCallBlockUpdater.completeRemainingToolCalls(
      in: &messages[index].contentBlocks,
      terminalStatus: terminalStatus
    )
  }

  private func appendSegment(_ segment: PendingSegment) {
    guard let last = pendingSegments.last else {
      pendingSegments.append(segment)
      return
    }

    switch (last, segment) {
    case (.text(let lastMessageId, let existing), .text(let messageId, let text)) where lastMessageId == messageId:
      pendingSegments[pendingSegments.count - 1] = .text(messageId: messageId, text: existing + text)
    case (.thinking(let lastMessageId, let existing), .thinking(let messageId, let text))
    where lastMessageId == messageId:
      pendingSegments[pendingSegments.count - 1] = .thinking(messageId: messageId, text: existing + text)
    default:
      pendingSegments.append(segment)
    }
  }

  private func appendTextSegment(
    _ text: String,
    to message: inout ChatMessage,
    normalizeText: (_ message: ChatMessage, _ text: String) -> String
  ) {
    // Seed from what the message already carries the first time this turn
    // appends, so a message that was restored or resumed keeps its prefix.
    var accumulator = rawAccumulators[message.id] ?? RawAccumulator(text: message.text)
    accumulator.text += text
    message.text = normalizeText(message, accumulator.text)

    if let lastBlockIndex = message.contentBlocks.indices.last,
      case .text(let blockId, let existing) = message.contentBlocks[lastBlockIndex]
    {
      let rawBlock = (accumulator.blocks[blockId] ?? existing) + text
      accumulator.blocks[blockId] = rawBlock
      message.contentBlocks[lastBlockIndex] = .text(
        id: blockId,
        text: normalizeText(message, rawBlock)
      )
    } else {
      let blockId = UUID().uuidString
      accumulator.blocks[blockId] = text
      message.contentBlocks.append(
        .text(id: blockId, text: normalizeText(message, text))
      )
    }
    rawAccumulators[message.id] = accumulator
  }

  private func appendThinkingSegment(_ text: String, to message: inout ChatMessage) {
    if let lastBlockIndex = message.contentBlocks.indices.last,
      case .thinking(let thinkId, let existing) = message.contentBlocks[lastBlockIndex]
    {
      message.contentBlocks[lastBlockIndex] = .thinking(id: thinkId, text: existing + text)
    } else {
      message.contentBlocks.append(.thinking(id: UUID().uuidString, text: text))
    }
  }

  private func scheduleFlushIfNeeded(_ scheduleFlush: @escaping () -> Void) {
    guard flushWorkItem == nil else { return }
    let workItem = DispatchWorkItem(block: scheduleFlush)
    flushWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + flushInterval, execute: workItem)
  }
}

/// Canonical mutation rules for visible tool-call blocks.
/// Adapter streams may emit multiple lifecycle events for one invocation;
/// the chat transcript keeps exactly one block per `toolUseId`.
enum ToolCallBlockUpdater {
  static func applyToolActivity(
    to blocks: inout [ChatContentBlock],
    toolName: String,
    status: ToolCallStatus,
    toolUseId: String?,
    input: [String: Any]?
  ) {
    let normalizedToolUseId = toolUseId?.isEmpty == false ? toolUseId : nil
    let toolInput = input.flatMap { ChatContentBlock.toolInputSummary(for: toolName, input: $0) }

    if status == .running {
      if let existingIndex = existingToolIndexForStart(
        in: blocks,
        toolName: toolName,
        toolUseId: normalizedToolUseId
      ) {
        if case .toolCall(let id, let name, let existingStatus, let existingToolUseId, let existingInput, let output) =
          blocks[existingIndex]
        {
          blocks[existingIndex] = .toolCall(
            id: id,
            name: name,
            status: existingStatus,
            toolUseId: normalizedToolUseId ?? existingToolUseId,
            input: toolInput ?? existingInput,
            output: output
          )
        }
        return
      }

      blocks.append(
        .toolCall(
          id: UUID().uuidString,
          name: toolName,
          status: .running,
          toolUseId: normalizedToolUseId,
          input: toolInput
        )
      )
      return
    }

    for index in blocks.indices {
      guard
        case .toolCall(let id, let name, let existingStatus, let existingToolUseId, let existingInput, let output) =
          blocks[index],
        existingStatus.isInFlight,
        toolMatches(
          name: name,
          toolUseId: existingToolUseId,
          requestedName: toolName,
          requestedToolUseId: normalizedToolUseId
        )
      else {
        continue
      }

      blocks[index] = .toolCall(
        id: id,
        name: name,
        status: status,
        toolUseId: normalizedToolUseId ?? existingToolUseId,
        input: toolInput ?? existingInput,
        output: output
      )
    }
  }

  static func completeRemainingToolCalls(
    in blocks: inout [ChatContentBlock],
    terminalStatus: ToolCallStatus = .completed
  ) {
    for index in blocks.indices {
      if case .toolCall(let id, let name, let status, let toolUseId, let input, let output) = blocks[index],
        status.isInFlight
      {
        blocks[index] = .toolCall(
          id: id,
          name: name,
          status: terminalStatus,
          toolUseId: toolUseId,
          input: input,
          output: output
        )
      }
    }
  }

  static func applyToolOutput(
    to blocks: inout [ChatContentBlock],
    toolUseId: String,
    name: String,
    output: String
  ) {
    let normalizedToolUseId = toolUseId.isEmpty ? nil : toolUseId
    for index in blocks.indices {
      guard
        case .toolCall(let id, let blockName, let status, let existingToolUseId, let input, _) =
          blocks[index],
        toolMatches(
          name: blockName,
          toolUseId: existingToolUseId,
          requestedName: name,
          requestedToolUseId: normalizedToolUseId
        )
      else {
        continue
      }

      blocks[index] = .toolCall(
        id: id,
        name: blockName,
        status: status,
        toolUseId: normalizedToolUseId ?? existingToolUseId,
        input: input,
        output: output
      )
    }
  }

  private static func existingToolIndexForStart(
    in blocks: [ChatContentBlock],
    toolName: String,
    toolUseId: String?
  ) -> Int? {
    if let toolUseId {
      for index in stride(from: blocks.count - 1, through: 0, by: -1) {
        guard case .toolCall(_, _, _, let existingToolUseId, _, _) = blocks[index] else {
          continue
        }
        if existingToolUseId == toolUseId {
          return index
        }
      }
    }

    for index in stride(from: blocks.count - 1, through: 0, by: -1) {
      guard case .toolCall(_, let name, let status, let existingToolUseId, _, _) = blocks[index],
        status.isInFlight
      else {
        continue
      }

      if existingToolUseId == nil && name == toolName {
        return index
      }
    }
    return nil
  }

  private static func toolMatches(
    name: String,
    toolUseId: String?,
    requestedName: String,
    requestedToolUseId: String?
  ) -> Bool {
    if let requestedToolUseId {
      return toolUseId == requestedToolUseId || (toolUseId == nil && name == requestedName)
    }
    return name == requestedName
  }
}
