import Foundation

// MARK: - Onboarding Chat Persistence

/// Persists onboarding UI progress across app restarts (e.g. screen recording permission requires restart).
/// Messages are stored on the backend via the normal chat save path. Session identity is resolved
/// by the kernel via `surface_conversations` for the onboarding surface.
enum OnboardingChatPersistence {
  /// Mark that onboarding is in progress (for restart detection)
  static func saveMidOnboarding() {
    UserDefaults.standard.set(true, forKey: .onboardingMidOnboarding)
  }

  /// Whether the app was restarted mid-onboarding
  static var isMidOnboarding: Bool {
    UserDefaults.standard.bool(forKey: .onboardingMidOnboarding)
  }

  // MARK: - Tool Completion

  /// Mark that `complete_onboarding` tool was called (so button shows on restart)
  static func markToolCompleted() {
    UserDefaults.standard.set(true, forKey: .onboardingToolCompleted)
  }

  /// Mark that the user answered the monthly goal question
  static func markGoalCompleted() {
    UserDefaults.standard.set(true, forKey: .onboardingGoalCompleted)
  }

  /// Whether the user already answered the monthly goal question
  static var isGoalCompleted: Bool {
    UserDefaults.standard.bool(forKey: .onboardingGoalCompleted)
  }

  /// Clear all persisted onboarding data
  static func clear() {
    // Legacy onboarding ACP session id (pre-kernel surface_conversations)
    UserDefaults.standard.removeObject(forKey: .onboardingACPSessionId)
    UserDefaults.standard.removeObject(forKey: .onboardingMidOnboarding)
    // Written only by the retired step-wizard OnboardingView; still wiped so
    // installs that ran it don't leak state across accounts.
    UserDefaults.standard.removeObject(forKey: .onboardingExplorationText)
    UserDefaults.standard.removeObject(forKey: .onboardingExplorationCompleted)
    UserDefaults.standard.removeObject(forKey: .onboardingToolCompleted)
    UserDefaults.standard.removeObject(forKey: .onboardingGoalCompleted)
    // Clean up legacy messages key if present
    UserDefaults.standard.removeObject(forKey: .onboardingChatMessages)
  }
}
