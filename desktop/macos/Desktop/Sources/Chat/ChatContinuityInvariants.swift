import Foundation

/// Pure INV-6 continuity helpers — prefer these over ad-hoc UI string/resource logic.
/// Behavioral tests call these APIs; source tripwires guard forbidden dual-write patterns.
enum ChatContinuityInvariants {
  /// Collapsed agent-card / list header preview prefers the prompt/objective.
  /// Response output belongs in the expanded body, not the one-line preview.
  static func agentPreviewText(prompt: String, output: String) -> String {
    let promptTrimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
    if !promptTrimmed.isEmpty {
      return promptTrimmed
    }
    return output.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Floating/notch viewport may only surface resources owned by viewport message ids.
  /// Historical timeline resources outside the cursor must not appear as orphans.
  static func resourcesBelongingToMessages(
    messages: [ChatMessage],
    messageIds: Set<String>
  ) -> [ChatResource] {
    guard !messageIds.isEmpty else { return [] }
    var seen = Set<String>()
    var resources: [ChatResource] = []
    for message in messages where messageIds.contains(message.id) {
      for resource in message.displayResources where seen.insert(resource.id).inserted {
        resources.append(resource)
      }
    }
    return resources
  }
}
