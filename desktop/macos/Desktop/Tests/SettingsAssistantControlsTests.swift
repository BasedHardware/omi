import XCTest

@testable import Omi_Computer

// The four keys asserted directly, so a test can compare what a store *holds* against what it
// *answers*. Named rather than inlined at the call sites, per the repo's UserDefaults key rule.
private let taskIntervalDefaultsKey = "taskExtractionInterval"
private let insightIntervalDefaultsKey = "adviceExtractionInterval"
private let memoryIntervalDefaultsKey = "memoryExtractionInterval"
private let analysisDelayDefaultsKey = "assistantsAnalysisDelay"

/// The defaults keys these tests write. File-level so the nonisolated `setUp`/`tearDown` overrides
/// can reach them without the `@MainActor` class's isolation.
private let assistantControlDefaultsKeys = [
  "taskAssistantEnabled", taskIntervalDefaultsKey, "taskMinConfidence", "taskAllowedApps",
  "taskBrowserKeywords",
  "adviceAssistantEnabled", insightIntervalDefaultsKey, "adviceMinConfidence", "adviceExcludedApps",
  "memoryAssistantEnabled", memoryIntervalDefaultsKey, "memoryMinConfidence", "memoryExcludedApps",
  analysisDelayDefaultsKey,
]

/// Settings ▸ Advanced ▸ the three proactive assistants and the throttle they share.
///
/// These cards were declared and rendered by nothing for as long as the file has existed, so the
/// defects underneath them had never been exercised. Three of them are pinned here:
///
/// * the slider handle lied about any value its step list did not contain, and parked on step 0;
/// * the settings stores answered a different number than the one they held, and the next push to
///   the account then overwrote the account's value with that answer;
/// * the cards painted stale values after an account sync rewrote the stores under them.
@MainActor
final class SettingsAssistantControlsTests: XCTestCase {
  /// The step lists the Advanced pane offers. Mirrored rather than read off a `SettingsContentView`
  /// because constructing one needs an `AppState` and a pair of `Binding`s; the values themselves are
  /// asserted against the pane's own properties in `testPaneStepListsAreTheOnesUnderTest`.
  private let intervalSteps: [Double] = [10.0, 60.0, 300.0, 600.0, 1800.0, 3600.0]
  private let delaySteps: [Int] = [0, 10, 20, 30, 60, 300]

  override func setUp() {
    super.setUp()
    for key in assistantControlDefaultsKeys { UserDefaults.standard.removeObject(forKey: key) }
  }

  override func tearDown() {
    for key in assistantControlDefaultsKeys { UserDefaults.standard.removeObject(forKey: key) }
    super.tearDown()
  }

  // MARK: - The handle's position

  /// The regression. `extractionIntervalOptions.firstIndex(of: stored) ?? 0` answered 0 for every
  /// value the list did not contain, so a stored 8 minutes put the handle on "10 seconds" and a
  /// stored 40 minutes put it there too — while the readout beside it printed the real number. Worse,
  /// dragging to step 0 then wrote 10, the value the handle already claimed, so the control could not
  /// be used to correct itself. Asserted against the *old* three-step list, so the answer that fails
  /// here is the one that shipped.
  func testHandleSnapsToNearestStepInsteadOfParkingOnTheFirst() {
    let oldSteps: [Double] = [10.0, 600.0, 3600.0]

    // The shipped expression, reproduced so the answer this test replaces is written down.
    XCTAssertEqual(oldSteps.firstIndex(of: 500.0) ?? 0, 0)

    XCTAssertEqual(SettingsControlMetrics.nearestLadderIndex(of: 500.0, in: oldSteps), 1)
    XCTAssertEqual(SettingsControlMetrics.nearestLadderIndex(of: 2400.0, in: oldSteps), 2)
    // Genuinely nearest to the first step — a snap to 0 here is an answer, not a fallback.
    XCTAssertEqual(SettingsControlMetrics.nearestLadderIndex(of: 45.0, in: oldSteps), 0)
  }

