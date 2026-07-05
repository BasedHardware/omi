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
}
