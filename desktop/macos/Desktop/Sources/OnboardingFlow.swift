import Foundation

enum OnboardingFlow {
  static let steps = [
    "Name",
    "Language",
    "HowDidYouHear",
    "Trust",
    "ScreenRecording",
    "FullDiskAccess",
    "FileScan",
    "Microphone",
    "Accessibility",
    "Automation",
    "FloatingBarShortcut",
    "FloatingBar",
    "VoiceShortcut",
    "VoiceDemo",
    "DataSources",
    "Exports",
    "Goal",
    "BringYourOwnKeys",
    "Tasks",
  ]
  static let introStepCount = 13
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
    hasReorderedTrustStep: Bool,
    hasInsertedHowDidYouHearStep: Bool = true,
    hasInsertedDataSourcesStep: Bool = true,
    hasInsertedExportsStep: Bool = true,
    hasInsertedSecondBrainStep: Bool = false,
    hasRemovedResearchStep: Bool = false,
    hasInsertedBYOKStep: Bool = true
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

    // HowDidYouHear step inserted at index 2; shift users at 2+ up
    if !hasInsertedHowDidYouHearStep, migratedStep >= 2 {
      migratedStep += 1
    }

    // DataSources step inserted after Research; shift users at Goal+ up
    if !hasInsertedDataSourcesStep, migratedStep >= 16 {
      migratedStep += 1
    }

    if !hasInsertedExportsStep, migratedStep >= 16 {
      migratedStep += 1
    }

    // Research step was merged into DataSources. Keep users on that stage if they were
    // already there, and shift later steps down by one.
    if !hasRemovedResearchStep, migratedStep > 15 {
      migratedStep -= 1
    }

    // Temporary SecondBrainLive step was removed; shift users at Goal+ down
    if hasInsertedSecondBrainStep, migratedStep >= 18 {
      migratedStep -= 1
    }

    // BringYourOwnKeys step inserted at index 17 (between Goal and Tasks);
    // push users who were on Tasks forward by one so they still land on Tasks.
    if !hasInsertedBYOKStep, migratedStep >= 17 {
      migratedStep += 1
    }

    // Only reorder for existing users who already had the old Trust-first layout.
    // New users (all flags false) start with the correct Name-first order.
    if !hasReorderedTrustStep && hasMigratedPagedIntro {
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
