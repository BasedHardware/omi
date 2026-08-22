import AppKit
import OmiTheme
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

final class ChatBubbleMetadataControlMetricsTests: XCTestCase {
  func testMetadataControlsUseStablePointerTargetsAndMatchingInsets() {
    XCTAssertGreaterThanOrEqual(ChatBubbleMetadataControlMetrics.targetSize, 24)
    XCTAssertEqual(ChatBubbleMetadataControlMetrics.leadingInset, OmiSpacing.xxs)
    XCTAssertEqual(ChatBubbleMetadataControlMetrics.topInset, ChatBubbleMetadataControlMetrics.leadingInset)
  }

  func testPointerCanCrossFromMessageIntoControlsWithoutHidingThem() throws {
    var hover = ChatBubbleMetadataHoverState()

    XCTAssertNil(hover.update(.row, hovering: true))
    let rowExit = try XCTUnwrap(hover.update(.row, hovering: false))
    XCTAssertTrue(hover.keepsMetadataVisible)

    XCTAssertNil(hover.update(.controls, hovering: true))
    hover.completeRelease(rowExit)
    XCTAssertTrue(
      hover.keepsMetadataVisible,
      "a stale row-exit release must not hide buttons after the pointer enters them")

    let controlsExit = try XCTUnwrap(hover.update(.controls, hovering: false))
    hover.completeRelease(controlsExit)
    XCTAssertFalse(hover.keepsMetadataVisible)
  }
}

/// Metadata controls need a real layout and hit-test region. Painting controls
/// outside a zero-height row left visible pixels that could not receive clicks.
@MainActor
final class ChatBubbleMetadataBandLayoutTests: XCTestCase {
  private static let width: CGFloat = 480

  func testSyncedAssistantRowReservesARealMetadataControlRegion() {
    let synced = rowHeight(showsMetadata: true)
    let streaming = rowHeight(showsMetadata: false)

    XCTAssertGreaterThanOrEqual(
      synced - streaming,
      ChatBubbleMetadataControlMetrics.targetSize + ChatBubbleMetadataControlMetrics.topInset - 1,
      "the metadata strip must remain inside the row's hit-test bounds")
  }

  func testFinishedUnsyncedReplyReservesTheSameMetadataControlRegionAsASyncedReply() {
    let synced = rowHeight(isStreaming: false, isSynced: true)
    let unsynced = rowHeight(isStreaming: false, isSynced: false)
    let streaming = rowHeight(isStreaming: true, isSynced: false)

    XCTAssertEqual(synced, unsynced, accuracy: 1)
    XCTAssertGreaterThanOrEqual(
      unsynced - streaming,
      ChatBubbleMetadataControlMetrics.targetSize + ChatBubbleMetadataControlMetrics.topInset - 1)
  }

  private func bubble(showsMetadata: Bool) -> ChatBubble {
    bubble(isStreaming: !showsMetadata, isSynced: showsMetadata)
  }

  private func bubble(isStreaming: Bool, isSynced: Bool) -> ChatBubble {
    ChatBubble(
      message: ChatMessage(
        id: "assistant-band",
        text: "A one-line answer.",
        createdAt: Date(timeIntervalSince1970: 1_700_000_000),
        sender: .ai,
        isStreaming: isStreaming,
        isSynced: isSynced),
      app: nil,
      showsOmiMark: false,
      onRate: { _ in })
  }

  private func rowHeight(showsMetadata: Bool) -> CGFloat {
    rowHeight(isStreaming: !showsMetadata, isSynced: showsMetadata)
  }

  private func rowHeight(isStreaming: Bool, isSynced: Bool) -> CGFloat {
    NSHostingView(rootView: bubble(isStreaming: isStreaming, isSynced: isSynced).frame(width: Self.width))
      .fittingSize.height
  }
}

