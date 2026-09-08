import Foundation
import XCTest

@testable import Omi_Computer

final class RawWebSocketValidationTests: XCTestCase {
  func testInvalidPortReportsErrorInsteadOfCrashing() {
    let errorExpectation = expectation(description: "invalid port error")
    let webSocket = RawWebSocket(
      url: URL(string: "wss://example.com:0/ws")!,
      queue: DispatchQueue(label: "raw-websocket-validation-test")
    )

    webSocket.onError = { failure in
      XCTAssertTrue(
        failure.message.contains("invalid WebSocket port"),
        "Unexpected error message: \(failure.message)"
      )
      errorExpectation.fulfill()
    }

    webSocket.connect()

    wait(for: [errorExpectation], timeout: 1.0)
  }
}
