import XCTest

@testable import Omi_Computer

final class MainChatRuntimeSessionStoreTests: XCTestCase {
  override func setUp() {
    super.setUp()
    MainChatRuntimeSessionStore.clearAll()
  }

  override func tearDown() {
    MainChatRuntimeSessionStore.clearAll()
    super.tearDown()
  }

  func testStoresRuntimeSessionPerOwnerAndChat() {
    MainChatRuntimeSessionStore.save(sessionId: "omi-session-default", ownerId: "owner-a", chatId: "default")
    MainChatRuntimeSessionStore.save(sessionId: "omi-session-chat", ownerId: "owner-a", chatId: "chat-1")
    MainChatRuntimeSessionStore.save(sessionId: "omi-session-other-owner", ownerId: "owner-b", chatId: "chat-1")

    XCTAssertEqual(
      MainChatRuntimeSessionStore.sessionId(ownerId: "owner-a", chatId: "default"),
      "omi-session-default"
    )
    XCTAssertEqual(
      MainChatRuntimeSessionStore.sessionId(ownerId: "owner-a", chatId: "chat-1"),
      "omi-session-chat"
    )
    XCTAssertEqual(
      MainChatRuntimeSessionStore.sessionId(ownerId: "owner-b", chatId: "chat-1"),
      "omi-session-other-owner"
    )
  }

  func testClearRemovesOnlyOneChat() {
    MainChatRuntimeSessionStore.save(sessionId: "omi-session-default", ownerId: "owner-a", chatId: "default")
    MainChatRuntimeSessionStore.save(sessionId: "omi-session-chat", ownerId: "owner-a", chatId: "chat-1")

    MainChatRuntimeSessionStore.clear(ownerId: "owner-a", chatId: "chat-1")

    XCTAssertEqual(
      MainChatRuntimeSessionStore.sessionId(ownerId: "owner-a", chatId: "default"),
      "omi-session-default"
    )
    XCTAssertNil(MainChatRuntimeSessionStore.sessionId(ownerId: "owner-a", chatId: "chat-1"))
  }
}
