import XCTest

@testable import Omi_Computer

/// Every proactive card must say what it is before it can reach the transcript.
///
/// `showNotification` used to take an optional `kind:` and `FloatingBarNotification`
/// filled it in from `assistantId`, whose default arm was `.general`. Five
/// producers never passed one, so their rows journaled a bare
/// `notification:<uuid>` key and came back badged "Notification" — a row that
/// says nothing about what Omi noticed. Nothing failed; the copy was simply
/// wrong forever.
final class ProactiveNotificationKindTests: XCTestCase {
  /// Every assistant id a producer actually ships, mapped to what its card is.
  /// `.general` is not reachable from any of them — it is decode-only.
  private static let producerAssistantIDs = [
    "suggestion", "insight", "task", "memory-extraction", "goals", "meeting-notes",
    "integration_connect", "context-director", "trial", "onboarding", "daily_recap",
    "notch_receipt", "notch_end", "reach_error", "unknown-future-assistant",
  ]

  /// The transcript row a journaled notification comes back as.
  private static func journaledRow(clientTurnId: String) -> ChatMessage {
    ChatMessage(id: UUID().uuidString, clientTurnId: clientTurnId, text: "Body", sender: .ai)
  }

  func testNoProducerAssistantIDDerivesTheDecodeOnlyGeneralKind() {
    for assistantID in Self.producerAssistantIDs {
      XCTAssertNotEqual(
        ProactiveNotificationKind.from(assistantId: assistantID), .general,
        "\(assistantID) would journal a bare notification:<uuid> key badged \"Notification\"")
    }
    for decisionType in ["suggest", "focus_nudge", "insight", "task_candidate", "resurface", ""] {
      XCTAssertNotEqual(ProactiveNotificationKind.from(decisionType: decisionType), .general)
    }
  }

  func testEveryProducerKindJournalsAKindedContinuityKey() {
    let id = UUID()
    let bare = ChatContinuityInvariants.proactiveNotificationContinuityKey(id: id)

    for kind in ProactiveNotificationKind.allCases where kind != .general {
      let key = ChatContinuityInvariants.proactiveNotificationContinuityKey(id: id, kind: kind)
      XCTAssertNotEqual(key, bare, "\(kind.rawValue) must not journal the bare historical key")
      XCTAssertTrue(key.hasPrefix("notification:\(kind.rawValue):"))
      XCTAssertEqual(
        ChatContinuityInvariants.proactiveNotificationKind(Self.journaledRow(clientTurnId: key)), kind,
        "the kind must survive the round trip that renders the badge")
    }
  }

  /// Historical rows carry the bare key. Decoding must keep working, and it must
  /// keep resolving to `.general` — that arm is the only reason `.general` exists.
  func testHistoricalBareKeysStillDecode() {
    let id = UUID()
    let bare = ChatContinuityInvariants.proactiveNotificationContinuityKey(id: id)
    XCTAssertEqual(bare, "notification:\(id.uuidString)")
    XCTAssertEqual(
      ChatContinuityInvariants.proactiveNotificationKind(Self.journaledRow(clientTurnId: bare)),
      .general)
    XCTAssertEqual(
      ChatContinuityInvariants.proactiveNotificationContinuityKey(id: id, kind: .general), bare,
      "the bare form stays reachable for round-tripping history, never for minting")
  }

  /// Trial messaging, onboarding permission help, and the daily recap's
  /// announcement are cards, not observations. They present and dismiss; they
  /// must never become chat rows.
  func testProductCopyCardsAreExcludedFromJournaling() {
    XCTAssertFalse(ProactiveNotificationKind.trial.isJournaled)
    XCTAssertFalse(ProactiveNotificationKind.onboarding.isJournaled)
    XCTAssertFalse(ProactiveNotificationKind.dailyRecap.isJournaled)
    for kind in ProactiveNotificationKind.allCases
    where kind != .trial && kind != .onboarding && kind != .dailyRecap {
      XCTAssertTrue(kind.isJournaled, "\(kind.rawValue) is something Omi observed")
    }
  }

  /// The recap announcement must present under the recap identity, never the
  /// default assistant: the default derives `.functional`, which journals a
  /// bell card into the transcript — a truncated, stat-less duplicate of the
  /// dedicated `ChatDailyRecapRow` day boundary the thread already renders.
  func testTheRecapAnnouncementPresentsUnjournaledUnderItsOwnIdentity() {
    @MainActor func announcementKind() -> ProactiveNotificationKind {
      ProactiveNotificationKind.from(assistantId: ChatDailySummaryCoordinator.assistantID)
    }
    let kind = MainActor.assumeIsolated(announcementKind)
    XCTAssertEqual(kind, .dailyRecap)
    XCTAssertFalse(ProactiveNotificationKind.dailyRecap.isJournaled)
  }

  /// The five category toggles gate the five proactive categories and nothing
  /// else. Functional notices and the two never-journaled cards stay ungated.
  func testCategoryTogglesGateOnlyTheFiveProactiveCategories() {
    func allows(_ kind: ProactiveNotificationKind) -> Bool {
      NotificationService.categoryToggleAllows(
        kind: kind,
        focusEnabled: false,
        taskEnabled: false,
        insightEnabled: false,
        memoryEnabled: false,
        integrationEnabled: false,
        meetingSummaryEnabled: false)
    }
    for gated: ProactiveNotificationKind in [
      .suggestion, .task, .meetingNotes, .insight, .resurface, .goal, .memory, .integration,
    ] {
      XCTAssertFalse(allows(gated), "\(gated.rawValue) must honour its category toggle")
    }
    for ungated: ProactiveNotificationKind in [.general, .functional, .trial, .onboarding, .dailyRecap] {
      XCTAssertTrue(allows(ungated), "\(ungated.rawValue) sits outside the five-category taxonomy")
    }
  }

  /// Every kind still presents as one of the five user-facing badges (or the two
  /// neutral ones), so a new kind cannot reach the transcript unlabelled.
  func testEveryKindHasABadge() {
    for kind in ProactiveNotificationKind.allCases {
      let badge = ProactiveNotificationBadge(kind: kind)
      XCTAssertFalse(badge.label.isEmpty, kind.rawValue)
      XCTAssertFalse(badge.systemImage.isEmpty, kind.rawValue)
    }
  }
}
