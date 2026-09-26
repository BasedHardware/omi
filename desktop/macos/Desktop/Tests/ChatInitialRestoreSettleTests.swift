import XCTest

@testable import Omi_Computer

/// The stability check that lets the initial restore's settling passes stop
/// before the ladder's end. The restore completes on the first pair of
/// consecutive passes that measure the same laid-out document height; a
/// document that is still reflowing, or that has not laid out at all, must
/// never settle early.
final class ChatInitialRestoreSettleTests: XCTestCase {
  func testFirstPassNeverSettles() {
    XCTAssertFalse(
      ChatInitialRestoreSettle.hasSettled(
        previousPassDocumentHeight: nil,
        currentDocumentHeight: 4_000))
  }

  func testPreLayoutZeroHeightsNeverSettle() {
    // Both passes ran before the scroll view resolved: a zero height is not a
    // laid-out document, and settling there would strand the restore.
    XCTAssertFalse(
      ChatInitialRestoreSettle.hasSettled(
        previousPassDocumentHeight: 0,
        currentDocumentHeight: 0))
    XCTAssertFalse(
      ChatInitialRestoreSettle.hasSettled(
        previousPassDocumentHeight: nil,
        currentDocumentHeight: 0))
  }

  func testStableHeightSettles() {
    XCTAssertTrue(
      ChatInitialRestoreSettle.hasSettled(
        previousPassDocumentHeight: 4_000,
        currentDocumentHeight: 4_000))
  }

  func testSubPointDriftSettles() {
    XCTAssertTrue(
      ChatInitialRestoreSettle.hasSettled(
        previousPassDocumentHeight: 4_000,
        currentDocumentHeight: 4_000 + ChatInitialRestoreSettle.stabilityEpsilon))
  }

  func testReflowingDocumentDoesNotSettle() {
    XCTAssertFalse(
      ChatInitialRestoreSettle.hasSettled(
        previousPassDocumentHeight: 4_000,
        currentDocumentHeight: 4_201))
  }

  func testGrowingPastZeroDoesNotSettle() {
    // First real height after a pre-layout pass: nothing stable to compare.
    XCTAssertFalse(
      ChatInitialRestoreSettle.hasSettled(
        previousPassDocumentHeight: 0,
        currentDocumentHeight: 4_000))
  }

  func testDelaysAreStrictlyIncreasing() {
    // The ladder's last pass completes the restore unconditionally (the call
    // site marks the final index), so a document that never holds still for
    // two consecutive passes still reaches `.completed`. That contract needs
    // the schedule to progress: each pass must fire strictly later than the
    // one before it, and the ladder must never be empty.
    XCTAssertFalse(ChatInitialRestoreSettle.delays.isEmpty)
    for (earlier, later) in zip(ChatInitialRestoreSettle.delays, ChatInitialRestoreSettle.delays.dropFirst()) {
      XCTAssertLessThan(earlier, later)
    }
  }
}
