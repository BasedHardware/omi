import Darwin
import XCTest

@testable import Omi_Computer

final class LocalAgentProviderInstallerTests: XCTestCase {
  // MARK: - Confirmation dialog content (the code-level consent gate)

  func testConfirmationTextShowsExactCommandAndSourceDomain() {
    for provider in AgentPillsManager.orderedDirectedProviders {
      let text = LocalAgentProviderInstaller.confirmationText(for: provider)
      // The dialog must show the LITERAL command that will run — no summary.
      XCTAssertTrue(text.contains(provider.unattendedInstallCommand))
      XCTAssertTrue(text.contains("Downloads and runs software from \(provider.installSourceDomain)."))
    }
    XCTAssertEqual(AgentPillsManager.DirectedProvider.hermes.installSourceDomain, "hermes-agent.nousresearch.com")
    XCTAssertEqual(AgentPillsManager.DirectedProvider.openclaw.installSourceDomain, "openclaw.ai")
    XCTAssertEqual(AgentPillsManager.DirectedProvider.codex.installSourceDomain, "registry.npmjs.org")
  }

  func testConsentRuleMatchesTheTSManifestGuideline() throws {
    // ONE consent sentence everywhere. The TS manifest keeps its own copy —
    // keep them literally identical so neither side drifts.
    let manifestURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("agent/src/runtime/omi-tool-manifest.ts")
    let manifest = try String(contentsOf: manifestURL, encoding: .utf8)
    XCTAssertTrue(manifest.contains("\"\(LocalAgentProviderInstaller.consentRule)\""))
  }

  // MARK: - Install subprocess environment

  func testInstallPATHCoversDetectorDirectoriesAndDedupes() {
    let home = "/Users/test"
    let path = LocalAgentProviderInstaller.installPATH(
      existingPath: "/usr/bin:/opt/homebrew/bin",
      homeDirectory: home)
    let elements = path.split(separator: ":").map(String.init)

    // Every authoritative detection directory is on the install PATH, so a
    // fresh install lands somewhere the detector can already see.
    for dir in LocalAgentProviderDetector.adapterActivationSearchDirectories(homeDirectory: home) {
      XCTAssertTrue(elements.contains(dir), "missing detector dir \(dir)")
    }
    // Standard system dirs are appended; inherited entries are deduplicated.
    XCTAssertTrue(elements.contains("/bin"))
    XCTAssertTrue(elements.contains("/usr/sbin"))
    XCTAssertEqual(elements.filter { $0 == "/usr/bin" }.count, 1)
    XCTAssertEqual(elements.filter { $0 == "/opt/homebrew/bin" }.count, 1)
  }

  func testInstallPATHWorksWithoutInheritedPath() {
    let path = LocalAgentProviderInstaller.installPATH(existingPath: nil, homeDirectory: "/Users/test")
    let elements = path.split(separator: ":").map(String.init)
    XCTAssertTrue(elements.contains("/usr/bin"))
    XCTAssertTrue(elements.contains("/Users/test/.local/bin"))
    XCTAssertFalse(elements.contains(""))
  }

