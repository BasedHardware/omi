import Foundation

enum OnboardingFlow {
  static let steps = ["Chat", "FloatingBar", "VoiceShortcut", "Tasks"]
  static let lastStepIndex = steps.count - 1

  static func migratedStep(
    currentStep: Int,
    hasMigratedVideoStep: Bool,
    hasInsertedVoiceShortcutStep: Bool,
    hasMergedVoiceInputStep: Bool,
    hasRemovedNotificationStep: Bool
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

    // Notifications step (old step 1) was removed; shift users down
    if !hasRemovedNotificationStep, migratedStep >= 1 {
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
