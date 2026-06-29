import Foundation

// MARK: - New 8-Step Spec

enum OnboardingStep: String, CaseIterable {
  case welcome
  case whatOmiNeeds
  case screenAndFiles
  case audioAndControl
  case shortcuts
  case yourGoal
  case connectedContext
  case ready

  var index: Int { OnboardingStep.allCases.firstIndex(of: self)! }
  var phase: OnboardingPhase {
    switch self {
    case .welcome, .whatOmiNeeds: return .meetOmi
    case .screenAndFiles, .audioAndControl: return .unlock
    case .shortcuts, .yourGoal: return .connect
    case .connectedContext, .ready: return .ready
    }
  }
  var showsSkip: Bool {
    switch self {
    case .screenAndFiles, .audioAndControl, .shortcuts, .yourGoal: return true
    default: return false
    }
  }
}

enum OnboardingPhase: Int {
  case meetOmi = 1
  case unlock = 2
  case connect = 3
  case ready = 4
}

// MARK: - Flow & Migration

enum OnboardingFlow {
  /// New 8-step names (also used as string IDs for backward compatibility)
  static let steps = OnboardingStep.allCases.map(\.rawValue)
  static let lastStepIndex = steps.count - 1

  /// Intro steps before the permissions phase — kept for backward compat
  static let introStepCount = 2
  /// Offset used in legacy migration — kept at 0 since all steps are now "intro"
  static let legacyPostIntroOffset = 0

  // Old step index → new step index mapping
  private static let legacyStepMap: [Int: Int] = [
    0: 0,   // Name → Welcome
    3: 1,   // Trust → What Omi needs
    4: 2,   // ScreenRecording → Screen & Files
    7: 3,   // Microphone → Audio & Control
    10: 4,  // FloatingBarShortcut → Shortcuts
    16: 5,  // Goal → Your Goal
    18: 7,  // Tasks → Ready
  ]

  /// Check if a legacy step should be shown in the new 8-step flow.
  /// Returns nil for removed steps (Language, HowDidYouHear, DataSources, etc.).
  static func migrateTo8Step(oldStep: Int) -> Int {
    let clamped = min(max(0, oldStep), 18)
    for oldIdx in (0...clamped).reversed() {
      if let newIdx = legacyStepMap[oldIdx] {
        return min(newIdx, lastStepIndex)
      }
    }
    return 0
  }

  // MARK: - Legacy migration API (kept for backward compatibility)

  static func migratedStep(
    currentStep: Int,
    hasMigratedVideoStep: Bool = true,
    hasInsertedVoiceShortcutStep: Bool = true,
    hasMergedVoiceInputStep: Bool = true,
    hasRemovedNotificationStep: Bool = true,
    hasInsertedFloatingBarShortcutStep: Bool = true,
    hasMigratedPagedIntro: Bool = true,
    hasReorderedTrustStep: Bool = true,
    hasInsertedHowDidYouHearStep: Bool = true,
    hasInsertedDataSourcesStep: Bool = true,
    hasInsertedExportsStep: Bool = true,
    hasInsertedSecondBrainStep: Bool = false,
    hasRemovedResearchStep: Bool = true,
    hasInsertedBYOKStep: Bool = true
  ) -> Int {
    // Use the new 8-step migration directly
    return migrateTo8Step(oldStep: currentStep)
  }

  static func shouldUnlockVoiceShortcutContinue(
    observedShortcutPress: Bool,
    pttState: PushToTalkManager.PTTState
  ) -> Bool {
    observedShortcutPress && pttState == .idle
  }
}
