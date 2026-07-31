import Foundation

/// Runs AppleScript through `osascript` with a bounded timeout.
///
/// Scripts are always passed as a single `-e` program with untrusted values
/// supplied as `argv` arguments. Interpolating agent- or contact-derived text
/// into script source would let a message body containing AppleScript escape
/// into executable code, so callers must use `arguments` for every value that
/// did not come from a literal in this repository.
struct AppleScriptResult: Sendable {
  let output: String
  let errorOutput: String
  let exitCode: Int32
  let timedOut: Bool

  var succeeded: Bool { exitCode == 0 && !timedOut }
}

enum AppleScriptRunnerError: LocalizedError {
  case notPermitted(detail: String)
  case executionFailed(detail: String)

  var errorDescription: String? {
    switch self {
    case .notPermitted(let detail):
      return
        "macOS refused the automation request. Grant Automation permission for the target app in System Settings > Privacy & Security > Automation, then try again. Detail: \(detail)"
    case .executionFailed(let detail):
      return "AppleScript failed: \(detail)"
    }
  }

  var reasonCode: String {
    switch self {
    case .notPermitted: return "automation_not_permitted"
    case .executionFailed: return "execution_failed"
    }
  }
}

enum AppleScriptRunner {
  private static let osascriptURL = URL(fileURLWithPath: "/usr/bin/osascript")

  /// AppleScript reports a TCC denial as error -1743, and a missing target app
  /// as -1728. Both are permission problems the user can act on.
  static func isPermissionError(_ stderr: String) -> Bool {
    stderr.contains("-1743") || stderr.localizedCaseInsensitiveContains("not authorized")
      || stderr.localizedCaseInsensitiveContains("not allowed assistive access")
  }

  static func run(
    script: String,
    arguments: [String] = [],
    timeoutSeconds: TimeInterval = 30
  ) throws -> AppleScriptResult {
    let bounded = max(1, min(timeoutSeconds, 120))
    let result = try PipeProcessRunner.run(
      executableURL: osascriptURL,
      arguments: ["-e", script] + (arguments.isEmpty ? [] : ["--"] + arguments),
      timeoutSeconds: bounded)

    let output = String(data: result.stdout, encoding: .utf8) ?? ""
    let errorOutput = String(data: result.stderr, encoding: .utf8) ?? ""

    if result.timedOut {
      return AppleScriptResult(
        output: output.trimmingCharacters(in: .whitespacesAndNewlines),
        errorOutput: errorOutput.trimmingCharacters(in: .whitespacesAndNewlines),
        exitCode: result.terminationStatus,
        timedOut: true)
    }

    if result.terminationStatus != 0, isPermissionError(errorOutput) {
      throw AppleScriptRunnerError.notPermitted(
        detail: errorOutput.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    return AppleScriptResult(
      output: output.trimmingCharacters(in: .whitespacesAndNewlines),
      errorOutput: errorOutput.trimmingCharacters(in: .whitespacesAndNewlines),
      exitCode: result.terminationStatus,
      timedOut: false)
  }
}
