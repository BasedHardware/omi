import Foundation
import OSLog
import Sentry

enum OmiLogPathResolver {
  static func launchID(processID: Int32) -> String { "pid-\(processID)" }

  /// Owner-only production log directory. `/tmp` is world-writable and sticky, so
  /// an attacker can pre-create the log path there and we may be unable to remove
  /// it; a per-user directory under the home folder removes that race entirely.
  static func productionLogDirectory(
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> String {
    homeDirectory.appendingPathComponent("Library/Logs/Omi", isDirectory: true).path
  }

  static func logPath(
    isNonProduction: Bool,
    bundleIdentifier: String?,
    processID: Int32,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> String {
    // Stable and Omi Beta can run at the same time; interleaving one shared log file
    // would corrupt both transcripts, so each production identity owns its own path.
    guard isNonProduction else {
      let directory = productionLogDirectory(homeDirectory: homeDirectory)
      let name =
        bundleIdentifier == AppBuild.betaProductionBundleIdentifier ? "omi-beta.log" : "omi.log"
      return (directory as NSString).appendingPathComponent(name)
    }
    let rawBundleID = bundleIdentifier?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "unknown"
    let safeBundleID = rawBundleID.replacingOccurrences(
      of: #"[^A-Za-z0-9._-]+"#,
      with: "-",
      options: .regularExpression)
    return "/private/tmp/omi-dev-\(safeBundleID)-\(processID).log"
  }
}

private let logBundleIdentifier = Bundle.main.bundleIdentifier ?? "unknown"
private let logProcessID = getpid()
private let logFile: String = OmiLogPathResolver.logPath(
  isNonProduction: AppBuild.isNonProduction,
  bundleIdentifier: logBundleIdentifier,
  processID: logProcessID)
private let logLaunchID = OmiLogPathResolver.launchID(processID: logProcessID)
/// The on-disk app-log path for the current build. Single source of truth for
/// the log location so callers (feedback export, diagnostics bundle) don't
/// re-derive it. Owner-only permissions are enforced by `ensureLogFileOwnerOnly`.
func omiLogFilePath() -> String { logFile }
func omiLogLaunchID() -> String { logLaunchID }

private let logQueue = DispatchQueue(label: "me.omi.logger", qos: .utility)
private let logFailureDiagnostics = Logger(subsystem: "me.omi.desktop", category: "file-logger")
private let dateFormatter: DateFormatter = {
  let formatter = DateFormatter()
  formatter.dateFormat = "HH:mm:ss.SSS"  // Added milliseconds for perf tracking
  return formatter
}()

/// Appends to a file using Foundation's throwing APIs. Legacy `FileHandle.write(_:)`
/// raises an Objective-C exception for I/O failures, which aborts a Swift process.
enum OmiLogFileAppender {
  /// Open the log for appending without ever following a symlink, creating it
  /// owner-only when absent. `O_NOFOLLOW` refuses a swapped-in link, and the
  /// `fstat` check refuses a FIFO/device/foreign-owned node on the descriptor we
  /// actually hold, so no TOCTOU window exists between the check and the write.
  static func openOwnedRegularFile(at file: URL) throws -> FileHandle {
    let descriptor = file.withUnsafeFileSystemRepresentation { path -> Int32 in
      guard let path else { return -1 }
      return open(path, O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW, 0o600)
    }
    guard descriptor >= 0 else {
      throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
    }
    var info = stat()
    let isOwnedRegularFile =
      fstat(descriptor, &info) == 0
      && (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG)
      && info.st_uid == getuid()
    guard isOwnedRegularFile else {
      close(descriptor)
      throw CocoaError(.fileWriteNoPermission)
    }
    return FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
  }

  static func append(
    _ data: Data,
    to file: URL,
    openFile: (URL) throws -> FileHandle = { try openOwnedRegularFile(at: $0) },
    seekToEnd: (FileHandle) throws -> Void = { try $0.seekToEnd() },
    write: (FileHandle, Data) throws -> Void = { try $0.write(contentsOf: $1) },
    close: (FileHandle) throws -> Void = { try $0.close() }
  ) -> Result<Void, Error> {
    var handle: FileHandle?
    do {
      let openedHandle = try openFile(file)
      handle = openedHandle
      try seekToEnd(openedHandle)
      try write(openedHandle, data)
      try close(openedHandle)
      return .success(())
    } catch {
      // A failed seek or write can leave the handle open; closing is best-effort
      // here because the original I/O failure is the useful diagnostic.
      if let handle {
        try? close(handle)
      }
      return .failure(error)
    }
  }
}

/// Bounds diagnostics when every file write fails (for example, on a full disk).
/// Instances are confined to the serial log queue.
final class OmiLogFileFailureReporter: @unchecked Sendable {
  private var didReport = false
  private let emit: (Error) -> Void

  init(emit: @escaping (Error) -> Void) {
    self.emit = emit
  }

  func report(_ error: Error) {
    guard !didReport else { return }
    didReport = true
    emit(error)
  }
}

/// Records a local-log failure without recursing into the unavailable file logger.
private func reportLogFileWriteFailure(_ error: Error) {
  let nsError = error as NSError
  let diagnostic = "Local log write failed; dropped entry (domain=\(nsError.domain), code=\(nsError.code))"
  logFailureDiagnostics.error("\(diagnostic, privacy: .public)")

  // A breadcrumb accompanies any later crash report without turning expected disk
  // exhaustion into a high-volume Sentry error event.
  guard !AppBuild.isNonProduction else { return }
  let breadcrumb = Breadcrumb(level: .error, category: "file-logger")
  breadcrumb.message = diagnostic
  SentrySDK.addBreadcrumb(breadcrumb)
}

private let logFileFailureReporter = OmiLogFileFailureReporter(emit: reportLogFileWriteFailure)

/// Append data to the log file on a background queue (non-blocking)
private func appendToLogFile(_ line: String) {
  guard let data = (line + "\n").data(using: .utf8) else { return }
  logQueue.async {
    writeToLogFile(data)
  }
}

/// Append data to the log file synchronously (blocks caller until written).
/// Use for critical events that must survive imminent app termination (e.g. Sparkle updates).
private func appendToLogFileSync(_ line: String) {
  guard let data = (line + "\n").data(using: .utf8) else { return }
  logQueue.sync {
    writeToLogFile(data)
  }
}

/// Create the file at `path` (if missing) or tighten an existing file so it is
/// readable and writable only by its owner (0600).
///
/// The log lives in the shared, world-*writable* `/tmp` directory and can contain
/// UIDs, request context, and operational detail, so other local users must not
/// be able to read it (BL-024 / SET-06). Because any local user can pre-create
/// the path, we refuse to adopt anything that isn't a regular file owned by the
/// current user: a symlink, a non-regular node, or someone else's file is removed
/// and recreated owner-only, so we never chmod a symlink target or hand our logs
/// to a file we don't control. Uses `lstat` (not `stat`) so a symlink is judged
/// on its own, not its target. Idempotent and safe to call repeatedly. Returns
/// whether the path is now a regular, owner-only file under our control.
@discardableResult
func ensureLogFileOwnerOnly(atPath path: String) -> Bool {
  let fileManager = FileManager.default
  var info = stat()
  if lstat(path, &info) == 0 {
    let isRegularFile = (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG)
    let isOwnedByUs = info.st_uid == getuid()
    if isRegularFile && isOwnedByUs {
      // Tighten files created by older builds (or a create without attributes).
      return (try? fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: path)) != nil
    }
    // Symlink, non-regular node, or another user's file — never adopt it. In
    // sticky `/tmp` we may be unable to remove an attacker-owned file; then we
    // report failure (the caller keeps retrying) rather than trusting it.
    guard (try? fileManager.removeItem(atPath: path)) != nil else { return false }
  }
  return fileManager.createFile(atPath: path, contents: nil, attributes: [.posixPermissions: 0o600])
}

/// Non-production bundles can run side by side during QA. Keep a private directory per bundle
/// and launch so one app cannot truncate or contaminate another app's diagnostic evidence.
@discardableResult
func ensureLogDirectoryOwnerOnly(atPath path: String) -> Bool {
  let fileManager = FileManager.default
  var info = stat()
  if lstat(path, &info) == 0 {
    let isDirectory = (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFDIR)
    let isOwnedByUs = info.st_uid == getuid()
    guard isDirectory, isOwnedByUs else {
      guard (try? fileManager.removeItem(atPath: path)) != nil else { return false }
      return
        (try? fileManager.createDirectory(
          atPath: path,
          withIntermediateDirectories: false,
          attributes: [.posixPermissions: 0o700])) != nil
    }
    return (try? fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: path)) != nil
  }
  return
    (try? fileManager.createDirectory(
      atPath: path,
      withIntermediateDirectories: false,
      attributes: [.posixPermissions: 0o700])) != nil
}

