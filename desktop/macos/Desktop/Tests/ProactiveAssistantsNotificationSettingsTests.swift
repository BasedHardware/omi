import XCTest

@testable import Omi_Computer

final class ProactiveAssistantsNotificationSettingsTests: XCTestCase {
  func testNotificationSettingsCallbackDeliveredOffMainUsesMainDispatcherBeforeHandler() async {
    let dispatcherCalled = expectation(description: "main dispatcher called")
    let result = await withCheckedContinuation { continuation in
      ProactiveAssistantsPlugin.queryStartupNotificationSettings(
        query: { completion in
          DispatchQueue.global(qos: .userInitiated).async {
            completion(.notDetermined)
          }
        },
        handler: { status in
          continuation.resume(returning: (Thread.isMainThread, status))
        },
        dispatchToMain: { work in
          dispatcherCalled.fulfill()
          DispatchQueue.main.async {
            work()
          }
        }
      )
    }

    await fulfillment(of: [dispatcherCalled])
    XCTAssertTrue(result.0)
    XCTAssertEqual(result.1, .notDetermined)
  }
}
