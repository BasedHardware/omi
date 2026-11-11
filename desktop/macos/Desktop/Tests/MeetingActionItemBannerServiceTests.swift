import XCTest

@testable import Omi_Computer

final class MeetingActionItemBannerServiceTests: XCTestCase {
  // MARK: - Item filtering

  func testRecommendedItemsKeepOnlyOpenUserOwnedItems() {
    let items = [
      MeetingActionItemBannerServiceTests.item("Send the deck to Alex", owner: "user"),
      MeetingActionItemBannerServiceTests.item("Alex reviews the deck", owner: "other"),
      MeetingActionItemBannerServiceTests.item("Legacy item without owner", owner: nil),
      MeetingActionItemBannerServiceTests.item("Already done", owner: "user", completed: true),
      MeetingActionItemBannerServiceTests.item("Deleted locally", owner: "user", deleted: true),
      MeetingActionItemBannerServiceTests.item("Book the follow-up", owner: "user"),
    ]

    let recommended = MeetingActionItemBannerPolicy.recommendedItems(from: items)

    XCTAssertEqual(
      recommended.map(\.description),
      ["Send the deck to Alex", "Book the follow-up"]
    )
  }

  // MARK: - Body formatting

  func testBannerBodyForSingleItemHasNoCountTail() {
    let body = MeetingActionItemBannerPolicy.bannerBody(
      conversationTitle: "Weekly sync",
      recommendedItems: [Self.item("Send the deck to Alex", owner: "user")]
    )
    XCTAssertEqual(body, "Weekly sync: Send the deck to Alex")
  }

  func testBannerBodyCountsAdditionalItems() {
    let body = MeetingActionItemBannerPolicy.bannerBody(
      conversationTitle: "Weekly sync",
      recommendedItems: [
        Self.item("Send the deck to Alex", owner: "user"),
        Self.item("Book the follow-up", owner: "user"),
        Self.item("File the expense report", owner: "user"),
      ]
    )
    XCTAssertEqual(body, "Weekly sync: Send the deck to Alex and 2 more")
  }

  func testBannerBodyTruncatesButPreservesCountTail() throws {
    let longDescription = String(repeating: "plan ", count: 40)
    let body = MeetingActionItemBannerPolicy.bannerBody(
      conversationTitle: "Quarterly planning marathon",
      recommendedItems: [
        Self.item(longDescription, owner: "user"),
        Self.item("Second item", owner: "user"),
      ]
    )

    let unwrapped = try XCTUnwrap(body)
    XCTAssertLessThanOrEqual(unwrapped.count, MeetingActionItemBannerPolicy.maxBodyLength)
    XCTAssertTrue(unwrapped.hasSuffix(" and 1 more"))
    XCTAssertTrue(unwrapped.contains("…"))
    XCTAssertTrue(unwrapped.hasPrefix("Quarterly planning marathon: "))
  }

  func testBannerBodyIsNilForZeroItems() {
    XCTAssertNil(
      MeetingActionItemBannerPolicy.bannerBody(
        conversationTitle: "Weekly sync",
        recommendedItems: []
      )
    )
  }

  // MARK: - Service behavior

  @MainActor
  func testCompletionWithUserItemsPresentsOneBanner() async {
    var presented: [(title: String, body: String)] = []
    let service = MeetingActionItemBannerService(
      fetchConversation: { id in
        Self.conversation(
          id: id,
          title: "Weekly sync",
          items: [
            Self.item("Send the deck to Alex", owner: "user"),
            Self.item("Alex reviews the deck", owner: "other"),
          ]
        )
      },
      fetchShareRecipients: { _ in [] },
      presentBanner: { title, body, _, _ in
        presented.append((title, body))
      }
    )

    service.handleMeetingCompletion(MeetingCompletionNotification(conversationIDs: ["conv-1"]))
    await service.waitForPendingRecommendations()

    XCTAssertEqual(presented.count, 1)
    XCTAssertEqual(presented.first?.title, "Meeting notes ready")
    XCTAssertEqual(presented.first?.body, "Weekly sync: Send the deck to Alex")
  }

  @MainActor
  func testZeroOpenUserItemsStillPresentsShareCardWithTitleBody() async {
    var presented: [(title: String, body: String)] = []
    let service = MeetingActionItemBannerService(
      fetchConversation: { id in
        Self.conversation(
          id: id,
          title: "Weekly sync",
          items: [
            Self.item("Alex reviews the deck", owner: "other"),
            Self.item("Already done", owner: "user", completed: true),
          ]
        )
      },
      fetchShareRecipients: { _ in [] },
      presentBanner: { title, body, _, _ in presented.append((title, body)) }
    )

    service.handleMeetingCompletion(MeetingCompletionNotification(conversationIDs: ["conv-1"]))
    await service.waitForPendingRecommendations()

    XCTAssertEqual(presented.count, 1)
    XCTAssertEqual(presented.first?.body, "Weekly sync")
  }

