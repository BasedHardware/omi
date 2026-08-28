import XCTest

@testable import Omi_Computer

/// The panel is one card serving every shape of answer a voice request can produce, so
/// what earns wrapping, what gets dropped, and where the bounds sit are the contract.
@MainActor
final class VoicePanelItemMappingTests: XCTestCase {
  func testUnlabeledItemWraps() {
    let fields = VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Hey David.")])
    XCTAssertEqual(fields.count, 1)
    XCTAssertTrue(fields[0].wraps)
    XCTAssertEqual(fields[0].label, "")
  }

  func testShortLabeledValueStaysOnOneLine() {
    let fields = VoicePanel.copyFields(from: [VoicePanelItem(label: "Region", text: "us-east-1")])
    XCTAssertFalse(fields[0].wraps)
  }

  func testLongLabeledValueWraps() {
    let long = String(repeating: "a", count: 200)
    let fields = VoicePanel.copyFields(from: [VoicePanelItem(label: "Bio", text: long)])
    XCTAssertTrue(fields[0].wraps)
  }

  /// The model is asked to show these values, so hiding one behind bullets would hide
  /// the answer. Masking belongs to the connector card, where the value is a secret the
  /// user already owns.
  func testValuesAreNeverMasked() {
    let fields = VoicePanel.copyFields(from: [
      VoicePanelItem(label: "Secret key", text: "wJalrXUtnFEMI")
    ])
    XCTAssertFalse(fields[0].masksValue)
    XCTAssertEqual(fields[0].displayValue, "wJalrXUtnFEMI")
  }

  func testEmptyTextIsDropped() {
    let fields = VoicePanel.copyFields(from: [
      VoicePanelItem(label: "Key", text: "   "),
      VoicePanelItem(label: "Region", text: "us-east-1"),
    ])
    XCTAssertEqual(fields.map(\.label), ["Region"])
  }

  func testDuplicateLabelsKeepUniqueIDs() {
    let fields = VoicePanel.copyFields(from: [
      VoicePanelItem(label: "Key", text: "one"),
      VoicePanelItem(label: "Key", text: "two"),
    ])
    XCTAssertEqual(Set(fields.map(\.id)).count, 2)
  }

  func testItemCountAndTextAreBounded() {
    let many = (0..<40).map { VoicePanelItem(label: "f\($0)", text: "v\($0)") }
    XCTAssertEqual(VoicePanel.copyFields(from: many).count, VoicePanel.maxItems)

    let huge = VoicePanelItem(label: "", text: String(repeating: "b", count: 10_000))
    XCTAssertEqual(
      VoicePanel.copyFields(from: [huge])[0].value.count, VoicePanel.maxTextLength)
  }
}

/// Provider arguments arrive as loose JSON; an entry with nothing to copy is not a row.
final class VoicePanelToolArgumentTests: XCTestCase {
  func testItemsDecodeWithOptionalLabels() {
    let items = RealtimeHubController.voicePanelItems([
      ["label": "Region", "text": "us-east-1"],
      ["text": "Hey David."],
    ])
    XCTAssertEqual(items.count, 2)
    XCTAssertEqual(items[0].label, "Region")
    XCTAssertEqual(items[1].label, "")
  }

  func testEntriesWithoutTextAreDropped() {
    let items = RealtimeHubController.voicePanelItems([
      ["label": "Region"],
      ["label": "Key", "text": "  "],
      ["text": "kept"],
    ])
    XCTAssertEqual(items.map(\.text), ["kept"])
  }

  func testNonArrayArgumentsYieldNoItems() {
    XCTAssertTrue(RealtimeHubController.voicePanelItems(nil).isEmpty)
    XCTAssertTrue(RealtimeHubController.voicePanelItems("items").isEmpty)
  }
}

/// A wrapped value is as tall as its text; the card that never had one must measure
/// exactly as it did before wrapping existed.
@MainActor
final class FieldCopyCardSizingTests: XCTestCase {
  private func height(wrapped: [Int]) -> CGFloat {
    CloudConnectorGuidanceOverlay.fieldCopyCardSize(
      title: "Draft", subtitle: "Copy it with the button.",
      fieldCount: wrapped.count, wrappedCharacterCounts: wrapped
    ).height
  }

  func testCompactCardIsUnchangedByTheWrappingParameter() {
    let compact = CloudConnectorGuidanceOverlay.fieldCopyCardSize(
      title: "AWS", subtitle: "Copy each with its button.", fieldCount: 3)
    XCTAssertEqual(compact.height, 96 + 3 * 30)
  }

  func testWrappedValueGrowsWithItsText() {
    XCTAssertGreaterThan(height(wrapped: [600]), height(wrapped: [40]))
  }

  func testWrappedCardStopsAtTheOfferedHeight() {
    let bounded = CloudConnectorGuidanceOverlay.fieldCopyCardSize(
      title: "Draft", subtitle: "Copy it with the button.", fieldCount: 1,
      maxHeight: 300, wrappedCharacterCounts: [8_000])
    XCTAssertEqual(bounded.height, 300)
  }
}
