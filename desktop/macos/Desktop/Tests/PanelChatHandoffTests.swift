import XCTest

@testable import Omi_Computer

/// What a voice-requested panel leaves behind in the chat transcript: a collapsible
/// card whose header names the values and whose fold carries them.
final class PanelChatHandoffTests: XCTestCase {
  private func field(
    _ label: String, _ value: String, pending: Bool = false, masked: Bool = false
  ) -> CloudConnectorCopyField {
    CloudConnectorCopyField(
      id: label.isEmpty ? "passage" : label, label: label, value: value, masksValue: masked,
      isPending: pending)
  }

  func testLabeledValuesBecomeACard() {
    XCTAssertEqual(
      PanelSession.chatCard(
        title: "Your Information",
        fields: [field("Email", "a@b.c"), field("Phone", "555-0100")]),
      PanelSession.PanelChatCard(
        title: "Your Information",
        summary: "Email, Phone",
        text: "Email: a@b.c\nPhone: 555-0100"))
  }

  /// A passage has no labels to summarize with, so its first line stands in — and a
  /// panel that somehow lost its title still gets a name on the card.
  func testPassageSummarizesWithItsFirstLine() {
    XCTAssertEqual(
      PanelSession.chatCard(title: " ", fields: [field("", "Thanks so much!\nSee you Monday.")]),
      PanelSession.PanelChatCard(
        title: "Saved from your panel",
        summary: "Thanks so much!",
        text: "Thanks so much!\nSee you Monday."))
  }

  /// A cancelled or unanswered panel is spinner rows and empty values — nothing worth
  /// a card. Masked values are secrets and never leave the panel.
  func testPendingMaskedAndEmptyFieldsNeverReachChat() {
    XCTAssertNil(
      PanelSession.chatCard(
        title: "Mid-flight",
        fields: [
          field("Email", "", pending: true),
          field("Key", "wJalrXUtnFEMI", masked: true),
          field("Skipped", "   "),
        ]))
    XCTAssertEqual(
      PanelSession.chatCard(
        title: "Partial",
        fields: [field("Email", "a@b.c"), field("Portfolio", "", pending: true)]),
      PanelSession.PanelChatCard(title: "Partial", summary: "Email", text: "Email: a@b.c"))
  }

  /// The card must survive the journal round trip: encoded as a discoveryCard block
  /// and decoded back with the fold intact.
  func testCardSurvivesContentBlockRoundTrip() {
    let card = PanelSession.chatCard(
      title: "Your Information", fields: [field("Email", "a@b.c")])!
    let block = ChatContentBlock.discoveryCard(
      id: "voice-panel-key-0", title: card.title, summary: card.summary, fullText: card.text)
    guard let json = ChatContentBlockCodec.encode([block]),
      let decoded = ChatContentBlockCodec.decode(json),
      case .discoveryCard(let id, let title, let summary, let fullText)? = decoded.first
    else { return XCTFail("round trip failed") }
    XCTAssertEqual(id, "voice-panel-key-0")
    XCTAssertEqual(title, "Your Information")
    XCTAssertEqual(summary, "Email")
    XCTAssertEqual(fullText, "Email: a@b.c")
  }
}

/// A panel the user bought with ✓ is a panel they asked for. The offer starts ambient
/// because nobody asked for it; the tick is the ask, and everything that follows from
/// being asked has to follow from it too — including surviving into the transcript,
/// which is the only place the content lives once the panel leaves with its context.
@MainActor
final class PanelAskPromotionTests: XCTestCase {
  /// PanelSession is process-wide state. Draining on the way IN as well as out makes
  /// these order-independent: a suite that leaves a record behind must not be able to
  /// fail a later one.
  override func setUp() async throws {
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
  }

  private func present(origin: PanelSession.Origin, ask: CopyCardAsk?) {
    PanelSession.present(
      title: "Fill this form?",
      subtitle: "2 fields",
      fields: [
        CloudConnectorCopyField(id: "email", label: "Email", value: "a@b.c", masksValue: false)
      ],
      grain: .context,
      origin: origin,
      ask: ask)
  }

  private var ask: CopyCardAsk {
    CopyCardAsk(placeholder: "Add context…", confirmLabel: "Fill it", onConfirm: { _ in })
  }

  func testAnUnansweredAmbientOfferLeavesNothingInTheTranscript() {
    present(origin: .ambient, ask: ask)
    XCTAssertTrue(PanelSession.takeChatCards().isEmpty)
  }

  func testAnsweringTheAskPromotesTheOfferIntoTheTranscript() {
    present(origin: .ambient, ask: ask)
    PanelSession.resolveAsk()
    XCTAssertEqual(PanelSession.takeChatCards().map(\.summary), ["Email"])
  }

  /// Promotion also decides who may take the screen. Once bought, the panel must not be
  /// replaced by the next unrequested offer.
  func testAPromotedPanelOutranksALaterAmbientOffer() {
    present(origin: .ambient, ask: ask)
    XCTAssertTrue(PanelSession.canPresentAmbient)
    PanelSession.resolveAsk()
    XCTAssertFalse(PanelSession.canPresentAmbient)
  }

  /// Content that streams in after the ✓ is what the user actually wanted; the record
  /// started at tick time has to keep up with it.
  func testAnswersArrivingAfterTheTickReachTheTranscript() {
    present(origin: .ambient, ask: ask)
    PanelSession.resolveAsk()
    PanelSession.update(
      title: "Omi can fill this",
      fields: [
        CloudConnectorCopyField(id: "email", label: "Email", value: "a@b.c", masksValue: false),
        CloudConnectorCopyField(id: "site", label: "Website", value: "example.dev", masksValue: false),
      ])
    let cards = PanelSession.takeChatCards()
    XCTAssertEqual(cards.map(\.title), ["Omi can fill this"])
    XCTAssertEqual(cards.first?.text, "Email: a@b.c\nWebsite: example.dev")
  }

  /// resolveAsk is only ever the user's tick. A panel with no offer on it must not be
  /// quietly promoted by a stray call.
  func testResolvingWithNoAskChangesNothing() {
    present(origin: .ambient, ask: nil)
    PanelSession.resolveAsk()
    XCTAssertTrue(PanelSession.takeChatCards().isEmpty)
  }
}
