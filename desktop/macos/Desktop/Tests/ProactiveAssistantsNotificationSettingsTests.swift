import XCTest

@testable import Omi_Computer

final class ProactiveAssistantsNotificationSettingsTests: XCTestCase {
  func testNotificationSettingsCallbackDeliveredOffMainHopsToMainActor() async {
    let result = await withCheckedContinuation { continuation in
      ProactiveAssistantsPlugin.queryStartupNotificationSettings(
        query: { completion in
          DispatchQueue.global(qos: .userInitiated).async {
            completion(.notDetermined)
          }
        },
        handler: { status in
          continuation.resume(returning: (Thread.isMainThread, status))
        }
      )
    }

    XCTAssertTrue(result.0)
    XCTAssertEqual(result.1, .notDetermined)
  }
}
