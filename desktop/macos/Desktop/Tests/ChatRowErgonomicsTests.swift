import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The transcript can never host native selection (FC-selection-overlay-layout-loop:
/// PR #10834 reopened it in Omi Beta 0.12.146). The remedy the boundary names is a
/// separate non-live reading surface, and this is it — one AppKit text view over
/// one message, mounted only when the reader asks for it.
@MainActor
final class ChatSelectableTextSurfaceTests: XCTestCase {
  private func textView(for text: String) throws -> NSTextView {
    let scrollView = OmiSelectableTextView.makeScrollView(text: text)
    return try XCTUnwrap(scrollView.documentView as? NSTextView)
  }

  func testTheReadingSurfaceIsSelectableButNotEditable() throws {
    let view = try textView(for: "They arrive on Saturday.")
    XCTAssertTrue(view.isSelectable, "selecting is the entire point of this surface")
    XCTAssertFalse(view.isEditable, "a transcript row is not a document the reader may rewrite")
  }

  func testTheReadingSurfaceCarriesTheMessageItWasOpenedFor() throws {
    XCTAssertEqual(try textView(for: "Booking confirmed.").string, "Booking confirmed.")
  }

  /// It is one AppKit view, so a rebuild replaces a string rather than
  /// installing another selection overlay.
  func testUpdatingTheSurfaceReplacesTheTextInPlace() throws {
    let scrollView = OmiSelectableTextView.makeScrollView(text: "first")
    let first = try XCTUnwrap(scrollView.documentView as? NSTextView)

    OmiSelectableTextView.apply(text: "second", to: scrollView)

    XCTAssertIdentical(scrollView.documentView as? NSTextView, first)
    XCTAssertEqual(first.string, "second")
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
      rootView: ChatBubble(message: message, app: nil, showsOmiMark: true, onRate: { _ in })
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
