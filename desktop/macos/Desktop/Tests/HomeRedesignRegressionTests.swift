import XCTest

@testable import Omi_Computer

/// Regressions from the chat-as-home redesign (#10184) and the floating-bar
/// typing removal (#10181).
final class HomeStageCollapseCatcherTests: XCTestCase {
  func testChatWithHistoryIsRestingSoNoCatcherMounts() {
    // Chat with history is Home itself: no click-outside / Esc catcher.
    XCTAssertFalse(HomeStageMode.collapseCatcherActive(mode: .chat, resting: .chat))
  }

  func testHubNeverGetsACatcherEvenWhenChatIsResting() {
    // Regression: with history present the hub differs from the resting mode,
    // which used to mount the catchers over the hub — a stray click or Esc
    // then *opened* the chat instead of leaving the user on the hub.
    XCTAssertFalse(HomeStageMode.collapseCatcherActive(mode: .hub, resting: .chat))
    XCTAssertFalse(HomeStageMode.collapseCatcherActive(mode: .hub, resting: .hub))
  }

  func testNonRestingPanelsStillCollapse() {
    // Empty-history chat and the connect tray remain escapable overlays.
    XCTAssertTrue(HomeStageMode.collapseCatcherActive(mode: .chat, resting: .hub))
    XCTAssertTrue(HomeStageMode.collapseCatcherActive(mode: .connect, resting: .hub))
    XCTAssertTrue(HomeStageMode.collapseCatcherActive(mode: .connect, resting: .chat))
  }
}

@MainActor
final class MainChatNavigationRequestStoreTests: XCTestCase {
  func testRequestIsConsumedExactlyOnce() {
    let store = MainChatNavigationRequestStore.shared
    _ = store.consume()  // clear any pending state from other tests

    XCTAssertFalse(store.consume())

    store.request()
    XCTAssertTrue(store.isPending)
    XCTAssertTrue(store.consume())
    XCTAssertFalse(store.consume())
  }

  func testRequestPostsOpenMainChatNotification() {
    let store = MainChatNavigationRequestStore.shared
    _ = store.consume()

    let expectation = expectation(
      forNotification: .openMainChatRequested, object: nil, notificationCenter: .default)
    store.request()
    wait(for: [expectation], timeout: 1)
    _ = store.consume()
  }
}

final class ChatBubbleMetadataRevealTests: XCTestCase {
  func testKeyboardFocusAloneRevealsMetadataRow() {
    // Regression: the quiet-timeline redesign gated the row on pointer hover
    // only, leaving Tab / Full Keyboard Access focused on invisible buttons.
    XCTAssertTrue(
      ChatBubbleMetadataReveal.isVisible(hovering: false, controlFocused: true, transientFeedback: false))
  }

  func testHiddenOnlyWhenNeitherHoveredNorFocusedNorMidInteraction() {
    XCTAssertFalse(
      ChatBubbleMetadataReveal.isVisible(hovering: false, controlFocused: false, transientFeedback: false))
    XCTAssertTrue(
      ChatBubbleMetadataReveal.isVisible(hovering: true, controlFocused: false, transientFeedback: false))
    XCTAssertTrue(
      ChatBubbleMetadataReveal.isVisible(hovering: false, controlFocused: false, transientFeedback: true))
  }
}
