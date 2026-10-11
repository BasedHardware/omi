import Foundation
import XCTest

@testable import Omi_Computer

final class ScreenTaskLoggingTests: XCTestCase {
  private final class Messages: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String] = []
    func append(_ value: String) { lock.withLock { values.append(value) } }
    var captured: [String] { lock.withLock { values } }
  }

  func testNewPathSuppressesContentAndErrorsIncludingInheritedTasksButKeepsBoundedSummary() async {
    let messages = Messages()
    await DesktopLogPrivacy.$sink.withValue({ messages.append($0) }) {
      await DesktopLogPrivacy.$suppressContent.withValue(true) {
        log("Task: Analysis complete - context: private-screen-context")
        log("Task: [95% conf.] private-task-title")
        logSync("private-window-title")
        logPerf("private-search-query")
        logError("private-model-response", error: NSError(domain: "private-error", code: 1))
        await Task { log("private-observation-child") }.value
        ScreenTaskLogging.completed(results: 100, extracted: 100, searches: 100)
        ScreenTaskLogging.failed()
      }
    }
    XCTAssertEqual(
      messages.captured,
      [
        "Task: Analysis complete - results: 9, extracted: 8, searches: 16",
        "Task: Analysis outcome=failed",
      ])
  }

  func testFreeFormLoggerPrivacyScopeDoesNotLeak() {
    let messages = Messages()
    DesktopLogPrivacy.$sink.withValue({ messages.append($0) }) {
      DesktopLogPrivacy.$suppressContent.withValue(true) { log("suppressed") }
      DesktopLogPrivacy.$suppressContent.withValue(false) {
        log("Task: Analysis complete - context: legacy-context")
        log("Task: [95% conf.] legacy-title")
      }
      log("outside-scope")
    }
    XCTAssertEqual(
      messages.captured,
      [
        "Task: Analysis complete - context: legacy-context", "Task: [95% conf.] legacy-title", "outside-scope",
      ])
  }
}
