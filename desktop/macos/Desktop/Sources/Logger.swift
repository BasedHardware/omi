import Darwin
import Foundation
import Sentry

private let logFile: String = {
  let isDev = AppBuild.isNonProduction
  return isDev ? "/tmp/omi-dev.log" : "/tmp/omi.log"
}()
/// The on-disk app-log path for the current build. Single source of truth for
/// the log location so callers (feedback export, diagnostics bundle) don't
/// re-derive it. Owner-only permissions are enforced by `ensureLogFileOwnerOnly`.
func omiLogFilePath() -> String { logFile }

private let logQueue = DispatchQueue(label: "me.omi.logger", qos: .utility)
private let logFileFailureCooldown: TimeInterval = 60
private var lastLogFileFailure: Date?
private let dateFormatter: DateFormatter = {
  let formatter = DateFormatter()
  formatter.dateFormat = "HH:mm:ss.SSS"  // Added milliseconds for perf tracking
  return formatter
}()

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

/// Guards the one-time permission normalization. Mutated only on the serial
/// `logQueue` (every writer hops through it), so it needs no extra locking.
private var didEnsureLogFilePermissions = false

/// Shared file-write implementation (must be called on logQueue)
private func writeToLogFile(_ data: Data) {
  if !didEnsureLogFilePermissions {
    // Latch only when normalization actually succeeds, so a transient failure
    // (e.g. a racing create) is retried on the next write instead of leaving
    // the log permanently world-readable.
    didEnsureLogFilePermissions = ensureLogFileOwnerOnly(atPath: logFile)
  }
  switch LocalLogFileWriter.append(data, to: logFile) {
  case .success:
    return
  case .failure(let error):
    reportLogFileFailure(error)
  }
}

private func reportLogFileFailure(_ error: LocalLogFileWriteError) {
  let now = Date()
  if let lastLogFileFailure, now.timeIntervalSince(lastLogFileFailure) < logFileFailureCooldown {
    return
  }
  lastLogFileFailure = now
  writeToStandardError("[logger] failed to append \(logFile): \(error.description)\n")
}

private func writeToStandardError(_ message: String) {
  message.withCString { buffer in
    var remaining = strlen(buffer)
    var pointer = UnsafeRawPointer(buffer)
    while remaining > 0 {
      let written = Darwin.write(STDERR_FILENO, pointer, remaining)
      if written > 0 {
        pointer = pointer.advanced(by: written)
        remaining -= written
      } else if written == -1 && errno == EINTR {
        continue
      } else {
        return
      }
    }
  }
}

enum LocalLogFileWriteError: Error, Equatable, CustomStringConvertible {
  case openFailed(errno: Int32)
  case writeFailed(errno: Int32)
  case closeFailed(errno: Int32)

  var description: String {
    switch self {
    case .openFailed(let code):
      return "open failed: \(Self.message(for: code))"
    case .writeFailed(let code):
      return "write failed: \(Self.message(for: code))"
    case .closeFailed(let code):
      return "close failed: \(Self.message(for: code))"
    }
  }

  private static func message(for code: Int32) -> String {
    String(cString: strerror(code))
  }
}

enum LocalLogFileWriter {
  static func append(_ data: Data, to path: String) -> Result<Void, LocalLogFileWriteError> {
    let fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, S_IRUSR | S_IWUSR)
    guard fd >= 0 else {
      return .failure(.openFailed(errno: errno))
    }

    let writeFailure = data.withUnsafeBytes { rawBuffer -> LocalLogFileWriteError? in
      guard let baseAddress = rawBuffer.baseAddress else { return nil }
      var pointer = baseAddress
      var remaining = rawBuffer.count

      while remaining > 0 {
        let written = Darwin.write(fd, pointer, remaining)
        if written > 0 {
          pointer = pointer.advanced(by: written)
          remaining -= written
        } else if written == -1 && errno == EINTR {
          continue
        } else {
          return .writeFailed(errno: errno)
        }
      }
      return nil
    }

    let closeStatus = close(fd)
    if let writeFailure {
      return .failure(writeFailure)
    }
    guard closeStatus == 0 else {
      return .failure(.closeFailed(errno: errno))
    }
    return .success(())
  }
}

// MARK: - Performance Logging

