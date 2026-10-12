import Foundation

/// Title compatibility for catalogs that predate explicit plan IDs.
/// Bare Pro is Operator; the retired Omi Pro title still identifies Architect.
enum SubscriptionPlanNames {
  static func planId(from title: String) -> String? {
    let normalized = title.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if normalized.contains("architect") || normalized.contains("omi pro") { return "architect" }
    if normalized.contains("operator") || normalized == "pro" || normalized.hasPrefix("pro ") {
      return "operator"
    }
    if normalized.contains("plus") { return "plus" }
    if normalized.contains("neo") || normalized.contains("legacy")
      || normalized == "unlimited plan" || normalized.hasPrefix("omi unlimited")
    {
      return "unlimited"
    }
    if normalized.contains("unlimited") { return "unlimited_v2" }
    return nil
  }
}
