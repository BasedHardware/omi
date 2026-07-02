import AppKit
import Darwin
import Foundation

/// Deterministic, code-owned installer for missing local agent providers
/// (OpenClaw, Hermes, Codex). Runs the provider's official unattended install
/// command via `Process` after the user confirms in a native dialog — never
/// through an agent. The previous design spawned an auto-approving DEFAULT
/// agent pill that shell-ran `curl … | bash`, which meant a prompt-injected
/// tool call could execute remote scripts with no code-level gate; this
/// component is the fix (integrations philosophy: code owns contracts).
///
/// Flow: setup_agent_provider tool → `beginInstall` (tool result returns
/// immediately) → NSAlert consent gate on the main actor → `Process` off the
/// main actor (`/bin/bash -c`, no login shell, no TTY, 10-minute cap,
/// process-tree kill) → verification via `LocalAgentProviderDetector` → a
/// floating-bar notification with the outcome → hub session re-warm so voice
/// picks up the freshly installed provider.
@MainActor
final class LocalAgentProviderInstaller {
  static let shared = LocalAgentProviderInstaller()

  /// Single consent-rule sentence shared by the capability registry bullet,
  /// the hub instruction, and the realtime tool description. The TS manifest
  /// keeps its own copy of the same sentence (cross-language).
  nonisolated static let consentRule =
    "Call setup_agent_provider ONLY after the user explicitly agrees in this conversation to install that provider — never unprompted."

  /// Hard cap for one install run. Generous — npm and curl installers can be
  /// slow on cold caches — but nothing interactive can be waiting (no TTY),
  /// so anything longer is stuck and gets its process tree terminated.
  nonisolated static let installTimeoutSeconds: TimeInterval = 600

  /// Providers with an install currently pending (dialog up) or running —
  /// prevents concurrent duplicate installs of the same provider.
  private var inFlight: Set<AgentPillsManager.DirectedProvider> = []

  private init() {}

  // MARK: - Tool entry point (shared by the voice hub and typed chat)

  /// Kick off the consent + install flow. Returns the tool result string
  /// IMMEDIATELY — the native confirmation dialog and the install itself run
  /// after this returns, so no surface ever blocks a turn on the dialog.
  /// Idempotent: an already-installed provider just reports ready.
  func beginInstall(for provider: AgentPillsManager.DirectedProvider) -> String {
    if case .available(let command) = LocalAgentProviderDetector.availability(for: provider).status {
      return "\(provider.displayName) is already installed and ready (\(command)) — no setup needed."
    }
    guard !inFlight.contains(provider) else {
      return
        "A \(provider.displayName) install is already in progress — Omi will report the result when it finishes."
    }
    inFlight.insert(provider)
    Task { @MainActor in
      self.confirmAndRun(provider)
    }
    return
      "Waiting for the user to confirm the \(provider.displayName) install in a native dialog — nothing downloads or runs until they click Install. The install then runs in the background and Omi reports the result when it finishes; interactive sign-in or onboarding steps are left to the user."
  }

  // MARK: - Consent gate (code-level, not prompt-level)

  /// The REAL install gate: a native dialog showing the exact command about
  /// to run, so a prompt-injected or over-eager tool call can never start a
  /// download on its own. The prompt-level consent wording (`consentRule`)
  /// stays as the first layer only.
  private func confirmAndRun(_ provider: AgentPillsManager.DirectedProvider) {
    let alert = NSAlert()
    alert.messageText = "Install \(provider.displayName)?"
    alert.informativeText = Self.confirmationText(for: provider)
    alert.alertStyle = .warning
    alert.addButton(withTitle: "Install")
    alert.addButton(withTitle: "Cancel")
    NSApp.activate()
    let response = alert.runModal()
    guard response == .alertFirstButtonReturn else {
      inFlight.remove(provider)
      log("LocalAgentProviderInstaller: user declined \(provider.rawValue) install")
      return
    }
    log(
      "LocalAgentProviderInstaller: user confirmed \(provider.rawValue) install — running `\(provider.unattendedInstallCommand)`"
    )
    Task.detached(priority: .userInitiated) {
      let outcome = Self.runInstallProcess(for: provider)
      await self.finishInstall(provider, outcome: outcome)
    }
  }

