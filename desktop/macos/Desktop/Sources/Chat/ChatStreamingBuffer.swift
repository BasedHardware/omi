import Foundation

/// How much of the buffered text one flush lets through.
///
/// The wire delivers an answer in bursts — a provider chunk, a whole paragraph
/// the moment a tool returns — and a flush that dumped everything it had made
/// the transcript lurch by a sentence at a time and then sit still. Revealing
/// a bounded slice per flush turns those bursts into a steady flow: a small
/// backlog drains over a handful of flushes, a large one is let through fast
/// enough that the reader is never far behind the model, and the tail of every
/// burst tapers rather than stops.
enum ChatStreamingReveal {
  /// Characters the reveal may trail the wire by before it stops pacing and
  /// simply catches up. About two lines of prose at the transcript's width.
  static let maximumLag = 480
  /// Fewest characters a flush reveals while anything is pending, so a trickle
  /// still moves and a taper still ends.
  static let minimumPerFlush = 4
  /// A backlog drains over roughly this many flushes.
  static let drainFlushes = 5

  static func characters(pending: Int) -> Int {
    guard pending > 0 else { return 0 }
    let paced = max(minimumPerFlush, Int((Double(pending) / Double(drainFlushes)).rounded(.up)))
    let catchUp = pending - maximumLag
    return min(pending, max(paced, catchUp))
  }
}

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

  private var pendingSegments: [PendingSegment] = []
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

  /// Drop only the buffered deltas for a revoked turn. A newer turn may already
  /// share this buffer, so cancelling or flushing the whole queue would either
  /// lose its tokens or apply the stopped turn's late output.
  func discardPendingSegments(messageId: String) {
    pendingSegments.removeAll { $0.messageId == messageId }
    if pendingSegments.isEmpty {
      cancelPendingFlush()
    }
  }

  /// Characters of answer text waiting to be shown.
  var pendingTextCount: Int {
    pendingSegments.reduce(0) { total, segment in
      if case .text(_, let text) = segment { return total + text.count }
      return total
    }
  }

  /// Re-arm the flush timer. `flushPaced` leaves a remainder behind on purpose,
  /// and the remainder needs a next flush that no new delta may ever schedule.
  func scheduleFlush(_ scheduleFlush: @escaping () -> Void) {
    scheduleFlushIfNeeded(scheduleFlush)
  }

  /// Apply the pending deltas in order, but let only `ChatStreamingReveal`'s
  /// share of the answer text through; the rest stays queued, at the head,
  /// for the next flush. Thinking is not paced — it is folded away behind a
  /// disclosure, so there is no flow to smooth. Returns whether anything is
  /// still waiting.
  @discardableResult
  func flushPaced(
    messages: inout [ChatMessage],
    normalizeText: (_ message: ChatMessage, _ text: String) -> String = { _, text in text }
  ) -> Bool {
    flushWorkItem?.cancel()
    flushWorkItem = nil

    var budget = ChatStreamingReveal.characters(pending: pendingTextCount)
    var consumed = 0
    segments: while consumed < pendingSegments.count {
      let segment = pendingSegments[consumed]
      guard let index = messages.firstIndex(where: { $0.id == segment.messageId }) else {
        consumed += 1
        continue
      }
      switch segment {
      case .thinking(_, let text):
        appendThinkingSegment(text, to: &messages[index])
        consumed += 1
      case .text(let messageId, let text):
        guard budget > 0 else { break segments }
        if text.count <= budget {
          appendTextSegment(text, to: &messages[index], normalizeText: normalizeText)
          budget -= text.count
          consumed += 1
        } else {
          appendTextSegment(String(text.prefix(budget)), to: &messages[index], normalizeText: normalizeText)
          pendingSegments[consumed] = .text(messageId: messageId, text: String(text.dropFirst(budget)))
          budget = 0
          break segments
        }
      }
    }
    pendingSegments.removeFirst(consumed)
    return !pendingSegments.isEmpty
  }

  /// Apply everything pending at once. This is the flush for a boundary — a
  /// tool starting, the turn settling — where the order of what follows
  /// depends on all of the text being in place first.
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
    message.text = normalizeText(message, message.text + text)

    if let lastBlockIndex = message.contentBlocks.indices.last,
      case .text(let blockId, let existing) = message.contentBlocks[lastBlockIndex]
    {
      message.contentBlocks[lastBlockIndex] = .text(
        id: blockId,
        text: normalizeText(message, existing + text)
      )
    } else {
      message.contentBlocks.append(
        .text(id: UUID().uuidString, text: normalizeText(message, text))
      )
    }
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