final class ChatBubbleMetadataBandTests: XCTestCase {
  func testFinishedReplyOffersRatingsBeforeJournalSync() {
    let message = ChatMessage(
      id: "live-tail",
      text: "On it — I'll look up the backend IDs and delete the duplicates now.",
      sender: .ai,
      isStreaming: false,
      isSynced: false)

    XCTAssertEqual(ChatBubbleMetadataBand.of(message), .actions)
  }

  func testStreamingReplyHidesTheMetadataBand() {
    let message = ChatMessage(
      id: "live-tail",
      text: "On it — I'll look up the backend IDs and delete the duplicates now.",
      sender: .ai,
      isStreaming: true,
      isSynced: false)

    XCTAssertEqual(ChatBubbleMetadataBand.of(message), .hidden)
  }

  func testEmptyCompletedReplyKeepsTimestampOnly() {
    let message = ChatMessage(
      id: "empty-tail",
      text: "",
      sender: .ai,
      isStreaming: false,
      isSynced: false)

    XCTAssertEqual(ChatBubbleMetadataBand.of(message), .timestampOnly)
  }
}

@MainActor
final class ChatBubbleIdentityTests: XCTestCase {
  func testSyncAndMetadataAreVisibleIdentity() {
    let unsynced = bubble(isSynced: false, metadata: nil)
    let synced = bubble(isSynced: true, metadata: nil)
    let withInfo = bubble(isSynced: false, metadata: Self.sampleMetadata)

    XCTAssertNotEqual(unsynced, synced)
    XCTAssertNotEqual(unsynced, withInfo)
  }

  func testMatchingCompletedRepliesRemainEqual() {
    XCTAssertEqual(
      bubble(isSynced: false, metadata: Self.sampleMetadata),
      bubble(isSynced: false, metadata: Self.sampleMetadata))
  }

  func testLateArtifactsAreVisibleIdentity() {
    let withoutArtifact = bubble(isSynced: false, metadata: nil)
    let withArtifact = ChatBubble(
      message: ChatMessage(
        id: "live-tail",
        text: "On it — I'll look up the backend IDs and delete the duplicates now.",
        sender: .ai,
        isStreaming: false,
        isSynced: false,
        resources: [
          ChatResource(
            id: "artifact:late",
            origin: .generatedArtifact,
            title: "result.json",
            subtitle: "application/json",
            mimeType: "application/json",
            thumbnailURL: nil,
            imageData: nil,
            uri: "omi-artifact://late",
            artifactId: "late",
            sessionId: nil,
            runId: nil,
            state: .ready)
        ]),
      app: nil,
      showsOmiMark: true,
      onRate: { _ in })
    XCTAssertNotEqual(withoutArtifact, withArtifact)
  }

  func testJournalFailureIsVisibleIdentity() {
    let completed = bubble(isSynced: false, metadata: nil)
    let failed = ChatBubble(
      message: ChatMessage(
        id: "live-tail",
        text: "On it — I'll look up the backend IDs and delete the duplicates now.",
        sender: .ai,
        isStreaming: false,
        isSynced: false,
        journalStatus: .failed),
      app: nil,
      showsOmiMark: true,
      onRate: { _ in })
    XCTAssertNotEqual(completed, failed)
  }

  private static let sampleMetadata = MessageMetadata(toolNames: ["search"])

