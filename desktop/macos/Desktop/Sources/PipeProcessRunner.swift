import Darwin
import Foundation

struct PipeProcessResult {
  let stdout: Data
  let stderr: Data
  let terminationStatus: Int32
  let duration: TimeInterval
  let timedOut: Bool
}

enum PipeProcessRunnerError: LocalizedError {
  case launchFailed(String)
  case timedOut(seconds: TimeInterval, stderr: String)
  case pipeDrainTimedOut(streams: String)
  case outputLimitExceeded
  case cancelled

  var errorDescription: String? {
    switch self {
    case .launchFailed(let message):
      return "Failed to run helper process: \(message)"
    case .timedOut(let seconds, let stderr):
      let detail = stderr.isEmpty ? "" : " Stderr: \(stderr.prefix(300))"
      return "Helper process timed out after \(Int(seconds)) seconds.\(detail)"
    case .pipeDrainTimedOut(let streams):
      return "Helper process exited before \(streams) finished draining."
    case .outputLimitExceeded:
      return "Helper process output exceeded the capture limit."
    case .cancelled:
      return "Helper process was cancelled."
    }
  }
}

enum PipeProcessRunner {
  static func run(
    executableURL: URL,
    arguments: [String],
    environment: [String: String] = [:],
    stdinData: Data? = nil,
    timeoutSeconds: TimeInterval,
    killGraceSeconds: TimeInterval = 2,
    maxOutputBytes: Int = 1_048_576,
    cancellationCheck: @escaping @Sendable () -> Bool = { false }
  ) throws -> PipeProcessResult {
    let process = Process()
    process.executableURL = executableURL
    process.arguments = arguments
    if !environment.isEmpty {
      var processEnvironment = ProcessInfo.processInfo.environment
      for (key, value) in environment {
        processEnvironment[key] = value
      }
      process.environment = processEnvironment
    }

    let stdoutPipe = Pipe()
    let stderrPipe = Pipe()
    process.standardOutput = stdoutPipe
    process.standardError = stderrPipe
    let stdinPipe = Pipe()
    if stdinData != nil {
      process.standardInput = stdinPipe
    }

    let stdout = LockedData()
    let stderr = LockedData()
    let stdoutSem = DispatchSemaphore(value: 0)
    let stderrSem = DispatchSemaphore(value: 0)
    let cancellationState = LockedBool(false)
    let outputLimitState = LockedBool(false)

    stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
      let data = handle.availableData
      if data.isEmpty {
        handle.readabilityHandler = nil
        stdoutSem.signal()
      } else if !stdout.append(data, maxBytes: maxOutputBytes) {
        outputLimitState.set(true)
        process.terminate()
      }
    }
    stderrPipe.fileHandleForReading.readabilityHandler = { handle in
      let data = handle.availableData
      if data.isEmpty {
        handle.readabilityHandler = nil
        stderrSem.signal()
      } else if !stderr.append(data, maxBytes: maxOutputBytes) {
        outputLimitState.set(true)
        process.terminate()
      }
    }

    let timeoutState = LockedBool(false)
    let startedAt = Date()
    let timeoutWork = DispatchWorkItem {
      guard process.isRunning else { return }
      timeoutState.set(true)
      process.terminate()
      DispatchQueue.global().asyncAfter(deadline: .now() + killGraceSeconds) {
        if process.isRunning {
          kill(process.processIdentifier, SIGKILL)
        }
      }
    }

    do {
      try process.run()
    } catch {
      stdoutPipe.fileHandleForReading.readabilityHandler = nil
      stderrPipe.fileHandleForReading.readabilityHandler = nil
      timeoutWork.cancel()
      throw PipeProcessRunnerError.launchFailed(error.localizedDescription)
    }

    // Arm the timeout BEFORE the (potentially blocking) stdin write. Writing more
    // than the pipe buffer (~64KB) to a child that hasn't started draining stdin
    // blocks this thread; the timeout — which terminate()s the child and thereby
    // unblocks the write via EPIPE — was previously scheduled only AFTER the write,
    // so a stalled child hung the caller forever with the timeout never armed.
    DispatchQueue.global().asyncAfter(deadline: .now() + timeoutSeconds, execute: timeoutWork)

    let cancellationWork = DispatchWorkItem {
      while process.isRunning {
        if cancellationCheck() {
          cancellationState.set(true)
          process.terminate()
          DispatchQueue.global().asyncAfter(deadline: .now() + killGraceSeconds) {
            if process.isRunning {
              kill(process.processIdentifier, SIGKILL)
            }
          }
          return
        }
        Thread.sleep(forTimeInterval: 0.05)
      }
    }
    DispatchQueue.global().async(execute: cancellationWork)

    if let stdinData {
      // Use the throwing write(contentsOf:) — the legacy write(_:) raises an
      // uncatchable NSFileHandleOperationException on EPIPE, which is exactly what
      // the timeout's terminate() triggers on a blocked write.
      try? stdinPipe.fileHandleForWriting.write(contentsOf: stdinData)
      try? stdinPipe.fileHandleForWriting.close()
    }

    process.waitUntilExit()
    timeoutWork.cancel()
    cancellationWork.cancel()

    let stdoutDrained = stdoutSem.wait(timeout: .now() + .seconds(5)) == .success
    let stderrDrained = stderrSem.wait(timeout: .now() + .seconds(5)) == .success

    let result = PipeProcessResult(
      stdout: stdout.snapshot(),
      stderr: stderr.snapshot(),
      terminationStatus: process.terminationStatus,
      duration: Date().timeIntervalSince(startedAt),
      timedOut: timeoutState.get()
    )

    if result.timedOut {
      let stderrText = String(data: result.stderr, encoding: .utf8) ?? ""
      throw PipeProcessRunnerError.timedOut(seconds: timeoutSeconds, stderr: stderrText)
    }
    if cancellationState.get() {
      throw PipeProcessRunnerError.cancelled
    }
    if outputLimitState.get() {
      throw PipeProcessRunnerError.outputLimitExceeded
    }
    if !stdoutDrained || !stderrDrained {
      let streams = [
        stdoutDrained ? nil : "stdout",
        stderrDrained ? nil : "stderr",
      ].compactMap(\.self).joined(separator: " and ")
      throw PipeProcessRunnerError.pipeDrainTimedOut(streams: streams)
    }

    return result
  }
}

private final class LockedData: @unchecked Sendable {
  private var data = Data()
  private let lock = NSLock()

  func append(_ chunk: Data, maxBytes: Int) -> Bool {
    lock.lock()
    guard data.count < maxBytes else {
      lock.unlock()
      return false
    }
    let remaining = maxBytes - data.count
    data.append(chunk.prefix(remaining))
    let complete = chunk.count <= remaining
    lock.unlock()
    return complete
  }

  func snapshot() -> Data {
    lock.lock()
    defer { lock.unlock() }
    return data
  }
}

private final class LockedBool: @unchecked Sendable {
  private var value: Bool
  private let lock = NSLock()

  init(_ value: Bool) {
    self.value = value
  }

  func set(_ newValue: Bool) {
    lock.lock()
    value = newValue
    lock.unlock()
  }

  func get() -> Bool {
    lock.lock()
    defer { lock.unlock() }
    return value
  }
}
