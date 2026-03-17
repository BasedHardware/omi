import Foundation

enum OnboardingFlow {
  static let steps = ["Chat", "Notifications", "FloatingBar", "VoiceShortcut", "Tasks"]
  static let lastStepIndex = steps.count - 1

  static func migratedStep(
    currentStep: Int,
    hasMigratedVideoStep: Bool,
    hasInsertedVoiceShortcutStep: Bool,
    hasMergedVoiceInputStep: Bool
  ) -> Int {
    var migratedStep = currentStep

    if !hasMigratedVideoStep, migratedStep > 0 {
      migratedStep -= 1
    }

    if !hasInsertedVoiceShortcutStep, migratedStep >= 3 {
      migratedStep += 1
    }

    if !hasMergedVoiceInputStep, migratedStep >= 4 {
      migratedStep -= 1
    }

    return min(max(0, migratedStep), lastStepIndex)
  }

  static func shouldUnlockVoiceShortcutContinue(
    observedShortcutPress: Bool,
    pttState: PushToTalkManager.PTTState
  ) -> Bool {
    observedShortcutPress && pttState == .idle
  }
}
