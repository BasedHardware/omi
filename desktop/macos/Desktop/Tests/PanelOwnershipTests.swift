import AppKit
import XCTest

@testable import Omi_Computer

/// One owner, one screen. The copy card and the draft card live in different windows, so
/// "is a card up" was answered in two places and each surface guarded only its own — a
/// form offer would draw straight over a live draft. These pin the shared answer.
@MainActor
final class PanelOwnershipTests: XCTestCase {
  /// PanelSession is process-wide state. Draining on the way IN as well as out makes
  /// these order-independent: a suite that leaves a record behind must not be able to
  /// fail a later one.
  override func setUp() async throws {
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
      PanelSession.forgetClosedHistory()
    }
  }

  override func tearDown() async throws {
    await MainActor.run {
      PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
      PanelSession.forgetClosedHistory()
    }
  }

  private func presentCopy(origin: PanelSession.Origin) {
    PanelSession.present(
      title: "Values",
      subtitle: "Copy each",
      fields: [
        CloudConnectorCopyField(id: "email", label: "Email", value: "a@b.c", masksValue: false)
      ],
      grain: .context,
      origin: origin)
  }

  private func presentCompose(origin: PanelSession.Origin, fingerprint: String = "convo-1") {
    PanelSession.presentCompose(
      fingerprint: fingerprint,
      appDisplayName: "Telegram",
      targetWindowFrame: nil,
      restore: nil,
      origin: origin,
      onGenerate: { _, _ in .success(MessageDraft(subject: nil, body: "drafted")) },
      onDecline: {})
  }

  // MARK: - The bug

  /// The regression. Before, `canPresentAmbient` checked only the copy overlay, so an
  /// unrequested form offer could take the screen while the draft card was up.
  func testAnAmbientOfferMayNotDrawOverADraftCard() {
    presentCompose(origin: .requested)
    XCTAssertTrue(PanelSession.isPresenting)
    XCTAssertFalse(PanelSession.canPresentAmbient)
  }

  /// And the mirror: a requested copy card is not replaceable either.
  func testAnAmbientOfferMayNotDrawOverARequestedCopyCard() {
    presentCopy(origin: .requested)
    XCTAssertFalse(PanelSession.canPresentAmbient)
  }

  /// An offer nobody asked for may still be replaced by another offer — that rule has
  /// to survive the unification, or ambient surfaces deadlock each other.
  func testOneAmbientOfferStillYieldsToAnother() {
    presentCopy(origin: .ambient)
    XCTAssertTrue(PanelSession.canPresentAmbient)
  }

  // MARK: - One window at a time

  /// Switching kind must close the window the other presenter was holding, or both stay
  /// on screen and the user sees two cards.
  func testSwitchingFromCopyToComposeLeavesOnlyOneWindow() {
    presentCopy(origin: .requested)
    XCTAssertTrue(CloudConnectorGuidanceOverlay.shared.isPresenting)
    presentCompose(origin: .requested)
    XCTAssertFalse(CloudConnectorGuidanceOverlay.shared.isPresenting)
    XCTAssertTrue(MessageDraftCardController.shared.isPresenting)
  }

  func testSwitchingFromComposeToCopyLeavesOnlyOneWindow() {
    presentCompose(origin: .requested)
    presentCopy(origin: .requested)
    XCTAssertFalse(MessageDraftCardController.shared.isPresenting)
    XCTAssertTrue(CloudConnectorGuidanceOverlay.shared.isPresenting)
  }

  func testDismissClosesBothPresenters() {
    presentCompose(origin: .requested)
    PanelSession.dismiss()
    XCTAssertFalse(MessageDraftCardController.shared.isPresenting)
    XCTAssertFalse(CloudConnectorGuidanceOverlay.shared.isPresenting)
    XCTAssertFalse(PanelSession.isPresenting)
  }

  // MARK: - Identity

  /// Each surface retires its own card and nobody else's.
  func testDismissComposeOnlyTouchesThatConversation() {
    presentCompose(origin: .ambient, fingerprint: "convo-1")
    PanelSession.dismissCompose("convo-2")
    XCTAssertTrue(PanelSession.isPresenting)
    PanelSession.dismissCompose("convo-1")
    XCTAssertFalse(PanelSession.isPresenting)
  }

  func testIsShowingComposeAnswersForTheLiveConversationOnly() {
    presentCompose(origin: .ambient, fingerprint: "convo-1")
    XCTAssertTrue(PanelSession.isShowingCompose("convo-1"))
    XCTAssertFalse(PanelSession.isShowingCompose("convo-2"))
  }

  /// A compose panel must never be tested by the form scanner: `formFingerprint` is what
  /// the liveness sweep reads, and a draft card has none.
  func testAComposePanelIsNeverMistakenForAForm() {
    presentCompose(origin: .ambient, fingerprint: "convo-1")
    XCTAssertFalse(PanelSession.isShowingForm("convo-1"))
  }

  // MARK: - The connector card

  /// Sections survive the fold: the connector form hides some values behind a
  /// disclosure, and flattening them would silently regroup a shipped setup card.
  func testSectionedCopyCardsKeepTheirSections() {
    PanelSession.present(
      sections: [
        CloudConnectorCopySection(
          id: "main", title: "",
          fields: [
            CloudConnectorCopyField(id: "url", label: "URL", value: "https://x", masksValue: false)
          ]),
        CloudConnectorCopySection(
          id: "advanced", title: "Advanced",
          fields: [
            CloudConnectorCopyField(id: "key", label: "Key", value: "abc", masksValue: true)
          ]),
      ],
      title: "Connect", subtitle: "Copy each", grain: .app, origin: .requested)
    XCTAssertTrue(PanelSession.isPresenting)
    // The masked value is a secret and must not reach the transcript; the other must.
    let cards = PanelSession.takeChatCards()
    XCTAssertEqual(cards.first?.text, "URL: https://x")
  }
}
