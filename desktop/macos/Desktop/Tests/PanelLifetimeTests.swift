import XCTest

@testable import Omi_Computer

/// Who a panel belongs to and how long it lasts.
///
/// Both were owned in name only. Work that filled a panel wrote wherever the overlay
/// happened to be, and a card that timed out stayed remembered — so it came back on the
/// next context return, with a fresh countdown.
@MainActor
final class PanelLifetimeTests: XCTestCase {
  /// PanelSession is process-wide state, so drain on the way in as well as out: a suite
  /// that leaves a panel or a record behind must not be able to fail a later one.
  override func setUp() async throws {
    try await super.setUp()
    _ = PanelSession.dismiss()
    _ = PanelSession.takeChatCards()
  }

  override func tearDown() async throws {
    _ = PanelSession.dismiss()
    _ = PanelSession.takeChatCards()
    try await super.tearDown()
  }

  private func field(_ label: String, _ value: String) -> CloudConnectorCopyField {
    CloudConnectorCopyField(id: label, label: label, value: value, masksValue: false)
  }

  @discardableResult
  private func present(_ title: String, _ value: String) -> PanelSession.Token {
    PanelSession.present(
      title: title, subtitle: "Copy it with the button.", fields: [field("Email", value)],
      grain: .app, origin: .requested)
  }

  // MARK: - Identity

  /// A lookup that finishes after the user asked for something else must reach its own
  /// panel or nothing — never the card that replaced it.
  func testALateAnswerNeverWritesIntoThePanelThatReplacedIt() {
    let first = present("Finding that", "old@b.c")
    present("Second", "new@b.c")
    PanelSession.update(title: "Late", fields: [field("Email", "late@b.c")], token: first)
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: new@b.c")
  }

  /// The same for a failure: a lookup that gives up must not close somebody else's card.
  func testALateFailureNeverClosesThePanelThatReplacedIt() {
    let first = present("Finding that", "old@b.c")
    present("Second", "new@b.c")
    XCTAssertFalse(PanelSession.dismiss(token: first))
    XCTAssertTrue(PanelSession.isPresenting)
  }

  /// The panel that started the work still answers to its own token.
  func testWorkStillReachesThePanelItStartedFor() {
    let panel = present("Finding that", "old@b.c")
    PanelSession.update(fields: [field("Email", "found@b.c")], token: panel)
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: found@b.c")
    XCTAssertTrue(PanelSession.dismiss(token: panel))
  }

  /// An untokened caller still addresses whatever is up — the surfaces that own the only
  /// panel in play do not have to carry one.
  func testAnUntokenedUpdateStillReachesThePanelOnScreen() {
    present("Panel", "a@b.c")
    PanelSession.update(fields: [field("Email", "c@d.e")])
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: c@d.e")
  }

  // MARK: - Lifetime

  /// The card's countdown running out has to reach the owner. Left remembered, the panel
  /// returns the next time the user comes back to its context.
  func testACardThatTimesOutIsForgottenRatherThanRemembered() {
    let panel = present("Offer", "a@b.c")
    PanelSession.expire(panel)
    XCTAssertFalse(PanelSession.isPresenting)
    XCTAssertNil(PanelSession.reopen())
  }

  /// A countdown belongs to the panel that started it. One that fires after the panel was
  /// replaced must not take the replacement down.
  func testAStaleCountdownDoesNotTakeDownTheCurrentPanel() {
    let first = present("First", "a@b.c")
    present("Second", "c@d.e")
    PanelSession.expire(first)
    XCTAssertTrue(PanelSession.isPresenting)
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: c@d.e")
  }

  // MARK: - The transcript queue

  /// A voice turn is the only thing that drains the queue, and a panel bought with the ✓
  /// on an ambient offer may never be followed by one. Waiting is right; waiting forever
  /// puts it under an unrelated reply hours later.
  func testARecordNobodyClaimedAgesOutRatherThanLandingUnderALaterTurn() {
    present("Your Information", "a@b.c")
    XCTAssertTrue(PanelSession.takeChatCards(now: Date().addingTimeInterval(3_600)).isEmpty)
  }

  /// Until it ages out it waits: a turn that cannot carry content blocks leaves the
  /// record alone, and the next one picks it up.
  func testARecordWaitsForATurnThatCanCarryIt() {
    present("Your Information", "a@b.c")
    XCTAssertEqual(PanelSession.takeChatCards().map(\.summary), ["Email"])
    XCTAssertTrue(PanelSession.takeChatCards().isEmpty)
  }

  // MARK: - Cards that are not Omi's to rewrite

  /// The assisted connector card is a setup the user is walking through, and its grouping
  /// is part of the instructions. `update_panel` must refuse it rather than flatten it.
  func testTheConnectorSetupCardIsNotRewrittenByVoice() {
    PanelSession.present(
      sections: [
        CloudConnectorCopySection(id: "basic", title: "", fields: [field("URL", "https://x")]),
        CloudConnectorCopySection(id: "advanced", title: "Advanced", fields: [field("Port", "8080")]),
      ],
      title: "Connect Notion", subtitle: "Paste each value.", grain: .app, origin: .requested,
      editable: false)
    guard case .refused = PanelSession.revise(title: "Shorter", fields: [field("URL", "https://y")])
    else { return XCTFail("a setup card must not be overwritten") }
    XCTAssertEqual(PanelSession.modelVisibleContent(), "URL: https://x\nPort: 8080")
  }

  /// Nor is connector configuration transcript material.
  func testConnectorSetupValuesNeverReachTheTranscript() {
    PanelSession.present(
      sections: [
        CloudConnectorCopySection(id: "basic", title: "", fields: [field("URL", "https://x")])
      ],
      title: "Connect Notion", subtitle: "Paste each value.", grain: .app, origin: .requested,
      editable: false)
    XCTAssertTrue(PanelSession.takeChatCards().isEmpty)
  }
}
