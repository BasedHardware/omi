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

  @MainActor
  func testApplyMovesAFlippedClipViewByTheInsertedHeight() {
    let document = NSView(frame: NSRect(x: 0, y: 0, width: 400, height: 1_000))
    let clip = NSClipView(frame: NSRect(x: 0, y: 0, width: 400, height: 400))
    clip.documentView = document
    let scrollView = NSScrollView(frame: clip.frame)
    scrollView.contentView = clip
    scrollView.documentView = document
    clip.scroll(to: NSPoint(x: 0, y: 40))
    scrollView.reflectScrolledClipView(clip)

    document.setFrameSize(NSSize(width: 400, height: 1_800))
    let applied = ChatTranscriptPrependPreservation.apply(
      to: scrollView,
      snapshot: .init(documentHeight: 1_000, scrollTop: 40)
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