/// Guards the one-time permission normalization. Mutated only on the serial
/// `logQueue` (every writer hops through it), so it needs no extra locking.
private nonisolated(unsafe) var didEnsureLogFilePermissions = false

private func ensureLogParentDirectories() -> Bool {
  // Non-production logs live as owner-only files directly under private tmp.
  // Do not chmod `/private/tmp`: it is shared infrastructure owned by macOS.
  guard !AppBuild.isNonProduction else { return true }
  let directory = OmiLogPathResolver.productionLogDirectory()
  let fileManager = FileManager.default
  var isDirectory: ObjCBool = false
  if !fileManager.fileExists(atPath: directory, isDirectory: &isDirectory) {
    // `~/Library/Logs` is missing inside a fresh app container, so intermediates
    // must be created; the mode is then applied to the leaf explicitly because
    // `createDirectory` attributes do not repair an existing directory.
    try? fileManager.createDirectory(
      atPath: directory,
      withIntermediateDirectories: true,
      attributes: [.posixPermissions: 0o700])
  }
  return ensureLogDirectoryOwnerOnly(atPath: directory)
}

/// Hard ceiling for the on-disk log. Exceeding it rolls the file over once to
/// `<path>.1` (replacing any previous rollover), so the logger owns at most
/// `2 * maxLogFileBytes` on disk instead of growing for the life of the install.
private let maxLogFileBytes: UInt64 = 8 * 1024 * 1024

