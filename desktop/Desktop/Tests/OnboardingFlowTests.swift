import XCTest

@testable import Omi_Computer

final class OnboardingFlowTests: XCTestCase {
  func testMergedFlowUsesFiveSteps() {
    XCTAssertEqual(
      OnboardingFlow.steps, ["Chat", "Notifications", "FloatingBar", "VoiceShortcut", "Tasks"])
    XCTAssertEqual(OnboardingFlow.lastStepIndex, 4)
  }

  func testMigrationMovesLegacyVoiceInputToMergedVoiceShortcutStep() {
    let migrated = OnboardingFlow.migratedStep(
      currentStep: 4,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: false
    )

    XCTAssertEqual(migrated, 3)
  }

  func testMigrationClampsOverflowToTasksStep() {
    let migrated = OnboardingFlow.migratedStep(
      currentStep: 9,
      hasMigratedVideoStep: true,
      hasInsertedVoiceShortcutStep: true,
      hasMergedVoiceInputStep: true
    )

    XCTAssertEqual(migrated, OnboardingFlow.lastStepIndex)
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
