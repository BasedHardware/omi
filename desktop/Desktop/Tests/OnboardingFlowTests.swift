import XCTest

@testable import Omi_Computer

final class OnboardingFlowTests: XCTestCase {
  func testMergedFlowUsesEighteenSteps() {
    XCTAssertEqual(
      OnboardingFlow.steps,
      [
        "Name", "Language", "HowDidYouHear", "Trust", "ScreenRecording",
        "FullDiskAccess", "FileScan", "Microphone", "Accessibility", "Automation",
        "FloatingBarShortcut", "FloatingBar", "VoiceShortcut", "VoiceDemo", "DataSources",
        "Exports", "Goal", "Tasks",
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
      hasInsertedExportsStep: true,
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
      hasInsertedExportsStep: true,
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
      hasInsertedExportsStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: false
    )

    let migratedLegacyGoalAfterExportInsert = OnboardingFlow.migratedStep(
      currentStep: 16,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: true,
      hasRemovedNotificationStep: true,
      hasInsertedFloatingBarShortcutStep: true,
      hasMigratedPagedIntro: true,
      hasReorderedTrustStep: true,
      hasInsertedHowDidYouHearStep: true,
      hasInsertedDataSourcesStep: true,
      hasInsertedExportsStep: false,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: true
    )

    let migratedGoal = OnboardingFlow.migratedStep(
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
      hasInsertedExportsStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: false
    )

    let migratedTasks = OnboardingFlow.migratedStep(
      currentStep: 19,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: true,
      hasRemovedNotificationStep: true,
      hasInsertedFloatingBarShortcutStep: true,
      hasMigratedPagedIntro: true,
      hasReorderedTrustStep: true,
      hasInsertedHowDidYouHearStep: true,
      hasInsertedDataSourcesStep: true,
      hasInsertedExportsStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: false
    )

    XCTAssertEqual(migratedResearch, 15)
    XCTAssertEqual(migratedLegacyGoalAfterExportInsert, 17)
    XCTAssertEqual(migratedGoal, 17)
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
