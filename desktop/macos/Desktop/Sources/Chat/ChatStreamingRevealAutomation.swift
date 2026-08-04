import Foundation

enum ChatStreamingRevealContract {
  static func isStrictPrefix(_ visibleText: String, expectedPrefix: String, expectedText: String?) -> Bool {
    guard !visibleText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
    guard expectedPrefix.isEmpty || visibleText.hasPrefix(expectedPrefix) else { return false }
    guard let expectedText = expectedText?.trimmingCharacters(in: .whitespacesAndNewlines), !expectedText.isEmpty else {
      return true
    }
    return visibleText != expectedText && expectedText.hasPrefix(visibleText)
  }
}

extension DesktopAutomationActionRegistry {
  func registerChatStreamingRevealAutomationActions() {
    register(
      name: "wait_main_chat_streaming_reveal",
      summary: "Wait for a visible assistant prefix while the main-chat turn is still streaming",
      params: ["timeoutMs", "pollMs", "expectedPrefix", "expectedText"]
    ) { params in
      let timeoutMs = max(1_000, Int(params["timeoutMs"] ?? "") ?? 10_000)
      let pollMs = max(25, Int(params["pollMs"] ?? "") ?? 50)
      let expectedPrefix = params["expectedPrefix"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      let expectedText = params["expectedText"]
      guard let provider = ChatProvider.mainInstance else {
        return ["error": "main ChatProvider not yet initialized"]
      }
      let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1_000)
      while Date() < deadline {
        if let message = provider.messages.last(where: {
          $0.sender == .ai && $0.isStreaming
            && ChatStreamingRevealContract.isStrictPrefix(
              $0.copyableText,
              expectedPrefix: expectedPrefix,
              expectedText: expectedText
            )
        }) {
          var detail = provider.automationMainChatSnapshot(limit: 8)
          detail["streaming_reveal_observed"] = "true"
          detail["strict_prefix_observed"] = "true"
          detail["visible_assistant_text"] = message.copyableText
          detail["visible_assistant_prefix"] = expectedPrefix
          return detail
        }
        try await Task.sleep(nanoseconds: UInt64(pollMs) * 1_000_000)
      }
      var detail = provider.automationMainChatSnapshot(limit: 8)
      detail["error"] = "timeout"
      detail["timeout_ms"] = "\(timeoutMs)"
      return detail
    }
  }
}
