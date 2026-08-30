import XCTest

@testable import Omi_Computer

/// What a panel does with content the model gets wrong or sends too much of. The model
/// writes these items; none of these shapes should reach the user as a broken card.
@MainActor
final class PanelEdgeCaseTests: XCTestCase {
  override func setUp() async throws {
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
    }
  }

  override func tearDown() async throws {
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
    }
  }

  private func items(_ pairs: [(String, String)]) -> [VoicePanelItem] {
    pairs.map { VoicePanelItem(label: $0.0, text: $0.1) }
  }

  // MARK: - Too much

  func testMoreItemsThanFitAreCappedNotSpilled() {
    let many = (1...20).map { VoicePanelItem(label: "L\($0)", text: "V\($0)") }
    XCTAssertEqual(VoicePanel.copyFields(from: many).count, VoicePanel.maxItems)
  }

  func testAValueLongerThanTheCapIsClipped() {
    let long = String(repeating: "x", count: 9_000)
    let field = VoicePanel.copyFields(from: items([("Body", long)])).first
    XCTAssertEqual(field?.value.count, VoicePanel.maxTextLength)
  }

  // MARK: - Empty and blank

  func testItemsWithNoTextAreDroppedRatherThanShownAsBlankRows() {
    let fields = VoicePanel.copyFields(from: items([("A", "keep"), ("B", ""), ("C", "   ")]))
    XCTAssertEqual(fields.map(\.value), ["keep"])
  }

  func testAPanelOfNothingButBlanksIsNeverPresented() {
    XCTAssertNil(VoicePanel.present(title: "Empty", items: items([("A", ""), ("B", "  ")])))
    XCTAssertFalse(PanelSession.isPresenting)
  }

  // MARK: - Identity

  /// Labels repeat and may be empty, so the row id is positional. Duplicate ids would
  /// make SwiftUI reuse one row's copy button for another's value.
  func testRepeatedAndEmptyLabelsStillProduceUniqueRowIDs() {
    let fields = VoicePanel.copyFields(
      from: items([("Email", "a@b.c"), ("Email", "d@e.f"), ("", "loose")]))
    XCTAssertEqual(Set(fields.map(\.id)).count, 3)
  }

  // MARK: - Shape

  /// A value past one line at the card's width reads as a passage and wraps; a short
  /// labelled value stays on its row.
  func testLongValuesWrapAndShortLabelledOnesDoNot() {
    let fields = VoicePanel.copyFields(
      from: items([("Short", "abc"), ("Long", String(repeating: "y", count: 120))]))
    XCTAssertEqual(fields[0].wraps, false)
    XCTAssertEqual(fields[1].wraps, true)
  }

  func testAnUnlabelledPassageAlwaysWraps() {
    XCTAssertEqual(VoicePanel.copyFields(from: items([("", "hi")])).first?.wraps, true)
  }

  /// Nothing on a voice panel came from the credential store, so masking a value would
  /// hide the answer behind its own label.
  func testVoicePanelValuesAreNeverMasked() {
    XCTAssertEqual(
      VoicePanel.copyFields(from: items([("Key", "abc")])).allSatisfy { !$0.masksValue }, true)
  }

  // MARK: - Text the model actually sends

  func testNewlinesAndUnicodeSurviveIntact() {
    let body = "Line one\nLine two\n\n— Résumé · 日本語 · 🎉"
    XCTAssertEqual(VoicePanel.copyFields(from: items([("", body)])).first?.value, body)
  }

  func testSurroundingWhitespaceIsTrimmedFromValuesAndLabels() {
    let fields = VoicePanel.copyFields(from: items([("  Name  ", "  Yash  ")]))
    XCTAssertEqual(fields.first?.value, "Yash")
    XCTAssertEqual(fields.first?.label, "Name")
  }

  // MARK: - Sequence

  /// Putting up a second panel must leave exactly one on screen.
  func testASecondPanelReplacesTheFirst() {
    XCTAssertEqual(VoicePanel.present(title: "One", items: items([("", "first")])), 1)
    XCTAssertEqual(VoicePanel.present(title: "Two", items: items([("", "second")])), 1)
    XCTAssertEqual(PanelSession.modelVisibleContent(), "second")
  }

  func testClosingThenReopeningReportsHonestly() {
    VoicePanel.present(title: "One", items: items([("", "first")]))
    XCTAssertTrue(VoicePanel.dismiss())
    XCTAssertNil(VoicePanel.reopen(), "a closed panel is forgotten, not parked")
    XCTAssertFalse(VoicePanel.dismiss())
  }
}

/// The caps are silent by default: 20 items become 12 and a 9,000-character value
/// becomes 4,000, with nothing telling the model. It then reports the whole list is on
/// screen while a third of it is not.
final class PanelShortfallTests: XCTestCase {
  private func items(_ pairs: [(String, String)]) -> [VoicePanelItem] {
    pairs.map { VoicePanelItem(label: $0.0, text: $0.1) }
  }

  func testContentThatFitsReportsNoShortfall() {
    XCTAssertNil(VoicePanel.shortfall(from: items([("A", "one"), ("B", "two")])))
  }

  func testTooManyItemsIsNamedWithBothCounts() {
    let many = (1...20).map { VoicePanelItem(label: "L\($0)", text: "V\($0)") }
    let note = VoicePanel.shortfall(from: many)
    XCTAssertEqual(note?.contains("first 12 of 20 items"), true)
  }

  func testAClippedValueIsNamed() {
    let note = VoicePanel.shortfall(
      from: items([("Body", String(repeating: "x", count: 9_000))]))
    XCTAssertEqual(note?.contains("cut to 4000 characters"), true)
  }

  func testEmptyItemsAreNamedSoTheModelKnowsARowVanished() {
    let note = VoicePanel.shortfall(from: items([("A", "keep"), ("B", ""), ("C", "  ")]))
    XCTAssertEqual(note?.contains("2 items had no text"), true)
  }

  /// Blank items are dropped before the cap, so a list of 12 real values plus blanks is
  /// not reported as overflowing.
  func testBlanksDoNotCountTowardTheItemCap() {
    var entries = (1...12).map { VoicePanelItem(label: "L\($0)", text: "V\($0)") }
    entries.append(VoicePanelItem(label: "extra", text: "   "))
    let note = VoicePanel.shortfall(from: entries)
    XCTAssertEqual(note?.contains("items fit"), false, "twelve real values are not an overflow")
    XCTAssertEqual(note?.contains("had no text"), true)
  }
}