  /// The step list is the other half of the same defect: with only 10s / 10min / 1hr, everything
  /// between "ten seconds" and "ten minutes" — the whole usable range — had to be approximated by
  /// one end or the other. Five minutes now has a step of its own.
  func testTheMiddleOfTheRangeHasStepsOfItsOwn() {
    XCTAssertTrue(SettingsControlMetrics.isOnLadder(300.0, in: intervalSteps))
    XCTAssertFalse(SettingsControlMetrics.isOnLadder(300.0, in: [10.0, 600.0, 3600.0]))
    XCTAssertEqual(SettingsControlMetrics.nearestLadderIndex(of: 500.0, in: intervalSteps), 3)
    // Exactly between two steps. The rule is the lower one, so the handle never jumps forward past
    // a value the user did not choose.
    XCTAssertEqual(SettingsControlMetrics.nearestLadderIndex(of: 450.0, in: intervalSteps), 2)
  }

  func testHandleIsExactOnEveryStepItOffers() {
    for (index, step) in intervalSteps.enumerated() {
      XCTAssertEqual(
        SettingsControlMetrics.nearestLadderIndex(of: step, in: intervalSteps), index,
        "interval step \(step)")
    }
    for (index, step) in delaySteps.enumerated() {
      XCTAssertEqual(
        SettingsControlMetrics.nearestLadderIndex(of: step, in: delaySteps), index,
        "delay step \(step)")
    }
  }

  /// A value below the first step or above the last still has a nearest step, and it is an end of
  /// the track rather than an arbitrary one.
  func testHandleClampsToTheEndsOfTheTrack() {
    XCTAssertEqual(SettingsControlMetrics.nearestLadderIndex(of: 1.0, in: intervalSteps), 0)
    XCTAssertEqual(
      SettingsControlMetrics.nearestLadderIndex(of: 86_400.0, in: intervalSteps),
      intervalSteps.count - 1)
  }

  /// The other half of the fix: the pane says so when the handle is only an approximation, so the
  /// disagreement between handle and readout is stated rather than hidden.
  func testOffStepValuesAreDistinguishableFromStepValues() {
    XCTAssertTrue(SettingsControlMetrics.isOnLadder(600.0, in: intervalSteps))
    XCTAssertFalse(SettingsControlMetrics.isOnLadder(420.0, in: intervalSteps))
    XCTAssertTrue(SettingsControlMetrics.isOnLadder(0, in: delaySteps))
    XCTAssertFalse(SettingsControlMetrics.isOnLadder(45, in: delaySteps))
  }

  /// The slider used to subscript its step list directly with an index derived from a `Double`.
  func testDraggingOutsideTheStepListCannotTrap() {
    XCTAssertEqual(SettingsControlMetrics.ladderValue(at: -3, in: intervalSteps), 10.0)
    XCTAssertEqual(SettingsControlMetrics.ladderValue(at: 99, in: intervalSteps), 3600.0)
    XCTAssertNil(SettingsControlMetrics.ladderValue(at: 0, in: [Double]()))
  }

  // MARK: - What the store holds vs. what it answers

  /// Every value the sliders can write survives a round trip, so the handle never lands on a step
  /// the store then silently changes underneath it.
  func testEveryOfferedStepRoundTripsThroughItsStore() {
    for step in intervalSteps {
      TaskAssistantSettings.shared.extractionInterval = step
      XCTAssertEqual(TaskAssistantSettings.shared.extractionInterval, step)

      InsightAssistantSettings.shared.extractionInterval = step
      XCTAssertEqual(InsightAssistantSettings.shared.extractionInterval, step)

      MemoryAssistantSettings.shared.extractionInterval = step
      XCTAssertEqual(MemoryAssistantSettings.shared.extractionInterval, step)
    }

    for step in delaySteps {
      AssistantSettings.shared.analysisDelay = step
      XCTAssertEqual(AssistantSettings.shared.analysisDelay, step)
    }
  }

