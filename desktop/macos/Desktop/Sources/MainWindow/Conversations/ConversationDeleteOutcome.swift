// Owns conversation delete outcomes and the shared row/detail feedback surface.
// Failed deletes keep their row and offer a retry through the shell confirmation.

import Foundation
import SwiftUI

/// A delete only removes the local row once the server confirms absence.
enum ConversationDeleteOutcome: Equatable, Sendable {
  case deleted
  case alreadyDeleted
  case busy(retryAfter: TimeInterval)
  case failed(message: String)

  var succeeded: Bool {
    switch self {
    case .deleted, .alreadyDeleted: return true
    case .busy, .failed: return false
    }
  }

  var message: String {
    switch self {
    case .deleted: return "Conversation deleted"
    case .alreadyDeleted: return "Conversation was already deleted"
    case .busy(let retryAfter):
      return "Omi is finishing another account task. Try again in \(Int(ceil(retryAfter))) seconds."
    case .failed(let message): return message
    }
  }
}

/// Shared by row-menu and detail deletes so neither entry point loses a failure.
@MainActor
final class ConversationDeleteFeedback: ObservableObject {
  @Published var failure: ConversationDeleteOutcome?

  @discardableResult
  func present(_ outcome: ConversationDeleteOutcome) -> Bool {
    if outcome.succeeded {
      failure = nil
      OmiToastCenter.shared.confirm(outcome.message)
    } else {
      failure = outcome
    }
    return outcome.succeeded
  }
}

extension View {
  func conversationDeleteFeedback(_ feedback: ConversationDeleteFeedback, retry: @escaping () -> Void) -> some View {
    modifier(ConversationDeleteFeedbackHost(feedback: feedback, retry: retry))
  }
}

private struct ConversationDeleteFeedbackHost: ViewModifier {
  @ObservedObject var feedback: ConversationDeleteFeedback
  let retry: () -> Void

  func body(content: Content) -> some View {
    content.shellConfirmation(
      isPresented: Binding(
        get: { feedback.failure != nil },
        set: { if !$0 { feedback.failure = nil } }
      ),
      title: "Couldn't Delete Conversation",
      message: feedback.failure?.message ?? "Please try again.",
      confirmTitle: "Retry",
      isDestructive: false,
      onConfirm: retry
    )
  }
}
