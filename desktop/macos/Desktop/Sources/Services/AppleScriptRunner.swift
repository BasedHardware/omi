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
  /// UI scripting refused for want of Accessibility, which is a different
  /// System Settings pane and a different grant from Automation.
  case assistiveAccessDenied(detail: String)
  case outputLimitExceeded
  case executionFailed(detail: String)

  var errorDescription: String? {
    switch self {
    case .notPermitted(let detail):
      return
        "macOS refused the automation request. Grant Automation permission for the target app in System Settings > Privacy & Security > Automation, then try again. Detail: \(detail)"
    case .assistiveAccessDenied(let detail):
      return
        "macOS refused UI scripting. Grant Omi Accessibility permission in System Settings > Privacy & Security > Accessibility, then try again. Detail: \(detail)"
    case .outputLimitExceeded:
      return "AppleScript output exceeded the capture limit."
    case .executionFailed(let detail):
      return "AppleScript failed: \(detail)"
    }
  }

  var reasonCode: String {
    switch self {
    case .notPermitted: return "automation_not_permitted"
    case .assistiveAccessDenied: return "accessibility_not_permitted"
    case .outputLimitExceeded: return "output_limit_exceeded"
    case .executionFailed: return "execution_failed"
    }
  }

  /// The grant the user has to change. Reporting Automation for an Accessibility
  /// denial sent the model to `request_permission(type: "automation")`, which
  /// probes Apple Events against System Events, answers "granted", and leaves
  /// the actual block in place — so every retry failed the same way.
  var requiredPermission: String {
    switch self {
    case .notPermitted: return "automation"
    case .assistiveAccessDenied: return "accessibility"
    case .outputLimitExceeded: return "automation"
    case .executionFailed: return "automation"
    }
  }
}

enum AppleScriptRunner {
  private static let osascriptURL = URL(fileURLWithPath: "/usr/bin/osascript")

  /// AppleScript reports a TCC denial as error -1743, and a missing target app
  /// as -1728. Both are permission problems the user can act on.
  static func isPermissionError(_ stderr: String) -> Bool {
    stderr.contains("-1743") || stderr.localizedCaseInsensitiveContains("not authorized")
      || isAssistiveAccessError(stderr)
  }

  /// UI scripting blocked by a missing Accessibility grant, which osascript
  /// reports in its own words and which no amount of Automation permission
  /// will fix.
  static func isAssistiveAccessError(_ stderr: String) -> Bool {
    stderr.localizedCaseInsensitiveContains("not allowed assistive access")
      || stderr.localizedCaseInsensitiveContains("assistive access")
  }

  static func run(
    script: String,
    arguments: [String] = [],
    timeoutSeconds: TimeInterval = 30,
    cancellationCheck: @escaping @Sendable () -> Bool = { false }
  ) throws -> AppleScriptResult {
    let bounded = max(1, min(timeoutSeconds, 120))
    let result: PipeProcessResult
    do {
      result = try PipeProcessRunner.run(
        executableURL: osascriptURL,
        arguments: ["-e", script] + (arguments.isEmpty ? [] : ["--"] + arguments),
        timeoutSeconds: bounded,
        cancellationCheck: cancellationCheck)
    } catch let error as PipeProcessRunnerError {
      // PipeProcessRunner throws on timeout rather than returning a result with
      // timedOut set, so the branch below could never be reached and a hung
      // osascript escaped as a generic failure. That matters most for
      // send_message: Messages may have accepted the send before osascript
      // hung, and a clean-looking failure invites the model to retry and send
      // the message twice. Translated back into the ambiguous result the
      // callers are written to handle.
      if case .timedOut = error {
        return AppleScriptResult(output: "", errorOutput: error.localizedDescription, exitCode: -1, timedOut: true)
      }
      if case .outputLimitExceeded = error {
        throw AppleScriptRunnerError.outputLimitExceeded
      }
      throw error
    }

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
      let detail = errorOutput.trimmingCharacters(in: .whitespacesAndNewlines)
      throw isAssistiveAccessError(errorOutput)
        ? AppleScriptRunnerError.assistiveAccessDenied(detail: detail)
        : AppleScriptRunnerError.notPermitted(detail: detail)
    }

    return AppleScriptResult(
      output: output.trimmingCharacters(in: .whitespacesAndNewlines),
      errorOutput: errorOutput.trimmingCharacters(in: .whitespacesAndNewlines),
      exitCode: result.terminationStatus,
      timedOut: false)
  }
}
