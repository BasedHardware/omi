import Foundation

/// Pure selection policy for the conversation detail summary pane.
///
/// Mobile parity (`ConversationDetailProvider.getSummarizedApp`): the backend's
/// `_trigger_apps` clears `apps_results` and appends exactly the app it ran, so
/// the first result with usable content *is* the selected summarization app's
/// output. When no app produced a usable result, the pane falls back to the
/// first-party `structured.overview`.
enum ConversationSummarySelection {
  /// The markdown the summary pane renders as primary, plus the app that
  /// produced it (`nil` = first-party structured overview).
  struct Primary: Equatable {
    let content: String
    let appId: String?
  }

  static func primarySummary(for conversation: ServerConversation) -> Primary {
    if let result = conversation.appsResults.first(where: { !$0.content.isEmpty }) {
      return Primary(content: result.content, appId: result.appId)
    }
    return Primary(content: conversation.overview, appId: nil)
  }

  /// "App Insights" keeps only results that are not the primary summary. With
  /// no usable result there is no primary to promote, so every row stays.
  static func secondaryResults(for conversation: ServerConversation) -> [AppResponse] {
    guard let primaryResult = conversation.appsResults.first(where: { !$0.content.isEmpty }) else {
      return conversation.appsResults
    }
    return conversation.appsResults.filter { $0.id != primaryResult.id }
  }

  /// Suggested "Try with Apps" rows: memories-capable apps that have not
  /// produced a result for this conversation yet.
  ///
  /// Regression note: the inline closure this replaces compared `$0.appId == $0.id`
  /// inside `contains(where:)` — the inner `$0` shadowed the outer app, every
  /// appsResults entry compared to itself, and the section was always empty.
  static func suggestedApps(_ apps: [OmiApp], results: [AppResponse]) -> [OmiApp] {
    let resultAppIds = Set(results.compactMap(\.appId))
    return apps.filter { app in
      app.capabilities.contains("memories") && !resultAppIds.contains(app.id)
    }
  }
}