  private func bubble(isSynced: Bool, metadata: MessageMetadata?) -> ChatBubble {
    ChatBubble(
      message: ChatMessage(
        id: "live-tail",
        text: "On it — I'll look up the backend IDs and delete the duplicates now.",
        sender: .ai,
        isStreaming: false,
        isSynced: isSynced,
        metadata: metadata),
      app: nil,
      showsOmiMark: true,
      onRate: { _ in })
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

  func testTypedNotificationContinuitySurvivesJournalProjection() {
    let id = UUID()
    let key = ChatContinuityInvariants.proactiveNotificationContinuityKey(id: id, kind: .insight)
    let push = message("A useful connection", sender: .ai, clientTurnId: key)

    XCTAssertEqual(key, "notification:insight:\(id.uuidString)")
    XCTAssertEqual(ChatContinuityInvariants.proactiveNotificationKind(push), .insight)
    XCTAssertEqual(ProactiveNotificationBadge(kind: .insight).systemImage, "sparkles")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .insight).label, "Insight")
  }

  func testInsightGlyphIsSparklesAcrossSurfacesAndDoesNotCollideWithSuggestion() {
    XCTAssertEqual(ProactiveNotificationBadge.insightSystemImage, "sparkles")
    XCTAssertEqual(ProactiveNotificationBadge.suggestionSystemImage, "lightbulb")
    XCTAssertEqual(
      ProactiveNotificationBadge(kind: .insight).systemImage,
      ProactiveNotificationBadge.insightSystemImage)
    XCTAssertEqual(
      ProactiveNotificationBadge(kind: .suggestion).systemImage,
      ProactiveNotificationBadge.suggestionSystemImage)
    XCTAssertNotEqual(
      ProactiveNotificationBadge.insightSystemImage,
      ProactiveNotificationBadge.suggestionSystemImage,
      "Insight and Suggestion must keep distinct glyphs")
  }

  func testLegacyNotificationContinuityUsesTheNeutralBadge() {
    let key = ChatContinuityInvariants.proactiveNotificationContinuityKey(id: UUID())
    let push = message("An older notification", sender: .ai, clientTurnId: key)

    XCTAssertEqual(ChatContinuityInvariants.proactiveNotificationKind(push), .general)
    XCTAssertEqual(ProactiveNotificationBadge(kind: .general).systemImage, "bell")
  }

  func testExistingAssistantIDsMapToDistinctNotificationKinds() {
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: "suggestion"), .suggestion)
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: "insight"), .insight)
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: "task"), .task)
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: "memory-extraction"), .memory)
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: "goals"), .goal)
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: "meeting-notes"), .meetingNotes)
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: "integration_connect"), .integration)
    XCTAssertEqual(ProactiveNotificationBadge(kind: .meetingNotes).label, "Task")
  }

  /// The user-facing taxonomy is exactly five proactive categories — Focus, Task,
  /// Insight, Memory, Integration — matching the five toggles in Settings →
  /// Notifications. Focus is the focus-nudge assistant alone; tips, resurfaced items,
  /// and generated goals are insights; connect-an-app offers are integrations.
  /// `.general` is reserved for functional system alerts outside the taxonomy.
  func testEveryProactiveKindPresentsAsOneOfTheFiveCategories() {
    XCTAssertEqual(ProactiveNotificationBadge(kind: .suggestion).label, "Focus")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .task).label, "Task")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .meetingNotes).label, "Task")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .insight).label, "Insight")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .resurface).label, "Insight")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .goal).label, "Insight")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .memory).label, "Memory")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .integration).label, "Integration")
    XCTAssertEqual(ProactiveNotificationBadge(kind: .general).label, "Notification")
  }

  func testNotificationJournalTextPreservesTheHeadlineAndBody() {
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(
        title: "Insight",
        body: "PR blocked, needs review"),
      "Insight\nPR blocked, needs review")
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(title: "Meeting notes ready", body: ""),
      "Meeting notes ready")
  }

  /// The director's copy contract makes the title and the message both name the same
  /// referent; journaled together into one chat row that read as saying everything
  /// twice (observed live on beta after 5a076e10b3). A headline whose every token the
  /// body already carries — quoted, inflected, or reordered — is dropped from the row.
  func testJournalDropsAHeadlineTheBodyAlreadyRestates() {
    // Body quotes the title verbatim (smart quotes stripped by tokenization).
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(
        title: "Instruct David Editor to write extra script for main Omi demo video",
        body:
          "\u{201C}Instruct David Editor to write extra script for main Omi demo video\u{201D} is due August 21."),
      "\u{201C}Instruct David Editor to write extra script for main Omi demo video\u{201D} is due August 21.")
    // Body restates the title with different casing and inflection.
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(
        title: "Latest Omi desktop app download link",
        body: "The latest Omi desktop app download link is omi.me/desktop."),
      "The latest Omi desktop app download link is omi.me/desktop.")
    // Body reorders the title's tokens ("fix on main" -> "fix is live on main").
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(
        title: "The Omi macOS click-away deadzone fix on main",
        body: "The Omi macOS click-away deadzone fix is live on main; verify it when you can."),
      "The Omi macOS click-away deadzone fix is live on main; verify it when you can.")
    // A headline contributing even one new token keeps its own line.
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(
        title: "Ship the quarterly report",
        body: "You promised it by 5pm — draft the summary now."),
      "Ship the quarterly report\nYou promised it by 5pm — draft the summary now.")
    // Live beta rows (Aug 21): the title's only novel tokens were prepositions
    // ("for", "at") the body phrased differently — function words never keep a
    // redundant headline alive.
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(
        title: "Latest Omi desktop link for David at scalingforever.com",
        body:
          "The latest Omi desktop app download link is omi.me/desktop. You can paste it into the message to david@scalingforever.com."
      ),
      "The latest Omi desktop app download link is omi.me/desktop. You can paste it into the message to david@scalingforever.com."
    )
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(
        title: "Latest Omi desktop link for david@scalingforever.com",
        body:
          "The latest Omi desktop download link is omi.me/desktop, so you may not need to send the draft to david@scalingforever.com."
      ),
      "The latest Omi desktop download link is omi.me/desktop, so you may not need to send the draft to david@scalingforever.com."
    )
    // A title whose content genuinely differs from the body still keeps its line
    // even when it shares function words.
    XCTAssertEqual(
      FloatingControlBarManager.notificationJournalText(
        title: "Draft for the board meeting",
        body: "You promised the revenue summary by 5pm."),
      "Draft for the board meeting\nYou promised the revenue summary by 5pm.")
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
  /// Fixtures are built and rendered in one pinned zone, so neither the machine's zone nor its
  /// language decides whether these assertions hold. `America/New_York` matches what the rest of
  /// the desktop suite pins; the month and year below are only stable against a pinned `locale`,
  /// since production deliberately renders in the user's own (`ja_JP` says 6月, not "Jun").
  private var calendar = Calendar(identifier: .gregorian)
  private let locale = Locale(identifier: "en_US_POSIX")

  override func setUpWithError() throws {
    try super.setUpWithError()
    calendar.timeZone = try XCTUnwrap(
      TimeZone(identifier: "America/New_York"),
      "the pinned fixture zone must exist in the system time zone database")
  }

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
    let text = ChatMessageTimestampFormat.text(
      for: date(2026, 8, 6, 13, 28), now: now, calendar: calendar, locale: locale)

    XCTAssertFalse(text.contains("2026"), "the year on a message sent hours ago is chrome")
    XCTAssertFalse(text.contains("Aug"))
    XCTAssertTrue(text.contains("28"))
  }

  func testAnEarlierDayThisYearAddsTheDayButNotTheYear() {
    let now = date(2026, 8, 6, 17, 0)
    let text = ChatMessageTimestampFormat.text(
      for: date(2026, 6, 1, 9, 5), now: now, calendar: calendar, locale: locale)

    XCTAssertTrue(text.contains("Jun"))
    XCTAssertFalse(text.contains("2026"))
  }

  func testAnotherYearIsTheOnlyCaseWorthNamingTheYearFor() {
    let now = date(2026, 8, 6, 17, 0)
    let text = ChatMessageTimestampFormat.text(
      for: date(2025, 12, 24, 9, 5), now: now, calendar: calendar, locale: locale)

    XCTAssertTrue(text.contains("2025"))
  }
}

final class ChatBubbleLayoutRegressionTests: XCTestCase {
  func testCollapsedReplyKeepsAnEllipsisBeforeTheBelowMessageExpansionControl() {
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
