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
    // After Research removal and BYOK removal, legacy Tasks (19) lands on Tasks (17).
    XCTAssertEqual(migratedTasks, 17)
  }

  func testMigrationRemovesBYOKStepAndKeepsUsersOnTasks() {
    let migratedFromBYOK = OnboardingFlow.migratedStep(
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
      hasInsertedExportsStep: true,
      hasInsertedSecondBrainStep: false,
      hasRemovedResearchStep: true,
      hasInsertedBYOKStep: true,
      hasRemovedBYOKStep: false
    )

    let migratedFromTasks = OnboardingFlow.migratedStep(
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
      hasInsertedBYOKStep: true,
      hasRemovedBYOKStep: false
    )

    XCTAssertEqual(migratedFromBYOK, 17)
    XCTAssertEqual(migratedFromTasks, 17)
  }

  func testMigrationRemovesBYOKAfterPendingNotificationPermissionRemoval() {
    // Legacy index 18 = BYOK while the old notification-permission step (index 8)
    // was still counted. Notification removal must run before BYOK removal so the
    // user lands on Tasks (17), not Goal (16).
    let migratedFromLegacyBYOK = OnboardingFlow.migratedStep(
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
      hasInsertedBYOKStep: true,
      hasRemovedBYOKStep: false,
      hasRemovedNotificationPermissionStep: false
    )

    let migratedFromLegacyTasks = OnboardingFlow.migratedStep(
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
      hasRemovedResearchStep: true,
      hasInsertedBYOKStep: true,
      hasRemovedBYOKStep: false,
      hasRemovedNotificationPermissionStep: false
    )

    // Users paused on the removed notification-permission step (8) advance to
    // Accessibility (still 8), not back to Microphone (7).
    let migratedFromLegacyNotificationPermission = OnboardingFlow.migratedStep(
      currentStep: 8,
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
      hasInsertedBYOKStep: true,
      hasRemovedBYOKStep: false,
      hasRemovedNotificationPermissionStep: false
    )

    XCTAssertEqual(migratedFromLegacyBYOK, 17)
    XCTAssertEqual(migratedFromLegacyTasks, 17)
    XCTAssertEqual(migratedFromLegacyNotificationPermission, 8)
    XCTAssertEqual(OnboardingFlow.steps[8], "Accessibility")
  }

  func testCanJumpAllowsBackwardAndReachedStepsAlways() {
    XCTAssertTrue(OnboardingFlow.canJump(to: 0, furthestStep: 10))
    XCTAssertTrue(OnboardingFlow.canJump(to: 10, furthestStep: 10))
    XCTAssertTrue(OnboardingFlow.canJump(to: 2, furthestStep: 2))
  }

  func testCanJumpBlocksForwardOverUnansweredRequiredSteps() {
    // Steps 0-3 (Name/Language/HowDidYouHear/Trust) have no Skip button.
    XCTAssertFalse(OnboardingFlow.canJump(to: 3, furthestStep: 2))
    XCTAssertFalse(OnboardingFlow.canJump(to: 9, furthestStep: 0))
    XCTAssertFalse(OnboardingFlow.canJump(to: 4, furthestStep: 3))
  }

  func testCanJumpAllowsForwardOverSkippableSteps() {
    // Every step from ScreenRecording (4) onward has a Skip button, so once the
    // required intro is cleared the user may jump anywhere forward.
    XCTAssertTrue(OnboardingFlow.canJump(to: 9, furthestStep: 4))
    XCTAssertTrue(
      OnboardingFlow.canJump(to: OnboardingFlow.lastStepIndex, furthestStep: 4))
    XCTAssertTrue(OnboardingFlow.canJump(to: 17, furthestStep: 10))
  }

  func testCanJumpRejectsOutOfRangeTargets() {
    XCTAssertFalse(OnboardingFlow.canJump(to: -1, furthestStep: 10))
    XCTAssertFalse(
      OnboardingFlow.canJump(to: OnboardingFlow.steps.count, furthestStep: 17))
  }

  func testUnskippableStepsMatchFlowLayout() {
    // Static tripwire: if steps are reordered/inserted so that the Skip-less
    // intro block moves, unskippableSteps must be updated with it.
    XCTAssertEqual(OnboardingFlow.steps[0], "Name")
    XCTAssertEqual(OnboardingFlow.steps[1], "Language")
    XCTAssertEqual(OnboardingFlow.steps[2], "HowDidYouHear")
    XCTAssertEqual(OnboardingFlow.steps[3], "Trust")
    XCTAssertEqual(OnboardingFlow.unskippableSteps, [0, 1, 2, 3])
  }

  func testVoiceShortcutContinueUnlocksOnlyAfterReleaseFollowingObservedPress() {
    XCTAssertFalse(
      OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: false,
        voiceTurnPhase: nil
      )
    )
    XCTAssertFalse(
      OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: true,
        voiceTurnPhase: .recording
      )
    )
    XCTAssertTrue(
      OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: true,
        voiceTurnPhase: nil
      )
    )
  }

  /// Static tripwire (source inspection, not behavioral coverage): a step's
  /// deferred completion callback must not fire after the user navigates away.
  /// Each step that schedules "advance later" work stores it in a cancellable
  /// Task and cancels it in .onDisappear — an uncancellable asyncAfter here
  /// yanks the user forward after they pressed Back (free-navigation regression).
  func testDeferredStepAdvanceCallbacksAreCancellableAndCancelledOnDisappear() throws {
    // OnboardingPermissionStepView is intentionally absent: it no longer defers
    // advance at all (granting stays on the page until the user presses
    // Continue) — covered by testPermissionStepNeverAutoAdvancesOnGrant.
    let sites: [(file: String, task: String)] = [
      ("OnboardingGoalStepView.swift", "saveTask"),
      ("OnboardingHowDidYouHearStepView.swift", "advanceTask"),
    ]
    for site in sites {
      let source = try onboardingSourceFile(site.file)
      XCTAssertTrue(
        source.contains("@State private var \(site.task): Task<Void, Never>?"),
        "\(site.file): deferred advance must be a stored cancellable Task")
      XCTAssertTrue(
        source.contains(".onDisappear"), "\(site.file): must cancel on disappear")
      XCTAssertTrue(
        source.contains("\(site.task)?.cancel()"),
        "\(site.file): stored task must be cancelled")
      XCTAssertFalse(
        source.contains("asyncAfter"),
        "\(site.file): asyncAfter is uncancellable — use a stored Task")
    }
  }

  /// Regression: lazy dev mode makes checkAllPermissions() skip the
  /// FDA/accessibility/automation probes, so the permission page's status froze
  /// on named dev bundles. The page must probe its own permission directly.
  func testPermissionPageProbesItsOwnPermission() throws {
    // omi-test-quality: source-inspection -- static contract: the probes hit
    // live TCC/AX/AppleEvents APIs and cannot be exercised hermetically.
    let source = try onboardingSourceFile("OnboardingPermissionStepView.swift")
    guard let refresh = source.range(of: "private func refreshPermissionState()") else {
      return XCTFail("refreshPermissionState must exist")
    }
    let body = String(source[refresh.lowerBound...].prefix(1200))
    for probe in ["checkFullDiskAccess()", "checkAccessibilityPermission()", "checkAutomationPermission()"] {
      XCTAssertTrue(
        body.contains(probe),
        "refreshPermissionState must call \(probe) so lazy dev mode can't freeze the page status")
    }
  }

  func testPermissionContinueAdvancesWhenGrantAlreadyApplies() {
    XCTAssertEqual(OnboardingFlow.permissionContinueAction(needsRelaunchToApply: false), .advance)
  }

  func testPermissionContinueOffersReopenOnlyWhenGrantNeedsRelaunch() {
    XCTAssertEqual(OnboardingFlow.permissionContinueAction(needsRelaunchToApply: true), .offerReopen)
  }

  func testPermissionStepNeverAutoAdvancesOnGrant() throws {
    // omi-test-quality: source-inspection -- static contract: SwiftUI navigation-on-grant
    // cannot be exercised hermetically; the review-blocked pattern (navigating when
    // isGranted flips) must stay out — grant stays on the page until Continue.
    let source = try onboardingSourceFile("OnboardingPermissionStepView.swift")
    XCTAssertFalse(
      source.contains("scheduleAutoAdvance"),
      "granting a permission must not schedule an auto-advance")
    if let grantChange = source.range(of: "onChange(of: isGranted)") {
      let handler = source[grantChange.upperBound...].prefix(300)
      XCTAssertFalse(
        handler.contains("onContinue()"),
        "granting must not navigate — only the explicit Continue button advances")
      XCTAssertFalse(
        handler.contains("showReopenPrompt = true"),
        "granting must not pop the reopen prompt — Continue raises it")
    }
  }

  func testHowDidYouHearKeepsOtherLast() {
    XCTAssertEqual(OnboardingHowDidYouHearStepView.sources.last?.name, "Other")
    XCTAssertEqual(
      OnboardingHowDidYouHearStepView.sources.first(where: { $0.name == "YouTube" })?.glyph,
      .youtube)
    XCTAssertEqual(
      OnboardingHowDidYouHearStepView.sources.first(where: { $0.name == "Product Hunt" })?.glyph,
      .productHunt)
    XCTAssertEqual(
      OnboardingHowDidYouHearStepView.sources.count,
      Set(OnboardingHowDidYouHearStepView.sources.map(\.name)).count,
      "duplicate chips would break selection")
  }

  private func onboardingSourceFile(_ name: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Onboarding")
      .appendingPathComponent(name)
    // omi-test-quality: source-inspection -- static contract: forbids uncancellable deferred-advance patterns in step views
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
