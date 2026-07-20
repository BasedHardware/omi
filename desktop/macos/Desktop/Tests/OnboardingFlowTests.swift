import AppKit
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

  func testPhasesTileAllStepsContiguously() {
    // The segmented progress bar renders one segment per phase; a step outside
    // every phase (or in two) would render a broken bar. Phases must cover
    // 0..<steps.count exactly, in order, with no gaps or overlaps.
    var nextStep = 0
    for phase in OnboardingFlow.phases {
      XCTAssertFalse(phase.steps.isEmpty, "phase \(phase.title) is empty")
      XCTAssertEqual(phase.steps.lowerBound, nextStep, "phase \(phase.title) leaves a gap or overlaps")
      nextStep = phase.steps.upperBound
    }
    XCTAssertEqual(nextStep, OnboardingFlow.steps.count)
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

  func testNameFieldNeverPrefillsTherePlaceholder() {
    XCTAssertEqual(OnboardingFlow.nameFieldPrefill("there"), "")
    XCTAssertEqual(OnboardingFlow.nameFieldPrefill(""), "")
    XCTAssertEqual(OnboardingFlow.nameFieldPrefill("Skander"), "Skander")
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

  // Regression: arrow navigation must be computed from persisted step state and
  // applied by the mounted view — the NSEvent monitor's captured view copy drops
  // @AppStorage writes on some macOS versions. These cover the extracted
  // decision + validation seam the monitor and .onReceive now route through.
  func testArrowNavigationDecisions() {
    // Left/up go back one step; blocked at the first step.
    XCTAssertEqual(
      OnboardingFlow.arrowNavigation(keyCode: 123, step: 10, furthestStep: 15), .jump(to: 9))
    XCTAssertEqual(
      OnboardingFlow.arrowNavigation(keyCode: 126, step: 1, furthestStep: 1), .jump(to: 0))
    XCTAssertNil(OnboardingFlow.arrowNavigation(keyCode: 123, step: 0, furthestStep: 5))
    // Right/down jump when the next step is cleared or skippable.
    XCTAssertEqual(
      OnboardingFlow.arrowNavigation(keyCode: 124, step: 10, furthestStep: 15), .jump(to: 11))
    XCTAssertEqual(
      OnboardingFlow.arrowNavigation(keyCode: 125, step: 5, furthestStep: 5), .jump(to: 6))
    // At an uncleared required step, defer to the step's own Continue gating.
    XCTAssertEqual(
      OnboardingFlow.arrowNavigation(keyCode: 124, step: 1, furthestStep: 1),
      .forwardDefaultAction)
    // Non-arrow keys navigate nothing.
    XCTAssertNil(OnboardingFlow.arrowNavigation(keyCode: 36, step: 5, furthestStep: 10))
  }

  @MainActor
  func testKeyboardNavigationOwnerInstallsOnceAndRoutesAcceptedArrowToMountedState() {
    let monitor = OnboardingKeyboardMonitorSpy()
    let owner = OnboardingKeyboardNavigationCoordinator(
      installMonitor: monitor.install,
      removeMonitor: monitor.remove
    )
    var currentStep = 10
    var navigationCount = 0
    let navigation = OnboardingKeyboardNavigationCoordinator.Navigation(
      isActive: { true },
      focusedControlOwnsArrows: { false },
      currentStep: { currentStep },
      furthestStep: { 15 },
      apply: { action in
        navigationCount += 1
        guard case .jump(let target) = action else { return false }
        currentStep = target
        return true
      }
    )

    let firstLease = owner.mount(navigation)
    let replacementLease = owner.mount(navigation)

    XCTAssertEqual(monitor.installCount, 1, "repeated mount must retain one monitor token")
    XCTAssertNil(monitor.dispatch(onboardingKeyEvent(keyCode: 124)))
    XCTAssertEqual(navigationCount, 1, "the installed monitor must call the mounted navigation owner")
    XCTAssertEqual(currentStep, 11)
    owner.unmount(firstLease)
    XCTAssertEqual(monitor.removeCount, 0, "the first lease is stale after replacement")
    owner.unmount(replacementLease)
    XCTAssertEqual(monitor.removeCount, 1)
  }

  @MainActor
  func testKeyboardNavigationReplacementSharesOneMonitorAndIgnoresStaleUnmount() {
    let monitor = OnboardingKeyboardMonitorSpy()
    let owner = OnboardingKeyboardNavigationCoordinator(
      installMonitor: monitor.install,
      removeMonitor: monitor.remove
    )
    var outgoingMutations = 0
    var replacementStep = 10

    let firstLease = owner.mount(
      .init(
        isActive: { true },
        focusedControlOwnsArrows: { false },
        currentStep: { 10 },
        furthestStep: { 15 },
        apply: { _ in
          outgoingMutations += 1
          return true
        }
      ))
    let replacementLease = owner.mount(
      .init(
        isActive: { true },
        focusedControlOwnsArrows: { false },
        currentStep: { replacementStep },
        furthestStep: { 15 },
        apply: { action in
          guard case .jump(let target) = action else { return false }
          replacementStep = target
          return true
        }
      ))

    XCTAssertEqual(monitor.installCount, 1, "a replacement must not install a second local monitor")
    owner.unmount(firstLease)
    XCTAssertNil(monitor.dispatch(onboardingKeyEvent(keyCode: 124)))
    XCTAssertEqual(outgoingMutations, 0, "a stale owner must not receive navigation")
    XCTAssertEqual(replacementStep, 11)
    owner.unmount(replacementLease)
    XCTAssertEqual(monitor.removeCount, 1, "the final active lease removes the one monitor")
  }

  @MainActor
  func testKeyboardNavigationResponderPolicyPreservesTextAndDirectionalControlsButNotButtons() {
    XCTAssertTrue(OnboardingKeyboardResponderPolicy.ownsArrows(firstResponder: NSTextView()))
    XCTAssertTrue(OnboardingKeyboardResponderPolicy.ownsArrows(firstResponder: NSSegmentedControl()))
    XCTAssertTrue(OnboardingKeyboardResponderPolicy.ownsArrows(firstResponder: NSStepper()))
    XCTAssertFalse(
      OnboardingKeyboardResponderPolicy.ownsArrows(
        firstResponder: NSButton(title: "Continue", target: nil, action: nil)),
      "ordinary default-action buttons must leave arrows available to onboarding navigation"
    )
  }

  @MainActor
  func testKeyboardNavigationPreservesFocusedModifiedAndRepeatedArrows() {
    let monitor = OnboardingKeyboardMonitorSpy()
    let owner = OnboardingKeyboardNavigationCoordinator(
      installMonitor: monitor.install,
      removeMonitor: monitor.remove
    )
    var navigationCount = 0
    var firstResponder: NSResponder? = NSTextView()
    let navigation = OnboardingKeyboardNavigationCoordinator.Navigation(
      isActive: { true },
      focusedControlOwnsArrows: { OnboardingKeyboardResponderPolicy.ownsArrows(firstResponder: firstResponder) },
      currentStep: { 10 },
      furthestStep: { 15 },
      apply: { _ in
        navigationCount += 1
        return true
      }
    )

    let textLease = owner.mount(navigation)
    let focusedArrow = onboardingKeyEvent(keyCode: 124)
    XCTAssertTrue(monitor.dispatch(focusedArrow) === focusedArrow)

    firstResponder = NSButton(title: "Continue", target: nil, action: nil)
    let buttonLease = owner.mount(
      OnboardingKeyboardNavigationCoordinator.Navigation(
        isActive: { true },
        focusedControlOwnsArrows: {
          OnboardingKeyboardResponderPolicy.ownsArrows(firstResponder: firstResponder)
        },
        currentStep: { 10 },
        furthestStep: { 15 },
        apply: { _ in
          navigationCount += 1
          return true
        }
      ))
    XCTAssertNil(monitor.dispatch(onboardingKeyEvent(keyCode: 124)))
    let modifiedArrow = onboardingKeyEvent(keyCode: 124, modifierFlags: [.command])
    let repeatArrow = onboardingKeyEvent(keyCode: 124, isARepeat: true)
    XCTAssertTrue(monitor.dispatch(modifiedArrow) === modifiedArrow)
    XCTAssertTrue(monitor.dispatch(repeatArrow) === repeatArrow)
    XCTAssertEqual(navigationCount, 1, "an ordinary button must not block onboarding navigation")
    XCTAssertEqual(monitor.installCount, 1, "updating mounted state must not install a second monitor")
    owner.unmount(textLease)
    XCTAssertEqual(monitor.removeCount, 0)
    owner.unmount(buttonLease)
  }

  @MainActor
  func testKeyboardNavigationInvokesRequiredStepDefaultActionOnce() {
    let monitor = OnboardingKeyboardMonitorSpy()
    let owner = OnboardingKeyboardNavigationCoordinator(
      installMonitor: monitor.install,
      removeMonitor: monitor.remove
    )
    let window = OnboardingDefaultActionRecordingWindow()
    let lease = owner.mount(
      OnboardingKeyboardNavigationCoordinator.Navigation(
        isActive: { true },
        focusedControlOwnsArrows: { false },
        currentStep: { 1 },
        furthestStep: { 1 },
        apply: { action in
          guard case .forwardDefaultAction = action else { return false }
          return OnboardingDefaultActionPoster.post(in: window)
        }
      ))

    XCTAssertNil(monitor.dispatch(onboardingKeyEvent(keyCode: 124)))
    XCTAssertEqual(window.postedEvents.map(\.type), [.keyDown, .keyUp])
    XCTAssertTrue(window.postedEvents.allSatisfy { $0.keyCode == 36 })
    owner.unmount(lease)
  }

  @MainActor
  func testKeyboardNavigationOwnerRemountsWithFreshTokenAndDeinitIsSafe() {
    let monitor = OnboardingKeyboardMonitorSpy()
    var owner: OnboardingKeyboardNavigationCoordinator? = OnboardingKeyboardNavigationCoordinator(
      installMonitor: monitor.install,
      removeMonitor: monitor.remove
    )
    let weakOwner = OnboardingWeakReference(owner)
    let navigation = OnboardingKeyboardNavigationCoordinator.Navigation(
      isActive: { true },
      focusedControlOwnsArrows: { false },
      currentStep: { 10 },
      furthestStep: { 15 },
      apply: { _ in true }
    )

    let firstLease = owner?.mount(navigation)
    owner?.unmount(firstLease)
    _ = owner?.mount(navigation)
    XCTAssertEqual(monitor.installCount, 2)
    XCTAssertEqual(monitor.removeCount, 1)
    XCTAssertNotEqual(monitor.installedTokens[0], monitor.installedTokens[1])

    owner = nil

    XCTAssertNil(weakOwner.value)
    XCTAssertEqual(monitor.removeCount, 2, "deinit must remove a mounted token safely")
  }

  func testValidatedNavigationTargetPolicy() {
    // Backward always allowed, forward gated by canJump, range clamped.
    XCTAssertEqual(
      OnboardingFlow.validatedNavigationTarget(9, currentStep: 10, furthestStep: 15), 9)
    XCTAssertEqual(
      OnboardingFlow.validatedNavigationTarget(11, currentStep: 10, furthestStep: 15), 11)
    XCTAssertNil(OnboardingFlow.validatedNavigationTarget(2, currentStep: 1, furthestStep: 1))
    XCTAssertNil(OnboardingFlow.validatedNavigationTarget(-1, currentStep: 0, furthestStep: 0))
    XCTAssertNil(
      OnboardingFlow.validatedNavigationTarget(
        OnboardingFlow.lastStepIndex + 1, currentStep: 5, furthestStep: 17))
  }

  @MainActor
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

  @MainActor
  private func onboardingKeyEvent(
    keyCode: UInt16,
    modifierFlags: NSEvent.ModifierFlags = [],
    isARepeat: Bool = false
  ) -> NSEvent {
    guard
      let event = NSEvent.keyEvent(
        with: .keyDown,
        location: .zero,
        modifierFlags: modifierFlags,
        timestamp: ProcessInfo.processInfo.systemUptime,
        windowNumber: 0,
        context: nil,
        characters: "",
        charactersIgnoringModifiers: "",
        isARepeat: isARepeat,
        keyCode: keyCode
      )
    else {
      fatalError("Unable to create a synthetic key event")
    }
    return event
  }
}

@MainActor
private final class OnboardingKeyboardMonitorSpy {
  private var handler: ((NSEvent) -> NSEvent?)?
  private var nextToken = 0
  private(set) var installCount = 0
  private(set) var removeCount = 0
  private(set) var installedTokens: [Int] = []

  func install(_ handler: @escaping (NSEvent) -> NSEvent?) -> Any? {
    installCount += 1
    nextToken += 1
    installedTokens.append(nextToken)
    self.handler = handler
    return nextToken
  }

  func remove(_ token: Any) {
    removeCount += 1
    handler = nil
  }

  func dispatch(_ event: NSEvent) -> NSEvent? {
    guard let handler else { return event }
    return handler(event)
  }
}

@MainActor
private final class OnboardingDefaultActionRecordingWindow: NSWindow {
  private(set) var postedEvents: [NSEvent] = []

  init() {
    super.init(
      contentRect: .zero,
      styleMask: [.titled],
      backing: .buffered,
      defer: false
    )
  }

  override func postEvent(_ event: NSEvent, atStart flag: Bool) {
    postedEvents.append(event)
  }
}

private final class OnboardingWeakReference<Value: AnyObject> {
  weak var value: Value?

  init(_ value: Value?) {
    self.value = value
  }
}
