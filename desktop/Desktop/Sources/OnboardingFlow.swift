import Foundation

enum OnboardingFlow {
  static let steps = [
    "Name",
    "Language",
    "Trust",
    "ScreenRecording",
    "FullDiskAccess",
    "FileScan",
    "Microphone",
    "Notifications",
    "Accessibility",
    "Automation",
    "FloatingBarShortcut",
    "FloatingBar",
    "VoiceShortcut",
    "VoiceDemo",
    "Research",
    "Goal",
    "Tasks",
  ]
  static let introStepCount = 12
  static let legacyPostIntroOffset = 11
  static let lastStepIndex = steps.count - 1

  static func migratedStep(
    currentStep: Int,
    hasMigratedVideoStep: Bool,
    hasInsertedVoiceShortcutStep: Bool,
    hasMergedVoiceInputStep: Bool,
    hasRemovedNotificationStep: Bool,
    hasInsertedFloatingBarShortcutStep: Bool,
    hasMigratedPagedIntro: Bool,
    hasReorderedTrustStep: Bool
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

    // FloatingBarShortcut step inserted at index 1; shift users at 1+ up
    if !hasInsertedFloatingBarShortcutStep, migratedStep >= 1 {
      migratedStep += 1
    }

    if !hasMigratedPagedIntro, migratedStep > 0 {
      migratedStep += legacyPostIntroOffset
    }

    if !hasReorderedTrustStep {
      switch migratedStep {
      case 0:
        migratedStep = 2
      case 1:
        migratedStep = 0
      case 2:
        migratedStep = 1
      default:
        break
      }
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
