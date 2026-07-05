import Foundation
import XCTest
@testable import Omi_Computer

final class TranscriptionConnectionStateTests: XCTestCase {
  func testWebSocketConnectionDelegateForwardsOpenAndClose() {
    let delegate = WebSocketConnectionDelegate()
    var didOpen = false
    var closeCode: URLSessionWebSocketTask.CloseCode?

    delegate.onOpen = {
      didOpen = true
    }
    delegate.onClose = { code in
      closeCode = code
    }

    let session = URLSession(configuration: .default)
    let task = session.webSocketTask(with: URL(string: "wss://example.com/listen")!)
    delegate.urlSession(session, webSocketTask: task, didOpenWithProtocol: nil)
    delegate.urlSession(session, webSocketTask: task, didCloseWith: .goingAway, reason: nil)
    session.invalidateAndCancel()

    XCTAssertTrue(didOpen)
    XCTAssertEqual(closeCode, .goingAway)
  }

  func testWebSocketConnectionAttemptMatchesOnlyCurrentTaskIdentity() {
    let session = URLSession(configuration: .default)
    let currentTask = session.webSocketTask(with: URL(string: "wss://example.com/listen")!)
    let staleTask = session.webSocketTask(with: URL(string: "wss://example.com/listen")!)
    session.invalidateAndCancel()

    XCTAssertTrue(WebSocketConnectionAttempt.matches(currentTask, current: currentTask))
    XCTAssertFalse(WebSocketConnectionAttempt.matches(staleTask, current: currentTask))
    XCTAssertFalse(WebSocketConnectionAttempt.matches(nil, current: currentTask))
    XCTAssertFalse(WebSocketConnectionAttempt.matches(currentTask, current: nil))
  }
}