/// Log a performance event with timing info - writes to omi.log with [perf] tag
func logPerf(_ message: String, duration: Double? = nil, cpu: Bool = false) {
  let timestamp = dateFormatter.string(from: Date())
  var parts = ["[\(timestamp)] [perf] \(message)"]

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
func measurePerfAsync<T>(_ name: String, logCPU: Bool = false, _ block: () async -> T) async -> T {
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
  let line = "[\(timestamp)] [app] \(message)"
  print(line)
  fflush(stdout)

  if !isDevBuild {
    let breadcrumb = Breadcrumb(level: .info, category: "app")
    breadcrumb.message = message
    SentrySDK.addBreadcrumb(breadcrumb)
  }

  appendToLogFileSync(line)
}

/// Write to log file, stdout, and Sentry breadcrumbs
func log(_ message: String) {
  let timestamp = dateFormatter.string(from: Date())
  let line = "[\(timestamp)] [app] \(message)"
  print(line)
  fflush(stdout)

  if !isDevBuild {
    let breadcrumb = Breadcrumb(level: .info, category: "app")
    breadcrumb.message = message
    SentrySDK.addBreadcrumb(breadcrumb)
  }

  appendToLogFile(line)
}

// MARK: - Sentry Error Noise Control

/// Network/IO error codes that are transient and not actionable as Sentry errors:
/// offline, timeouts, dropped connections, cancellations. These dominate event
/// volume (timeouts, "no internet", socket resets) without indicating an app bug.
/// We still write them to the local log + breadcrumbs for debugging context.
private func isNonActionableTransient(_ error: Error?) -> Bool {
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
     geminiError.isTransient || geminiError.isExpectedProductState { return true }
  // Embedding backfills/searches can hit expected backend/product states (trial
  // expired/BYOK required, rate limit, 5xx). Keep those local-only so screenshot
  // backfill loops don't create high-volume Sentry issues.
  if let embeddingError = error as? EmbeddingService.EmbeddingError,
     embeddingError.isNonActionableForSentry { return true }
  let nsError = error as NSError
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
    return [54, 57, 89].contains(nsError.code)
  default:
    return false
  }
}

/// Rate-limit identical Sentry error captures. High-frequency loops (per-frame
/// ffmpeg writes, per-cycle assistant failures, repeated DB-constraint hits) can
/// emit the same error thousands of times. We collapse them by a digit-normalized
/// key so a single root cause produces ~one Sentry event per window, not thousands.
private let sentryDedupLock = NSLock()
private var sentryLastCaptured: [String: Date] = [:]
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

/// Log an error and capture it in Sentry
func logError(_ message: String, error: Error? = nil) {
  let timestamp = dateFormatter.string(from: Date())
  let errorDesc = error?.localizedDescription ?? ""
  let fullMessage = error != nil ? "\(message): \(errorDesc)" : message
  let line = "[\(timestamp)] [error] \(fullMessage)"
  print(line)
  fflush(stdout)

  if !isDevBuild {
    let breadcrumb = Breadcrumb(level: .error, category: "error")
    breadcrumb.message = fullMessage
    SentrySDK.addBreadcrumb(breadcrumb)
  }

  // Always persist locally; only the Sentry capture is filtered/rate-limited below.
  appendToLogFile(line)

  // Transient network/IO errors (offline, timeouts, cancellations, socket resets)
  // are not actionable bugs — keep them as local logs + breadcrumbs only.
  if isNonActionableTransient(error) { return }

  guard !isDevBuild else { return }

  // Collapse repeated identical errors so a single root cause doesn't flood Sentry.
  guard shouldCaptureToSentry(fullMessage) else { return }

  // Capture error context in Sentry without passing the raw Swift Error object.
  // Some Swift-native error payloads can crash inside Sentry's reflection path.
  if let error = error {
    let nsError = error as NSError
    let errorType = String(reflecting: type(of: error))
    SentrySDK.capture(message: fullMessage) { scope in
      scope.setLevel(.error)
      scope.setContext(
        value: [
          "message": message,
          "error_type": errorType,
          "error_domain": nsError.domain,
          "error_code": nsError.code,
          "localized_description": errorDesc,
        ], key: "app_context")
    }
  } else {
    SentrySDK.capture(message: fullMessage) { scope in
      scope.setLevel(.error)
    }
  }
}
