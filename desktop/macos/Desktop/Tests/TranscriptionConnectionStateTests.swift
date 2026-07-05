import Foundation
import XCTest
@testable import Omi_Computer

final class TranscriptionConnectionStateTests: XCTestCase {
  func testStreamingConnectionStateIsDrivenByWebSocketOpenEvent() throws {
    let source = try transcriptionServiceSource()

    XCTAssertFalse(
      source.contains("asyncAfter(deadline: .now() + 0.5)"),
      "TranscriptionService must not mark the WebSocket connected from a fixed timer"
    )
    XCTAssertTrue(
      source.contains("URLSession(configuration: configuration, delegate:"),
      "TranscriptionService should install a URLSessionWebSocketDelegate"
    )
    XCTAssertTrue(
      source.contains("didOpenWithProtocol"),
      "TranscriptionService should mark connected from URLSessionWebSocketDelegate.didOpenWithProtocol"
    )
  }

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

  private func transcriptionServiceSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/TranscriptionService.swift")
    return try String(contentsOf: url, encoding: .utf8)
  }
}
