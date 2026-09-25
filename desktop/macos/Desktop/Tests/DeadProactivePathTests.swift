import XCTest

final class DeadProactivePathTests: XCTestCase {
  func testProductionSourcesDoNotRestoreUnreachableProactiveWriters() throws {
    let sourcesRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources", isDirectory: true)
    let sourceFiles = recursiveSwiftFiles(in: sourcesRoot)
    XCTAssertFalse(sourceFiles.isEmpty)

    var violations: [String] = []
    for file in sourceFiles {
      // omi-test-quality: source-inspection -- static contract: forbids restoring the unreachable PTT Gemini cleanup actor and the unused FocusSessionRecord writer; neither had a production caller at the SCA-335 branch point, so a behavioral test cannot observe them coming back
      let source = try String(contentsOf: file, encoding: .utf8)
      let relative = file.path.replacingOccurrences(of: sourcesRoot.path + "/", with: "")
      if source.contains("PTTTranscriptCleanupService") {
        violations.append("\(relative): PTTTranscriptCleanupService")
      }
      if source.contains("struct FocusSessionRecord") {
        violations.append("\(relative): struct FocusSessionRecord")
      }
      if relative.hasSuffix("Rewind/Services/RewindIndexer.swift"), source.contains("focusStatus") {
        violations.append("\(relative): RewindIndexer focusStatus writer")
      }
    }

    XCTAssertEqual(violations, [])

    let settingsControls = try sourceContents(
      relativePath: "MainWindow/Pages/Settings/Components/SettingsContentView+Controls.swift",
      in: sourcesRoot)
    XCTAssertTrue(settingsControls.contains("getTotalFocusSessionCount"))
    let settingsAdvanced = try sourceContents(
      relativePath: "MainWindow/Pages/Settings/Sections/SettingsContentView+Advanced.swift",
      in: sourcesRoot)
    XCTAssertTrue(settingsAdvanced.contains("Focus Sessions"))
  }

  private func sourceContents(relativePath: String, in sourcesRoot: URL) throws -> String {
    // omi-test-quality: source-inspection -- static contract: Settings must keep reading leftover focus_sessions rows so removing the dead writer does not hide historical counts
    try String(contentsOf: sourcesRoot.appendingPathComponent(relativePath), encoding: .utf8)
  }

  private func recursiveSwiftFiles(in directory: URL) -> [URL] {
    let enumerator = FileManager.default.enumerator(
      at: directory,
      includingPropertiesForKeys: nil,
      options: [.skipsHiddenFiles])
    return enumerator?.compactMap { element in
      guard let file = element as? URL, file.pathExtension == "swift" else { return nil }
      return file
    } ?? []
  }
}
