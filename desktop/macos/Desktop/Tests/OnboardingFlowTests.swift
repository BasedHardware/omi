import XCTest

@testable import Omi_Computer

final class OnboardingFlowTests: XCTestCase {
  func testNewFlowUsesEightSteps() {
    XCTAssertEqual(
      OnboardingFlow.steps,
      ["welcome", "whatOmiNeeds", "screenAndFiles", "audioAndControl", "shortcuts", "yourGoal", "connectedContext", "ready"])
    XCTAssertEqual(OnboardingFlow.lastStepIndex, 7)
  }

  func testStepPhaseAssignment() {
    XCTAssertEqual(OnboardingStep.welcome.phase, .meetOmi)
    XCTAssertEqual(OnboardingStep.whatOmiNeeds.phase, .meetOmi)
    XCTAssertEqual(OnboardingStep.screenAndFiles.phase, .unlock)
    XCTAssertEqual(OnboardingStep.audioAndControl.phase, .unlock)
    XCTAssertEqual(OnboardingStep.shortcuts.phase, .connect)
    XCTAssertEqual(OnboardingStep.yourGoal.phase, .connect)
    XCTAssertEqual(OnboardingStep.connectedContext.phase, .ready)
    XCTAssertEqual(OnboardingStep.ready.phase, .ready)
  }

  func testSkipAvailability() {
    XCTAssertFalse(OnboardingStep.welcome.showsSkip)
    XCTAssertFalse(OnboardingStep.whatOmiNeeds.showsSkip)
    XCTAssertTrue(OnboardingStep.screenAndFiles.showsSkip)
    XCTAssertTrue(OnboardingStep.audioAndControl.showsSkip)
    XCTAssertTrue(OnboardingStep.shortcuts.showsSkip)
    XCTAssertTrue(OnboardingStep.yourGoal.showsSkip)
    XCTAssertFalse(OnboardingStep.connectedContext.showsSkip)
    XCTAssertFalse(OnboardingStep.ready.showsSkip)
  }

  func testStepIndexOrder() {
    XCTAssertEqual(OnboardingStep.allCases.map(\.index), [0, 1, 2, 3, 4, 5, 6, 7])
  }

  // MARK: - Legacy Migration

  func testMigrationMapsNameToWelcome() {
    let result = OnboardingFlow.migrateTo8Step(oldStep: 0)
    XCTAssertEqual(result, 0) // Welcome
  }

  func testMigrationMapsTrustToWhatOmiNeeds() {
    let result = OnboardingFlow.migrateTo8Step(oldStep: 3)
    XCTAssertEqual(result, 1) // What Omi needs
  }

  func testMigrationMapsScreenRecordingToScreenAndFiles() {
    let result = OnboardingFlow.migrateTo8Step(oldStep: 4)
    XCTAssertEqual(result, 2)
  }

  func testMigrationMapsGoalToYourGoal() {
    let result = OnboardingFlow.migrateTo8Step(oldStep: 16)
    XCTAssertEqual(result, 5)
  }

  func testMigrationMapsTasksToReady() {
    let result = OnboardingFlow.migrateTo8Step(oldStep: 18)
    XCTAssertEqual(result, 7)
  }

  func testMigrationClampsOverflow() {
    let result = OnboardingFlow.migrateTo8Step(oldStep: 99)
    XCTAssertEqual(result, OnboardingFlow.lastStepIndex)
  }

  func testMigrationMapsRemovedStepToPreceding() {
    // Old step 2 = HowDidYouHear (removed) → should map to preceding mapped step (Name → Welcome)
    let result = OnboardingFlow.migrateTo8Step(oldStep: 2)
    XCTAssertEqual(result, 0)
  }

  func testMigrationMapsLanguageToWelcome() {
    // Old step 1 = Language (removed) → should map to preceding mapped step (Name → Welcome)
    let result = OnboardingFlow.migrateTo8Step(oldStep: 1)
    XCTAssertEqual(result, 0)
  }

  func testMigrationMapsDataSourcesToGoal() {
    // Old step 14 = DataSources (removed) → should map to preceding mapped step (Goal → Your Goal)
    let result = OnboardingFlow.migrateTo8Step(oldStep: 14)
    XCTAssertEqual(result, 5)
  }

  func testLegacyApiCallsNewMigration() {
    let result = OnboardingFlow.migratedStep(
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
      hasRemovedResearchStep: true,
      hasInsertedBYOKStep: true
    )
    XCTAssertEqual(result, 7)
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
