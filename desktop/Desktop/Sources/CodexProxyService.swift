import Foundation

/// Loopback Codex proxy endpoints (nonisolated constants).
enum CodexProxyEndpoints {
  static let defaultPort: Int = 10531

  static var baseURL: String {
    let port: Int
    if let raw = ProcessInfo.processInfo.environment["OMI_CODEX_PROXY_PORT"],
      let value = Int(raw), value > 0
    {
      port = value
    } else {
      port = defaultPort
    }
    return "http://127.0.0.1:\(port)/v1"
  }

  static var healthURL: String {
    baseURL.replacingOccurrences(of: "/v1", with: "") + "/health"
  }
}

private final class LockedCodexProxyStderrBuffer: @unchecked Sendable {
  private let lock = NSLock()
  private let limit: Int
  private var data = Data()

  init(limit: Int = 16 * 1024) {
    self.limit = limit
  }

  func append(_ chunk: Data) {
    guard !chunk.isEmpty else { return }
    lock.lock()
    data.append(chunk)
    if data.count > limit {
      data.removeFirst(data.count - limit)
    }
    lock.unlock()
  }

  func snapshot() -> String? {
    lock.lock()
    let snapshot = data
    lock.unlock()
    return String(data: snapshot, encoding: .utf8)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

/// Manages the loopback Codex OpenAI-compatible proxy (`desktop/codex-proxy`).
@MainActor
final class CodexProxyService: ObservableObject {
  static let shared = CodexProxyService()

  static var defaultBaseURL: String { CodexProxyEndpoints.baseURL }

  private static var port: Int {
    if let raw = ProcessInfo.processInfo.environment["OMI_CODEX_PROXY_PORT"],
      let value = Int(raw), value > 0
    {
      return value
    }
    return CodexProxyEndpoints.defaultPort
  }

  @Published private(set) var isRunning = false
  @Published private(set) var lastError: String?

  private var process: Process?
  private var healthTask: Task<Void, Never>?
  private var ensureTask: Task<Void, Never>?
  private var stderrPipe: Pipe?

  private init() {}

  /// Start proxy when ChatGPT tier is active. Idempotent.
  func ensureRunning() async {
    if let ensureTask {
      await ensureTask.value
      return
    }

    let task = Task { @MainActor [weak self] in
      guard let self else { return }
      await self.ensureRunningOnce()
    }
    ensureTask = task
    await task.value
    ensureTask = nil
  }

  private func ensureRunningOnce() async {
    guard CodexAuthService.isActive else {
      await stop()
      return
    }
    // Reuse an already-healthy proxy (e.g. from a prior session or manual start).
    if await healthCheck() {
      isRunning = true
      lastError = nil
      startHealthMonitor()
      return
    }
    if isRunning {
      await stop()
    }
    guard let executable = resolveExecutableURL() else {
      lastError =
        "Codex proxy binary not found. Build with: cd desktop/codex-proxy && cargo build --release"
      isRunning = false
      return
    }
    guard CodexAuthService.loadSnapshot() != nil else {
      lastError = "Sign in with ChatGPT first (run Codex login or connect in Settings)."
      isRunning = false
      return
    }

    let proc = Process()
    proc.executableURL = executable
    proc.arguments = []
    var env = ProcessInfo.processInfo.environment
    env["OMI_CODEX_PROXY_PORT"] = String(Self.port)
    proc.environment = env
    let stderrPipe = Pipe()
    let stderrBuffer = LockedCodexProxyStderrBuffer()
    stderrPipe.fileHandleForReading.readabilityHandler = { handle in
      stderrBuffer.append(handle.availableData)
    }
    proc.standardError = stderrPipe
    proc.standardOutput = FileHandle.nullDevice

    do {
      try proc.run()
      process = proc
      self.stderrPipe = stderrPipe
      for _ in 0..<50 {
        try? await Task.sleep(nanoseconds: 100_000_000)
        guard !Task.isCancelled else { return }
        if await healthCheck() {
          isRunning = true
          lastError = nil
          startHealthMonitor()
          log("CodexProxyService: proxy running at \(Self.defaultBaseURL)")
          return
        }
      }
      let stderrHint = stderrBuffer.snapshot()
      let detail =
        (stderrHint?.isEmpty == false)
        ? stderrHint!
        : "Codex proxy failed to start (health check timeout)."
      lastError = detail
      logError("CodexProxyService: failed to start — \(detail)")
      await stop()
    } catch {
      stderrPipe.fileHandleForReading.readabilityHandler = nil
      lastError = error.localizedDescription
      await stop()
    }
  }

  func stop() async {
    healthTask?.cancel()
    healthTask = nil
    ensureTask?.cancel()
    ensureTask = nil
    stderrPipe?.fileHandleForReading.readabilityHandler = nil
    stderrPipe = nil
    if let process, process.isRunning {
      process.terminate()
    }
    process = nil
    isRunning = false
  }

  private func startHealthMonitor() {
    healthTask?.cancel()
    healthTask = Task {
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 15_000_000_000)
        guard !Task.isCancelled else { return }
        guard CodexAuthService.isActive else {
          await stop()
          return
        }
        if !(await healthCheck()) {
          log("CodexProxyService: health failed — restarting")
          await ensureRunning()
          return
        }
      }
    }
  }

  private func healthCheck() async -> Bool {
    guard let url = URL(string: CodexProxyEndpoints.healthURL) else {
      return false
    }
    var request = URLRequest(url: url)
    request.timeoutInterval = 2
    do {
      let (_, response) = try await URLSession.shared.data(for: request)
      return (response as? HTTPURLResponse)?.statusCode == 200
    } catch {
      return false
    }
  }

  private func resolveExecutableURL() -> URL? {
    let names = ["omi-codex-proxy", "codex-proxy"]
    if let resource = Bundle.main.resourceURL {
      for name in names {
        let candidate = resource.appendingPathComponent(name)
        if FileManager.default.isExecutableFile(atPath: candidate.path) {
          return candidate
        }
      }
    }
    let repoRelative = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("codex-proxy/target/release/omi-codex-proxy")
    if FileManager.default.isExecutableFile(atPath: repoRelative.path) {
      return repoRelative
    }
    for name in names {
      if let path = which(name) {
        return URL(fileURLWithPath: path)
      }
    }
    return nil
  }

  private func which(_ name: String) -> String? {
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/usr/bin/which")
    proc.arguments = [name]
    let pipe = Pipe()
    proc.standardOutput = pipe
    proc.standardError = FileHandle.nullDevice
    do {
      try proc.run()
      proc.waitUntilExit()
      guard proc.terminationStatus == 0 else { return nil }
      let data = pipe.fileHandleForReading.readDataToEndOfFile()
      let path = String(data: data, encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard let path, !path.isEmpty else { return nil }
      return path
    } catch {
      return nil
    }
  }
}
