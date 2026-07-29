import Foundation

/// Deterministic install/repair recipes for local agent providers. Recipes are
/// typed steps — shell commands plus explicit user actions (sign-in, API keys)
/// — so setup is reproducible and testable, never an LLM improvising installs.
/// Every recipe run must be user-consented upstream (voice confirmation or an
/// explicit tool/bridge call); this layer never self-triggers.
enum AgentProviderInstaller {

  struct Step {
    enum Kind {
      /// Run to completion via `zsh -lc`, streaming output lines.
      case shell(String)
      /// Something only the user can finish (OAuth, API key). `launch`
      /// (optional, `zsh -lc`) kicks off the flow — e.g. `codex login`
      /// opens the browser and blocks until done. `isComplete` is polled
      /// every 2s until true or timeout.
      case userAction(instructions: String, launch: String?, isComplete: () -> Bool)
    }

    let title: String
    let kind: Kind
    var timeout: TimeInterval = 300

    /// Stable description for tests and logs (closures aren't equatable).
    var testDescription: String {
      switch kind {
      case .shell(let script): return "shell:\(title):\(script)"
      case .userAction(_, let launch, _): return "userAction:\(title):\(launch ?? "-")"
      }
    }
  }

  enum RunResult {
    case success
    case failed(step: String, message: String)
  }

  // MARK: - Recipes

  static func plan(
    for provider: AgentPillsManager.DirectedProvider,
    health: AgentProviderHealthReport? = nil,
    homeDirectory: String = NSHomeDirectory(),
    fileManager: FileManager = .default,
    searchDirectories: [String]? = nil
  ) -> [Step] {
    let report = health ?? AgentProviderHealth.report(for: provider)
    guard report.readiness != .ready else { return [] }

    func executable(_ name: String) -> String? {
      LocalAgentProviderDetector.firstExecutable(
        named: name, fileManager: fileManager, homeDirectory: homeDirectory,
        searchDirectories: searchDirectories)
    }

    switch provider {
    case .codex:
      var steps: [Step] = []
      if executable("codex") == nil {
        steps.append(
          Step(
            title: "Install Codex CLI",
            kind: .shell("npm install -g @openai/codex")))
      }
      if executable("codex-acp") == nil {
        steps.append(
          Step(
            title: "Install codex-acp bridge",
            kind: .shell("npm install -g @agentclientprotocol/codex-acp")))
      }
      let authPath = (homeDirectory as NSString).appendingPathComponent(".codex/auth.json")
      if !fileManager.fileExists(atPath: authPath) {
        steps.append(
          Step(
            title: "Sign in to Codex",
            kind: .userAction(
              instructions: "Finish the ChatGPT sign-in in your browser.",
              launch: "codex login",
              isComplete: { fileManager.fileExists(atPath: authPath) })))
      }
      return steps

    case .hermes:
      var steps: [Step] = []
      if executable("hermes") == nil {
        steps.append(
          Step(
            title: "Install Hermes agent",
            kind: .shell("curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"),
            timeout: 600))
      }
      steps.append(
        Step(
          title: "Connect Hermes to Nous Portal",
          kind: .userAction(
            instructions:
              "Complete the Nous Portal sign-in in your browser, then answer the prompts in the Terminal window.",
            // `hermes setup --portal` has interactive terminal prompts
            // (model choice), so it must run in a real Terminal.
            launch: openInTerminalScript(command: "hermes setup --portal"),
            // Binary presence is NOT auth — a fresh install reports
            // "logged out" and every run fails until portal auth lands.
            // Resolve the binary at poll time (it may not exist when
            // the plan is built) with the same search dirs the plan
            // uses — venv-only installs are on no default PATH.
            isComplete: {
              guard
                let hermesPath = LocalAgentProviderDetector.firstExecutable(
                  named: "hermes", fileManager: fileManager, homeDirectory: homeDirectory,
                  searchDirectories: searchDirectories)
              else { return false }
              return hermesNousAuthenticated(hermesPath: hermesPath)
            }),
          timeout: 420))
      return steps

    case .openclaw:
      var steps: [Step] = []
      if executable("openclaw") == nil {
        steps.append(
          Step(
            title: "Install OpenClaw",
            kind: .shell("npm install -g openclaw"),
            timeout: 600))
      }
      let configPath = (homeDirectory as NSString).appendingPathComponent(".openclaw/openclaw.json")
      if !fileManager.fileExists(atPath: configPath) {
        steps.append(
          Step(
            title: "Onboard OpenClaw",
            kind: .userAction(
              instructions: "Complete `openclaw onboard` in the Terminal window (model/API key choices are yours).",
              launch: openInTerminalScript(command: "openclaw onboard"),
              isComplete: { fileManager.fileExists(atPath: configPath) }),
            timeout: 600))
      }
      return steps
    }
  }

