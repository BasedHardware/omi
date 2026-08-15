import Foundation

/// Distinguishes "Full Disk Access was never granted" from "it was granted, but
/// this process started before the grant".
///
/// macOS binds Full Disk Access at process start. A user who grants it while Omi
/// is running stays locked out until Omi relaunches, and an in-process read
/// fails exactly as it would if they had never granted anything. Telling those
/// two apart is the difference between "open System Settings" — which the user
/// has already done, and will do again to no effect — and "quit and reopen Omi".
///
/// The test is to ask a *child* process the same question. A freshly spawned
/// child inherits the current grant rather than the one in force when Omi
/// launched, so child-can-read plus parent-cannot means the grant is live and
/// only the restart is missing.
enum FullDiskAccessProbe {
  enum State: String, Sendable {
    /// This process can read protected paths right now.
    case granted
    /// The grant exists but predates nothing — the running process missed it.
    case grantedPendingRestart = "granted_pending_restart"
    /// No grant.
    case denied
  }

  /// Probed in order; the first one that exists decides. All three are
  /// TCC-protected, so any of them answers the question.
  static func protectedPaths(home: URL = FileManager.default.homeDirectoryForCurrentUser) -> [URL] {
    [
      home.appendingPathComponent("Library/Messages"),
      home.appendingPathComponent("Library/Mail"),
      home.appendingPathComponent("Library/Safari"),
    ]
  }

  static func currentState(
    fileManager: FileManager = .default,
    home: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> State {
    let candidates = protectedPaths(home: home)

    for path in candidates {
      // `access` rather than `fileExists`: for a protected path TCC makes
      // fileExists report false for a directory that is really there, which
      // would end the loop on the wrong answer.
      guard MessagesReaderService.storePresence(atPath: path.path) != .absent else { continue }
      if (try? fileManager.contentsOfDirectory(atPath: path.path)) != nil { return .granted }
      return childCanRead(path) ? .grantedPendingRestart : .denied
    }

    // Nothing protected exists to test against — a very fresh account. Nothing
    // is being withheld, so there is nothing to ask the user for.
    return .granted
  }

  /// Whether a newly spawned process can list `path`.
  ///
  /// Any failure answers "no". A probe that cannot run must not be able to tell
  /// the user a grant exists when it does not — that would send them to restart
  /// the app and land them back where they started.
  private static func childCanRead(_ path: URL) -> Bool {
    do {
      let result = try PipeProcessRunner.run(
        executableURL: URL(fileURLWithPath: "/bin/ls"),
        arguments: [path.path],
        timeoutSeconds: 5)
      return result.terminationStatus == 0
    } catch {
      return false
    }
  }
}
