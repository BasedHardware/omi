import Foundation

extension ChatProvider {
  /// How old a still-streaming turn must be before a replay may call it abandoned. A live answer
  /// is seconds old; a turn a dead process left behind is minutes old by the time anyone reads it.
  static let abandonedStreamingAge: TimeInterval = 90

  /// A relaunch under a live answer (or a crash mid-stream) leaves the turn non-terminal in the
  /// journal, and every replay after that shows it pulsing as if still loading. Nothing in the new
  /// process owns it, so nothing will ever finish it. With no send and no voice turn owned here, a
  /// streaming AI turn older than `abandonedStreamingAge` is terminalized on projection.
  static func terminalizeTurnsLeftStreamingByAPreviousProcess(
    _ messages: inout [ChatMessage],
    hasActiveSendLock: Bool,
    hasActiveVoiceTurn: Bool,
    now: Date
  ) -> [String] {
    guard !hasActiveSendLock, !hasActiveVoiceTurn else { return [] }
    var terminalizedMessageIDs: [String] = []
    for index in messages.indices
    where messages[index].sender == .ai && messages[index].isStreaming
      && now.timeIntervalSince(messages[index].createdAt) >= abandonedStreamingAge
    {
      messages[index].isStreaming = false
      ToolCallBlockUpdater.completeRemainingToolCalls(
        in: &messages[index].contentBlocks,
        terminalStatus: .failed
      )
      terminalizedMessageIDs.append(messages[index].id)
    }
    return terminalizedMessageIDs
  }

  /// A released send lock is the UI's terminal boundary. A transport failure
  /// can otherwise leave an old tool row marked streaming while `isSending`
  /// is already false, which makes later chat/PTT turns look stuck.
  static func terminalizeOrphanedStreamingMessages(
    _ messages: inout [ChatMessage],
    hasActiveSendLock: Bool
  ) -> [String] {
    guard !hasActiveSendLock else { return [] }
    var terminalizedMessageIDs: [String] = []
    for index in messages.indices where messages[index].sender == .ai && messages[index].isStreaming {
      messages[index].isStreaming = false
      ToolCallBlockUpdater.completeRemainingToolCalls(
        in: &messages[index].contentBlocks,
        terminalStatus: .failed
      )
      terminalizedMessageIDs.append(messages[index].id)
    }
    return terminalizedMessageIDs
  }
}
