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

  func testSelectorRegistrationCopiesPayloadAndHopsToMainActor() async {
    let notificationName = Notification.Name("com.omi.test.insight.\(UUID().uuidString)")
    let events = AsyncStream<(isMainThread: Bool, hours: String?, unsupported: String?)>.makeStream()
    let observer = ProactiveTestNotificationObserver(name: notificationName) { payload in
      events.continuation.yield(
        (
          Thread.isMainThread,
          payload["hours"],
          payload["unsupported"]
        ))
      events.continuation.finish()
    }
    let center = NotificationCenter.default
    observer.register(in: center)
    defer {
      observer.unregister(from: center)
    }

    DispatchQueue.global(qos: .userInitiated).async {
      NotificationCenter.default.post(
        name: notificationName,
        object: nil,
        userInfo: ["hours": "2.5", "unsupported": "must-not-cross-actor-boundary"]
      )
    }

    guard let result = await events.stream.first(where: { _ in true }) else {
      return XCTFail("expected selector-delivered notification")
    }

    XCTAssertTrue(result.isMainThread)
    XCTAssertEqual(result.hours, "2.5")
    XCTAssertNil(result.unsupported)
  }
}
