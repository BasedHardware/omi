import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

/// **Selection lives in the transcript now.**
///
/// It used to live in a popover beside the row, because SwiftUI's own selection
/// is barred here for good (FC-selection-overlay-layout-loop: PR #10834
/// reopened it in Omi Beta 0.12.146). The bar is on `SelectionOverlay`, not on
/// selecting — an `NSTextView` *is* one selection, with no per-`Text` overlay to
/// install — so the words themselves are the surface now, on the reader's own
/// turns as much as Omi's.
@MainActor
final class ChatSelectableProseTests: XCTestCase {
  private func attributed(
    _ markdown: String,
    style: OmiMarkdown.Style = .assistant,
    citations: Set<Int> = []
  ) throws -> NSAttributedString {
    try XCTUnwrap(
      ChatSelectableProse.attributedString(
        markdown: markdown, style: style, fontSize: 14, fontScale: 1, citationOrdinals: citations))
  }

  private func attribute(
    _ key: NSAttributedString.Key, of text: NSAttributedString, at substring: String
  ) throws -> Any? {
    let range = try XCTUnwrap(
      text.string.range(of: substring), "\(substring) is not in \(text.string)")
    return text.attribute(
      key, at: text.string.distance(from: text.string.startIndex, to: range.lowerBound), effectiveRange: nil)
  }

  func testTheProseViewIsSelectableAndNotEditable() {
    let view = ChatProseTextView()
    view.isEditable = false
    view.isSelectable = true
    XCTAssertTrue(view.isSelectable, "selecting the answer is the entire point")
    XCTAssertFalse(view.isEditable, "a transcript row is not a document the reader may rewrite")
  }

  /// Both senders. A user turn was never selectable by any means — the popover
  /// was reachable from the hover strip, and a user row has no hover strip.
  func testBothSendersRenderSelectableProse() throws {
    for style in [OmiMarkdown.Style.assistant, .user] {
      let text = try attributed("Booking confirmed.", style: style)
      XCTAssertEqual(text.string, "Booking confirmed.")
    }
  }

  func testEmphasisSurvivesTheCrossingIntoAppKit() throws {
    let text = try attributed("Do **YC application** with *Nick* and run `agentctl`.")
    XCTAssertEqual(text.string, "Do YC application with Nick and run agentctl.")

    let bold = try XCTUnwrap(try attribute(.font, of: text, at: "YC application") as? NSFont)
    XCTAssertTrue(
      bold.fontDescriptor.symbolicTraits.contains(.bold), "bold must not flatten into body text")

    let italic = try XCTUnwrap(try attribute(.font, of: text, at: "Nick") as? NSFont)
    XCTAssertTrue(italic.fontDescriptor.symbolicTraits.contains(.italic))

    let code = try XCTUnwrap(try attribute(.font, of: text, at: "agentctl") as? NSFont)
    XCTAssertTrue(
      code.fontDescriptor.symbolicTraits.contains(.monoSpace),
      "inline code keeps its monospace face now that it is text rather than a button")
    XCTAssertNotNil(
      try attribute(.backgroundColor, of: text, at: "agentctl"), "and keeps its chip wash")
  }

  /// The marker stays inside the one text view, so it is draggable and
  /// copyable — which the chip button never was — and still opens its source.
  func testAKnownCitationMarkerBecomesAnOpenableLink() throws {
    let text = try attributed("You favoured the clearer concept. [1]", citations: [1])
    let link = try XCTUnwrap(try attribute(.link, of: text, at: "[1]") as? URL)
    XCTAssertEqual(ChatSelectableProse.citationOrdinal(from: link), 1)
  }

  /// Ordinals run to four digits, and the model also writes the kind alongside
  /// them. Both used to fall outside a narrower pattern and render as dead text.
  func testWideAndKindPrefixedMarkersAreLinkedToo() throws {
    let wide = try attributed("You preferred the clearer direction. [5004]", citations: [5004])
    XCTAssertEqual(
      ChatSelectableProse.citationOrdinal(
        from: try XCTUnwrap(try attribute(.link, of: wide, at: "[5004]") as? URL)),
      5004)

    let prefixed = try attributed("You prefer mornings. [memory 5023]", citations: [5023])
    XCTAssertEqual(
      ChatSelectableProse.citationOrdinal(
        from: try XCTUnwrap(try attribute(.link, of: prefixed, at: "[memory 5023]") as? URL)),
      5023)
  }

  /// A bracketed number the turn has no source for is prose, not a control.
  func testAnUnknownBracketedNumberIsLeftAsWords() throws {
    let text = try attributed("Section [4] of the lease.", citations: [1])
    XCTAssertNil(try attribute(.link, of: text, at: "[4]"))
  }

