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

  /// The backend sends 1008 for transient conditions — the PTT endpoint's
  /// "Idle timeout: no audio for 60s" and "Rate limit exceeded. Retry in Ns" —
  /// so treating it as terminal permanently killed transcription until restart.
  func testPolicyViolationCloseCodeBacksOffButStillReconnects() throws {
    let policyViolation = try XCTUnwrap(URLSessionWebSocketTask.CloseCode(rawValue: 1008))
    XCTAssertEqual(
      TranscriptionService.extraReconnectDelay(for: policyViolation),
      TranscriptionService.policyCloseReconnectDelay)
    XCTAssertEqual(TranscriptionService.extraReconnectDelay(for: .abnormalClosure), 0)
    XCTAssertEqual(TranscriptionService.extraReconnectDelay(for: .goingAway), 0)
  }
}
