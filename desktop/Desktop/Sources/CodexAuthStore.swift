import Foundation

/// Publishes ChatGPT / Codex enrollment changes so Settings can refresh without re-navigation.
@MainActor
final class CodexAuthStore: ObservableObject {
  static let shared = CodexAuthStore()

  var isEnrolled: Bool { CodexAuthService.isEnrolled }

  var isActive: Bool { CodexAuthService.isActive }

  private init() {}

  func notifyEnrollmentChanged() {
    objectWillChange.send()
  }
}
