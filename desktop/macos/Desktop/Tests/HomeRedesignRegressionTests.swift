import AppKit
import SwiftUI
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

/// **Revealing the metadata band must not change what the transcript measures.**
///
/// The band was zero-height at rest and took its intrinsic height on reveal, so
/// a hovered assistant row was ~16 pt taller than the same row unhovered, and
/// every row below it moved. Scrolling happens with the pointer over the
/// transcript, so rows entered and left hover continuously during a gesture and
/// the document reflowed under the cursor — measured on the mounted transcript
/// as a document height that oscillated between 7773 and 7789 pt depending on
/// where the mouse was.
///
/// Both halves are asserted here because either one alone is satisfiable by a
/// bug: a band that reserves its height keeps the row stable, and a band that
/// never renders keeps it stable too.
@MainActor
final class ChatBubbleMetadataBandLayoutTests: XCTestCase {
  private static let width: CGFloat = 480
  /// The gap the transcript keeps after an assistant row, which is the space
  /// the band draws into.
  private static let gap = ChatTranscriptLayout.regularRowSpacing

  func testRevealingTheMetadataBandDoesNotChangeTheRowHeight() {
    XCTAssertEqual(
      rowHeight(revealed: true),
      rowHeight(revealed: false),
      accuracy: 0.5,
      "a revealed metadata band must add no layout height, or a hovered row pushes "
        + "every row below it down and the document reflows under the pointer")
  }

  func testTheRevealedMetadataBandStillPaints() throws {
    let revealed = try render(revealed: true)
    let hidden = try render(revealed: false)

    XCTAssertGreaterThan(
      differingPixels(revealed, hidden), 20,
      "the metadata band drew nothing when revealed — drawing out of a zero-height "
        + "frame is what keeps the row stable, so losing the paint is the other failure")
  }

  private func bubble(revealed: Bool) -> ChatBubble {
    var bubble = ChatBubble(
      message: ChatMessage(
        id: "assistant-band",
        text: "A one-line answer.",
        createdAt: Date(timeIntervalSince1970: 1_700_000_000),
        sender: .ai,
        isSynced: true),
      app: nil,
      showsOmiMark: false,
      onRate: { _ in })
    bubble.metadataRevealOverrideForTesting = revealed
    return bubble
  }

  private func rowHeight(revealed: Bool) -> CGFloat {
    NSHostingView(rootView: bubble(revealed: revealed).frame(width: Self.width)).fittingSize.height
  }

  /// Renders the row plus the gap underneath it over an opaque mid-grey ground,
  /// so the comparison holds whichever appearance the test host is in — chat ink
  /// is near-white in one and near-black in the other.
  private func render(revealed: Bool) throws -> NSBitmapImageRep {
    let height = rowHeight(revealed: false) + Self.gap
    let host = NSHostingView(
      rootView: VStack(spacing: 0) {
        bubble(revealed: revealed)
        Spacer(minLength: 0)
      }
      .frame(width: Self.width, height: height, alignment: .top)
    )
    host.frame = NSRect(x: 0, y: 0, width: Self.width, height: height)

    let ground = NSView(frame: host.frame)
    ground.wantsLayer = true
    ground.layer?.backgroundColor = NSColor(white: 0.5, alpha: 1).cgColor
    ground.addSubview(host)
    ground.layoutSubtreeIfNeeded()

    let rep = try XCTUnwrap(ground.bitmapImageRepForCachingDisplay(in: ground.bounds))
    ground.cacheDisplay(in: ground.bounds, to: rep)
    return rep
  }

  private func differingPixels(_ lhs: NSBitmapImageRep, _ rhs: NSBitmapImageRep) -> Int {
    guard lhs.pixelsWide == rhs.pixelsWide, lhs.pixelsHigh == rhs.pixelsHigh else { return 0 }
    var differing = 0
    for y in 0..<lhs.pixelsHigh {
      for x in 0..<lhs.pixelsWide {
        guard let left = lhs.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB),
          let right = rhs.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB)
        else { continue }
        if abs(left.brightnessComponent - right.brightnessComponent) > 0.02 { differing += 1 }
      }
    }
    return differing
  }
}

