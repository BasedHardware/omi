import Foundation

// MARK: - Onboarding Chat Persistence

/// Persists onboarding UI progress across app restarts (e.g. screen recording permission requires restart).
/// Messages are stored on the backend via the normal chat save path. Session identity is resolved
/// by the kernel via `surface_conversations` for the onboarding surface.
enum OnboardingChatPersistence {
  private static let midOnboardingKey = "onboardingMidOnboarding"
  private static let explorationTextKey = "onboardingExplorationText"
  private static let explorationCompletedKey = "onboardingExplorationCompleted"
  private static let toolCompletedKey = "onboardingToolCompleted"
  private static let goalCompletedKey = "onboardingGoalCompleted"

  /// Mark that onboarding is in progress (for restart detection)
  static func saveMidOnboarding() {
    UserDefaults.standard.set(true, forKey: midOnboardingKey)
  }

  /// Whether the app was restarted mid-onboarding
  static var isMidOnboarding: Bool {
    UserDefaults.standard.bool(forKey: midOnboardingKey)
  }

  // MARK: - Exploration Persistence

  /// Save exploration state so it survives app restarts
  static func saveExplorationState(text: String, completed: Bool) {
    UserDefaults.standard.set(text, forKey: explorationTextKey)
    UserDefaults.standard.set(completed, forKey: explorationCompletedKey)
  }

  /// Load saved exploration state (returns nil if no exploration was saved)
  static func loadExplorationState() -> (text: String, completed: Bool)? {
    let text = UserDefaults.standard.string(forKey: explorationTextKey) ?? ""
    let completed = UserDefaults.standard.bool(forKey: explorationCompletedKey)
    guard !text.isEmpty || completed else { return nil }
    return (text, completed)
  }

  /// Whether exploration already completed in a prior session
  static var isExplorationCompleted: Bool {
    UserDefaults.standard.bool(forKey: explorationCompletedKey)
  }

  // MARK: - Tool Completion

  /// Mark that `complete_onboarding` tool was called (so button shows on restart)
  static func markToolCompleted() {
    UserDefaults.standard.set(true, forKey: toolCompletedKey)
  }

  /// Whether `complete_onboarding` was already called in a prior session
  static var isToolCompleted: Bool {
    UserDefaults.standard.bool(forKey: toolCompletedKey)
  }

  /// Mark that the user answered the monthly goal question
  static func markGoalCompleted() {
    UserDefaults.standard.set(true, forKey: goalCompletedKey)
  }

  /// Whether the user already answered the monthly goal question
  static var isGoalCompleted: Bool {
    UserDefaults.standard.bool(forKey: goalCompletedKey)
  }

  /// Clear all persisted onboarding data
  static func clear() {
    // Legacy onboarding ACP session id (pre-kernel surface_conversations)
    UserDefaults.standard.removeObject(forKey: .onboardingACPSessionId)
    UserDefaults.standard.removeObject(forKey: midOnboardingKey)
    UserDefaults.standard.removeObject(forKey: explorationTextKey)
    UserDefaults.standard.removeObject(forKey: explorationCompletedKey)
    UserDefaults.standard.removeObject(forKey: toolCompletedKey)
    UserDefaults.standard.removeObject(forKey: goalCompletedKey)
    // Clean up legacy messages key if present
    UserDefaults.standard.removeObject(forKey: .onboardingChatMessages)
  }
}
