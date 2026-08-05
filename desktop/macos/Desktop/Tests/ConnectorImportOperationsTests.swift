import XCTest

@testable import Omi_Computer

@MainActor
final class ConnectorImportOperationsTests: XCTestCase {
  private func outcome(
    hasReadableUserFileTarget: Bool = true,
    didCompleteSuccessfully: Bool = true,
    indexedFileCount: Int = 0,
    deniedUserFolders: [String] = []
  ) -> ChatToolExecutor.LocalFileScanOutcome {
    ChatToolExecutor.LocalFileScanOutcome(
      hasReadableUserFileTarget: hasReadableUserFileTarget,
      didCompleteSuccessfully: didCompleteSuccessfully,
      indexedFileCount: indexedFileCount,
      deniedUserFolders: deniedUserFolders,
      summaryText: "# File Scan Results — agent-facing markdown that must never surface in the UI"
    )
  }

  /// Password-protected notes are invisible to the Notes export, so an import
  /// that silently covers fewer notes than the library holds must say so.
  func testAppleNotesCompletionMessageNamesSkippedLockedNotes() {
    XCTAssertEqual(
      ConnectorImportOperations.appleNotesCompletionMessage(
        importedNotes: 832, totalNotes: 834, memoryCount: 40, lockedSkipped: 2),
      "Imported 832 of 834 notes and saved 40 memories. (2 locked notes skipped)"
    )
    XCTAssertEqual(
      ConnectorImportOperations.appleNotesCompletionMessage(
        importedNotes: 3, totalNotes: 4, memoryCount: 12, lockedSkipped: 1),
      "Imported 3 of 4 notes and saved 12 memories. (1 locked note skipped)"
    )
  }

  func testAppleNotesCompletionMessageOmitsTheLockedClauseWhenNothingWasSkipped() {
    XCTAssertEqual(
      ConnectorImportOperations.appleNotesCompletionMessage(
        importedNotes: 0, totalNotes: 834, memoryCount: 0, lockedSkipped: 0),
      "Imported 0 of 834 notes and saved 0 memories."
    )
  }

  func testStatusLineWithoutNewItems() {
    let line = ConnectorImportOperations.localFilesStatusLine(
      indexedCount: 12, newItems: 0, deniedFolders: [])
    XCTAssertEqual(line, "Indexed 12 files.")
  }

  func testStatusLineWithNewItemsAndGroupedFormatting() {
    let line = ConnectorImportOperations.localFilesStatusLine(
      indexedCount: 1849, newItems: 37, deniedFolders: [])
    XCTAssertEqual(line, "Indexed \(1849.formatted()) files (+37 new).")
  }

  func testStatusLineMentionsDeniedFoldersWithoutTildePrefix() {
    let line = ConnectorImportOperations.localFilesStatusLine(
      indexedCount: 12, newItems: 3, deniedFolders: ["~/Downloads", "~/Documents"])
    XCTAssertEqual(
      line,
      "Indexed 12 files (+3 new). Some folders weren't scanned (Downloads, Documents) — grant access and reindex."
    )
  }

  func testFailureLineForIncompleteScan() {
    let line = ConnectorImportOperations.localFilesFailureLine(
      for: outcome(didCompleteSuccessfully: false))
    XCTAssertEqual(line, "Indexing couldn't complete. Try again.")
  }

  func testFailureLineForNoAccessListsDeniedFolders() {
    let line = ConnectorImportOperations.localFilesFailureLine(
      for: outcome(
        hasReadableUserFileTarget: false, deniedUserFolders: ["~/Downloads", "~/Desktop"]))
    XCTAssertEqual(
      line,
      "Omi couldn't access your folders (Downloads, Desktop). Click Allow on the macOS permission dialogs, then reindex."
    )
  }

  func testFailureLineForNoAccessWithoutFolderList() {
    let line = ConnectorImportOperations.localFilesFailureLine(
      for: outcome(hasReadableUserFileTarget: false))
    XCTAssertEqual(
      line,
      "Omi couldn't access your folders. Click Allow on the macOS permission dialogs, then reindex."
    )
  }

  func testMemoryLogImportedMapsToSuccessWithCounts() {
    let outcome = ConnectorImportOperations.memoryLogOutcome(
      .imported(memories: 14, profileSummary: "profile"), source: .claude)
    guard case .success(let result, let message) = outcome else {
      return XCTFail("expected success, got \(outcome)")
    }
    XCTAssertEqual(result.memoryCount, 14)
    XCTAssertEqual(result.newItems, 14)
    XCTAssertEqual(message, "Imported 14 memories from Claude.")
  }

  func testMemoryLogNoDurableMemoriesGuidesPasteFix() {
    let outcome = ConnectorImportOperations.memoryLogOutcome(.noDurableMemories, source: .chatgpt)
    guard case .failure(let message, failureClass: _) = outcome else {
      return XCTFail("expected failure, got \(outcome)")
    }
    XCTAssertEqual(
      message,
      "No durable memories found in that text. Make sure you pasted ChatGPT's full response, then import again."
    )
  }

  func testMemoryLogFailedGuidesRetry() {
    let outcome = ConnectorImportOperations.memoryLogOutcome(.failed, source: .claude)
    guard case .failure(let message, failureClass: _) = outcome else {
      return XCTFail("expected failure, got \(outcome)")
    }
    XCTAssertEqual(message, "The import couldn't run. Try again.")
  }

  func testCompletedXImportWithZeroPostsDoesNotSayStillRunning() {
    let message = ConnectorImportOperations.xImportCompletionMessage(
      handle: "omi",
      posts: 0,
      memories: 0,
      importCompleted: true
    )

    XCTAssertEqual(message, "Connected to X as @omi. No posts or bookmarks were ready to import.")
  }

  func testIncompleteXImportWithZeroPostsStillShowsRunningFallback() {
    let message = ConnectorImportOperations.xImportCompletionMessage(
      handle: "omi",
      posts: 0,
      memories: 0,
      importCompleted: false
    )

    XCTAssertEqual(message, "Connected to X as @omi. Import is still running; check back shortly.")
  }

  func testCompletedXImportWithPostsIncludesHandleAndMemoryClause() {
    XCTAssertEqual(
      ConnectorImportOperations.xImportCompletionMessage(
        handle: "omi",
        posts: 12,
        memories: 3,
        importCompleted: true
      ),
      "Imported 12 posts from @omi — 3 memories added. View them in Memories."
    )
    XCTAssertEqual(
      ConnectorImportOperations.xImportCompletionMessage(
        handle: "omi",
        posts: 12,
        memories: 0,
        importCompleted: true
      ),
      "Imported 12 posts from @omi. Extracted memories appear in Memories."
    )
  }

  func testUserFacingLinesNeverContainAgentSummary() {
    let scan = outcome(hasReadableUserFileTarget: false, deniedUserFolders: ["~/Downloads"])
    let failure = ConnectorImportOperations.localFilesFailureLine(for: scan)
    XCTAssertFalse(failure.contains("File Scan Results"))
    XCTAssertFalse(failure.contains("#"))
  }
}
