import XCTest

@testable import Omi_Computer

/// Regression test for the FileIndexer fail-open delete: an incremental rescan
/// treated an unreadable directory (permission revoked / transient I/O) as "all
/// its files were deleted" and purged every indexed row under it. The retention
/// diff must exclude files under any directory whose enumeration failed.
final class FileIndexerRetentionTests: XCTestCase {

  func testFilesUnderAFailedDirectoryAreNotDeleted() {
    let existing: Set<String> = [
      "~/Documents/report.pdf",
      "~/Documents/notes/todo.txt",
      "~/Downloads/installer.dmg",
    ]
    // Documents failed to enumerate this scan (so none of its files were seen),
    // but Downloads scanned fine and installer.dmg is genuinely gone.
    let scanned: Set<String> = []
    let protectedPrefixes: Set<String> = ["~/Documents"]

    let toDelete = FileIndexerService.pathsToDelete(
      scannedPaths: scanned,
      existingPaths: existing,
      protectedPrefixes: protectedPrefixes
    )

    XCTAssertEqual(toDelete, ["~/Downloads/installer.dmg"])
    XCTAssertFalse(toDelete.contains("~/Documents/report.pdf"))
    XCTAssertFalse(toDelete.contains("~/Documents/notes/todo.txt"))
  }

  func testSubtreeUnderAnUnstattableDirectoryIsProtected() {
    // A per-item `resourceValues` failure (transient stat/permission error)
    // leaves a subdirectory's type indeterminate. scanDirectory now inserts that
    // directory's relative path into the protected set instead of dropping it, so
    // its entire nested subtree must survive the retention diff even though none
    // of its files were seen this scan.
    let existing: Set<String> = [
      "~/Projects/app/Package.swift",
      "~/Projects/app/Sources/main.swift",
      "~/Projects/app/Sources/util/helper.swift",
      "~/Projects/other/readme.md",
    ]
    let scanned: Set<String> = ["~/Projects/other/readme.md"]
    let protectedPrefixes: Set<String> = ["~/Projects/app"]

    let toDelete = FileIndexerService.pathsToDelete(
      scannedPaths: scanned,
      existingPaths: existing,
      protectedPrefixes: protectedPrefixes
    )

    XCTAssertTrue(toDelete.isEmpty, "nested files under the unstattable dir must not be purged")
  }

  func testGenuinelyRemovedFilesAreStillDeleted() {
    // No failed directories: a previously-indexed file not seen this scan is a
    // real deletion and must be purged.
    let existing: Set<String> = ["~/Documents/old.txt", "~/Documents/kept.txt"]
    let scanned: Set<String> = ["~/Documents/kept.txt"]

    let toDelete = FileIndexerService.pathsToDelete(
      scannedPaths: scanned,
      existingPaths: existing,
      protectedPrefixes: []
    )

    XCTAssertEqual(toDelete, ["~/Documents/old.txt"])
  }

  func testPrefixMatchDoesNotOverMatchSiblingDirectories() {
    // "~/Documents" must not protect "~/Documents2/..." (prefix must be a path
    // boundary, not a raw string prefix).
    let existing: Set<String> = ["~/Documents2/file.txt"]
    let scanned: Set<String> = []
    let protectedPrefixes: Set<String> = ["~/Documents"]

    let toDelete = FileIndexerService.pathsToDelete(
      scannedPaths: scanned,
      existingPaths: existing,
      protectedPrefixes: protectedPrefixes
    )

    XCTAssertEqual(toDelete, ["~/Documents2/file.txt"])
  }
}
