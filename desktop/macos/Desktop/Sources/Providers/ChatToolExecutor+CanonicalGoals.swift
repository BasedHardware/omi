import Foundation

extension ChatToolExecutor {
  static func canonicalGoalCreationInput(_ arguments: [String: Any]) -> CanonicalGoalCreationInput? {
    func requiredText(_ name: String) -> String? {
      guard let value = arguments[name] as? String else { return nil }
      let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
      return trimmed.isEmpty ? nil : trimmed
    }

    let whyItMatters = (arguments["why_it_matters"] as? String)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let successCriteria = ((arguments["success_criteria"] as? [String]) ?? [])
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    guard let title = requiredText("title"), let desiredOutcome = requiredText("desired_outcome") else {
      return nil
    }
    return CanonicalGoalCreationInput(
      title: title,
      desiredOutcome: desiredOutcome,
      whyItMatters: whyItMatters?.isEmpty == false ? whyItMatters : nil,
      successCriteria: successCriteria
    )
  }
}
