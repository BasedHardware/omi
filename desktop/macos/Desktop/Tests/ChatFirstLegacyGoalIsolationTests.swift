import Foundation
import XCTest

@testable import Omi_Computer

final class ChatFirstLegacyGoalIsolationTests: XCTestCase {
  func testChatFirstSourcesDoNotReferenceLegacyGoalModels() throws {
    // omi-test-quality: source-inspection -- static contract: cohort-only goal
    // UI must never add a legacy-goal dependency, which behavior tests cannot
    // observe after a forbidden fallback has already been compiled in.
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let chatFirstDirectory = testsDirectory
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/ChatFirst")
    let forbiddenSymbols = ["GoalStorage", "GoalRecord", "GoalsHistoryPage"]
    let files = FileManager.default.enumerator(
      at: chatFirstDirectory,
      includingPropertiesForKeys: [.isRegularFileKey]
    )?.compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" } ?? []

    for file in files {
      let source = try String(contentsOf: file, encoding: .utf8)
      for symbol in forbiddenSymbols {
        XCTAssertFalse(source.contains(symbol), "\(file.lastPathComponent) must not depend on \(symbol)")
      }
    }
  }
}
