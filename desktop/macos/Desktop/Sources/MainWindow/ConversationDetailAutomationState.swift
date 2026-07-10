import Foundation

/// Tracks conversation detail UI state for hermetic automation bridge snapshots.
@MainActor
final class ConversationDetailAutomationState {
  static let shared = ConversationDetailAutomationState()

  private(set) var openConversationId: String?
  private(set) var transcriptDrawerOpen = false

  private init() {}

  func setOpen(conversationId: String, transcriptDrawerOpen: Bool) {
    openConversationId = conversationId
    self.transcriptDrawerOpen = transcriptDrawerOpen
  }

  func setTranscriptDrawerOpen(_ open: Bool, conversationId: String) {
    guard openConversationId == conversationId else { return }
    transcriptDrawerOpen = open
  }

  func clear(conversationId: String) {
    guard openConversationId == conversationId else { return }
    openConversationId = nil
    transcriptDrawerOpen = false
  }
}