  @MainActor
  func testFetchFailurePresentsNothing() async {
    var presentedCount = 0
    let service = MeetingActionItemBannerService(
      fetchConversation: { _ in throw URLError(.notConnectedToInternet) },
      fetchShareRecipients: { _ in [] },
      presentBanner: { _, _, _, _ in presentedCount += 1 }
    )

    service.handleMeetingCompletion(MeetingCompletionNotification(conversationIDs: ["conv-1"]))
    await service.waitForPendingRecommendations()

    XCTAssertEqual(presentedCount, 0)
  }

  @MainActor
  func testDuplicateCompletionSignalsPresentOneBannerPerConversation() async {
    var presentedCount = 0
    let service = MeetingActionItemBannerService(
      fetchConversation: { id in
        Self.conversation(
          id: id,
          title: "Weekly sync",
          items: [Self.item("Send the deck to Alex", owner: "user")]
        )
      },
      fetchShareRecipients: { _ in [] },
      presentBanner: { _, _, _, _ in presentedCount += 1 }
    )

    // A finalization retry can re-signal the same conversation, including
    // within one coalesced flush and again from a later projection poll.
    service.handleMeetingCompletion(
      MeetingCompletionNotification(conversationIDs: ["conv-1", "conv-2"]))
    service.handleMeetingCompletion(MeetingCompletionNotification(conversationIDs: ["conv-1"]))
    await service.waitForPendingRecommendations()
    service.handleMeetingCompletion(MeetingCompletionNotification(conversationIDs: ["conv-2"]))
    await service.waitForPendingRecommendations()

    XCTAssertEqual(presentedCount, 2)
  }

  // MARK: - Click routing

  @MainActor
  func testMeetingBannerClickOpensMainChat() {
    XCTAssertEqual(
      NotificationService.openAction(
        assistantId: MeetingActionItemBannerPolicy.assistantID,
        title: MeetingActionItemBannerPolicy.bannerTitle
      ),
      .openMainChat
    )
    XCTAssertEqual(
      NotificationService.openAction(assistantId: "default", title: "Anything else"),
      .none
    )
  }

  func testSystemBannerOnlyDeliveryNeverPresentsOrJournalsThroughTheFloatingBar() {
    XCTAssertFalse(NotificationDeliveryMode.systemBannerOnly.presentsInFloatingBar)
    XCTAssertTrue(NotificationDeliveryMode.systemBannerOnly.requiresSystemBanner)
    XCTAssertTrue(NotificationDeliveryMode.standard.presentsInFloatingBar)
    XCTAssertFalse(NotificationDeliveryMode.standard.requiresSystemBanner)
  }

  @MainActor
  func testDetectedRecipientsReachThePresenterAndFailureDegradesToEmpty() async {
    var received: [[ConversationShareRecipient]] = []
    let service = MeetingActionItemBannerService(
      fetchConversation: { id in
        Self.conversation(
          id: id, title: "Weekly sync", items: [Self.item("Send the deck", owner: "user")])
      },
      fetchShareRecipients: { id in
        if id == "conv-1" {
          return [ConversationShareRecipient(name: "Sarah Chen", email: "sarah@acme.com")]
        }
        throw URLError(.notConnectedToInternet)
      },
      presentBanner: { _, _, _, recipients in received.append(recipients) }
    )

    service.handleMeetingCompletion(
      MeetingCompletionNotification(conversationIDs: ["conv-1", "conv-2"]))
    await service.waitForPendingRecommendations()

    XCTAssertEqual(received.count, 2)
    XCTAssertTrue(received.contains(where: { $0.map(\.email) == ["sarah@acme.com"] }))
    XCTAssertTrue(received.contains(where: { $0.isEmpty }))
  }

  func testShareRecipientShortLabelPrefersFirstName() {
    XCTAssertEqual(ConversationShareRecipient(name: "Sarah Chen", email: "sarah@acme.com").shortLabel, "Sarah")
    XCTAssertEqual(ConversationShareRecipient(name: nil, email: "jordan@acme.com").shortLabel, "jordan")
  }

  // MARK: - Fixtures

  private static func item(
    _ description: String,
    owner: String?,
    completed: Bool = false,
    deleted: Bool = false
  ) -> ActionItem {
    ActionItem(
      description: description,
      completed: completed,
      deleted: deleted,
      captureOwner: owner
    )
  }

  private static func conversation(
    id: String,
    title: String,
    items: [ActionItem]
  ) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: Date(timeIntervalSinceReferenceDate: 700_000_000),
      startedAt: nil,
      finishedAt: nil,
      structured: Structured(
        title: title,
        overview: "",
        emoji: "",
        category: "other",
        actionItems: items,
        events: []
      ),
      transcriptSegments: [],
      transcriptSegmentsIncluded: false,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: nil,
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil
    )
  }
}
