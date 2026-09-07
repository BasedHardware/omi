import XCTest

@testable import Omi_Computer

/// Skip must be a durable off for the skipped capability's automatic path.
///
/// Regression coverage for the "skipped/denied macOS onboarding permissions must not
/// auto-reprompt" contract (#12695): the mic skip writes `audioRecordingMode == .off`
/// so launch/restore never starts (and prompts), the screen skip writes
/// `screenAnalysisEnabled == false` so completion stops force-enabling Rewind, and the
/// accessibility skip records a marker the sidebar reads instead of pulsing a
/// deliberate skip as "denied".
@MainActor
final class SBOnboardingSkipPermissionIntentTests: XCTestCase {
  private var savedDefaults: [String: Any?] = [:]

  override func setUp() async throws {
    let defaults = UserDefaults.standard
    for key in [
      AssistantSettings.audioRecordingModeDefaultsKey,
      DefaultsKey.screenAnalysisEnabled.rawValue,
      DefaultsKey.onboardingAccessibilitySkipped.rawValue,
    ] {
      savedDefaults[key] = defaults.object(forKey: key)
    }
    defaults.removeObject(forKey: AssistantSettings.audioRecordingModeDefaultsKey)
    defaults.removeObject(forKey: DefaultsKey.screenAnalysisEnabled.rawValue)
    defaults.removeObject(forKey: DefaultsKey.onboardingAccessibilitySkipped.rawValue)
  }

  override func tearDown() async throws {
    let defaults = UserDefaults.standard
    for (key, value) in savedDefaults {
      if let value {
        defaults.set(value, forKey: key)
      } else {
        defaults.removeObject(forKey: key)
      }
    }
  }

  private let appState = AppState()

  private func makeModel() -> SBOnboardingModel {
    // The model holds `appState` unowned, so the test must keep the AppState
    // alive for the model's whole lifetime.
    SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
  }

  // MARK: - Microphone skip

  func testSkipMicWritesDurableOffForTheAutomaticListeningPath() {
    let model = makeModel()
    model.step = .mic
    model.micState = .ask

    model.answerMic()

    XCTAssertEqual(
      AssistantSettings.shared.audioRecordingMode, .off,
      "A mic skip must leave the persisted listening intent off so no automatic restore starts (and prompts)")
    XCTAssertFalse(
      PersistedCaptureLaunchPolicy.shouldStartTranscription(
        intentEnabled: AssistantSettings.shared.audioRecordingMode != .off,
        isTranscribing: false,
        micPermissionAuthorized: false),
      "Restore policy must not attempt a start after a mic skip")
  }

  func testAllowMicAfterAnEarlierSkipRestoresANonOffMode() {
    let model = makeModel()
    AssistantSettings.shared.audioRecordingMode = .off
    model.step = .mic
    model.micState = .on

    model.answerMic()

    XCTAssertNotEqual(
      AssistantSettings.shared.audioRecordingMode, .off,
      "Going Back and allowing the mic must not leave an earlier skip's durable off in place")
  }

  // MARK: - Screen skip

  func testSkipScreenLeavesScreenAnalysisIntentOff() {
    let model = makeModel()
    model.step = .screen
    model.scrState = .ask

    model.answerScreen()

    XCTAssertFalse(
      AssistantSettings.shared.screenAnalysisEnabled,
      "A screen skip must record a durable off, not a forced-on capture intent")
  }

  func testAllowScreenKeepsScreenAnalysisIntentOn() {
    let model = makeModel()
    model.step = .screen
    model.scrState = .on

    model.answerScreen()

    XCTAssertTrue(AssistantSettings.shared.screenAnalysisEnabled)
  }

  func testCompletionNeverForcesScreenAnalysisOnForASkippedGrant() {
    XCTAssertEqual(
      SBOnboardingModel.screenAnalysisIntentAtCompletion(screenRecordingGranted: false), false,
      "Completion must not force-enable screen analysis after a skip or denial")
    XCTAssertEqual(
      SBOnboardingModel.screenAnalysisIntentAtCompletion(screenRecordingGranted: true), true)
  }

  // MARK: - Accessibility skip marker

  func testSkipAccessibilityRecordsTheDurableSkipMarker() {
    let model = makeModel()
    model.step = .accessibility
    model.accState = .ask

    model.answerAccessibility()

    XCTAssertTrue(
      UserDefaults.standard.bool(forKey: .onboardingAccessibilitySkipped),
      "The sidebar needs a durable record that this user skipped, not lost, accessibility")
    XCTAssertFalse(
      SBOnboardingPermissionIntentPolicy.accessibilityDenied(
        hasCompletedOnboarding: true, accessibilityUsable: false, skippedInOnboarding: true),
      "A deliberate skip must not read as denied")
  }

  func testAllowAccessibilityClearsTheSkipMarker() {
    let model = makeModel()
    UserDefaults.standard.set(true, forKey: .onboardingAccessibilitySkipped)
    model.step = .accessibility
    model.accState = .on

    model.answerAccessibility()

    XCTAssertFalse(UserDefaults.standard.bool(forKey: .onboardingAccessibilitySkipped))
  }

  // MARK: - Sidebar denied projection

  func testScreenRecordingDeniedRequiresCaptureIntentOn() {
    // Intent on + grant missing = the user wants Rewind and macOS hasn't delivered.
    XCTAssertTrue(
      SBOnboardingPermissionIntentPolicy.screenRecordingDenied(
        hasCompletedOnboarding: true, screenAnalysisIntentEnabled: true, permissionGranted: false))
    // Skipped (intent off): not denied — the user's standing choice is off.
    XCTAssertFalse(
      SBOnboardingPermissionIntentPolicy.screenRecordingDenied(
        hasCompletedOnboarding: true, screenAnalysisIntentEnabled: false, permissionGranted: false))
    // Granted: never denied.
    XCTAssertFalse(
      SBOnboardingPermissionIntentPolicy.screenRecordingDenied(
        hasCompletedOnboarding: true, screenAnalysisIntentEnabled: true, permissionGranted: true))
    // Before onboarding completes there is no "denied" to report.
    XCTAssertFalse(
      SBOnboardingPermissionIntentPolicy.screenRecordingDenied(
        hasCompletedOnboarding: false, screenAnalysisIntentEnabled: true, permissionGranted: false))
  }

  func testAccessibilityDeniedKeepsLegacyMissingReadWithoutSkipMarker() {
    // Absent marker (pre-marker completions) keeps the previous missing-as-denied
    // read, so existing installs do not silently lose their sidebar warning.
    XCTAssertTrue(
      SBOnboardingPermissionIntentPolicy.accessibilityDenied(
        hasCompletedOnboarding: true, accessibilityUsable: false, skippedInOnboarding: false))
    XCTAssertFalse(
      SBOnboardingPermissionIntentPolicy.accessibilityDenied(
        hasCompletedOnboarding: true, accessibilityUsable: true, skippedInOnboarding: false))
  }
}