  /// The regression. The stores normalised on *read* — `value > 0 ? value : 600` — which left the
  /// store holding a number the app never honoured. `buildFromLocal()` reads the same getter, so the
  /// next `syncToServer()` pushed 600 and destroyed whatever the account had said. The write is now
  /// where an unusable value is refused, so stored and reported are one number.
  func testAnUnusableIntervalIsRefusedAtTheWriteNotMaskedAtTheRead() {
    TaskAssistantSettings.shared.extractionInterval = 0
    XCTAssertEqual(TaskAssistantSettings.shared.extractionInterval, 600)
    XCTAssertEqual(UserDefaults.standard.double(forKey: taskIntervalDefaultsKey), 600)

    InsightAssistantSettings.shared.extractionInterval = -30
    XCTAssertEqual(InsightAssistantSettings.shared.extractionInterval, 600)
    XCTAssertEqual(UserDefaults.standard.double(forKey: insightIntervalDefaultsKey), 600)

    // Memory's default is 1800 (30 min), not 600: 2026-08-17 measured value ranking —
    // worst CTR of any proactive lane at half the notification volume — cut its cadence 3x.
    MemoryAssistantSettings.shared.extractionInterval = 0
    XCTAssertEqual(MemoryAssistantSettings.shared.extractionInterval, 1800)
    XCTAssertEqual(UserDefaults.standard.double(forKey: memoryIntervalDefaultsKey), 1800)

    AssistantSettings.shared.analysisDelay = -1
    XCTAssertEqual(AssistantSettings.shared.analysisDelay, 60)
    XCTAssertEqual(UserDefaults.standard.integer(forKey: analysisDelayDefaultsKey), 60)
  }

  /// Zero is a real setting for the throttle — "Instant" — and must not be normalised away with the
  /// negatives. This is the one place a zero belongs in these controls.
  func testInstantIsAStorableAnalysisDelay() {
    AssistantSettings.shared.analysisDelay = 0
    XCTAssertEqual(AssistantSettings.shared.analysisDelay, 0)
    XCTAssertEqual(UserDefaults.standard.integer(forKey: analysisDelayDefaultsKey), 0)
  }

  /// A value an older build already wrote is healed on the way out, not answered around, so the
  /// same divergence cannot survive an upgrade.
  func testAnIntervalStoredByAnEarlierBuildIsHealedOnRead() {
    UserDefaults.standard.set(0.0, forKey: taskIntervalDefaultsKey)

    XCTAssertEqual(TaskAssistantSettings.shared.extractionInterval, 600)
    XCTAssertEqual(UserDefaults.standard.double(forKey: taskIntervalDefaultsKey), 600)
  }

  // MARK: - Following the account

  /// The cards are seeded once, in `SettingsContentView.init`; opening Settings then runs
  /// `SettingsSyncManager.syncFromServer()`, which rewrites the same stores underneath the pane.
  /// This drives the real apply path and asserts the projection the cards repaint from — the value
  /// `syncAssistantControlsFromSettings()` assigns when `.assistantSettingsDidSyncFromServer`
  /// arrives.
  func testControlProjectionFollowsAnAccountSnapshot() {
    TaskAssistantSettings.shared.isEnabled = false
    TaskAssistantSettings.shared.extractionInterval = 10
    InsightAssistantSettings.shared.isEnabled = false
    MemoryAssistantSettings.shared.isEnabled = false
    AssistantSettings.shared.analysisDelay = 0

    SettingsSyncManager.shared.applyRemoteSettings(
      AssistantSettingsResponse(
        shared: SharedAssistantSettingsResponse(analysisDelay: 30),
        task: TaskSettingsResponse(
          enabled: true, extractionInterval: 1800, minConfidence: 0.8,
          allowedApps: ["Mail"], browserKeywords: ["review"]),
        insight: InsightSettingsResponse(
          enabled: true, extractionInterval: 300, minConfidence: 0.9, excludedApps: ["Passwords"]),
        memory: MemorySettingsResponse(
          enabled: true, extractionInterval: 60, minConfidence: 0.65, excludedApps: ["Keychain"])
      ))

    let values = AssistantControlValues.current()

    XCTAssertTrue(values.taskEnabled)
    XCTAssertEqual(values.taskExtractionInterval, 1800)
    XCTAssertEqual(values.taskMinConfidence, 0.8)
    XCTAssertEqual(values.taskAllowedApps, ["Mail"])
    XCTAssertEqual(values.taskBrowserKeywords, ["review"])
    XCTAssertTrue(values.insightEnabled)
    XCTAssertEqual(values.insightExtractionInterval, 300)
    XCTAssertEqual(values.insightMinConfidence, 0.9)
    XCTAssertEqual(values.insightExcludedApps, ["Passwords"])
    XCTAssertTrue(values.memoryEnabled)
    XCTAssertEqual(values.memoryExtractionInterval, 60)
    XCTAssertEqual(values.memoryMinConfidence, 0.65)
    XCTAssertEqual(values.memoryExcludedApps, ["Keychain"])
    XCTAssertEqual(values.analysisDelay, 30)
  }

