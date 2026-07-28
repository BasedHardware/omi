import Foundation

extension ChatProvider {
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
