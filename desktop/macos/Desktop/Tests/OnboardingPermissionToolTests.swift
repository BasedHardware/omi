import XCTest

@testable import Omi_Computer

final class OnboardingPermissionToolTests: XCTestCase {
  private let hasCompletedFileIndexingKey = "hasCompletedFileIndexing"
  private let resumeStepKey = "sbOnboardingResumeStep"

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: hasCompletedFileIndexingKey)
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: hasCompletedFileIndexingKey)
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    super.tearDown()
  }

  func testPermissionStatusPayloadIncludesEveryPermissionAdvertisedToOnboardingAgent() {
    let statuses = ChatToolExecutor.onboardingPermissionStatusPayload(
      screenRecording: false,
      microphone: false,
      notifications: false,
      accessibility: false,
      automation: false,
      fullDiskAccess: false
    )

    XCTAssertEqual(
      Set(statuses.keys),
      Set(ChatToolExecutor.onboardingPermissionTypes)
    )
    XCTAssertTrue(statuses.keys.contains("notifications"))
  }

  func testSupportedPermissionTypesIncludeNotifications() {
    XCTAssertEqual(
      ChatToolExecutor.onboardingPermissionTypes,
      [
        "screen_recording",
        "microphone",
        "notifications",
        "accessibility",
        "automation",
        "full_disk_access",
      ])
  }

  @MainActor
  func testPregrantedScreenRecordingDoesNotSkipSeparateSystemAudioConsent() {
    let appState = AppState()
    appState.hasScreenRecordingPermission = true
    appState.recordSystemAudioCaptureOutcome(.unknown)
    let model = SBOnboardingModel(
      appState: appState,
      chatProvider: ChatProvider(),
      onComplete: nil)

    XCTAssertFalse(
      model.isGranted("system_audio"),
      "Screen Recording alone must never be reported as a system-audio grant")

    appState.recordSystemAudioCaptureOutcome(.denied)
    XCTAssertFalse(
      model.isGranted("system_audio"),
      "a real denied tap must never be reported as a system-audio grant")
  }

  @MainActor
  func testRepeatedSystemAudioPollingCancelsTheOlderConsentTask() throws {
    let model = SBOnboardingModel(
      appState: AppState(),
      chatProvider: ChatProvider(),
      onComplete: nil)

    model.pollPermission("system_audio")
    let first = try XCTUnwrap(model.pollTasks["system_audio"])
    model.pollPermission("system_audio")
    let second = try XCTUnwrap(model.pollTasks["system_audio"])
    defer { second.cancel() }

    XCTAssertTrue(first.isCancelled)
    XCTAssertFalse(second.isCancelled)
  }
}