/// Bytes appended since the last truncation/rollover. Mutated only on `logQueue`.
private nonisolated(unsafe) var logFileBytesWritten: UInt64 = 0

/// Start each launch from an empty log so a long-lived install cannot accumulate
/// an unbounded transcript, and so the previous run stays available as `.1`.
private func truncateLogFileForLaunch() {
  let fileManager = FileManager.default
  let rollover = logFile + ".1"
  if fileManager.fileExists(atPath: logFile) {
    try? fileManager.removeItem(atPath: rollover)
    try? fileManager.moveItem(atPath: logFile, toPath: rollover)
  }
  logFileBytesWritten = 0
}

private func rotateLogFileIfNeeded(adding byteCount: UInt64) {
  guard logFileBytesWritten + byteCount > maxLogFileBytes else {
    logFileBytesWritten += byteCount
    return
  }
  let fileManager = FileManager.default
  let rollover = logFile + ".1"
  try? fileManager.removeItem(atPath: rollover)
  try? fileManager.moveItem(atPath: logFile, toPath: rollover)
  logFileBytesWritten = byteCount
}

private func logLine(timestamp: String, category: String, message: String) -> String {
  "[\(timestamp)] [\(category)] [bundle_id=\(logBundleIdentifier) pid=\(logProcessID)] \(message)"
}

func writeToLogFile(
  _ data: Data,
  to file: URL,
  appendFile: (Data, URL) -> Result<Void, Error>,
  reportFailure: (Error) -> Void
) {
  if case .failure(let error) = appendFile(data, file) {
    reportFailure(error)
  }
}

/// Shared file-write implementation (must be called on logQueue)
private func writeToLogFile(_ data: Data) {
  if !didEnsureLogFilePermissions {
    // Latch only when normalization actually succeeds, so a transient failure
    // (e.g. a racing create) is retried on the next write instead of leaving
    // the log permanently world-readable.
    let normalized =
      ensureLogParentDirectories()
      && ensureLogFileOwnerOnly(atPath: logFile)
    if normalized {
      truncateLogFileForLaunch()
    }
    didEnsureLogFilePermissions = normalized
  }
  // Fail closed. Normalization returns false when the path is a node we could
  // neither adopt nor remove — writing anyway would stream the whole app log
  // into a file we do not own, or append to whatever the path resolves to.
  guard didEnsureLogFilePermissions else { return }

  rotateLogFileIfNeeded(adding: UInt64(data.count))
  writeToLogFile(
    data,
    to: URL(fileURLWithPath: logFile),
    appendFile: { data, file in OmiLogFileAppender.append(data, to: file) },
    reportFailure: { logFileFailureReporter.report($0) })
}

