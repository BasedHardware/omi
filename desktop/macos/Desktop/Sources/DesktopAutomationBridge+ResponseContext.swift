import Foundation

/// Response Context automation: opens the popover on the latest attributed
/// assistant message so harnesses can screenshot the rendered Model row —
/// hover-reveal and click are cursor gestures automation must not use.
extension DesktopAutomationActionRegistry {
  // Invoked from registerRealtimeHubActions() — the frozen main bridge file
  // stays at its origin/main line count (product-file line-count ratchet).
  func registerResponseContextActions() {
    // Opens the Response Context popover on the newest assistant message that
    // carries metadata, so harnesses can screenshot the rendered popover
    // (hover-reveal + click are cursor gestures automation must not use).
    register(
      name: "main_chat_open_response_context",
      summary: "Open the Response Context popover on the latest attributed assistant message (non-prod)",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "main_chat_open_response_context is disabled on production bundles"]
      }
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      guard
        let target = provider.messages.last(where: { $0.sender == .ai && $0.metadata != nil })
      else {
        return ["error": "no assistant message with metadata"]
      }
      NotificationCenter.default.post(
        name: ChatBubble.automationRevealResponseContext, object: target.id)
      return [
        "message_id": target.id,
        "models_used": target.metadata?.modelsUsed.joined(separator: ",") ?? "",
      ]
    }

  }
}