  /// A snapshot that says nothing about a setting must not reset it — the pane would otherwise
  /// repaint a local choice as the local default every time Settings opened.
  func testASilentAccountSnapshotLeavesLocalControlsAlone() {
    TaskAssistantSettings.shared.extractionInterval = 1800
    AssistantSettings.shared.analysisDelay = 20

    SettingsSyncManager.shared.applyRemoteSettings(
      AssistantSettingsResponse(insight: InsightSettingsResponse(enabled: true)))

    let values = AssistantControlValues.current()
    XCTAssertEqual(values.taskExtractionInterval, 1800)
    XCTAssertEqual(values.analysisDelay, 20)
  }

  /// A static tripwire, not behavioural coverage: it only keeps the step lists asserted above in
  /// step with the ones the pane actually draws. Building a `SettingsContentView` to read them needs
  /// an `AppState` and two `Binding`s, which is a SwiftUI host rather than a hermetic call.
  func testPaneStepListsAreTheOnesUnderTest() throws {
    // omi-test-quality: source-inspection -- static contract: the pane's step lists are stored properties on a view
    let settingsPage = try String(
      contentsOf: Self.sourceRoot.appendingPathComponent("MainWindow/Pages/SettingsPage.swift"),
      encoding: .utf8)

    XCTAssertTrue(
      settingsPage.contains(
        "let extractionIntervalOptions: [Double] = [10.0, 60.0, 300.0, 600.0, 1800.0, 3600.0]"),
      "interval steps under test no longer match the pane's")
    XCTAssertTrue(
      settingsPage.contains("let analysisDelayOptions = [0, 10, 20, 30, 60, 300]"),
      "delay steps under test no longer match the pane's")
  }

  /// A static tripwire, not behavioural coverage. The four cards were declared and referenced by
  /// nothing for the whole life of the file, which no behavioural test could have caught because
  /// there was no behaviour to call. This pins the one line of wiring that made them exist, and the
  /// subscription that makes them follow the account; what those cards then *do* is covered above.
  func testAdvancedSectionRendersTheAssistantCardsAndFollowsTheSync() throws {
    // omi-test-quality: source-inspection -- static contract: a SwiftUI body's contents are not observable
    let advanced = try String(
      contentsOf: Self.sourceRoot.appendingPathComponent(
        "MainWindow/Pages/Settings/Sections/SettingsContentView+Advanced.swift"),
      encoding: .utf8)

    for subsection in [
      "taskAssistantSubsection", "insightAssistantSubsection", "memoryAssistantSubsection",
      "analysisThrottleSubsection",
    ] {
      XCTAssertTrue(advanced.contains(subsection), "advancedSection no longer renders \(subsection)")
    }
    XCTAssertTrue(
      advanced.contains("assistantSettingsDidSyncFromServer"),
      "advancedSection no longer follows the account sync")
    XCTAssertTrue(
      advanced.contains("syncAssistantControlsFromSettings"),
      "advancedSection no longer repaints the assistant controls after a sync")
  }

  private static var sourceRoot: URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests
      .deletingLastPathComponent()  // Desktop
      .appendingPathComponent("Sources")
  }
}
