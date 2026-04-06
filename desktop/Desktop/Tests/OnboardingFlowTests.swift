import XCTest

@testable import Omi_Computer

final class OnboardingFlowTests: XCTestCase {
  func testMergedFlowUsesEighteenSteps() {
    XCTAssertEqual(
      OnboardingFlow.steps,
      [
        "Name", "Language", "HowDidYouHear", "Trust", "ScreenRecording",
        "FullDiskAccess", "FileScan", "Microphone", "Notifications", "Accessibility",
        "Automation", "FloatingBarShortcut", "FloatingBar", "VoiceShortcut", "VoiceDemo",
        "DataSources", "Goal", "Tasks",
      ])
    XCTAssertEqual(OnboardingFlow.lastStepIndex, 17)
  }

  func testMigrationMovesLegacyVoiceInputToMergedVoiceShortcutStep() {
    let migrated = OnboardingFlow.migratedStep(
      currentStep: 4,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: false,
      hasRemovedNotificationStep: true,
      hasInsertedFloatingBarShortcutStep: true,
      hasMigratedPagedIntro: true,
      hasReorderedTrustStep: true,
      hasInsertedDataSourcesStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: true
    )

    XCTAssertEqual(migrated, 3)
  }

  func testMigrationClampsOverflowToTasksStep() {
    let migrated = OnboardingFlow.migratedStep(
      currentStep: 99,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: true,
      hasRemovedNotificationStep: true,
      hasInsertedFloatingBarShortcutStep: true,
      hasMigratedPagedIntro: true,
      hasReorderedTrustStep: true,
      hasInsertedDataSourcesStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: true
    )

    XCTAssertEqual(migrated, OnboardingFlow.lastStepIndex)
  }

  func testMigrationMapsRemovedResearchStepToDataSourcesAndShiftsLaterSteps() {
    let migratedResearch = OnboardingFlow.migratedStep(
      currentStep: 15,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: true,
      hasRemovedNotificationStep: true,
      hasInsertedFloatingBarShortcutStep: true,
      hasMigratedPagedIntro: true,
      hasReorderedTrustStep: true,
      hasInsertedHowDidYouHearStep: true,
      hasInsertedDataSourcesStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: false
    )

    let migratedGoal = OnboardingFlow.migratedStep(
      currentStep: 17,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: true,
      hasRemovedNotificationStep: true,
      hasInsertedFloatingBarShortcutStep: true,
      hasMigratedPagedIntro: true,
      hasReorderedTrustStep: true,
      hasInsertedHowDidYouHearStep: true,
      hasInsertedDataSourcesStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: false
    )

    let migratedTasks = OnboardingFlow.migratedStep(
      currentStep: 18,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: true,
      hasRemovedNotificationStep: true,
      hasInsertedFloatingBarShortcutStep: true,
      hasMigratedPagedIntro: true,
      hasReorderedTrustStep: true,
      hasInsertedHowDidYouHearStep: true,
      hasInsertedDataSourcesStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: false
    )

    XCTAssertEqual(migratedResearch, 15)
    XCTAssertEqual(migratedGoal, 16)
    XCTAssertEqual(migratedTasks, 17)
  }

  func testVoiceShortcutContinueUnlocksOnlyAfterReleaseFollowingObservedPress() {
    XCTAssertFalse(
      OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: false,
        pttState: .idle
      )
    )
    XCTAssertFalse(
      OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: true,
        pttState: .listening
      )
    )
    XCTAssertTrue(
      OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: true,
        pttState: .idle
      )
    )
  }
}
