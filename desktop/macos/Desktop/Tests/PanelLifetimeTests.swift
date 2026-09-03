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
    _ = PanelSession.dismiss()
    _ = PanelSession.takeChatCards()
    PanelSession.forgetClosedHistory()
  }

  override func tearDown() async throws {
    _ = PanelSession.dismiss()
    _ = PanelSession.takeChatCards()
    PanelSession.forgetClosedHistory()
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
  func testACardThatTimesOutLeavesTheScreen() {
    let panel = present("Offer", "a@b.c")
    PanelSession.expire(panel)
    XCTAssertFalse(PanelSession.isPresenting, "the countdown takes it down")
    XCTAssertTrue(
      PanelSession.canPresentAmbient,
      "and it no longer holds the screen, which is what still being up would mean")
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

  /// Coming back to a context the panel already outlived must not flash the card up for
  /// its last second: the deadline kept running while it was hidden.
  func testAPanelWhoseDeadlinePassedWhileHiddenIsNotPutBackUp() {
    PanelSession.present(
      title: "Fill this form?", subtitle: "7 fields", fields: [field("Email", "a@b.c")],
      grain: .context, origin: .ambient, autoDismissAfter: -1)
    XCTAssertFalse(
      PanelSession.isPresenting, "showing a card its deadline already outlived is a flash")
  }

  /// Four minutes with neither the ✓ nor the ✗ is an answer, and the surface that offered
  /// has to hear it — otherwise the next scan offers the same form again.
  func testAnOfferThatRunsOutTellsTheSurfaceItWasIgnored() {
    var ignored = false
    var declined = false
    let panel = PanelSession.present(
      title: "Fill this form?", subtitle: "7 fields", fields: [field("Email", "a@b.c")],
      grain: .context, origin: .ambient,
      onUserDismiss: { declined = true }, onExpire: { ignored = true })
    PanelSession.expire(panel)
    XCTAssertTrue(ignored)
    XCTAssertFalse(declined, "an ignored offer is not a declined one")
  }

  /// Accepting it stops the countdown, so the ✓ can never be followed by an ignore.
  func testAcceptingAnOfferSilencesItsCountdown() {
    var ignored = false
    let panel = PanelSession.present(
      title: "Fill this form?", subtitle: "7 fields", fields: [field("Email", "a@b.c")],
      grain: .context, origin: .ambient,
      ask: CopyCardAsk(placeholder: "…", confirmLabel: "Fill it", onConfirm: { _ in }),
      onExpire: { ignored = true })
    PanelSession.resolveAsk()
    PanelSession.expire(panel)
    XCTAssertFalse(ignored)
  }

  /// A form panel holds answers a model call paid for, and asking again does not get them
  /// back for free. `update_panel` must refuse it rather than write prose over them.
  func testFormAnswersAreNotOverwrittenByAVoiceEdit() {
    PanelSession.present(
      title: "Safari form", subtitle: "3 of 7 fields", fields: [field("Email", "a@b.c")],
      grain: .context, origin: .requested, formFingerprint: "form-7")
    guard case .refused = PanelSession.revise(title: "Shorter", fields: [field("Note", "hi")])
    else { return XCTFail("form answers must not be overwritten") }
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: a@b.c")
  }

  /// A panel with no form behind it is ordinary content and still edits in place.
  func testAPanelWithNoFormBehindItStillEdits() {
    present("Train Stations", "Barbican")
    guard case .revised = PanelSession.revise(title: nil, fields: [field("Email", "Euston")])
    else { return XCTFail("an ordinary panel should still be editable") }
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: Euston")
  }

  // MARK: - Bringing a closed panel back

  /// "Close that panel" then "bring it back" is a pair the voice tools offer, and it was
  /// impossible to complete: closing forgot the panel outright, so reopen had nothing.
  func testAClosedPanelCanBeBroughtBack() {
    present("Train Stations", "Euston")
    XCTAssertTrue(PanelSession.dismiss())
    XCTAssertEqual(PanelSession.reopen(), 1)
    XCTAssertTrue(PanelSession.isPresenting)
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: Euston")
  }

  /// Only the last one, and only once — a second ask with nothing behind it must say so
  /// rather than resurrecting something older.
  func testOnlyTheMostRecentlyClosedPanelComesBack() {
    present("First", "a@b.c")
    _ = PanelSession.dismiss()
    present("Second", "c@d.e")
    _ = PanelSession.dismiss()
    XCTAssertEqual(PanelSession.reopen(), 1)
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: c@d.e")
    XCTAssertTrue(PanelSession.dismiss())
    XCTAssertNotNil(PanelSession.reopen(), "the one just closed is available again")
    _ = PanelSession.dismiss()
    _ = PanelSession.reopen()
    _ = PanelSession.dismiss()
    _ = PanelSession.reopen()
    XCTAssertTrue(PanelSession.isPresenting)
  }

  /// The ✗ means "not now", not "never mention it again": an explicit ask brings it back
  /// like any other close. The surface that offered it is still told it was declined, so
  /// the card never re-offers itself — only the user can call it back.
  func testACardDismissedWithTheCrossComesBackWhenAskedFor() {
    var declined = false
    PanelSession.present(
      title: "Fill this form?", subtitle: "7 fields", fields: [field("Email", "a@b.c")],
      grain: .context, origin: .ambient, onUserDismiss: { declined = true })
    XCTAssertTrue(PanelSession.dismiss())
    XCTAssertEqual(PanelSession.reopen(), 1)
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: a@b.c")
    XCTAssertFalse(declined, "dismiss() is not the ✗; only the card's own close declines")
  }

  /// A panel brought back by name is one the user asked for, so it does not run the
  /// countdown an unanswered offer runs on.
  func testAnOfferBroughtBackDoesNotExpireAgain() {
    let panel = PanelSession.present(
      title: "Fill this form?", subtitle: "7 fields", fields: [field("Email", "a@b.c")],
      grain: .context, origin: .ambient, autoDismissAfter: -1,
      ask: CopyCardAsk(placeholder: "…", confirmLabel: "Fill it", onConfirm: { _ in }))
    PanelSession.expire(panel)
    XCTAssertFalse(PanelSession.isPresenting)
    XCTAssertNotNil(PanelSession.reopen())
    XCTAssertTrue(PanelSession.isPresenting, "an already-passed deadline must not kill it again")
    XCTAssertFalse(PanelSession.isAsking, "the ✓ was not re-offered")
  }

  /// Nothing was ever up, so there is nothing to bring back.
  func testReopeningWithNothingEverShownStillReportsNothing() {
    XCTAssertNil(PanelSession.reopen())
  }

  // MARK: - The transcript queue

  /// A voice turn is the only thing that drains the queue, and a panel bought with the ✓
  /// on an ambient offer may never be followed by one. Waiting is right; waiting forever
  /// puts it under an unrelated reply hours later.
  func testARecordNobodyClaimedAgesOutRatherThanLandingUnderALaterTurn() {
    present("Your Information", "a@b.c")
    XCTAssertTrue(PanelSession.takeChatCards(now: Date().addingTimeInterval(3_600)).isEmpty)
  }

  /// A panel put up in one turn and edited in a later one leaves two cards, not one: the
  /// first turn's write already carried the original away, and dropping the correction
  /// leaves the transcript holding exactly the text the user asked to change.
  func testAnEditInALaterTurnStillReachesTheTranscript() {
    present("Train Stations", "Barbican")
    XCTAssertEqual(PanelSession.takeChatCards().map(\.text), ["Email: Barbican"])
    guard case .revised = PanelSession.revise(title: nil, fields: [field("Email", "Euston")])
    else { return XCTFail("the edit should have landed on the panel") }
    XCTAssertEqual(PanelSession.takeChatCards().map(\.text), ["Email: Euston"])
  }

  /// Within one turn it is still one card: a panel filling in updates its record rather
  /// than adding a second.
  func testStreamingFillsStillLeaveOneCard() {
    present("Finding that", "…")
    PanelSession.update(fields: [field("Email", "a@b.c")])
    PanelSession.update(fields: [field("Email", "final@b.c")])
    XCTAssertEqual(PanelSession.takeChatCards().map(\.text), ["Email: final@b.c"])
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