// MARK: - Performance Logging

/// Log a performance event with timing info - writes to omi.log with [perf] tag
func logPerf(_ message: String, duration: Double? = nil, cpu: Bool = false) {
  let timestamp = dateFormatter.string(from: Date())
  var parts = [logLine(timestamp: timestamp, category: "perf", message: message)]

  if let duration = duration {
    parts.append(String(format: "(%.1fms)", duration * 1000))
  }

  if cpu {
    // Get actual CPU via rusage
    var usage = rusage()
    if getrusage(RUSAGE_SELF, &usage) == 0 {
      let userTime = Double(usage.ru_utime.tv_sec) + Double(usage.ru_utime.tv_usec) / 1_000_000
      let sysTime = Double(usage.ru_stime.tv_sec) + Double(usage.ru_stime.tv_usec) / 1_000_000
      parts.append(String(format: "[cpu: user=%.2fs sys=%.2fs]", userTime, sysTime))
    }
  }

  let line = parts.joined(separator: " ")
  print(line)
  fflush(stdout)

  appendToLogFile(line)
}

/// Timer for measuring operation duration
class PerfTimer {
  private let name: String
  private let start: CFAbsoluteTime
  private let logCPU: Bool

  init(_ name: String, logCPU: Bool = false) {
    self.name = name
    self.start = CFAbsoluteTimeGetCurrent()
    self.logCPU = logCPU
  }

  func stop() {
    let duration = CFAbsoluteTimeGetCurrent() - start
    logPerf(name, duration: duration, cpu: logCPU)
  }

  /// Log intermediate checkpoint without stopping
  func checkpoint(_ label: String) {
    let duration = CFAbsoluteTimeGetCurrent() - start
    logPerf("\(name) → \(label)", duration: duration)
  }
}

/// Measure a block of code and log its duration
func measurePerf<T>(_ name: String, logCPU: Bool = false, _ block: () -> T) -> T {
  let timer = PerfTimer(name, logCPU: logCPU)
  let result = block()
  timer.stop()
  return result
}

/// Async version of measurePerf
func measurePerfAsync<T>(_ name: String, logCPU: Bool = false, _ block: @Sendable () async -> T) async -> T {
  let timer = PerfTimer(name, logCPU: logCPU)
  let result = await block()
  timer.stop()
  return result
}

/// Check if this is a development build
private let isDevBuild: Bool = AppBuild.isNonProduction

/// Write to log file synchronously — guaranteed to persist even if the app terminates immediately after.
/// Use sparingly (blocks the calling thread); prefer `log()` for normal logging.
func logSync(_ message: String) {
  let timestamp = dateFormatter.string(from: Date())
  let line = logLine(timestamp: timestamp, category: "app", message: message)
  print(line)
  fflush(stdout)

  // Free-form messages stay in the local log. Cloud incidents carry a bounded,
  // redacted diagnostic attachment when an error is captured instead.

  appendToLogFileSync(line)
}

/// Write to log file, stdout, and Sentry breadcrumbs
func log(_ message: String) {
  let timestamp = dateFormatter.string(from: Date())
  let line = logLine(timestamp: timestamp, category: "app", message: message)
  print(line)
  fflush(stdout)

  // Free-form messages stay in the local log. Cloud incidents carry a bounded,
  // redacted diagnostic attachment when an error is captured instead.

  appendToLogFile(line)
}

// MARK: - Sentry Error Noise Control

