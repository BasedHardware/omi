import SwiftUI

@testable import Omi_Computer

/// Test seam for the two Chat views whose content-block context is now required.
///
/// Most of these assertions are about row shape, hover regions, or view
/// identity, not about content blocks. They bind the same auxiliary context the
/// task panel and the notch use, so a test never asserts on a projection no
/// production surface has.
@MainActor
enum ChatSurfaceTestContext {
  static func make(chatProvider: ChatProvider? = nil) -> ChatFirstRichBlockContext {
    .auxiliary(chatProvider: chatProvider ?? ChatProvider.mainInstance ?? ChatProvider())
  }
}

@MainActor
extension ChatBubble {
  init(
    message: ChatMessage,
    app: OmiApp?,
    showsOmiMark: Bool,
    onRate: @escaping (Int?, ChatFeedbackReason?) -> Void,
    onCitationTap: ((Citation) -> Void)? = nil,
    onOpenInlineCitation: ((ChatCitationReference) -> Void)? = nil,
    isDuplicate: Bool = false,
    onCancelTurn: (() -> Void)? = nil,
    onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil,
    onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil
  ) {
    self.init(
      message: message,
      app: app,
      showsOmiMark: showsOmiMark,
      onRate: onRate,
      onCitationTap: onCitationTap,
      onOpenInlineCitation: onOpenInlineCitation,
      isDuplicate: isDuplicate,
      onCancelTurn: onCancelTurn,
      onOpenAgent: onOpenAgent,
      onOpenAgentRef: onOpenAgentRef,
      chatFirstRichBlockContext: ChatSurfaceTestContext.make()
    )
  }
}
