import AppKit
import XCTest

@testable import Omi_Computer

final class ChatTranscriptPrependPreservationTests: XCTestCase {
  func testRestoredScrollTopAddsTheInsertedHeight() {
    XCTAssertEqual(
      ChatTranscriptPrependPreservation.restoredScrollTop(
        previousDocumentHeight: 1_000,
        previousScrollTop: 40,
        newDocumentHeight: 1_800
      ),
      840
    )
  }

  func testAShorterDocumentDoesNotPullTheReaderUp() {
    XCTAssertEqual(
      ChatTranscriptPrependPreservation.restoredScrollTop(
        previousDocumentHeight: 1_000,
        previousScrollTop: 40,
        newDocumentHeight: 900
      ),
      40
    )
  }

  func testTheLoadMoreClickDoesNotAbortRestore() {
    XCTAssertFalse(
      ChatTranscriptPrependPreservation.shouldAbortRestoreBecauseUserIsScrolling(
        userIsScrolling: true,
        isPreservingPrepend: true
      )
    )
    XCTAssertTrue(
      ChatTranscriptPrependPreservation.shouldAbortRestoreBecauseUserIsScrolling(
        userIsScrolling: true,
        isPreservingPrepend: false
      )
    )
    XCTAssertFalse(
      ChatTranscriptPrependPreservation.shouldAbortRestoreBecauseUserIsScrolling(
        userIsScrolling: false,
        isPreservingPrepend: true
      )
    )
  }

  func testCancellingRestoreReleasesTheLatchOnlyAfterTheAnchorIsConsumed() {
    XCTAssertFalse(
      ChatTranscriptPrependPreservation.shouldReleasePreserveLatchAfterCancellingRestore(
        isPreservingPrepend: true,
        prependAnchorId: "still-loading"
      ),
      "the load-more click still holds the anchor; clearing the latch would abort restore"
    )
    XCTAssertTrue(
      ChatTranscriptPrependPreservation.shouldReleasePreserveLatchAfterCancellingRestore(
        isPreservingPrepend: true,
        prependAnchorId: nil
      )
    )
    XCTAssertFalse(
      ChatTranscriptPrependPreservation.shouldReleasePreserveLatchAfterCancellingRestore(
        isPreservingPrepend: false,
        prependAnchorId: nil
      )
    )
  }

  @MainActor
  func testApplyMovesANonFlippedClipViewByTheInsertedHeight() {
    assertApplyMovesClipView(
      document: NSView(frame: NSRect(x: 0, y: 0, width: 400, height: 1_000))
    )
  }

  @MainActor
  func testApplyMovesAFlippedClipViewByTheInsertedHeight() {
    assertApplyMovesClipView(
      document: FlippedDocumentView(frame: NSRect(x: 0, y: 0, width: 400, height: 1_000))
    )
  }

  @MainActor
  private func assertApplyMovesClipView(document: NSView) {
    let clip = NSClipView(frame: NSRect(x: 0, y: 0, width: 400, height: 400))
    clip.documentView = document
    let scrollView = NSScrollView(frame: clip.frame)
    scrollView.contentView = clip
    scrollView.documentView = document
    let initialTop: CGFloat = 40
    let originY =
      document.isFlipped
      ? initialTop
      : document.frame.height - initialTop - clip.bounds.height
    clip.scroll(to: NSPoint(x: 0, y: originY))
    scrollView.reflectScrolledClipView(clip)

    document.setFrameSize(NSSize(width: 400, height: 1_800))
    let applied = ChatTranscriptPrependPreservation.apply(
      to: scrollView,
      snapshot: .init(documentHeight: 1_000, scrollTop: initialTop)
    )

    XCTAssertTrue(applied)
    XCTAssertEqual(
      ChatScrollLiveEdge.topBasedScrollOffset(
        clipOriginY: clip.bounds.origin.y,
        viewportHeight: clip.bounds.height,
        documentHeight: document.frame.height,
        isDocumentFlipped: document.isFlipped
      ),
      840,
      accuracy: 1
    )
  }
}

private final class FlippedDocumentView: NSView {
  override var isFlipped: Bool { true }
}