/// Network/IO error codes that are transient and not actionable as Sentry errors:
/// offline, timeouts, dropped connections, cancellations. These dominate event
/// volume (timeouts, "no internet", socket resets) without indicating an app bug.
/// We still write them to the local log + breadcrumbs for debugging context.
func isNonActionableTransient(_ error: Error?) -> Bool {
  guard let error = error else { return false }
  // Swift structured-concurrency cancellation: thrown when a Task/operation is
  // cancelled (assistant stopped, frame superseded). Expected, not an app bug.
  if error is CancellationError { return true }
  // Benign sign-out race: background loops (conversation/advice/goals refresh,
  // upload retries) pass an isSignedIn guard, then the token is cleared mid-cycle
  // and the awaited request throws AuthError.notSignedIn. Expected when the user
  // signs out or runs signed-out — floods Sentry without indicating a bug.
  if case AuthError.notSignedIn = error { return true }
  // Transient AI backend-capacity errors (rate limit, quota, overload, 5xx) from
  // the Gemini proxy, surfaced by the proactive assistants (task/memory/advice/
  // insight extraction) after exhausting retries. Backend overload, not an app bug
  // (OMI-COMPUTER-6JK/6JR/6JM/6NC). Real auth/config/parse errors stay captured.
  if let geminiError = error as? GeminiClient.GeminiClientError,
    geminiError.isTransient || geminiError.isExpectedProductState
  {
    return true
  }
  // Embedding backfills/searches can hit expected backend/product states (trial
  // expired/BYOK required, rate limit, 5xx). Keep those local-only so screenshot
  // backfill loops don't create high-volume Sentry issues.
  if let embeddingError = error as? EmbeddingService.EmbeddingError,
    embeddingError.isNonActionableForSentry
  {
    return true
  }
  // Rewind encoder disk failures wrap the underlying OS error — inspect that so a
  // full/read-only disk ("The file couldn't be saved") is classified below rather
  // than captured as an opaque storage-error cluster (OMI-DESKTOP-28/29).
  let inspected = (error as? RewindError)?.underlyingError ?? error
  let nsError = inspected as NSError
  switch nsError.domain {
  case NSURLErrorDomain:
    // -999 cancelled, -1001 timed out, -1003 host not found, -1004 cannot connect,
    // -1005 connection lost, -1009 offline, -1011 bad server response, -1020 not allowed,
    // -1200 TLS handshake failed (transient secure-connection drop, same as -1005).
    let transient: Set<Int> = [
      NSURLErrorCancelled, NSURLErrorTimedOut, NSURLErrorCannotFindHost,
      NSURLErrorCannotConnectToHost, NSURLErrorNetworkConnectionLost,
      NSURLErrorNotConnectedToInternet, NSURLErrorBadServerResponse,
      NSURLErrorDataNotAllowed, NSURLErrorResourceUnavailable,
      NSURLErrorSecureConnectionFailed,
    ]
    return transient.contains(nsError.code)
  case NSPOSIXErrorDomain:
    // 54 connection reset, 57 socket not connected, 89 operation canceled.
    // 28 ENOSPC (disk full), 69 EDQUOT (over quota), 30 EROFS (read-only fs) —
    // environmental storage exhaustion, not app bugs.
    return [54, 57, 89, 28, 69, 30].contains(nsError.code)
  case NSCocoaErrorDomain:
    // Environmental file-write failures (disk full / read-only volume / no write
    // permission) surface here as "The file couldn't be saved". Not app bugs —
    // keep them as local logs + breadcrumbs instead of Sentry error clusters.
    let storageExhausted: Set<Int> = [
      NSFileWriteOutOfSpaceError,  // 640 — disk full
      NSFileWriteVolumeReadOnlyError,  // 642 — read-only volume
      NSFileWriteNoPermissionError,  // 513 — no write permission
    ]
    if storageExhausted.contains(nsError.code) { return true }
    // Cocoa file errors often wrap a POSIX cause in NSUnderlyingErrorKey.
    if let underlying = nsError.userInfo[NSUnderlyingErrorKey] as? NSError,
      underlying.domain == NSPOSIXErrorDomain,
      [28, 69, 30].contains(underlying.code)
    {
      return true
    }
    return false
  default:
    return false
  }
}

/// Rate-limit identical Sentry error captures. High-frequency loops (per-frame
/// ffmpeg writes, per-cycle assistant failures, repeated DB-constraint hits) can
/// emit the same error thousands of times. We collapse them by a digit-normalized
/// key so a single root cause produces ~one Sentry event per window, not thousands.
private let sentryDedupLock = NSLock()
private nonisolated(unsafe) var sentryLastCaptured: [String: Date] = [:]
private let sentryDedupWindow: TimeInterval = 300  // 5 minutes per unique error

