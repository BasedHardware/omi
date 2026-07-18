import AppKit
import Darwin
import Foundation

/// Prevents a second live copy of the app (same bundle id + launch mode) from
/// running concurrently against the same on-disk state.
///
/// Why this matters: two live instances share `~/Library/Application Support/Omi/`
/// (the Rewind SQLite DB and its `.omi_running` crash flag) and the `UserDefaults`
/// domain keyed by the bundle id. A second instance racing the first can corrupt the
/// database, clobber `lastSessionCleanExit` / auth state, and double-register global
/// shortcuts. LaunchServices usually coalesces a double-click into the running app,
/// but `open -n`, a launch from a second bundle path, a Sparkle relaunch race, or a
/// stale Dock item can each spawn a true duplicate — this guard is the backstop.
///
/// Mechanism: a per-`(bundle id, launch mode)` advisory `flock`. The OS releases the
/// lock automatically when the process dies, so a crashed instance never leaves a
/// stale lock behind (unlike a PID file). Keying on the bundle id keeps parallel
/// *named* dev/test bundles (`com.omi.omi-*`, `com.omi.desktop-dev`) independent of
/// each other and of production. Keying on the launch mode keeps rewind-only mode
/// (`--mode=rewind`) and the full app — which the rewind window intentionally spawns
/// via `open -n` — from evicting one another.
enum SingleInstanceGuard {
  /// Held for the whole process lifetime once acquired; intentionally never closed.
  /// The OS drops the `flock` when the process exits.
  private nonisolated(unsafe) static var lockFileDescriptor: Int32 = -1

  /// If another instance for this `(bundle id, launch mode)` already holds the lock,
  /// foreground it and exit **without** running the normal termination path.
  ///
  /// Call as early as possible in launch — before any database open or `UserDefaults`
  /// write. On conflict this uses `exit(0)` rather than `NSApp.terminate(_:)` on
  /// purpose: `applicationWillTerminate(_:)` writes the shared `lastSessionCleanExit`
  /// flag and tears down the *live* instance's global hotkeys / push-to-talk, so a
  /// duplicate must never run it.
  ///
  /// - Parameters:
  ///   - launchMode: this process's launch mode (full vs rewind-only).
  ///   - isExporting: whether this is a headless view-export run; such runs spawn
  ///     short-lived same-bundle subprocesses on purpose and must be exempt.
  static func enforceSingleInstanceOrExit(launchMode: LaunchMode, isExporting: Bool) {
    guard !isExporting else { return }

    let bundleID = AppBuild.bundleIdentifier
    let path = lockFilePath(bundleID: bundleID, launchMode: launchMode)

    switch acquireExclusiveLock(at: path) {
    case .acquired(let descriptor):
      lockFileDescriptor = descriptor  // hold for the process lifetime

    case .heldByAnotherInstance:
      log(
        "SingleInstanceGuard: another \(bundleID) (\(launchMode.rawValue)) instance is already "
          + "running — foregrounding it and exiting")
      activateExistingInstance(
        bundleID: bundleID,
        ownerProcessIdentifier: lockOwnerProcessIdentifier(at: path))
      exit(0)

    case .failed(let code):
      // Never block launch on a lock-infrastructure failure — fail open, just record it.
      log(
        "SingleInstanceGuard: could not acquire lock at \(path) (errno \(code)); "
          + "continuing without the single-instance guard")
    }
  }

  // MARK: - Pure helpers (unit-tested)

  /// Deterministic lock-file path, unique per `(bundle id, launch mode)`.
  ///
  /// Placed in the per-user temporary directory: it is stable within a login session
  /// and, unlike the app-support data dir, does not depend on the signed-in user id
  /// (which is not yet known this early in launch).
  static func lockFilePath(
    bundleID: String,
    launchMode: LaunchMode,
    directory: String = NSTemporaryDirectory()
  ) -> String {
    let name = "omi-single-instance-\(sanitizeForFilename(bundleID))-\(launchMode.rawValue).lock"
    return (directory as NSString).appendingPathComponent(name)
  }

