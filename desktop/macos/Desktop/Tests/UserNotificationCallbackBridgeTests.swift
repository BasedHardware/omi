@preconcurrency import UserNotifications
import XCTest

@testable import Omi_Computer

final class UserNotificationCallbackBridgeTests: XCTestCase {
  func testDefaultNotificationSettingsHandoffMovesOffMainCallbackToMainActorInRelease() async {
    let snapshot = UserNotificationSettingsSnapshot(
      authorizationStatus: .notDetermined,
      alertStyle: .none,
      soundSetting: .disabled,
      badgeSetting: .disabled
    )
    let result = await withCheckedContinuation { continuation in
      UserNotificationCallbackBridge.notificationSettings(
        query: { completion in
          DispatchQueue.global(qos: .userInitiated).async {
            completion(snapshot)
          }
        },
        handler: { deliveredSnapshot in
          continuation.resume(returning: (Thread.isMainThread, deliveredSnapshot.authorizationStatus))
        }
      )
    }

    XCTAssertTrue(result.0)
    XCTAssertEqual(result.1, .notDetermined)
  }

  func testSignedSmokeRequiresExplicitResultPath() {
    XCTAssertFalse(UserNotificationCallbackBridge.runSignedSmokeIfRequested(environment: [:]))
  }
}
