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