  /// Collapse anything that is not a safe filename character to `_` so an unusual
  /// bundle id can never escape the intended directory or break the path.
  static func sanitizeForFilename(_ value: String) -> String {
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: ".-_"))
    let scalars = value.unicodeScalars.map { allowed.contains($0) ? Character($0) : "_" }
    return String(scalars)
  }

  /// Result of attempting to take the single-instance lock.
  enum LockResult: Equatable {
    /// Lock acquired; the descriptor must be kept open for the process lifetime.
    case acquired(fileDescriptor: Int32)
    /// Another live instance already holds the lock.
    case heldByAnotherInstance
    /// The lock could not be evaluated (open/flock syscall failed); carries `errno`.
    case failed(errno: Int32)
  }

  /// Try to take an exclusive, non-blocking advisory lock on `path`.
  ///
  /// Returns the open file descriptor on success (the caller keeps it alive),
  /// `.heldByAnotherInstance` when another live process holds it, or `.failed` on any
  /// other syscall error. Exposed for tests.
  static func acquireExclusiveLock(at path: String) -> LockResult {
    let descriptor = path.withCString { open($0, O_CREAT | O_RDWR, 0o600) }
    guard descriptor >= 0 else { return .failed(errno: errno) }

    guard setCloseOnExec(on: descriptor) else {
      let flagErrno = errno
      close(descriptor)
      return .failed(errno: flagErrno)
    }

    if flock(descriptor, LOCK_EX | LOCK_NB) == 0 {
      writeLockOwnerProcessIdentifier(ProcessInfo.processInfo.processIdentifier, to: descriptor)
      return .acquired(fileDescriptor: descriptor)
    }

    let lockErrno = errno
    close(descriptor)
    if lockErrno == EWOULDBLOCK {
      return .heldByAnotherInstance
    }
    return .failed(errno: lockErrno)
  }

  static func descriptorHasCloseOnExec(_ descriptor: Int32) -> Bool {
    let flags = fcntl(descriptor, F_GETFD)
    return flags >= 0 && (flags & FD_CLOEXEC) != 0
  }

  private static func setCloseOnExec(on descriptor: Int32) -> Bool {
    let flags = fcntl(descriptor, F_GETFD)
    guard flags >= 0 else { return false }
    return fcntl(descriptor, F_SETFD, flags | FD_CLOEXEC) == 0
  }

  /// Read the PID written by the lock holder. The lock path is already scoped by
  /// launch mode, so this identifies the same-mode process to foreground.
  static func lockOwnerProcessIdentifier(at path: String) -> pid_t? {
    guard
      let contents = try? String(contentsOfFile: path, encoding: .utf8),
      let firstLine = contents.split(whereSeparator: \.isNewline).first,
      let pid = pid_t(String(firstLine))
    else {
      return nil
    }
    return pid
  }

  private static func writeLockOwnerProcessIdentifier(_ processIdentifier: pid_t, to descriptor: Int32) {
    let contents = "\(processIdentifier)\n"
    contents.withCString { pointer in
      _ = ftruncate(descriptor, 0)
      _ = lseek(descriptor, 0, SEEK_SET)
      _ = Darwin.write(descriptor, pointer, strlen(pointer))
    }
  }

  /// Release a held lock (test helper). Production keeps the descriptor open until the
  /// process exits, at which point the OS releases the lock.
  static func releaseLock(_ descriptor: Int32) {
    guard descriptor >= 0 else { return }
    flock(descriptor, LOCK_UN)
    close(descriptor)
  }

  // MARK: - Effect

  /// Best-effort: bring the lock-owning same-mode instance to the foreground.
  private static func activateExistingInstance(bundleID: String, ownerProcessIdentifier: pid_t?) {
    let myPID = ProcessInfo.processInfo.processIdentifier
    let applications = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
    let existing =
      ownerProcessIdentifier.flatMap { ownerPID in
        applications.first {
          $0.processIdentifier == ownerPID && $0.processIdentifier != myPID && !$0.isTerminated
        }
      }
      ?? applications.first { $0.processIdentifier != myPID && !$0.isTerminated }
    existing?.activate(options: [.activateAllWindows])
  }
}
