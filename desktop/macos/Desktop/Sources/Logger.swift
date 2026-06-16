import Foundation
import Sentry

private let logFile: String = {
  let isDev = AppBuild.isNonProduction
  return isDev ? "/tmp/omi-dev.log" : "/tmp/omi.log"
}()
private let logQueue = DispatchQueue(label: "me.omi.logger", qos: .utility)
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

/// Shared file-write implementation (must be called on logQueue)
private func writeToLogFile(_ data: Data) {
  if FileManager.default.fileExists(atPath: logFile) {
    if let handle = FileHandle(forWritingAtPath: logFile) {
      handle.seekToEndOfFile()
      handle.write(data)
      handle.closeFile()
    }
  } else {
    FileManager.default.createFile(atPath: logFile, contents: data)
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

  let breadcrumb = Breadcrumb(level: .info, category: "app")
  breadcrumb.message = message
  SentrySDK.addBreadcrumb(breadcrumb)

  appendToLogFileSync(line)
}

/// Write to log file, stdout, and Sentry breadcrumbs
func log(_ message: String) {
  let timestamp = dateFormatter.string(from: Date())
  let line = "[\(timestamp)] [app] \(message)"
  print(line)
  fflush(stdout)

  // Add breadcrumb to Sentry for context in crash reports (now enabled for dev builds too)
  let breadcrumb = Breadcrumb(level: .info, category: "app")
  breadcrumb.message = message
  SentrySDK.addBreadcrumb(breadcrumb)

  appendToLogFile(line)
}

// MARK: - Sentry Error Noise Control

/// Network/IO error codes that are transient and not actionable as Sentry errors:
/// offline, timeouts, dropped connections, cancellations. These dominate event
/// volume (timeouts, "no internet", socket resets) without indicating an app bug.
/// We still write them to the local log + breadcrumbs for debugging context.
private func isNonActionableTransient(_ error: Error?) -> Bool {
  guard let error = error else { return false }
  let nsError = error as NSError
  switch nsError.domain {
  case NSURLErrorDomain:
    // -999 cancelled, -1001 timed out, -1003 host not found, -1004 cannot connect,
    // -1005 connection lost, -1009 offline, -1011 bad server response, -1020 not allowed.
    let transient: Set<Int> = [
      NSURLErrorCancelled, NSURLErrorTimedOut, NSURLErrorCannotFindHost,
      NSURLErrorCannotConnectToHost, NSURLErrorNetworkConnectionLost,
      NSURLErrorNotConnectedToInternet, NSURLErrorBadServerResponse,
      NSURLErrorDataNotAllowed, NSURLErrorResourceUnavailable,
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

  // Add error breadcrumb and capture in Sentry (now enabled for dev builds too)
  let breadcrumb = Breadcrumb(level: .error, category: "error")
  breadcrumb.message = fullMessage
  SentrySDK.addBreadcrumb(breadcrumb)

  // Always persist locally; only the Sentry capture is filtered/rate-limited below.
  appendToLogFile(line)

  // Transient network/IO errors (offline, timeouts, cancellations, socket resets)
  // are not actionable bugs — keep them as local logs + breadcrumbs only.
  if isNonActionableTransient(error) { return }

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
