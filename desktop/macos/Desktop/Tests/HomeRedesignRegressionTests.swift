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

final class HomeHistoryPresentationPolicyTests: XCTestCase {
  func testInitialHistoryLoadKeepsUsefulHubVisible() {
    XCTAssertEqual(
      HomeHistoryPresentationPolicy.restingMode(isLoading: true, messageCount: 0),
      .hub)
    XCTAssertEqual(
      HomeHistoryPresentationPolicy.restingMode(isLoading: true, messageCount: 12),
      .hub)
  }

  func testCompletedHistoryLoadMakesChatTheRestingSurface() {
    XCTAssertEqual(
      HomeHistoryPresentationPolicy.restingMode(isLoading: false, messageCount: 12),
      .chat)
  }

  func testCompletedEmptyLoadKeepsNewUserHubVisible() {
    XCTAssertEqual(
      HomeHistoryPresentationPolicy.restingMode(isLoading: false, messageCount: 0),
      .hub)
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

final class ChatBubbleLayoutRegressionTests: XCTestCase {
  func testCollapsedReplyKeepsEllipsisAsTheInlineShowMoreAnchor() {
    let source = String(repeating: "reply ", count: 100)
    let collapsed = ChatBubbleTruncation.displayText(source, isStreaming: false, isExpanded: false)

    XCTAssertTrue(ChatBubbleTruncation.shouldTruncate(text: source, isStreaming: false, isExpanded: false))
    XCTAssertTrue(collapsed.hasSuffix("…"), "collapsed body must expose an ellipsis before Show more")
    XCTAssertEqual(collapsed.count, ChatBubbleTruncation.threshold + 1)
    XCTAssertEqual(
      ChatBubbleTruncation.displayText(source, isStreaming: false, isExpanded: true),
      source,
      "expanding must restore the complete reply"
    )
  }

  func testShortReplyDoesNotEnterCollapsedLayout() {
    let source = "A short assistant reply"

    XCTAssertFalse(ChatBubbleTruncation.shouldTruncate(text: source, isStreaming: false, isExpanded: false))
    XCTAssertEqual(
      ChatBubbleTruncation.displayText(source, isStreaming: false, isExpanded: false),
      source
    )
  }

}

final class ChatTranscriptWindowTests: XCTestCase {
  func testKeepsOnlyTheNewestFiveHundredMessagesInChronologicalOrder() {
    let messages = (0...500).map { index in
      ChatMessage(id: "message-\(index)", text: "Message \(index)", sender: .user)
    }

    let visible = ChatTranscriptWindow.recentMessages(in: messages)

    XCTAssertEqual(visible.count, 500)
    XCTAssertEqual(visible.first?.id, "message-1")
    XCTAssertEqual(visible.last?.id, "message-500")
  }

  func testCompactPolicyMountsOnlyItsRequestedSuffixAndExpansionKeepsTheBound() {
    let messages = (0..<120).map { index in
      ChatMessage(id: "message-\(index)", text: "Message \(index)", sender: .user)
    }
    let policy = ChatTranscriptWindow.Policy(initialMessageCount: 12, maximumMessageCount: 40)

    let initial = ChatTranscriptWindow.visibleMessages(
      in: messages,
      policy: policy,
      presentation: .initial
    )
    let expanded = ChatTranscriptWindow.visibleMessages(
      in: messages,
      policy: policy,
      presentation: .expanded
    )

    XCTAssertEqual(initial.map(\.id), (108..<120).map { "message-\($0)" })
    XCTAssertEqual(expanded.map(\.id), (80..<120).map { "message-\($0)" })
  }

  func testCompactPolicyOffersAPathToRevealLocallyLoadedRowsWithoutRemoteMore() {
    let messages = (0..<20).map { index in
      ChatMessage(id: "message-\(index)", text: "Message \(index)", sender: .user)
    }
    let policy = ChatTranscriptWindow.Policy(initialMessageCount: 5, maximumMessageCount: 20)

    XCTAssertEqual(
      ChatTranscriptWindow.earlierAction(
        for: messages,
        policy: policy,
        presentation: .initial,
        hasMoreMessages: false
      ),
      .revealLocallyLoadedRows
    )
    XCTAssertFalse(
      ChatTranscriptWindow.canRevealLocallyLoadedRows(
        in: messages,
        policy: policy,
        presentation: .expanded
      )
    )
    XCTAssertEqual(
      ChatTranscriptWindow.earlierAction(
        for: messages,
        policy: policy,
        presentation: .expanded,
        hasMoreMessages: false
      ),
      .none
    )
  }

  func testCompactPolicyPreservesRemoteLoadingWhenLocallyLoadedRowsAreAlsoHidden() {
    let messages = (0..<10).map { index in
      ChatMessage(id: "message-\(index)", text: "Message \(index)", sender: .user)
    }
    let policy = ChatTranscriptWindow.Policy(initialMessageCount: 4, maximumMessageCount: 20)

    XCTAssertEqual(
      ChatTranscriptWindow.earlierAction(
        for: messages,
        policy: policy,
        presentation: .initial,
        hasMoreMessages: true
      ),
      .revealLocallyLoadedRowsAndLoadMore
    )
    XCTAssertEqual(
      ChatTranscriptWindow.earlierAction(
        for: messages,
        policy: policy,
        presentation: .expanded,
        hasMoreMessages: true
      ),
      .loadMoreRows
    )
  }

  func testStandardPolicyRetainsTheExistingNonHomeDefaults() {
    XCTAssertEqual(
      ChatTranscriptWindow.visibleMessages(
        in: [ChatMessage(id: "one", text: "One", sender: .user)],
        policy: .standard,
        presentation: .initial
      ).map(\.id),
      ["one"]
    )
    XCTAssertEqual(ChatTranscriptWindow.Policy.standard.initialMessageCount, 500)
    XCTAssertEqual(ChatTranscriptWindow.Policy.standard.maximumMessageCount, 500)
  }

  func testStopsLoadingEarlierMessagesAtTheVisibleWindowLimit() {
    let belowLimit = (0..<499).map { ChatMessage(id: "message-\($0)", text: "", sender: .user) }
    let atLimit = (0..<500).map { ChatMessage(id: "message-\($0)", text: "", sender: .user) }

    XCTAssertTrue(ChatTranscriptWindow.allowsLoadingEarlier(for: belowLimit))
    XCTAssertFalse(ChatTranscriptWindow.allowsLoadingEarlier(for: atLimit))
  }
}

/// Home's ask bar is the app's primary composer and shipped missing two of the
/// three controls the other composers carry: no microphone at all, and a Send
/// button that only existed once you had already typed. Before the first
/// keystroke the bar rendered a paperclip and a Connect chip — a chat box with
/// no visible way to chat.
final class HomeAskBarControlsTests: XCTestCase {
  private func primary(
    isSending: Bool = false,
    isStopping: Bool = false,
    hasText: Bool = false,
    isFocused: Bool = false
  ) -> HomeAskBarPrimaryAction {
    HomeAskBarControls.resolve(
      isSending: isSending, isStopping: isStopping, hasText: hasText, isFocused: isFocused
    ).primary
  }

  func testSendIsOnScreenInEveryStateThatIsNotAlreadySending() {
    // The regression: focused-and-empty used to resolve to a fourth branch that
    // rendered nothing, so clicking into the bar made the only action vanish.
    XCTAssertEqual(primary(hasText: false, isFocused: true), .send(isArmed: false))
    XCTAssertEqual(primary(hasText: false, isFocused: false), .send(isArmed: false))
    XCTAssertEqual(primary(hasText: true, isFocused: true), .send(isArmed: true))
    XCTAssertEqual(primary(hasText: true, isFocused: false), .send(isArmed: true))
  }

  func testAnInFlightTurnReplacesSendWithStopRatherThanNothing() {
    XCTAssertEqual(primary(isSending: true), .stop(isStopping: false))
    XCTAssertEqual(primary(isSending: true, isStopping: true), .stop(isStopping: true))
    // Text typed while a reply streams still shows Stop: one slot, one turn.
    XCTAssertEqual(primary(isSending: true, hasText: true), .stop(isStopping: false))
  }

  func testConnectOnlyHoldsTheSlotWhileTheBarIsAtRest() {
    let resting = HomeAskBarControls.resolve(
      isSending: false, isStopping: false, hasText: false, isFocused: false)
    XCTAssertTrue(resting.showsConnect)

    for engaged in [
      HomeAskBarControls.resolve(isSending: false, isStopping: false, hasText: true, isFocused: false),
      HomeAskBarControls.resolve(isSending: false, isStopping: false, hasText: false, isFocused: true),
      HomeAskBarControls.resolve(isSending: true, isStopping: false, hasText: false, isFocused: false),
    ] {
      XCTAssertFalse(
        engaged.showsConnect,
        "Connect must yield the slot once the bar is engaged so Send is the only capsule.")
    }
  }
}