private func shouldCaptureToSentry(_ message: String) -> Bool {
  // Normalize: strip digits so "(3/5)", frame counts, IDs collapse to one key.
  let key = String(message.prefix(160)).replacingOccurrences(
    of: "[0-9]+", with: "#", options: .regularExpression)
  let now = Date()
  sentryDedupLock.lock()
  defer { sentryDedupLock.unlock() }
  if let last = sentryLastCaptured[key], now.timeIntervalSince(last) < sentryDedupWindow {
    return false
  }
  sentryLastCaptured[key] = now
  // Bound the map so it can't grow unbounded over a long session.
  if sentryLastCaptured.count > 500 {
    let cutoff = now.addingTimeInterval(-sentryDedupWindow)
    sentryLastCaptured = sentryLastCaptured.filter { $0.value > cutoff }
  }
  return true
}

/// Privacy-safe, bounded ownership for the shared `logError` Sentry boundary.
///
/// `logError` has hundreds of callers, including failures without an underlying
/// `Error`. Deriving the area from compile-time `#fileID` makes those failures
/// attributable without sending the path, the free-form log message, or user
/// content to Sentry.
struct DesktopErrorTelemetryDescriptor: Equatable {
  let area: String
  let failureClass: String
  let phase: String
  let errorType: String
  let errorDomain: String
  let errorCode: String

  var eventTitle: String {
    "Desktop error [\(area)/\(failureClass)/\(phase)]"
  }

  static func make(error: Error?, fileID: StaticString) -> Self {
    let area = area(for: String(describing: fileID))
    guard let error else {
      return Self(
        area: area,
        failureClass: "missing_underlying_error",
        phase: "runtime",
        errorType: "none",
        errorDomain: "none",
        errorCode: "none")
    }

    let nsError = error as NSError
    let domain = domainFamily(nsError.domain)
    return Self(
      area: area,
      failureClass: "underlying_error",
      phase: "runtime",
      errorType: typeFamily(error, domainFamily: domain),
      errorDomain: domain,
      errorCode: codeBucket(nsError.code, domainFamily: domain))
  }

  private static func area(for fileID: String) -> String {
    let value = fileID.lowercased()
    if value.contains("auth") || value.contains("credential") || value.contains("keychain") {
      return "auth"
    }
    if value.contains("automation") || value.contains("agent") {
      return "automation"
    }
    if value.contains("audio") || value.contains("microphone") || value.contains("transcription") {
      return "audio"
    }
    if value.contains("chat") || value.contains("conversation") {
      return "chat"
    }
    if value.contains("database") || value.contains("storage") || value.contains("sync") {
      return "data"
    }
    if value.contains("diagnostic") || value.contains("logger") || value.contains("resource") {
      return "diagnostics"
    }
    if value.contains("focus") {
      return "focus"
    }
    if value.contains("integration") || value.contains("connector") {
      return "integration"
    }
    if value.contains("memory") || value.contains("rewind") {
      return "memory"
    }
    if value.contains("onboarding") {
      return "onboarding"
    }
    if value.contains("recording") || value.contains("listen") {
      return "recording"
    }
    if value.contains("realtime") || value.contains("voice") {
      return "realtime"
    }
    if value.contains("settings") || value.contains("preference") {
      return "settings"
    }
    if value.contains("appstate") || value.contains("omiapp") || value.contains("system") {
      return "system"
    }
    if value.contains("view") || value.contains("page") || value.contains("window") {
      return "ui"
    }
    return "other"
  }

  private static func domainFamily(_ domain: String) -> String {
    switch domain {
    case NSURLErrorDomain:
      return "url"
    case NSPOSIXErrorDomain:
      return "posix"
    case NSCocoaErrorDomain:
      return "cocoa"
    case NSOSStatusErrorDomain:
      return "osstatus"
    case NSMachErrorDomain:
      return "mach"
    default:
      if domain.hasPrefix("com.omi.") || domain.hasPrefix("me.omi.") {
        return "app"
      }
      return "other"
    }
  }

  private static func typeFamily(_ error: Error, domainFamily: String) -> String {
    if error is DecodingError { return "decoding" }
    if error is URLError { return "url" }
    if error is CocoaError { return "cocoa" }
    if error is POSIXError { return "posix" }
    let reflected = String(reflecting: type(of: error))
    if reflected.hasPrefix("Omi_Computer.") { return "app" }
    return domainFamily
  }

