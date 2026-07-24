import XCTest

@testable import Omi_Computer

final class OnboardingPermissionToolTests: XCTestCase {
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
    XCTAssertEqual(
      model.firstUnaskedStep(from: .systemAudio),
      .systemAudio,
      "Screen Recording is only a prerequisite; it cannot stand in for a successful Core Audio tap")

    appState.recordSystemAudioCaptureOutcome(.denied)
    XCTAssertEqual(
      model.firstUnaskedStep(from: .systemAudio),
      .systemAudio,
      "a real denied tap must keep the system-audio permission step visible")
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
