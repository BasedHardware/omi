import SwiftUI

/// The one renderer for the six interactable content-block kinds.
///
/// Main chat, the task panel, and the floating/notch surfaces all project the
/// same journal, so they all render the same cards. This view is what keeps
/// that literal: each host hands it a grouped block plus the message it came
/// from, and gets the same control back. A host that "does not opt into rich
/// controls" used to mean a card silently became `EmptyView` — a turn that read
/// as an empty reply on one surface and a task you could tick off on another.
struct ChatFirstRichBlockGroupView: View {
  let group: ContentBlockGroup
  /// Identity of the message the block belongs to. `isQuestionCardActionable`
  /// is a tail-of-transcript question, so it needs the row, not just the block.
  let messageID: String
  let context: ChatFirstRichBlockContext

  var body: some View {
    switch group {
    case .questionCard(_, let questionID, let text, let options, let selectedOptionID):
      QuestionCardView(
        questionID: questionID,
        text: text,
        options: options,
        selectedOptionID: selectedOptionID,
        isActionable: context.chatProvider.isQuestionCardActionable(
          messageID: messageID,
          questionID: questionID,
          selectedOptionID: selectedOptionID
        ),
        isCapabilityAvailable: context.chatProvider.hasChatFirstMainChatCapability(),
        onSelect: { optionID, isDeferral in
          Task { @MainActor in
            AnalyticsManager.shared.chatFirst(
              .question(lifecycle: isDeferral ? .deferred : .answered)
            )
            AnalyticsManager.shared.chatFirst(
              .richBlock(kind: .questionCard, outcome: .acted, action: .select)
            )
            await context.chatProvider.selectQuestionCardOption(
              questionID: questionID,
              optionID: optionID
            )
          }
        }
      )
    case .taskCard(_, let taskID):
      TaskCardView(
        taskID: taskID,
        tasksStore: context.tasksStore,
        navigation: context.navigation
      )
    case .goalLink(_, let goalID, let summary):
      GoalLinkView(
        goalID: goalID,
        summary: summary,
        navigation: context.navigation,
        goalsStore: context.canonicalGoalsStore
      )
    case .captureLink(_, let conversationID, let momentTimestampMs, let summary):
      CaptureLinkView(
        conversationID: conversationID,
        momentTimestampMs: momentTimestampMs,
        summary: summary,
        navigation: context.navigation
      )
    case .conversationLink(_, let conversationID, let summary, let recommendedActionItems):
      ConversationLinkView(
        conversationID: conversationID,
        summary: summary,
        recommendedActionItems: recommendedActionItems,
        navigation: context.navigation
      )
    case .memoryLink(_, let memoryID, let summary):
      MemoryLinkView(
        memoryID: memoryID,
        summary: summary,
        navigation: context.navigation
      )
    case .text, .commentary, .toolCalls, .thinking, .discoveryCard, .agentSpawn, .agentCompletion,
      .memoryReviewCard, .followUp:
      // Not this view's kinds — the review card and the follow-up chip are
      // rendered by the bubble itself. Exhaustive rather than a `default` so a
      // block added later has to state its answer here instead of vanishing.
      EmptyView()
    }
  }
}
