import Foundation
import Sentry

private let logFile: String = {
    let isDev = Bundle.main.bundleIdentifier?.hasSuffix("-dev") == true
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
private let isDevBuild: Bool = Bundle.main.bundleIdentifier?.hasSuffix("-dev") == true

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

    // Capture the error in Sentry (skip intentional cancellations — they're noise)
    let isCancelledRequest = (error as? URLError)?.code == .cancelled ||
        (error as NSError?)?.domain == NSURLErrorDomain && (error as NSError?)?.code == NSURLErrorCancelled
    if let error = error, !isCancelledRequest {
        SentrySDK.capture(error: error) { scope in
            scope.setContext(value: ["message": message], key: "app_context")
        }
    } else if error == nil {
        SentrySDK.capture(message: fullMessage) { scope in
            scope.setLevel(.error)
        }
    }

    appendToLogFile(line)
}