  /// `hermes auth status nous` prints "logged in" once portal auth lands.
  /// Takes the resolved binary path so the probe uses the same executable
  /// the plan discovered, and terminates a hung probe so the polling loop's
  /// own deadline stays in control.
  static func hermesNousAuthenticated(hermesPath: String, timeout: TimeInterval = 10) -> Bool {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: hermesPath)
    process.arguments = ["auth", "status", "nous"]
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = Pipe()
    do { try process.run() } catch { return false }
    let watchdog = DispatchWorkItem { process.terminate() }
    DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: watchdog)
    process.waitUntilExit()
    watchdog.cancel()
    let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    return output.contains("logged in")
  }

  /// `openclaw onboard` is a TUI and must run in a real terminal.
  static func openInTerminalScript(command: String) -> String {
    "osascript -e 'tell application \"Terminal\" to activate' -e 'tell application \"Terminal\" to do script \"\(command)\"'"
  }

  // MARK: - Execution

  /// Run steps sequentially off the main thread. `onEvent` receives progress
  /// lines (step titles + command output) for the setup pill's activity feed.
  static func run(
    steps: [Step],
    onEvent: @escaping @Sendable (String) -> Void
  ) async -> RunResult {
    for step in steps {
      onEvent("▸ \(step.title)")
      switch step.kind {
      case .shell(let script):
        let result = await runShell(script, timeout: step.timeout, onEvent: onEvent)
        if case .failure(let message) = result {
          return .failed(step: step.title, message: message)
        }
      case .userAction(let instructions, let launch, let isComplete):
        onEvent(instructions)
        if let launch {
          // Fire the launch command; completion is judged by polling,
          // not by the command's exit (OAuth flows vary).
          _ = await runShell(launch, timeout: step.timeout, onEvent: onEvent, failOnNonZeroExit: false)
        }
        let deadline = Date().addingTimeInterval(step.timeout)
        while !isComplete() {
          if Date() > deadline {
            return .failed(step: step.title, message: "Timed out waiting: \(instructions)")
          }
          do {
            try await Task.sleep(nanoseconds: 2_000_000_000)
          } catch {
            // Cancellation must exit promptly — swallowing it would
            // turn this poll into a tight spin until the deadline.
            return .failed(step: step.title, message: "Setup cancelled.")
          }
        }
      }
    }
    return .success
  }

  private enum ShellOutcome {
    case success
    case failure(String)
  }

  private static func runShell(
    _ script: String,
    timeout: TimeInterval,
    onEvent: @escaping @Sendable (String) -> Void,
    failOnNonZeroExit: Bool = true
  ) async -> ShellOutcome {
    await withCheckedContinuation { continuation in
      DispatchQueue.global(qos: .userInitiated).async {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", script]
        var env = ProcessInfo.processInfo.environment
        let extraPath = "/opt/homebrew/bin:/usr/local/bin:\(NSHomeDirectory())/.local/bin"
        env["PATH"] = "\(extraPath):\(env["PATH"] ?? "/usr/bin:/bin")"
        process.environment = env

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        var lastLines: [String] = []
        pipe.fileHandleForReading.readabilityHandler = { handle in
          let data = handle.availableData
          guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
          for line in text.split(separator: "\n").map(String.init) where !line.isEmpty {
            lastLines.append(line)
            if lastLines.count > 8 { lastLines.removeFirst() }
            onEvent(line)
          }
        }

        let watchdog = DispatchWorkItem { process.terminate() }
        DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: watchdog)

        do {
          try process.run()
          process.waitUntilExit()
        } catch {
          watchdog.cancel()
          pipe.fileHandleForReading.readabilityHandler = nil
          continuation.resume(returning: .failure(error.localizedDescription))
          return
        }
        watchdog.cancel()
        pipe.fileHandleForReading.readabilityHandler = nil

        if failOnNonZeroExit && process.terminationStatus != 0 {
          let tail = lastLines.suffix(3).joined(separator: " · ")
          continuation.resume(
            returning: .failure(
              "exit \(process.terminationStatus)\(tail.isEmpty ? "" : " — \(tail)")"))
        } else {
          continuation.resume(returning: .success)
        }
      }
    }
  }
}
