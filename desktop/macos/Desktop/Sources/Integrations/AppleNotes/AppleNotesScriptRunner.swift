import AppKit
import Foundation

/// Raw result of one `osascript` invocation. Stdout stays `Data` so a large
/// export is decoded once, by the parser, rather than round-tripped to `String`.
struct AppleNotesScriptResult: Sendable {
  let stdout: Data
  let stderr: String
  let terminationStatus: Int32
  let duration: TimeInterval
}

/// Transport-level failures. These are deliberately *not* `AppleNotesReaderError`
/// so the service — not the transport — owns classification.
enum AppleNotesScriptRunnerError: Error, Equatable {
  case timedOut(seconds: TimeInterval)
  case launchFailed(reason: String)
}

/// Seam for running a JXA script. Injecting this is what lets the reader's
/// behavior (which scripts run, how many times, with what bounds) be asserted
/// without an Apple Events round trip.
protocol AppleNotesScriptRunning: Sendable {
  func run(
    source: String,
    environment: [String: String],
    timeoutSeconds: TimeInterval
  ) async throws -> AppleNotesScriptResult
}

/// Production runner: `/usr/bin/osascript -l JavaScript -e <source>` executed
/// through the shared `PipeProcessRunner`, which already provides off-main
/// execution, a hard timeout, and a SIGKILL grace period.
struct OSAScriptRunner: AppleNotesScriptRunning {
  private static let executableURL = URL(fileURLWithPath: "/usr/bin/osascript")

  func run(
    source: String,
    environment: [String: String],
    timeoutSeconds: TimeInterval
  ) async throws -> AppleNotesScriptResult {
    do {
      let result = try await Task.detached(priority: .utility) {
        try PipeProcessRunner.run(
          executableURL: Self.executableURL,
          arguments: ["-l", "JavaScript", "-e", source],
          environment: environment,
          timeoutSeconds: timeoutSeconds
        )
      }.value
      return AppleNotesScriptResult(
        stdout: result.stdout,
        stderr: String(data: result.stderr, encoding: .utf8) ?? "",
        terminationStatus: result.terminationStatus,
        duration: result.duration
      )
    } catch let error as PipeProcessRunnerError {
      switch error {
      case .timedOut(let seconds, _):
        throw AppleNotesScriptRunnerError.timedOut(seconds: seconds)
      case .launchFailed(let message):
        throw AppleNotesScriptRunnerError.launchFailed(reason: message)
      case .pipeDrainTimedOut(let streams):
        throw AppleNotesScriptRunnerError.launchFailed(reason: "pipe drain timed out (\(streams))")
      }
    }
  }
}

// MARK: - Automation gate

/// Passive automation-permission probe plus the minimum app lifecycle needed to
/// address Apple Events at Notes.
protocol AppleNotesAutomationGate: Sendable {
  /// TCC status for automating Notes. `noErr` granted, `-1743` denied, `-1744`
  /// undetermined, `-600` target not running. Must never prompt.
  func permissionStatus() async -> OSStatus
  func isNotesRunning() async -> Bool
  /// Launches Notes without stealing focus. Returns false when it could not start.
  func launchNotesInBackground() async -> Bool
}

struct SystemAppleNotesAutomationGate: AppleNotesAutomationGate {
  static let notesBundleIdentifier = "com.apple.Notes"

  /// Mirrors `AppState.queryAutomationPermissionStatus()`: create a bundle-id
  /// address descriptor and ask TCC with `askUserIfNeeded: false`, which never
  /// shows a dialog. The app ships `com.apple.security.automation.apple-events`
  /// and `NSAppleEventsUsageDescription` and is not sandboxed, so this probe is
  /// answerable without sending a real event.
  func permissionStatus() async -> OSStatus {
    var addressDesc = AEAddressDesc()
    return Self.notesBundleIdentifier.withCString { cString in
      AECreateDesc(typeApplicationBundleID, cString, strlen(cString), &addressDesc)
      let result = AEDeterminePermissionToAutomateTarget(
        &addressDesc,
        typeWildCard,
        typeWildCard,
        false  // askUserIfNeeded = false → never shows a dialog
      )
      AEDisposeDesc(&addressDesc)
      return result
    }
  }

  func isNotesRunning() async -> Bool {
    !NSRunningApplication.runningApplications(withBundleIdentifier: Self.notesBundleIdentifier).isEmpty
  }

  func launchNotesInBackground() async -> Bool {
    guard
      let applicationURL = NSWorkspace.shared.urlForApplication(
        withBundleIdentifier: Self.notesBundleIdentifier)
    else {
      return false
    }
    return await Self.openWithoutActivating(applicationURL)
  }

  /// `NSWorkspace.OpenConfiguration` is not `Sendable`, so it is built and used
  /// entirely on the main actor rather than crossing an isolation boundary.
  @MainActor
  private static func openWithoutActivating(_ applicationURL: URL) async -> Bool {
    let configuration = NSWorkspace.OpenConfiguration()
    configuration.activates = false
    configuration.hides = true
    configuration.addsToRecentItems = false
    do {
      _ = try await NSWorkspace.shared.openApplication(at: applicationURL, configuration: configuration)
      return true
    } catch {
      log("AppleNotesReaderService: background launch of Notes failed: \(error.localizedDescription)")
      return false
    }
  }
}