/// A proactive push is a different kind of row from a reply, and the transcript
/// has to be able to tell which is which before it can draw either one.
final class ChatRowPresentationTests: XCTestCase {
  private func message(_ text: String, sender: ChatSender, clientTurnId: String? = nil) -> ChatMessage {
    ChatMessage(id: UUID().uuidString, clientTurnId: clientTurnId, text: text, sender: sender)
  }

  func testAProactivePushIsRecognisedByTheContinuityKeyItIsJournaledUnder() {
    let key = ChatContinuityInvariants.proactiveNotificationContinuityKey(id: UUID())
    let push = message("Remove the search bar from the first release", sender: .ai, clientTurnId: key)

    XCTAssertEqual(ChatRowPresentation.of(push), .proactivePush)
    XCTAssertTrue(ChatContinuityInvariants.isProactiveNotification(push))
    XCTAssertFalse(push.text.isEmpty)
  }

  /// The prefix is the seam between the notification writer and this renderer.
  /// Both sides must build it from the same constant or the treatment silently
  /// stops applying the next time one of them is edited.
  func testTheContinuityKeyCarriesTheSharedPrefixTheWriterUses() {
    let id = UUID()
    XCTAssertEqual(
      ChatContinuityInvariants.proactiveNotificationContinuityKey(id: id),
      "\(ChatContinuityInvariants.proactiveNotificationContinuityKeyPrefix)\(id.uuidString)")
  }

  func testAnOrdinaryReplyAndAUserTurnAreNotPushes() {
    XCTAssertEqual(ChatRowPresentation.of(message("Sounds good.", sender: .ai)), .assistantReply)
    XCTAssertEqual(ChatRowPresentation.of(message("hey", sender: .user)), .userTurn)
    // A user turn is never a push even if something hands it the key.
    let key = ChatContinuityInvariants.proactiveNotificationContinuityKey(id: UUID())
    XCTAssertEqual(ChatRowPresentation.of(message("hey", sender: .user, clientTurnId: key)), .userTurn)
    XCTAssertFalse(ChatContinuityInvariants.isProactiveNotification(message("hey", sender: .user, clientTurnId: key)))
  }

  /// Only a user turn is a container, so only a user turn is padded like one. A
  /// reply that keeps a capsule's padding without a capsule is 16 pt of dead
  /// vertical air per message.
  func testOnlyAUserTurnIsFilled() {
    XCTAssertTrue(ChatRowPresentation.userTurn.isFilled)
    XCTAssertFalse(ChatRowPresentation.assistantReply.isFilled)
    XCTAssertFalse(ChatRowPresentation.proactivePush.isFilled)
  }
}

/// The stamp under a reply is read to the minute, not to the year.
final class ChatMessageTimestampFormatTests: XCTestCase {
  private let calendar = Calendar(identifier: .gregorian)

  private func date(_ y: Int, _ m: Int, _ d: Int, _ h: Int, _ min: Int) -> Date {
    var components = DateComponents()
    (components.year, components.month, components.day) = (y, m, d)
    (components.hour, components.minute) = (h, min)
    guard let date = calendar.date(from: components) else {
      XCTFail("bad fixture date")
      return Date()
    }
    return date
  }

  func testTodayIsJustTheTime() {
    let now = date(2026, 8, 6, 17, 0)
    let text = ChatMessageTimestampFormat.text(for: date(2026, 8, 6, 13, 28), now: now, calendar: calendar)

    XCTAssertFalse(text.contains("2026"), "the year on a message sent hours ago is chrome")
    XCTAssertFalse(text.contains("Aug"))
    XCTAssertTrue(text.contains("28"))
  }

  func testAnEarlierDayThisYearAddsTheDayButNotTheYear() {
    let now = date(2026, 8, 6, 17, 0)
    let text = ChatMessageTimestampFormat.text(for: date(2026, 6, 1, 9, 5), now: now, calendar: calendar)

    XCTAssertTrue(text.contains("Jun"))
    XCTAssertFalse(text.contains("2026"))
  }

  func testAnotherYearIsTheOnlyCaseWorthNamingTheYearFor() {
    let now = date(2026, 8, 6, 17, 0)
    let text = ChatMessageTimestampFormat.text(for: date(2025, 12, 24, 9, 5), now: now, calendar: calendar)

    XCTAssertTrue(text.contains("2025"))
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
