import Combine
import Foundation

/// Tracks conversation detail UI state for hermetic automation bridge snapshots.
@MainActor
final class ConversationDetailAutomationState: ObservableObject {
  struct OpenRequest: Equatable {
    let conversationId: String
    let showTranscript: Bool
  }

  static let shared = ConversationDetailAutomationState()

  @Published private(set) var openConversationId: String?
  @Published private(set) var transcriptDrawerOpen = false
  @Published private(set) var pendingOpenRequest: OpenRequest?
  private var pendingTranscriptConversationId: String?

  init() {}

  /// Retain and publish an automation request until the Conversations view consumes it.
  /// The state publisher remains observable across a tab transition, unlike a one-shot
  /// notification which can arrive before SwiftUI mounts its receiver.
  func requestOpen(conversationId: String, showTranscript: Bool) {
    pendingOpenRequest = OpenRequest(conversationId: conversationId, showTranscript: showTranscript)
    pendingTranscriptConversationId = showTranscript ? conversationId : nil
    if openConversationId == conversationId, showTranscript {
      transcriptDrawerOpen = true
    }
  }

  func takePendingOpenRequest() -> OpenRequest? {
    defer { pendingOpenRequest = nil }
    return pendingOpenRequest
  }

  /// Synchronizes the automation snapshot when a detail view appears or is reused
  /// for a different conversation by SwiftUI. Returns the drawer state to render.
  @discardableResult
  func syncPresentedDetail(conversationId: String, transcriptDrawerOpen: Bool) -> Bool {
    let shouldShowTranscript =
      transcriptDrawerOpen || pendingTranscriptConversationId == conversationId
    openConversationId = conversationId
    self.transcriptDrawerOpen = shouldShowTranscript
    if pendingTranscriptConversationId == conversationId {
      pendingTranscriptConversationId = nil
    }
    return shouldShowTranscript
  }

  func setTranscriptDrawerOpen(_ open: Bool, conversationId: String) {
    guard openConversationId == conversationId else { return }
    transcriptDrawerOpen = open
  }

  func clear(conversationId: String) {
    guard openConversationId == conversationId else { return }
    openConversationId = nil
    transcriptDrawerOpen = false
    if pendingTranscriptConversationId == conversationId {
      pendingTranscriptConversationId = nil
    }
  }
}
