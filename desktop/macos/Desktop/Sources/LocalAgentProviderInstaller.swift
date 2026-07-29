import AppKit
import Darwin
import Foundation

/// Deterministic, code-owned installer for missing local agent providers
/// (OpenClaw, Hermes, Codex). Runs the provider's official unattended install
/// command via `posix_spawn` after the user confirms in a native dialog — never
/// through an agent. The previous design spawned an auto-approving DEFAULT
/// agent pill that shell-ran `curl … | bash`, which meant a prompt-injected
/// tool call could execute remote scripts with no code-level gate; this
/// component is the fix (integrations philosophy: code owns contracts).
///
/// Flow: setup_agent_provider tool → `beginInstall` (tool result returns
/// immediately) → NSAlert consent gate on the main actor → `posix_spawn` off
/// the main actor (`/bin/bash -c`, no login shell, no TTY, minimal
/// allowlisted environment, its own process group, 10-minute cap with a
/// group-wide kill) → verification via
/// `LocalAgentProviderDetector` → a
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
  /// so anything longer is stuck and gets its whole process group killed.
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
  /// interactive can hang forever. The shell is spawned as the leader of its
  /// OWN process group (`spawnInstallProcessGroup`), so the timeout can tear
  /// down the entire installer tree with one signal to `-pid`. The subprocess
  /// gets a minimal allowlisted environment (`installEnvironment`), never the
  /// app environment wholesale.
  nonisolated private static func runInstallProcess(
    for provider: AgentPillsManager.DirectedProvider
  ) -> ProviderInstallOutcome {
    let stdoutPipe = Pipe()
    let stderrPipe = Pipe()

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

    let pid: pid_t
    do {
      pid = try spawnInstallProcessGroup(
        command: provider.unattendedInstallCommand,
        environment: installEnvironment(
          base: ProcessInfo.processInfo.environment, homeDirectory: NSHomeDirectory()),
        stdout: stdoutPipe.fileHandleForWriting.fileDescriptor,
        stderr: stderrPipe.fileHandleForWriting.fileDescriptor)
    } catch {
      stdoutPipe.fileHandleForReading.readabilityHandler = nil
      stderrPipe.fileHandleForReading.readabilityHandler = nil
      return ProviderInstallOutcome(
        launchFailure: error.localizedDescription, exitCode: -1, timedOut: false,
        stdoutTail: "", stderrTail: "")
    }
    // The child holds dup'd copies of the pipe write ends — close ours so the
    // readers see EOF once the install tree exits.
    try? stdoutPipe.fileHandleForWriting.close()
    try? stderrPipe.fileHandleForWriting.close()

    let exited = LockedFlag()
    let timeoutStarted = LockedFlag()
    let groupTornDown = LockedFlag()
    let teardownDone = DispatchSemaphore(value: 0)
    let timeoutWork = DispatchWorkItem {
      defer { teardownDone.signal() }
      // Set the started sentinel BEFORE checking exited: the reaper below
      // only skips waiting on the semaphore when it reads timeoutStarted ==
      // false, which proves this closure had not yet reached the sentinel —
      // and the reaper's exited.set() already happened by then, so the guard
      // stops us from ever signalling. Either way, no signal can race the
      // reap.
      timeoutStarted.set()
      guard !exited.isSet() else { return }
      groupTornDown.set()
      terminateProcessGroup(leader: pid)
    }
    DispatchQueue.global().asyncAfter(deadline: .now() + installTimeoutSeconds, execute: timeoutWork)
    // Wait WITHOUT reaping (WNOWAIT): as long as the leader stays a zombie,
    // its pid — and therefore the group id — cannot be recycled, so teardown
    // signals can never reach a stranger's process group.
    waitForInstallProcessExitWithoutReaping(pid: pid)
    exited.set()
    timeoutWork.cancel()
    if timeoutStarted.isSet() {
      // The teardown may still be signalling the group — let it finish before
      // reaping makes the group id recyclable.
      teardownDone.wait()
    }
    let exitCode = reapInstallProcess(pid: pid)

    return ProviderInstallOutcome(
      launchFailure: nil,
      exitCode: exitCode,
      timedOut: groupTornDown.isSet(),
      stdoutTail: stdoutTail.text(),
      stderrTail: stderrTail.text())
  }

  /// Spawn `/bin/bash -c <command>` as the leader of a NEW process group —
  /// `POSIX_SPAWN_SETPGROUP` with pgroup 0 makes the child's pgid its own
  /// pid, and every descendant (curl, npm, postinstall scripts, nested
  /// installers) inherits that group. This is the teardown contract
  /// `terminateProcessGroup` relies on; Foundation's `Process` leaves the
  /// child in the app's process group, which is why it is not used here.
  /// `POSIX_SPAWN_CLOEXEC_DEFAULT` keeps every app fd except the three stdio
  /// descriptors from crossing into the third-party installer. Internal (not
  /// private) so the group-leadership contract is covered by a real test.
  nonisolated static func spawnInstallProcessGroup(
    command: String,
    environment: [String: String],
    stdout stdoutDescriptor: Int32,
    stderr stderrDescriptor: Int32
  ) throws -> pid_t {
    // Every setup call is checked: if an attribute silently failed, the child
    // could start WITHOUT its own process group and the timeout teardown —
    // part of the security boundary — would not reach its descendants.
    func check(_ rc: Int32) throws {
      guard rc == 0 else { throw InstallSpawnError(code: rc) }
    }

    var fileActions: posix_spawn_file_actions_t? = nil
    try check(posix_spawn_file_actions_init(&fileActions))
    defer { posix_spawn_file_actions_destroy(&fileActions) }
    try check(posix_spawn_file_actions_addopen(&fileActions, 0, "/dev/null", O_RDONLY, 0))
    try check(posix_spawn_file_actions_adddup2(&fileActions, stdoutDescriptor, 1))
    try check(posix_spawn_file_actions_adddup2(&fileActions, stderrDescriptor, 2))

    var attributes: posix_spawnattr_t? = nil
    try check(posix_spawnattr_init(&attributes))
    defer { posix_spawnattr_destroy(&attributes) }
    let flags = POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSIGDEF | POSIX_SPAWN_SETSIGMASK
    try check(posix_spawnattr_setflags(&attributes, Int16(flags)))
    try check(posix_spawnattr_setpgroup(&attributes, 0))
    // Reset inherited signal state — dispositions back to default and an
    // empty mask — so an app-ignored or app-masked SIGTERM cannot neutralize
    // the graceful phase of the group teardown.
    var defaultSignals = sigset_t()
    sigfillset(&defaultSignals)
    sigdelset(&defaultSignals, SIGKILL)
    sigdelset(&defaultSignals, SIGSTOP)
    try check(posix_spawnattr_setsigdefault(&attributes, &defaultSignals))
    var emptyMask = sigset_t()
    sigemptyset(&emptyMask)
    try check(posix_spawnattr_setsigmask(&attributes, &emptyMask))

    var argv: [UnsafeMutablePointer<CChar>?] = ["/bin/bash", "-c", command].map { strdup($0) }
    argv.append(nil)
    var envp: [UnsafeMutablePointer<CChar>?] = environment.map { strdup("\($0.key)=\($0.value)") }
    envp.append(nil)
    defer {
      argv.forEach { free($0) }
      envp.forEach { free($0) }
    }

    var pid: pid_t = 0
    let rc = posix_spawn(&pid, "/bin/bash", &fileActions, &attributes, &argv, &envp)
    guard rc == 0 else { throw InstallSpawnError(code: rc) }
    return pid
  }

  /// Block until the spawned shell exits, WITHOUT reaping it (`WNOWAIT`).
  /// The zombie keeps the pid — and therefore the process-group id — from
  /// being recycled while teardown signals may still be in flight.
  nonisolated private static func waitForInstallProcessExitWithoutReaping(pid: pid_t) {
    var info = siginfo_t()
    while waitid(P_PID, id_t(pid), &info, WEXITED | WNOWAIT) == -1 {
      if errno != EINTR { return }
    }
  }

  /// Reap the spawned shell and derive a reportable exit code (128 + signal
  /// for a signalled death, matching the shell convention).
  nonisolated private static func reapInstallProcess(pid: pid_t) -> Int32 {
    var status: Int32 = 0
    while waitpid(pid, &status, 0) == -1 {
      if errno != EINTR { return -1 }
    }
    if (status & 0x7f) == 0 {
      return (status >> 8) & 0xff
    }
    return 128 + (status & 0x7f)
  }

  /// SIGTERM the whole install process group, give it a short grace, then
  /// SIGKILL anything still in it. Blocking — runs on the timeout worker
  /// thread, and completing before the caller reaps the leader is what makes
  /// it safe: the caller guarantees the leader is still unreaped (WNOWAIT),
  /// so the group id cannot have been recycled and every signal lands on our
  /// own install tree (bash → curl → nested installer), never a stranger's.
  /// `spawnInstallProcessGroup` guarantees pgid == pid. Internal (not
  /// private) so the teardown contract is covered by a real test.
  nonisolated static func terminateProcessGroup(leader pid: pid_t) {
    guard pid > 0 else { return }
    kill(-pid, SIGTERM)
    Thread.sleep(forTimeInterval: 2)
    // Escalate only if members are still alive (ESRCH means the whole group,
    // zombie leader aside, is already gone).
    if kill(-pid, 0) == 0 {
      kill(-pid, SIGKILL)
    }
  }

  /// Keys copied from the app environment into the install subprocess — the
  /// entire allowlist besides the always-set HOME and PATH. Every addition
  /// here crosses the third-party-installer boundary: keep it minimal, and
  /// the allowlist test must be edited consciously to match.
  nonisolated static let installEnvironmentAllowlistKeys = [
    "TMPDIR", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
  ]

  /// Environment for the install subprocess: a minimal allowlist built from
  /// scratch, never the app environment wholesale. The command executes
  /// third-party downloaded code (curl-piped installers, npm lifecycle
  /// scripts), so app/API/session credentials and provider tokens must not
  /// cross this boundary — only what installers legitimately need: PATH
  /// (rebuilt via `installPATH`), HOME, and locale/temp/user identity vars.
  /// Proxy/CA vars (`HTTP(S)_PROXY`, `NODE_EXTRA_CA_CERTS`, …) are
  /// deliberately excluded too — proxy URLs can embed credentials; proxied
  /// setups should install the provider manually.
  nonisolated static func installEnvironment(
    base: [String: String],
    homeDirectory: String,
    fileManager: FileManager = .default
  ) -> [String: String] {
    var environment: [String: String] = [:]
    for key in installEnvironmentAllowlistKeys {
      if let value = base[key] { environment[key] = value }
    }
    environment["HOME"] = homeDirectory
    environment["PATH"] = installPATH(
      existingPath: base["PATH"], homeDirectory: homeDirectory, fileManager: fileManager)
    return environment
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

/// `posix_spawn` launch failure with the errno text.
struct InstallSpawnError: LocalizedError, Sendable {
  let code: Int32
  var errorDescription: String? { "posix_spawn failed: \(String(cString: strerror(code))) (\(code))" }
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