  func testProseKeepsTheTranscriptsOwnLeading() throws {
    let text = try attributed("One line.")
    let paragraph = try XCTUnwrap(
      try attribute(.paragraphStyle, of: text, at: "One") as? NSParagraphStyle)
    XCTAssertEqual(paragraph.lineSpacing, OmiMarkdownContent.chatLineSpacing(fontSize: 14))
  }
}

/// A turn cut off by a barge-in used to render exactly like a finished one.
final class ChatTurnFailurePresentationTests: XCTestCase {
  private func failed(_ text: String, blocks: [ChatContentBlock] = []) -> ChatMessage {
    ChatMessage(
      id: "t", text: text, sender: .ai, isStreaming: false, contentBlocks: blocks,
      journalStatus: .failed)
  }

  func testAFailedTurnWithPartialTextIsMarkedTruncated() {
    XCTAssertEqual(
      ChatTurnFailurePresentation.of(failed("They arrive on Saturday,")), .truncatedAnswer)
  }

  func testAFailedTurnWithNothingToShowKeepsTheStamp() {
    XCTAssertEqual(ChatTurnFailurePresentation.of(failed("")), .emptyTurnStamp)
  }

  func testAFailedTurnThatOnlyProducedBlocksIsStillMarkedTruncated() {
    XCTAssertEqual(
      ChatTurnFailurePresentation.of(failed("", blocks: [.text(id: "b", text: "partial")])),
      .truncatedAnswer)
  }

  func testACompletedTurnIsNotAFailure() {
    let done = ChatMessage(
      id: "t", text: "All set.", sender: .ai, isStreaming: false, journalStatus: .completed)
    XCTAssertEqual(ChatTurnFailurePresentation.of(done), .none)
  }

  /// A turn still streaming has not failed yet, whatever the last journal row said.
  func testAStreamingRowIsNeverPresentedAsFailed() {
    let live = ChatMessage(
      id: "t", text: "They arrive on Sat", sender: .ai, isStreaming: true, journalStatus: .failed)
    XCTAssertEqual(ChatTurnFailurePresentation.of(live), .none)
  }
}

/// Each push-to-talk press mints a distinct journal turn, so the same short
/// answer three times is three legitimate rows. Collapsing them is a *display*
/// decision, and it has to be narrow enough not to eat a real repeated answer.
final class ChatShortDuplicateCollapseTests: XCTestCase {
  private let shortAnswer =
    "They arrive on Saturday, and the booking is already confirmed."

  private func msg(
    _ id: String, _ text: String, sender: ChatSender = .ai, offset: TimeInterval = 0,
    status: KernelJournalTurnStatus? = nil
  ) -> ChatMessage {
    ChatMessage(
      id: id, text: text, createdAt: Date(timeIntervalSince1970: 1_700_000_000 + offset),
      sender: sender, journalStatus: status)
  }

  func testConsecutiveIdenticalShortAnswersCollapse() {
    let messages = [
      msg("1", shortAnswer),
      msg("2", shortAnswer, offset: 30),
      msg("3", shortAnswer, offset: 60),
    ]
    XCTAssertEqual(ChatMessageDeduplicator.duplicateIDs(in: messages), ["2", "3"])
  }

  /// The same sentence answering a different question later is not a stutter.
  func testIdenticalShortAnswersSeparatedByAnotherTurnDoNotCollapse() {
    let messages = [
      msg("1", shortAnswer),
      msg("q", "and the flight?", sender: .user, offset: 10),
      msg("2", shortAnswer, offset: 20),
    ]
    XCTAssertTrue(ChatMessageDeduplicator.duplicateIDs(in: messages).isEmpty)
  }

  func testIdenticalShortAnswersFarApartInTimeDoNotCollapse() {
    let messages = [msg("1", shortAnswer), msg("2", shortAnswer, offset: 3_600)]
    XCTAssertTrue(ChatMessageDeduplicator.duplicateIDs(in: messages).isEmpty)
  }

  func testTheSameWordsFromDifferentSendersDoNotCollapse() {
    let messages = [msg("1", shortAnswer, sender: .user), msg("2", shortAnswer, offset: 5)]
    XCTAssertTrue(ChatMessageDeduplicator.duplicateIDs(in: messages).isEmpty)
  }