  /// Consent dialog body: the LITERAL command plus where it downloads from.
  /// Pure and nonisolated so tests can assert the exact wording.
  nonisolated static func confirmationText(for provider: AgentPillsManager.DirectedProvider) -> String {
    """
    This will run:

    \(provider.unattendedInstallCommand)

    Downloads and runs software from \(provider.installSourceDomain).
    """
  }

  // MARK: - Deterministic install process (off the main actor)

  /// Run the code-owned unattended install command. `/bin/bash -c` only —
  /// never a login shell — with pipe stdio, so there is no TTY and nothing
  /// interactive can hang forever; the timeout tears down the whole tree.
  nonisolated private static func runInstallProcess(
    for provider: AgentPillsManager.DirectedProvider
  ) -> ProviderInstallOutcome {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/bash")
    process.arguments = ["-c", provider.unattendedInstallCommand]

    var environment = ProcessInfo.processInfo.environment
    environment["PATH"] = installPATH(
      existingPath: environment["PATH"], homeDirectory: NSHomeDirectory())
    process.environment = environment

    let stdoutPipe = Pipe()
    let stderrPipe = Pipe()
    process.standardOutput = stdoutPipe
    process.standardError = stderrPipe
    process.standardInput = FileHandle.nullDevice

    // Bounded tail buffers — install logs can be huge and we only ever report
    // a short tail, so never accumulate the full output in memory.
    let stdoutTail = BoundedTailBuffer(limit: 16 * 1024)
    let stderrTail = BoundedTailBuffer(limit: 16 * 1024)
    stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
      let data = handle.availableData
      if data.isEmpty { handle.readabilityHandler = nil } else { stdoutTail.append(data) }
    }
    stderrPipe.fileHandleForReading.readabilityHandler = { handle in
      let data = handle.availableData
      if data.isEmpty { handle.readabilityHandler = nil } else { stderrTail.append(data) }
    }

    do {
      try process.run()
    } catch {
      stdoutPipe.fileHandleForReading.readabilityHandler = nil
      stderrPipe.fileHandleForReading.readabilityHandler = nil
      return ProviderInstallOutcome(
        launchFailure: error.localizedDescription, exitCode: -1, timedOut: false,
        stdoutTail: "", stderrTail: "")
    }

    let timedOut = LockedFlag()
    let timeoutWork = DispatchWorkItem {
      guard process.isRunning else { return }
      timedOut.set()
      terminateProcessTree(process)
    }
    DispatchQueue.global().asyncAfter(deadline: .now() + installTimeoutSeconds, execute: timeoutWork)
    process.waitUntilExit()
    timeoutWork.cancel()

