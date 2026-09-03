//
//  DesktopAutomationActivationActions.swift — bridge actions for the first-48h activation surfaces.
//
//  Three read/drive seams so a QA bundle can prove the surfaces without the cursor:
//  `daily_summary_snapshot` reports the shared daily-summary store shape-only,
//  `open_chat_prefilled` drives the one prefill-without-send entry
//  (`openMainAppChat(prefilledDraft:)`) so `chat_drafts_snapshot` can show the draft landed unsent,
//  and `tap_chat_follow_up_chip` performs the chip's own send so the `followup` question origin is
//  observable end to end. All three are second callers of production code, never a second
//  implementation.
//
//  Registered from `DesktopAutomationActionRegistry.registerBuiltins()` next to the Home-stage
//  actions.
//

import Foundation

extension DesktopAutomationActionRegistry {

  func registerActivationActions() {
    register(
      name: "daily_summary_snapshot",
      summary: "Shape-only state of the shared daily-summary store (has summary, date, stat presence; no text)",
      category: "chat",
      surfaces: ["main_chat"],
      safety: "read_only"
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "daily_summary_snapshot is disabled on production bundles"]
      }
      // Read only: no refresh here, because a refresh can post the "new summary" notch card.
      let store = ChatDailySummaryCoordinator.shared.store
      guard let latest = store.latest else {
        return [
          "hasSummary": "false",
          "isLoading": store.isLoading ? "true" : "false",
          "lastError": store.lastError ?? "",
        ]
      }
      return [
        "hasSummary": "true",
        "date": latest.date ?? "",
        "dateLabel": ChatDailySummaryPresentation.dateLabel(for: latest.date, now: Date()) ?? "",
        "headlineLength": String(latest.headline?.count ?? 0),
        "overviewLength": String(latest.overview?.count ?? 0),
        "hasStats": latest.stats == nil ? "false" : "true",
        "highlightCount": String(latest.highlights?.count ?? 0),
        "actionItemCount": String(latest.actionItems?.count ?? 0),
        "followUp": ChatDailySummaryPresentation.followUpQuestion(for: latest.date, now: Date()),
      ]
    }

    register(
      name: "open_chat_prefilled",
      summary: "Open the main chat with `query` prefilled and focused, NOT sent (the first-real-app card path)",
      params: ["query"],
      category: "chat",
      surfaces: ["main_chat"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "open_chat_prefilled is disabled on production bundles"]
      }
      guard let query = params["query"]?.trimmingCharacters(in: .whitespacesAndNewlines), !query.isEmpty else {
        return ["error": "missing 'query'"]
      }
      guard let target = AppDelegate.summonWindowTarget() else {
        return ["error": "no window target"]
      }
      target.openMainAppChat(prefilledDraft: query)
      return [
        "requested": "true",
        "pendingDraftLength": String(MainChatNavigationRequestStore.shared.pendingDraft?.count ?? 0),
      ]
    }

    register(
      name: "tap_chat_follow_up_chip",
      summary:
        "Tap the follow-up chip under the last main-chat answer (same send as the chip) and report "
        + "the `question_asked` origin it produced",
      params: [],
      category: "chat",
      surfaces: ["main_chat"]
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "tap_chat_follow_up_chip is disabled on production bundles"]
      }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      // The chip is a property of the answer, so a missing one is a real finding
      // rather than a harness setup error: report it instead of throwing, and
      // the flow's expectation on `question` fails with the reason attached.
      guard let question = provider.automationLastFollowUpQuestion() else {
        return ["error": "no follow-up chip on the last assistant message", "has_chip": "false"]
      }
      // `origin` is only observable where it is emitted: the property is
      // consumed inside `questionAsked` and gone by the time the send returns.
      // Reading it at the same seam the unit tests use keeps this a report of
      // what production emitted rather than a second guess at it.
      let analytics = AnalyticsManager.shared
      let previousCapture = analytics.questionTelemetryCaptureForTests
      var observedOrigin: String?
      analytics.questionTelemetryCaptureForTests = { event, properties in
        guard event == "question_asked", observedOrigin == nil else { return }
        observedOrigin = properties["origin"] as? String
      }
      defer { analytics.questionTelemetryCaptureForTests = previousCapture }

      let accepted = await FollowUpChipTap.send(question: question, provider: provider) != nil
      return [
        "has_chip": "true",
        "question": question,
        "accepted": accepted ? "true" : "false",
        "question_origin": observedOrigin ?? "",
      ]
    }
  }
}
