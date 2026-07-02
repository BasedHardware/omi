import XCTest

@testable import Omi_Computer

/// Runtime integration test: drives the REAL TelegramClientService against the
/// on-device helper running in `--selftest` mode (no Telegram/network). Exercises
/// the risky new glue — subprocess spawn, streaming newline-JSON stdout decoding,
/// and @MainActor event routing — end to end.
final class TelegramClientServiceTests: XCTestCase {

  /// Path to the helper source, resolved relative to this test file:
  /// desktop/macos/Desktop/Tests/…  ->  desktop/macos/telegram-helper/omi_telegram_helper.py
  private func helperPath() -> String {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // Tests/
      .deletingLastPathComponent()  // Desktop/
      .deletingLastPathComponent()  // macos/
      .appendingPathComponent("telegram-helper/omi_telegram_helper.py")
      .path
  }

  func testSelftestDrivesConnectListenAndIncomingMessage() throws {
    let helper = helperPath()
    try XCTSkipUnless(FileManager.default.fileExists(atPath: helper), "helper source not found at \(helper)")

    setenv("OMI_TELEGRAM_SELFTEST", "1", 1)
    setenv("OMI_TELEGRAM_HELPER_PY", helper, 1)
    setenv("OMI_TELEGRAM_PYTHON", "/usr/bin/env", 1)
    defer {
      unsetenv("OMI_TELEGRAM_SELFTEST")
      unsetenv("OMI_TELEGRAM_HELPER_PY")
      unsetenv("OMI_TELEGRAM_PYTHON")
    }

    let service = TelegramClientService()

    let ready = expectation(description: "ready")
    let connected = expectation(description: "connected")
    let listening = expectation(description: "listening")
    let newMessage = expectation(description: "new_message")
    let sent = expectation(description: "sent")

    // Collected on the main actor by the service's event callback.
    let box = EventBox()

    service.onEvent = { event in
      box.append(event.event)
      switch event.event {
      case "ready":
        ready.fulfill()
        // Kick the connect flow once the helper is up.
        service.connect()
      case "connected":
        connected.fulfill()
        service.startListening()
      case "listening":
        listening.fulfill()
      case "new_message":
        // Verify the decoded thread carries the fake incoming content.
        XCTAssertEqual(event.thread?.chatID, "999")
        XCTAssertEqual(event.thread?.awaitingReply, true)
        XCTAssertEqual(event.thread?.messages.last?.text, "wanna grab food later?")
        XCTAssertEqual(event.thread?.messages.last?.handle, "tg:12345")
        newMessage.fulfill()
        // Exercise the send command path; selftest echoes a "sent" event.
        service.send(chatID: "999", text: "sure thing")
      case "sent":
        XCTAssertEqual(event.chatID, "999")
        sent.fulfill()
      default:
        break
      }
    }

    XCTAssertTrue(service.start(), "helper process should launch")

    wait(for: [ready, connected, listening, newMessage, sent], timeout: 20, enforceOrder: true)
    service.shutdown()

    // The full happy-path sequence was observed, in order.
    XCTAssertEqual(box.events.prefix(5), ["ready", "connected", "listening", "new_message", "sent"])
  }
}

/// Thread-safe collector for the events observed on the main actor.
private final class EventBox: @unchecked Sendable {
  private let lock = NSLock()
  private var storage: [String] = []
  func append(_ s: String) {
    lock.lock()
    storage.append(s)
    lock.unlock()
  }
  var events: [String] {
    lock.lock()
    defer { lock.unlock() }
    return storage
  }
}