  private static func codeBucket(_ code: Int, domainFamily: String) -> String {
    let allowed: Set<Int>
    switch domainFamily {
    case "url":
      allowed = [-1200, -1020, -1011, -1009, -1005, -1004, -1003, -1001, -999]
    case "posix":
      allowed = [12, 24, 35, 49, 54, 57, 60, 61, 89]
    default:
      return "other"
    }
    return allowed.contains(code) ? String(code) : "other"
  }
}

/// Bounded, non-PII fields that may accompany a shared `logError` Sentry event.
/// Callers must construct these from enums, booleans, and numeric measurements;
/// paths, exception messages, identifiers, and user content do not belong here.
/// `Sendable` because these are produced on whichever actor detected the
/// failure and consumed on another (`AgentRuntimeProcess` -> `@MainActor`
/// ChatProvider). The element type is `any Sendable` rather than `Any` so the
/// compiler enforces the scalar-only contract above at every construction site.
struct DesktopErrorDiagnosticContext: Sendable {
  let values: [String: any Sendable]

  init(_ values: [String: any Sendable]) {
    self.values = values
  }
}

/// Log an error and capture it in Sentry
func logError(
  _ message: String,
  error: Error? = nil,
  context: DesktopErrorDiagnosticContext? = nil,
  fileID: StaticString = #fileID
) {
  let timestamp = dateFormatter.string(from: Date())
  let errorDesc = error?.localizedDescription ?? ""
  let fullMessage = error != nil ? "\(message): \(errorDesc)" : message
  let line = logLine(timestamp: timestamp, category: "error", message: fullMessage)
  print(line)
  fflush(stdout)

  // Keep raw error messages local. Sentry receives a stable incident event below
  // with a redacted local diagnostic attachment.

  // Always persist locally; only the Sentry capture is filtered/rate-limited below.
  appendToLogFile(line)

  let enhancedBetaDiagnostics = BetaEnhancedDiagnosticsConfiguration.isEnabled
  DesktopDiagnosticsManager.shared.recordBetaLogError(
    message: message,
    error: error,
    failureDiagnostics: context?.values,
    enabled: enhancedBetaDiagnostics)

  // Transient network/IO errors (offline, timeouts, cancellations, socket resets)
  // remain local-only. A beta trail entry can join a later authoritative incident,
  // but a transient alone must not create a new Sentry event.
  if isNonActionableTransient(error) { return }

  guard !isDevBuild else { return }

  // Collapse repeated identical errors so a single root cause doesn't flood Sentry.
  guard shouldCaptureToSentry(fullMessage) else { return }

  // Free-form error text stays local. Cloud capture is a stable title plus typed
  // error metadata and a redacted diagnostic attachment.
  let telemetry = DesktopErrorTelemetryDescriptor.make(error: error, fileID: fileID)
  let attachmentURL = DesktopDiagnosticsManager.shared.writeIncidentDiagnosticsAttachment(
    area: telemetry.area,
    failureClass: telemetry.failureClass,
    phase: telemetry.phase)
  defer {
    if let attachmentURL {
      try? FileManager.default.removeItem(at: attachmentURL)
    }
  }
  SentrySDK.capture(message: telemetry.eventTitle) { scope in
    scope.setLevel(.error)
    scope.setTag(value: telemetry.area, key: "diagnostic_area")
    scope.setTag(value: telemetry.failureClass, key: "failure_class")
    scope.setTag(value: telemetry.phase, key: "diagnostic_phase")
    scope.setTag(value: telemetry.errorType, key: "error_type")
    scope.setTag(value: telemetry.errorDomain, key: "error_domain")
    scope.setTag(value: telemetry.errorCode, key: "error_code")
    scope.setContext(
      value: [
        "area": telemetry.area,
        "failure_class": telemetry.failureClass,
        "phase": telemetry.phase,
        "error_type": telemetry.errorType,
        "error_domain": telemetry.errorDomain,
        "error_code": telemetry.errorCode,
      ], key: "app_context")
    if let context {
      scope.setContext(value: context.values, key: "failure_diagnostics")
    }
    if let attachmentURL {
      scope.addAttachment(
        Attachment(
          path: attachmentURL.path,
          filename: "desktop-incident-diagnostics.json",
          contentType: "application/json"))
    }
  }
}