    return ProviderInstallOutcome(
      launchFailure: nil,
      exitCode: process.terminationStatus,
      timedOut: timedOut.isSet(),
      stdoutTail: stdoutTail.text(),
      stderrTail: stderrTail.text())
  }

  /// SIGTERM, then SIGKILL after a short grace. `Process` children get their
  /// own process group on macOS, so signalling the negative pid takes the
  /// whole install tree down (bash → curl → nested installer), not just the
  /// top shell; falls back to the single pid if the child is not the leader.
  nonisolated private static func terminateProcessTree(_ process: Process) {
    let pid = process.processIdentifier
    guard pid > 0 else { return }
    let isGroupLeader = getpgid(pid) == pid
    if isGroupLeader {
      kill(-pid, SIGTERM)
    } else {
      process.terminate()
    }
    DispatchQueue.global().asyncAfter(deadline: .now() + 2) {
      guard process.isRunning else { return }
      kill(isGroupLeader ? -pid : pid, SIGKILL)
    }
  }

  /// PATH for the install subprocess: the app's PATH first, then the
  /// authoritative provider search directories (shared with
  /// `LocalAgentProviderDetector` so a fresh install lands somewhere
  /// detection can already see), then the standard system directories.
  /// Same dedup shape as `AgentRuntimeProcess.applyLocalAgentEnvironment`.
  nonisolated static func installPATH(
    existingPath: String?,
    homeDirectory: String,
    fileManager: FileManager = .default
  ) -> String {
    let inherited = (existingPath ?? "").split(separator: ":").map(String.init)
    let providerDirs = LocalAgentProviderDetector.adapterActivationSearchDirectories(
      homeDirectory: homeDirectory, fileManager: fileManager)
    let standardDirs = ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    var elements: [String] = []
    for dir in inherited + providerDirs + standardDirs where !dir.isEmpty && !elements.contains(dir) {
      elements.append(dir)
    }
    return elements.joined(separator: ":")
  }

  // MARK: - Verification + user-visible outcome

  /// Verification is code-owned too: no agent probing (`command -v`,
  /// `npm bin -g`, …) — the shared detector decides, exactly like every
  /// other availability check in the app.
  private func finishInstall(
    _ provider: AgentPillsManager.DirectedProvider, outcome: ProviderInstallOutcome
  ) {
    inFlight.remove(provider)
    let availability = LocalAgentProviderDetector.availability(for: provider)
    if case .available(let command) = availability.status {
      log(
        "LocalAgentProviderInstaller: \(provider.rawValue) install verified — \(command) (exit=\(outcome.exitCode))"
      )
      var message = "\(provider.displayName) is installed at \(command)."
      if let note = provider.postInstallNote {
        message += " Next: \(note)."
      }
      message += " Just ask Omi to use \(provider.displayName) again."
      NotificationService.shared.sendNotification(
        title: "\(provider.displayName) installed",
        message: message,
        respectFrequency: false)
      // Warm hub sessions freeze their tool schema and provider instruction
      // at session start — re-warm (idle-only) so voice sees the new provider.
      RealtimeHubController.shared.refreshForLocalAgentProviderChange()
      return
    }

    let reason: String
    if let launchFailure = outcome.launchFailure {
      reason = "the install command could not be started (\(launchFailure))"
    } else if outcome.timedOut {
      reason = "the install ran longer than \(Int(Self.installTimeoutSeconds / 60)) minutes and was stopped"
    } else if outcome.exitCode != 0 {
      reason = "the install command exited with code \(outcome.exitCode)"
    } else {
      reason = "the install command finished but `\(provider.executableName)` was not found afterwards"
    }
    var message = "\(provider.displayName) install failed — \(reason)."
    // Curl-based installers frequently report the failure on stdout.
    let stderrTail = outcome.stderrTail.trimmingCharacters(in: .whitespacesAndNewlines)
    let outputTail =
      stderrTail.isEmpty
      ? outcome.stdoutTail.trimmingCharacters(in: .whitespacesAndNewlines) : stderrTail
    if !outputTail.isEmpty {
      message += " Output: \(String(outputTail.suffix(300)))"
    }
    message += " Install guide: \(provider.installDocsURL)"
    log("LocalAgentProviderInstaller: \(provider.rawValue) install failed — \(reason)")
    NotificationService.shared.sendNotification(
      title: "\(provider.displayName) install failed",
      message: message,
      respectFrequency: false)
  }
}

/// Result of one install process run (file-scope so it is not pulled onto
/// the main actor by the installer's `@MainActor` annotation).
private struct ProviderInstallOutcome: Sendable {
  let launchFailure: String?
  let exitCode: Int32
  let timedOut: Bool
  let stdoutTail: String
  let stderrTail: String
}

/// Keeps only the LAST `limit` bytes written.
private final class BoundedTailBuffer: @unchecked Sendable {
  private var data = Data()
  private let limit: Int
  private let lock = NSLock()

  init(limit: Int) {
    self.limit = limit
  }

  func append(_ chunk: Data) {
    lock.lock()
    data.append(chunk)
    if data.count > limit {
      data.removeFirst(data.count - limit)
    }
    lock.unlock()
  }

  func text() -> String {
    lock.lock()
    defer { lock.unlock() }
    return String(data: data, encoding: .utf8) ?? ""
  }
}

private final class LockedFlag: @unchecked Sendable {
  private var value = false
  private let lock = NSLock()

  func set() {
    lock.lock()
    value = true
    lock.unlock()
  }

  func isSet() -> Bool {
    lock.lock()
    defer { lock.unlock() }
    return value
  }
}
