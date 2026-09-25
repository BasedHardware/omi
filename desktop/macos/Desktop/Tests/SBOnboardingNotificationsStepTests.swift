import XCTest

@testable import Omi_Computer

/// Regression coverage for the notification-permission dead end: the live
/// SecondBrain onboarding (`SBOnboardingModel`) had no `.notifications` step at
/// all, so a user who never happened to grant Notifications elsewhere was never
/// asked — and, per `AppState+Permissions.swift`, could never be asked again
/// outside this flow. These tests guard the step's placement and wiring rather
/// than re-testing `NotificationPermissionPolicy.enableAction`, which already
/// has coverage in `UserNotificationCallbackBridgeTests`.
@MainActor
final class SBOnboardingNotificationsStepTests: XCTestCase {
  private let resumeStepKey = "sbOnboardingResumeStep"
  private let resumeSchemaKey = "sbOnboardingResumeStepSchema"
  private let shortcutsCompletedKey = "sbOnboardingShortcutsCompleted"

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: resumeSchemaKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: resumeSchemaKey)
    UserDefaults.standard.removeObject(forKey: shortcutsCompletedKey)
    super.tearDown()
  }

  // MARK: persisted-step renumbering
  //
  // `Step`'s raw values go to disk. Inserting `.notifications` mid-enum shifted
  // every later case by one, so without a migration a build update silently
  // reinterprets an in-flight resume state as the step before the one the user
  // actually reached. The file already carries this obligation once
  // (`shortcutsCompletedKey`, for a legacy layout), so an explicit renumber is
  // the local convention rather than an extra.

  func testLegacyResumeStateAtOrAfterTheInsertionPointShiftsUpByOne() {
    // 11 was `shortcutOpen` before `.notifications` claimed that slot.
    XCTAssertEqual(
      SBOnboardingModel.migratedResumeStepRaw(savedRaw: 11, storedSchema: 0),
      SBOnboardingModel.Step.shortcutOpen.rawValue,
      "a legacy resume at shortcutOpen must still land on shortcutOpen, not on notifications")
    // 17 was `referral`, the final step.
    XCTAssertEqual(
      SBOnboardingModel.migratedResumeStepRaw(savedRaw: 17, storedSchema: 0),
      SBOnboardingModel.Step.referral.rawValue,
      "a legacy resume at the last step must not regress to the step before it")
  }

  func testLegacyResumeStateBeforeTheInsertionPointIsUnchanged() {
    for step in [
      SBOnboardingModel.Step.promise, .role, .mic, .accessibility, .automation,
    ] {
      XCTAssertEqual(
        SBOnboardingModel.migratedResumeStepRaw(savedRaw: step.rawValue, storedSchema: 0),
        step.rawValue,
        "steps at or before automation kept their raw values, so \(step) must not move")
    }
  }

  func testMigrationIsNotAppliedTwice() {
    let migrated = SBOnboardingModel.migratedResumeStepRaw(savedRaw: 11, storedSchema: 0)
    XCTAssertEqual(
      SBOnboardingModel.migratedResumeStepRaw(
        savedRaw: migrated, storedSchema: SBOnboardingModel.resumeStepSchemaVersion),
      migrated,
      "a stamped layout must be left alone; re-running the shift would skip a step per launch")
  }

  func testFreshInstallNeedsNoShift() {
    XCTAssertEqual(
      SBOnboardingModel.migratedResumeStepRaw(savedRaw: 0, storedSchema: 0), 0,
      "nothing persisted must stay nothing persisted, so the intro gate still fires")
  }

  /// Placement is a deliberate, called-out product decision (keep every
  /// permission ask in one contiguous block, right after Automation) rather than
  /// after the screen demo. Pin it so a reorder is a visible diff, not a silent
  /// step-index drift.
  func testStepEnumPlacesNotificationsImmediatelyAfterAutomationAndBeforeShortcuts() {
    XCTAssertEqual(
      SBOnboardingModel.Step.notifications.rawValue,
      SBOnboardingModel.Step.automation.rawValue + 1,
      "notifications must sit directly after automation, in the same permission block")
    XCTAssertEqual(
      SBOnboardingModel.Step.shortcutOpen.rawValue,
      SBOnboardingModel.Step.notifications.rawValue + 1,
      "notifications must sit directly before the shortcut stages, not after the screen demo")
  }

  /// Every step-enumerating switch this fix touched
  /// (`permissionKey(for:)`, `isGranted`/`setPermOn`/`resetPermToAsk`/`permState`,
  /// `message(for:)`) must actually resolve `.notifications` / `"notifications"`
  /// rather than silently falling through a `default:` case. A model constructed
  /// with no special fixtures is enough to drive every one of these.
  func testEveryStepEnumeratingSwitchHandlesNotifications() {
    // `appState` is `unowned` inside `SBOnboardingModel` (`AppState.current` is
    // itself only `weak`), so the instance needs a strong local owner for the
    // duration of the test — an inline `AppState()` argument is deallocated the
    // moment the initializer returns and crashes the first unowned access.
    let appState = AppState()
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)

    XCTAssertEqual(model.permissionKey(for: .notifications), "notifications")

    let copy = model.message(for: .notifications)
    XCTAssertTrue(
      copy.contains("Notifications"),
      "the notifications step must ask about notifications, not fall through to another step's copy")

    XCTAssertEqual(model.permState("notifications"), .ask)
    XCTAssertFalse(model.isGranted("notifications"))

    model.setPermOn("notifications")
    XCTAssertEqual(model.permState("notifications"), .on)
    XCTAssertEqual(model.notifState, .on, "setPermOn(\"notifications\") must write notifState, not silently no-op")

    model.resetPermToAsk("notifications")
    XCTAssertEqual(model.permState("notifications"), .ask)
  }

  /// The causal fix: Automation used to advance straight to the first shortcut
  /// stage. It must now advance into Notifications first, keeping every
  /// permission ask in one contiguous block.
  func testAnsweringAutomationAdvancesToNotificationsBeforeShortcuts() {
    let appState = AppState()
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    model.step = .automation
    model.autoState = .ask

    model.answerAutomation()

    XCTAssertEqual(model.step, .notifications)
  }

  /// The defect was never being asked, not being disallowed from declining.
  /// Skipping the notifications step (the same "Skip for now" affordance every
  /// other permission step offers) must still carry the flow forward into the
  /// shortcut stages rather than getting stuck.
  func testOnboardingStillAdvancesPastNotificationsWhenTheStepIsSkipped() {
    let appState = AppState()
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    model.step = .notifications
    model.notifState = .ask  // never granted — this is the "Skip for now" path

    model.answerNotifications()

    XCTAssertEqual(
      model.step, .shortcutOpen,
      "declining notifications must not block onboarding from reaching the shortcut stages")
  }

  /// A grant landing while the step is visible must auto-advance the same way
  /// every other permission step does, and must not skip past the notifications
  /// step's own row into some other step's widget.
  func testAutoAdvanceIfCurrentMovesOnOnceNotificationsIsGranted() {
    let appState = AppState()
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    model.step = .notifications
    model.notifState = .on

    model.autoAdvanceIfCurrent("notifications")

    XCTAssertEqual(model.step, .shortcutOpen)
  }

  /// A user who already granted Notifications before reaching this step (for
  /// example from a prior onboarding attempt, or from Settings) must not be
  /// asked again — mirrors the existing pre-granted-permission skip behavior
  /// already covered for Screen Recording / System Audio.
  func testFirstUnaskedStepSkipsAnAlreadyGrantedNotificationsPermission() {
    let appState = AppState()
    appState.hasNotificationPermission = true
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)

    XCTAssertEqual(model.firstUnaskedStep(from: .notifications), .shortcutOpen)
  }

  // MARK: the migration as `begin()` actually runs it
  //
  // The pure-function tests above pin the arithmetic. These pin the part that
  // touches disk: that `begin()` reads the legacy value, lands on the right
  // step, and stamps the schema so the shift can never be applied twice.

  /// Hold `AppState` for the life of the call — `SBOnboardingModel` keeps it
  /// `unowned`, so a temporary is deallocated before `begin()` reads it.
  private func resumedStep(fromPersistedRaw raw: Int, schema: Int?, appState: AppState)
    -> SBOnboardingModel.Step
  {
    UserDefaults.standard.set(raw, forKey: resumeStepKey)
    if let schema {
      UserDefaults.standard.set(schema, forKey: resumeSchemaKey)
    } else {
      UserDefaults.standard.removeObject(forKey: resumeSchemaKey)
    }
    // Shortcuts already done, so the mandatory-shortcuts clamp does not mask
    // where the migration actually landed.
    UserDefaults.standard.set(true, forKey: shortcutsCompletedKey)
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    model.begin()
    return model.step
  }

  func testBeginRenumbersALegacyResumeStateAndStampsTheSchema() {
    let appState = AppState()
    // 13 was `screenDemo` under the version-1 layout; it is 14 under version 2.
    let step = resumedStep(fromPersistedRaw: 13, schema: nil, appState: appState)

    XCTAssertEqual(step, .screenDemo, "a legacy screenDemo must resume at screenDemo")
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: resumeStepKey), SBOnboardingModel.Step.screenDemo.rawValue)
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: resumeSchemaKey),
      SBOnboardingModel.resumeStepSchemaVersion,
      "the stamp is what stops a second launch shifting the value again")
  }

  /// The regression the stamp exists for: run `begin()` twice over the same
  /// defaults. Without the stamp the second pass shifts an already-shifted
  /// value, and a legacy `.referral` (17 -> 18 -> 19) leaves `Step`'s range
  /// entirely, restarting onboarding from `.promise`.
  func testASecondBeginDoesNotShiftAnAlreadyMigratedResumeState() {
    let appState = AppState()
    XCTAssertEqual(resumedStep(fromPersistedRaw: 17, schema: nil, appState: appState), .referral)

    let secondLaunch = SBOnboardingModel(
      appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    secondLaunch.begin()

    XCTAssertEqual(secondLaunch.step, .referral)
  }

  /// The step that sat exactly at the insertion point is the one an off-by-one
  /// gets wrong, and it is the boundary the arithmetic is built around.
  func testBeginMovesTheStepThatSatExactlyAtTheInsertionPoint() {
    let appState = AppState()
    XCTAssertEqual(resumedStep(fromPersistedRaw: 11, schema: nil, appState: appState), .shortcutOpen)
  }

  func testBeginLeavesAStepBeforeTheInsertionPointAlone() {
    let appState = AppState()
    XCTAssertEqual(resumedStep(fromPersistedRaw: 10, schema: nil, appState: appState), .automation)
  }

  /// A current-schema install must be read verbatim — the migration is for
  /// version-1 state only, and applying it to current state would corrupt it.
  func testBeginDoesNotRenumberACurrentSchemaResumeState() {
    let appState = AppState()
    let step = resumedStep(
      fromPersistedRaw: SBOnboardingModel.Step.notifications.rawValue,
      schema: SBOnboardingModel.resumeStepSchemaVersion,
      appState: appState)

    XCTAssertEqual(step, .notifications)
  }
}
