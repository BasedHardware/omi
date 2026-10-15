import Foundation

/// Scoped to the flag-on screen pipeline. Child tasks inherit the restriction;
/// existing free-form logs remain identical outside this scope.
enum DesktopLogPrivacy {
  @TaskLocal static var suppressContent = false
  @TaskLocal static var sink: (@Sendable (String) -> Void)?
}

enum ScreenTaskLogging {
  static func completed(results: Int, extracted: Int, searches: Int) {
    DesktopLogPrivacy.$suppressContent.withValue(false) {
      log(
        "Task: Analysis complete - results: \(max(0, min(results, 9))), extracted: \(max(0, min(extracted, 8))), searches: \(max(0, min(searches, 16)))"
      )
    }
  }

  static func failed() {
    DesktopLogPrivacy.$suppressContent.withValue(false) { log("Task: Analysis outcome=failed") }
  }
}
