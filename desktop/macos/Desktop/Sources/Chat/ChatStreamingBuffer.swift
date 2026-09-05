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
  /// The deadline the armed flush was scheduled on (`uptimeNanoseconds`).
  /// Re-arms anchor to it rather than to flush completion, so a flush whose
  /// render work ran into its interval shifts that one beat instead of
  /// pushing every later beat back — the reveal keeps its period for as long
  /// as a flush fits inside one. Late-answer stutter reads as exactly this
  /// drift: each beat slower than the last by however long the render took.
  private var scheduledBeat: UInt64?

  /// Non-production leak detector for the projections this buffer emits. Nil on any bundle the
  /// automation bridge is not enabled on, so a shipped app allocates nothing and runs no extra
  /// work per flush. See `ChatStreamingTailProbe`.
  let tailProjectionProbe: ChatStreamingTailProbe?

  init(flushInterval: TimeInterval, probe: ChatStreamingTailProbe? = nil) {
    self.flushInterval = flushInterval
    tailProjectionProbe = probe ?? (DesktopAutomationLaunchOptions.isEnabled ? ChatStreamingTailProbe() : nil)
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
    scheduledBeat = nil
  }

  /// Release the raw accumulator for a finished turn.
  ///
  /// Called when the authoritative terminal answer replaces the streamed text.
  /// Without this the map grows for the life of the session, and a message id
  /// that streams a second time would resume from the first turn's text.
  func finishStreaming(messageId: String) {
    rawAccumulators[messageId] = nil
    tailProjectionProbe?.forget(messageId: messageId)
  }

  /// Drop only the buffered deltas for a revoked turn. A newer turn may already
  /// share this buffer, so cancelling or flushing the whole queue would either
  /// lose its tokens or apply the stopped turn's late output.
  func discardPendingSegments(messageId: String) {
    pendingSegments.removeAll { $0.messageId == messageId }
    rawAccumulators[messageId] = nil
    tailProjectionProbe?.forget(messageId: messageId)
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
    // A drained backlog ends the beat chain; the next delta starts a fresh
    // one rather than inheriting a deadline that has already passed.
    if pendingSegments.isEmpty { scheduledBeat = nil }
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
    // A boundary flush lands everything at once; there is no beat to hold.
    scheduledBeat = nil

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
    let seedText = message.text
    var accumulator = rawAccumulators[message.id] ?? RawAccumulator(text: message.text)
    accumulator.text += text
    message.text = normalizeText(message, accumulator.text)
    // Watched against a raw stream this buffer does not own, so the check survives the buffer
    // losing its own. See `ChatStreamingTailProbe`.
    tailProjectionProbe?.observe(
      messageId: message.id, seed: seedText, delta: text, projection: message.text)

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
    // Hold the metronome: the next beat belongs one interval after the beat
    // before it, clamped to now so a beat the render work overran fires at
    // once and resynchronizes instead of firing late and dragging the whole
    // cadence back with it.
    let now = DispatchTime.now().uptimeNanoseconds
    let interval = UInt64(flushInterval * 1_000_000_000)
    let deadline = Self.nextBeatDeadline(scheduledBeat: scheduledBeat, now: now, interval: interval)
    scheduledBeat = deadline
    let workItem = DispatchWorkItem(block: scheduleFlush)
    flushWorkItem = workItem
    DispatchQueue.main.asyncAfter(
      deadline: .now() + DispatchTimeInterval.nanoseconds(Int(deadline - now)),
      execute: workItem)
  }

  /// The anchoring contract, pure so it holds without a real clock: a beat
  /// whose flush work stays inside the interval keeps the grid (the next
  /// deadline is one interval after the scheduled beat, no matter when the
  /// work finished), and a beat that overran resynchronizes to now instead of
  /// compounding the overrun into every later beat.
  static func nextBeatDeadline(scheduledBeat: UInt64?, now: UInt64, interval: UInt64) -> UInt64 {
    max((scheduledBeat ?? now) &+ interval, now)
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

/// Counts projections that leaked text the follow-up tail rule had withheld.
///
/// The tail's damage is entirely mid-stream: the authoritative terminal answer overwrites
/// `message.text` when the turn finishes, so every assertion a flow can make *after* the turn
/// passes whether or not the chip's question was typed into the prose a token at a time on the way
/// there. c164760b6b fixed exactly that leak and could be proved only by unit-testing the buffer
/// directly. This makes the same property observable from a live app: not "the final text is
/// right", but "no intermediate projection the reader saw ever contained the withheld tail".
///
/// It is an observer, not a second projection. It keeps its own raw stream — seeded once from the
/// message and extended with the deltas the buffer is handed — and calls the shipped
/// `ChatFollowUpTail.strippingPendingTail` on it. Keeping its own stream is the whole point: the
/// defect was the buffer re-deriving the projection from its own withheld output, and a probe that
/// read the buffer's accumulator would have agreed with the bug. Two projections of the same raw
/// text differ only by the spacing normalizer, which inserts whitespace and never removes a
/// character, so the comparison is on non-whitespace content and is exact rather than fuzzy.
///
/// Nil in production (`ChatStreamingBuffer.init`), so nothing here is a shipped path and the
/// shipped projection is unchanged.
final class ChatStreamingTailProbe {
  /// Raw text per streaming message, independent of the buffer's own accumulator.
  private var rawByMessage: [String: String] = [:]

  /// How many projections have been checked. A flow reads it to know the probe was actually fed.
  private(set) var projectionCount = 0
  /// Whether any raw stream has carried a complete delimiter. Without this a zero leak count is
  /// unfalsifiable: a turn that never produced a tail cannot leak one.
  private(set) var delimiterSeen = false
  /// Projections whose visible content did not match what the tail rule would have shown.
  private(set) var leakCount = 0

  /// - Parameters:
  ///   - seed: the message text before this flush wrote to it, used only the first time this probe
  ///     sees the message so a resumed turn keeps its prefix.
  ///   - delta: the raw tokens this flush is applying.
  ///   - projection: what the buffer just wrote to `message.text`.
  func observe(messageId: String, seed: String, delta: String, projection: String) {
    let raw = (rawByMessage[messageId] ?? seed) + delta
    rawByMessage[messageId] = raw
    projectionCount += 1
    if raw.range(of: ChatFollowUpTail.delimiter) != nil { delimiterSeen = true }
    if Self.significant(projection) != Self.significant(ChatFollowUpTail.strippingPendingTail(raw)) {
      leakCount += 1
    }
  }

  func forget(messageId: String) {
    rawByMessage[messageId] = nil
  }

  /// Everything the spacing normalizer is not allowed to touch. It only ever inserts whitespace,
  /// so two projections of the same raw text agree here exactly.
  private static func significant(_ text: String) -> String {
    text.filter { !$0.isWhitespace }
  }
}
