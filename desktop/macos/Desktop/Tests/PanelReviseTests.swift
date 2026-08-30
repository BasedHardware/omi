import XCTest

@testable import Omi_Computer

/// A panel the model cannot see is a panel it cannot change. `draft_message` returned
/// "Draft is on screen to copy", so "make that shorter" had nothing to shorten and the
/// only move left was writing a new draft from scratch — losing the user's edits and
/// where they dragged the window. These pin what the model is now handed, and what it
/// must never be handed.
@MainActor
final class PanelReviseTests: XCTestCase {
  /// PanelSession is process-wide state. Draining on the way IN as well as out makes
  /// these order-independent: a suite that leaves a record behind must not be able to
  /// fail a later one.
  override func setUp() async throws {
    try await super.setUp()
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
    }
  }

  override func tearDown() async throws {
    await MainActor.run {
      PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
    }
    try await super.tearDown()
  }

  private func field(
    _ label: String, _ value: String, masked: Bool = false, pending: Bool = false
  ) -> CloudConnectorCopyField {
    CloudConnectorCopyField(
      id: label.isEmpty ? "body" : label, label: label, value: value, masksValue: masked,
      isPending: pending)
  }

  private func present(_ fields: [CloudConnectorCopyField], origin: PanelSession.Origin = .requested) {
    PanelSession.present(
      title: "Draft", subtitle: "Copy it", fields: fields, grain: .app, origin: origin)
  }

  // MARK: - What the model may see

  func testTheModelIsHandedThePanelText() {
    present([field("", "Thanks so much for the quick turnaround!")])
    XCTAssertEqual(
      PanelSession.modelVisibleContent(), "Thanks so much for the quick turnaround!")
  }

  func testLabelledValuesArriveWithTheirLabels() {
    present([field("Email", "a@b.c"), field("Site", "example.dev")])
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Email: a@b.c\nSite: example.dev")
  }

  /// The one thing that must never leave. A masked value is a secret the panel hides on
  /// screen precisely so it is not read or repeated; putting it in a tool result would
  /// hand it to the speech provider instead.
  func testMaskedSecretsAreNeverHandedToTheModel() {
    present([field("URL", "https://x"), field("API key", "sk-live-abcdef", masked: true)])
    let content = PanelSession.modelVisibleContent()
    XCTAssertEqual(content?.contains("sk-live-abcdef"), false)
    XCTAssertEqual(content?.contains("https://x"), true)
    // Their existence is still stated, so the model does not offer to read what it lacks.
    XCTAssertEqual(content?.contains("1 secret value on the panel, withheld here."), true)
  }

  func testSpinnerRowsAreNotContent() {
    present([field("Bio", "", pending: true)])
    XCTAssertNil(PanelSession.modelVisibleContent())
  }

  func testNoPanelMeansNothingToShow() {
    XCTAssertNil(PanelSession.modelVisibleContent())
  }

  /// Bounded, because this rides on every panel tool result for the rest of the session.
  func testLongPanelsAreClippedBeforeTheyReachTheModel() {
    present([field("", String(repeating: "word ", count: 3_000))])
    let content = PanelSession.modelVisibleContent()
    XCTAssertEqual(content?.count, 4_001, "4000 characters plus the ellipsis")
  }

  // MARK: - Revising

  func testReviseReplacesTheContentsInPlace() {
    present([field("", "A long formal paragraph that the user wants trimmed.")])
    XCTAssertEqual(
      PanelSession.revise(
        title: nil,
        fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Short now.")])),
      .revised(1))
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Short now.")
  }

  /// One panel is one card in the transcript however many times the user revises it.
  /// Re-presenting instead would log every revision as a separate thing.
  func testRevisingLeavesOneTranscriptCardCarryingTheFinalText() {
    present([field("", "First attempt.")])
    PanelSession.revise(
      title: "Reply",
      fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Second attempt.")]))
    PanelSession.revise(
      title: "Reply",
      fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Final answer.")]))
    let cards = PanelSession.takeChatCards()
    XCTAssertEqual(cards.count, 1)
    XCTAssertEqual(cards.first?.text, "Final answer.")
    XCTAssertEqual(cards.first?.title, "Reply")
  }

  /// A panel leaves the moment its context does, so "make that shorter" routinely
  /// arrives after the card is gone. Refusing produced the worst outcome available,
  /// measured live: the model said "I've put the shorter note on your screen now" with
  /// nothing on screen. It creates instead.
  func testRevisingWithNothingOnScreenPutsThePanelUp() {
    XCTAssertEqual(
      PanelSession.revise(
        title: "Note",
        fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Short one.")])),
      .created(1))
    XCTAssertTrue(PanelSession.isPresenting)
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Short one.")
  }

  /// A created-from-revision panel is one the user asked for, so it reaches the
  /// transcript like any other.
  func testAPanelCreatedByRevisingStillReachesTheTranscript() {
    PanelSession.revise(
      title: "Note",
      fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Short one.")]))
    XCTAssertEqual(PanelSession.takeChatCards().first?.title, "Note")
  }

  func testCreatingByRevisionWithNoTitleStillNamesTheCard() {
    PanelSession.revise(
      title: nil,
      fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Untitled.")]))
    XCTAssertEqual(PanelSession.takeChatCards().first?.title, "For you")
  }

  /// An empty edit would blank the panel the user is reading. Refused, so the model has
  /// to send the complete new contents.
  func testRevisingToNothingIsRefused() {
    present([field("", "Keep me.")])
    guard case .refused = PanelSession.revise(title: nil, fields: []) else {
      return XCTFail("an empty edit would blank the panel the user is reading")
    }
    XCTAssertEqual(PanelSession.modelVisibleContent(), "Keep me.")
  }

  // MARK: - Panels that must not be overwritten

  /// The ✓ is the user's permission to spend. Writing over an unanswered offer would
  /// take that decision away from them.
  func testAnUnansweredOfferIsNotOverwritten() {
    PanelSession.present(
      title: "Fill this form?", subtitle: "5 fields", fields: [], grain: .context,
      origin: .ambient,
      ask: CopyCardAsk(placeholder: "Add context…", confirmLabel: "Fill it", onConfirm: { _ in }))
    guard
      case .refused(let reason) = PanelSession.revise(
        title: nil, fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "x")]))
    else { return XCTFail("an unanswered offer must survive") }
    XCTAssertTrue(reason.contains("tap the check"))
  }

  /// A card mid-fill is an answer in flight; replacing it throws the model call away.
  func testAPanelStillFillingInIsNotOverwritten() {
    present([field("Bio", "", pending: true)])
    guard
      case .refused(let reason) = PanelSession.revise(
        title: nil, fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "x")]))
    else { return XCTFail("work in flight must survive") }
    XCTAssertTrue(reason.contains("still filling in"))
  }

  /// The draft card has its own edit box, so refining it is something the user does on
  /// the card directly.
  func testTheDraftCardIsNotOverwritten() {
    PanelSession.presentCompose(
      fingerprint: "convo-1", appDisplayName: "Telegram", targetWindowFrame: nil,
      restore: MessageDraft(subject: nil, body: "Hi there"), origin: .requested,
      onGenerate: { _, _ in .success(MessageDraft(subject: nil, body: "x")) }, onDecline: {})
    guard
      case .refused(let reason) = PanelSession.revise(
        title: nil, fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "x")]))
    else { return XCTFail("the draft card must survive") }
    XCTAssertTrue(reason.contains("its own box"))
  }

  /// Omitting the title keeps the one the panel has, so "make it shorter" does not
  /// silently rename the card.
  func testOmittingTheTitleKeepsIt() {
    present([field("", "First.")])
    PanelSession.revise(
      title: nil, fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Second.")]))
    XCTAssertEqual(PanelSession.takeChatCards().first?.title, "Draft")
  }
}

/// Titles the model supplies. Measured live: an update_panel call arrived with
/// `"title": "floating_chat"` — an internal surface token from its own tool vocabulary
/// — which would have renamed the user's card to that.
final class PanelTitleTests: XCTestCase {
  func testProseTitlesAreAccepted() {
    XCTAssertTrue(VoicePanel.isReadableTitle("Wi-Fi Network Names"))
    XCTAssertTrue(VoicePanel.isReadableTitle("Draft"))
    XCTAssertTrue(VoicePanel.isReadableTitle("Packing list for the weekend"))
  }

  func testIdentifierShapedTitlesAreRefused() {
    XCTAssertFalse(VoicePanel.isReadableTitle("floating_chat"))
    XCTAssertFalse(VoicePanel.isReadableTitle("main_chat"))
    XCTAssertFalse(VoicePanel.isReadableTitle("  "))
  }

  /// An underscore inside real prose is not an identifier; only a bare token is.
  func testAnUnderscoreInsideProseIsStillATitle() {
    XCTAssertTrue(VoicePanel.isReadableTitle("Notes on my_file.txt"))
  }
}
