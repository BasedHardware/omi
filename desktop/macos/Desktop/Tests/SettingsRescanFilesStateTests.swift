import XCTest

@testable import Omi_Computer

/// Settings ▸ Advanced ▸ Troubleshooting ▸ Rescan Files reports what the scan actually did.
///
/// The row previously advertised that it would "update your AI profile" — which the re-index it
/// triggers has never done — and then said nothing at all afterwards, so a press was
/// indistinguishable from a no-op. These pin the two halves that made it dishonest: the claim, and
/// the fact that a finished scan reports a result the user can read.
final class SettingsRescanFilesStateTests: XCTestCase {
  func testIdleSubtitleDoesNotPromiseAnAIProfileUpdate() {
    let subtitle = FileRescanState.idle.subtitle
    XCTAssertFalse(subtitle.localizedCaseInsensitiveContains("profile"), subtitle)
    XCTAssertTrue(subtitle.localizedCaseInsensitiveContains("re-index"), subtitle)
  }

  func testScanningSubtitleDiffersFromIdle() {
    XCTAssertNotEqual(FileRescanState.scanning.subtitle, FileRescanState.idle.subtitle)
  }

  func testFinishedSubtitleReportsTheIndexedCount() {
    XCTAssertTrue(
      FileRescanState.finished(indexedFiles: 42).subtitle.contains("42"),
      FileRescanState.finished(indexedFiles: 42).subtitle
    )
    XCTAssertTrue(
      FileRescanState.finished(indexedFiles: 1).subtitle.contains("1 file"),
      FileRescanState.finished(indexedFiles: 1).subtitle
    )
  }

  /// `FileIndexerService.getIndexedFileCount()` answers 0 both for an empty index and for a
  /// database it could not open, so zero must not be published as a counted result.
  func testFinishedWithNoCountDoesNotStateAZeroFileTotal() {
    let subtitle = FileRescanState.finished(indexedFiles: 0).subtitle
    XCTAssertFalse(subtitle.contains("0"), subtitle)
    XCTAssertNotEqual(subtitle, FileRescanState.scanning.subtitle)
    XCTAssertNotEqual(subtitle, FileRescanState.idle.subtitle)
  }
}
