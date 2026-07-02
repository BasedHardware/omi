import XCTest

@testable import Omi_Computer

/// Covers the per-chat auto-reply opt-in state on IMessageInboxStore: enabling,
/// disabling, and persistence across sessions (UserDefaults-backed).
@MainActor
final class IMessageAutoReplyStoreTests: XCTestCase {
  private let defaultsKey = "imessageAutoReplyChats"

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: defaultsKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: defaultsKey)
    super.tearDown()
  }

  func testDefaultsToDisabled() {
    let store = IMessageInboxStore()
    XCTAssertFalse(store.isAutoReplyEnabled("chat-1"))
    XCTAssertTrue(store.autoReplyChats.isEmpty)
  }

  func testEnableAndDisablePerChat() {
    let store = IMessageInboxStore()
    store.setAutoReply(true, for: "chat-1")
    XCTAssertTrue(store.isAutoReplyEnabled("chat-1"))
    XCTAssertFalse(store.isAutoReplyEnabled("chat-2"))

    store.setAutoReply(false, for: "chat-1")
    XCTAssertFalse(store.isAutoReplyEnabled("chat-1"))
  }

  func testOptInPersistsAcrossSessions() {
    let first = IMessageInboxStore()
    first.setAutoReply(true, for: "chat-persist")

    // A fresh store (new "session") should restore the opt-in from UserDefaults.
    let second = IMessageInboxStore()
    XCTAssertTrue(second.isAutoReplyEnabled("chat-persist"))
  }

  func testDisableIsPersisted() {
    let first = IMessageInboxStore()
    first.setAutoReply(true, for: "chat-x")
    first.setAutoReply(false, for: "chat-x")

    let second = IMessageInboxStore()
    XCTAssertFalse(second.isAutoReplyEnabled("chat-x"))
  }
}