  func testInstallEnvironmentIsAnAllowlistNeverWholesaleInheritance() {
    let base = [
      // One entry per allowlisted key, so every key's pass-through is pinned.
      "PATH": "/usr/bin:/opt/homebrew/bin",
      "HOME": "/Users/other",
      "TMPDIR": "/var/folders/xx/T/",
      "USER": "test",
      "LOGNAME": "test",
      "SHELL": "/bin/zsh",
      "LANG": "en_US.UTF-8",
      "LC_ALL": "en_US.UTF-8",
      "LC_CTYPE": "UTF-8",
      // Credentials/tokens that must NOT cross the install boundary — the
      // install command runs third-party downloaded code.
      "OMI_API_KEY": "secret",
      "OMI_DESKTOP_API_URL": "https://example.com",
      "ANTHROPIC_API_KEY": "secret",
      "OPENAI_API_KEY": "secret",
      "AWS_SECRET_ACCESS_KEY": "secret",
      "GITHUB_TOKEN": "secret",
      // Tempting-but-dangerous vars a future dev might reach for:
      // NODE_OPTIONS/npm_config_* inject code into npm runs, SSH_AUTH_SOCK
      // exposes the user's agent, proxy URLs embed credentials.
      "NODE_OPTIONS": "--require /tmp/evil.js",
      "npm_config_registry": "https://registry.evil.example",
      "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
      "HTTPS_PROXY": "http://user:secret@proxy.example:8080",
    ]
    let environment = LocalAgentProviderInstaller.installEnvironment(
      base: base, homeDirectory: "/Users/test")

    // Exactly the allowlist survives — nothing else leaks through.
    XCTAssertEqual(
      Set(environment.keys),
      ["PATH", "HOME", "TMPDIR", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE"])
    // HOME is the app's real home dir, PATH is the rebuilt install PATH.
    XCTAssertEqual(environment["HOME"], "/Users/test")
    XCTAssertEqual(
      environment["PATH"],
      LocalAgentProviderInstaller.installPATH(
        existingPath: "/usr/bin:/opt/homebrew/bin", homeDirectory: "/Users/test"))
  }

  func testInstallEnvironmentWorksFromAnEmptyBase() {
    let environment = LocalAgentProviderInstaller.installEnvironment(
      base: [:], homeDirectory: "/Users/test")
    XCTAssertEqual(environment["HOME"], "/Users/test")
    XCTAssertNotNil(environment["PATH"])
    XCTAssertNil(environment["TMPDIR"])
  }

  func testInstallEnvironmentAllowlistGrowthRequiresAConsciousTestEdit() {
    // The allowlist IS the security boundary: every addition crosses into
    // third-party installer code, so growing it must fail a test.
    XCTAssertEqual(
      LocalAgentProviderInstaller.installEnvironmentAllowlistKeys,
      ["TMPDIR", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE"])
  }

  // MARK: - Source contract: NSAlert gate + Process, never an agent

  func testInstallerGatesOnNativeDialogAndRunsProcessDirectly() throws {
    let source = try installerSource()

    // NSAlert consent gate on the main actor with explicit Install/Cancel;
    // only an explicit click proceeds.
    XCTAssertTrue(source.contains("let alert = NSAlert()"))
    XCTAssertTrue(source.contains(#"alert.messageText = "Install \(provider.displayName)?""#))
    XCTAssertTrue(source.contains(#"alert.addButton(withTitle: "Install")"#))
    XCTAssertTrue(source.contains(#"alert.addButton(withTitle: "Cancel")"#))
    XCTAssertTrue(source.contains("guard response == .alertFirstButtonReturn else"))

    // Deterministic spawn: /bin/bash -c with the code-owned command — never
    // a login shell, never an agent pill.
    XCTAssertTrue(source.contains(#"["/bin/bash", "-c", command]"#))
    XCTAssertTrue(source.contains("command: provider.unattendedInstallCommand"))
    XCTAssertFalse(source.contains("AgentPillsManager.shared.spawn"))
    XCTAssertFalse(source.contains("ChatProvider"))

    // The subprocess environment is built through the allowlist — the app
    // environment appears exactly once, as the filter input, and is never
    // assigned wholesale.
    XCTAssertTrue(source.contains("environment: installEnvironment("))
    XCTAssertEqual(
      source.components(separatedBy: "ProcessInfo.processInfo.environment").count - 1, 1,
      "the app environment must appear once, as installEnvironment's base argument")

    // The installer must start in a NEW process group (leader = child), and
    // no app fds may leak into it — Foundation's Process provides neither, so
    // the spawn must stay on posix_spawn with these attributes.
    XCTAssertTrue(source.contains("POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT"))
    XCTAssertTrue(source.contains("posix_spawnattr_setpgroup(&attributes, 0)"))
    XCTAssertFalse(source.contains("Process()"), "Foundation Process cannot guarantee group teardown")

    // Timeout tears the whole process GROUP down — SIGTERM, then SIGKILL.
    XCTAssertTrue(source.contains("installTimeoutSeconds: TimeInterval = 600"))
    XCTAssertTrue(source.contains("terminateProcessGroup(leader: pid)"))
    XCTAssertTrue(source.contains("kill(-pid, SIGTERM)"))
    XCTAssertTrue(source.contains("kill(-pid, SIGKILL)"))

    // Reap ordering makes group signals identity-safe: exit is detected
    // WITHOUT reaping (WNOWAIT keeps the pid/pgid un-recyclable), any
    // started teardown finishes first, and only then is the leader reaped.
    XCTAssertTrue(source.contains("WEXITED | WNOWAIT"))
    XCTAssertTrue(source.contains("teardownDone.wait()"))
    XCTAssertTrue(source.contains("reapInstallProcess(pid: pid)"))

    // Verification is the shared detector — no agent-side probing — and a
    // successful install re-warms the hub session directly.
    XCTAssertTrue(source.contains("LocalAgentProviderDetector.availability(for: provider)"))
    XCTAssertTrue(source.contains("RealtimeHubController.shared.refreshForLocalAgentProviderChange()"))

    // Outcomes reach the user through the existing notification surface.
    XCTAssertTrue(source.contains("NotificationService.shared.sendNotification("))
    XCTAssertTrue(source.contains(#"title: "\(provider.displayName) installed""#))
    XCTAssertTrue(source.contains(#"title: "\(provider.displayName) install failed""#))
    XCTAssertTrue(source.contains("Install guide: \\(provider.installDocsURL)"))
  }

  // MARK: - Process-group teardown (the timeout security boundary)

  func testSpawnedInstallShellLeadsItsOwnProcessGroupAndTeardownKillsDescendants() throws {
    // Real spawn: bash starts a long-sleeping grandchild, reports its pid,
    // then waits — the shape of a hung curl/npm installer. The install
    // command executes remote code, so the timeout MUST be able to take the
    // whole tree down, not just the top shell.
    let stdoutPipe = Pipe()
    let stderrPipe = Pipe()
    let pid = try LocalAgentProviderInstaller.spawnInstallProcessGroup(
      command: "sleep 600 & echo $!; wait",
      environment: ["PATH": "/usr/bin:/bin"],
      stdout: stdoutPipe.fileHandleForWriting.fileDescriptor,
      stderr: stderrPipe.fileHandleForWriting.fileDescriptor)
    defer { kill(-pid, SIGKILL) }  // safety net if an assertion fails mid-test
    try? stdoutPipe.fileHandleForWriting.close()
    try? stderrPipe.fileHandleForWriting.close()

    // The shell must lead its OWN process group — the teardown contract that
    // makes kill(-pid) reach every descendant.
    XCTAssertEqual(getpgid(pid), pid, "install shell must be its own process-group leader")

    let firstLine = try firstStdoutLine(stdoutPipe.fileHandleForReading)
    let grandchild = try XCTUnwrap(pid_t(firstLine), "expected the grandchild pid, got: \(firstLine)")
    XCTAssertEqual(getpgid(grandchild), pid, "descendants must inherit the install process group")

    LocalAgentProviderInstaller.terminateProcessGroup(leader: pid)

    var status: Int32 = 0
    XCTAssertEqual(waitpid(pid, &status, 0), pid, "install shell must exit after group teardown")
    XCTAssertTrue(
      waitForProcessDeath(grandchild, timeout: 5),
      "grandchild must die with the group — a surviving descendant is the reviewer-reported leak")
  }

  /// Blocking read until the first newline (bash echoes immediately; EOF on
  /// early death breaks the loop, so this cannot hang the suite).
  private func firstStdoutLine(_ handle: FileHandle) throws -> String {
    var buffer = Data()
    while !buffer.contains(0x0A) {
      let chunk = handle.availableData
      if chunk.isEmpty { break }
      buffer.append(chunk)
    }
    let line = buffer.prefix(while: { $0 != 0x0A })
    return String(decoding: line, as: UTF8.self).trimmingCharacters(in: .whitespaces)
  }

  private func waitForProcessDeath(_ pid: pid_t, timeout: TimeInterval) -> Bool {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
      if kill(pid, 0) != 0 { return true }
      usleep(50_000)
    }
    return kill(pid, 0) != 0
  }

  private func installerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/LocalAgentProviderInstaller.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