  /// A barge-in fragment followed by the answer it was cut out of.
  func testAFailedFragmentCollapsesIntoTheCompleteAnswerBelowIt() {
    let messages = [
      msg("fragment", "They arrive on Saturday, and the", offset: 0, status: .failed),
      msg("full", shortAnswer, offset: 20),
    ]
    XCTAssertEqual(ChatMessageDeduplicator.duplicateIDs(in: messages), ["fragment"])
  }

  /// The observed screenshot: the answer twice, then a third try cut off.
  func testATruncatedRetryAfterACompleteAnswerCollapses() {
    let messages = [
      msg("1", shortAnswer),
      msg("2", shortAnswer, offset: 20),
      msg("3", "They arrive on Saturday,", offset: 40, status: .failed),
    ]
    XCTAssertEqual(ChatMessageDeduplicator.duplicateIDs(in: messages), ["2", "3"])
  }

  /// A one-word "Done." repeated is not a stutter worth a chip.
  func testVeryShortRepeatsStayBelowTheFloor() {
    let messages = [msg("1", "Done."), msg("2", "Done.", offset: 5)]
    XCTAssertTrue(ChatMessageDeduplicator.duplicateIDs(in: messages).isEmpty)
  }
}

/// The rhythm complaint, measured on the real views rather than argued about.
@MainActor
final class ChatTranscriptRowRhythmTests: XCTestCase {
  private static let width: CGFloat = 520

  private func message(
    _ id: String, _ text: String, sender: ChatSender = .ai,
    blocks: [ChatContentBlock] = []
  ) -> ChatMessage {
    ChatMessage(
      id: id, text: text, createdAt: Date(timeIntervalSince1970: 1_700_000_000), sender: sender,
      isStreaming: false, isSynced: true, contentBlocks: blocks)
  }

  private func rowHeight(_ message: ChatMessage) -> CGFloat {
    NSHostingView(
      rootView: ChatBubble(message: message, app: nil, showsOmiMark: true, onRate: { _, _ in })
        .frame(width: Self.width)
    ).fittingSize.height
  }

  /// **The complaint, in numbers.** Two consecutive one-line answers sat roughly
  /// 100 device pixels apart: a 28 pt reserved hover band *plus* a full 16 pt
  /// inter-exchange gap, on top of a row that reserved 32 pt for a mark it did
  /// not need. The band is separation; the gap must not be charged twice.
  func testTwoConsecutiveShortAnswersAreNotSeparatedByHalfALineOfNothing() {
    let first = message("a0", "They arrive on Saturday.")
    let second = message("a1", "The booking is confirmed.")
    let gap = ChatTranscriptLayout.spacing(from: first, to: second)
    let deadSpaceUnderTheRow = ChatBubbleMetadataControlMetrics.bandHeight + gap

    XCTAssertLessThanOrEqual(
      deadSpaceUnderTheRow, 32,
      "a settled answer must not float in more than 64 device pixels of nothing")
    XCTAssertEqual(gap, ChatTranscriptLayout.afterMetadataBandRowSpacing)
  }

  /// A card-only row has nothing to copy or rate and stamps its own time, so it
  /// reserves no band — which is what left the memory card floating.
  func testACardOnlyRowReservesNoMetadataBand() {
    let card = message(
      "card", "", blocks: [.discoveryCard(id: "b", title: "Memory", summary: "summary", fullText: "full")])
    XCTAssertEqual(ChatBubbleMetadataBand.of(card), .hidden)
    XCTAssertEqual(
      ChatTranscriptLayout.spacing(from: card, to: message("a", "next")),
      ChatTranscriptLayout.regularRowSpacing,
      "with no band of its own the card takes the ordinary exchange gap")
  }

  /// A row with nothing at all still keeps its timestamp — that stamp is all it
  /// has to say it happened.
  func testAnEmptyCompletedRowStillKeepsItsTimestamp() {
    XCTAssertEqual(ChatBubbleMetadataBand.of(message("empty", "")), .timestampOnly)
  }

  /// The 32 pt reservation exists for an empty streaming reply, whose own
  /// content has no height. On a settled row it only centred short content in a
  /// box taller than itself.
  func testASettledShortRowDoesNotReserveTheStreamingMarkHeight() {
    let settled = message("a0", "Yes.")
    let streaming = ChatMessage(
      id: "a1", text: "", sender: .ai, isStreaming: true, isSynced: false)

    XCTAssertGreaterThanOrEqual(rowHeight(streaming), ChatOmiMarkPlacement.reservedRowHeight - 1)
    XCTAssertLessThan(
      rowHeight(settled),
      ChatOmiMarkPlacement.reservedRowHeight + ChatBubbleMetadataControlMetrics.bandHeight,
      "a one-line answer plus its band must not be padded out to the mark's box plus its band")
  }
}
