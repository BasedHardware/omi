import AppKit
import Foundation

/// Connects ChatGPT / Codex subscription: runs `codex login`, validates auth.json, enrolls backend.
@MainActor
enum CodexEnrollmentCoordinator {
  enum EnrollmentError: LocalizedError {
    case authFileMissing
    case proxyFailed(String)
    case backendFailed(String)

    var errorDescription: String? {
      switch self {
      case .authFileMissing:
        return
          "Sign-in timed out. Complete login in Terminal, then try again."
      case .proxyFailed(let msg):
        return "Codex proxy failed: \(msg)"
      case .backendFailed(let msg):
        return "Could not activate ChatGPT plan on account: \(msg)"
      }
    }
  }

  private static var connectInFlight = false
  private static var loginTerminalLaunched = false

  /// Opens Codex login in Terminal (user completes browser flow).
  private static func launchCodexLogin() {
    if loginTerminalLaunched {
      activateTerminal()
      return
    }
    loginTerminalLaunched = true

    let command = "npx @openai/codex login"
    // `do script` alone always opens a new window when Terminal is already running.
    // Reuse the front window (new tab) so one click does not spawn a second window.
    let script = """
      tell application "Terminal"
        if not running then
          do script "\(command)"
        else
          activate
          if (count of windows) is 0 then
            do script "\(command)"
          else
            do script "\(command)" in front window
          end if
        end if
      end tell
      """
    if let appleScript = NSAppleScript(source: script) {
      var error: NSDictionary?
      appleScript.executeAndReturnError(&error)
      if error != nil {
        loginTerminalLaunched = false
        NSWorkspace.shared.open(URL(string: "https://developers.openai.com/codex/auth")!)
      }
    }
  }

  private static func activateTerminal() {
    let script = """
      tell application "Terminal"
        activate
      end tell
      """
    if let appleScript = NSAppleScript(source: script) {
      var error: NSDictionary?
      appleScript.executeAndReturnError(&error)
    }
  }

  /// Sign in: use existing auth if present, otherwise open Codex login then poll.
  static func connect(pollSeconds: Int = 120) async throws {
    guard !connectInFlight else { return }
    connectInFlight = true
    defer {
      connectInFlight = false
      loginTerminalLaunched = false
    }

    if let snap = CodexAuthService.loadSnapshot() {
      try await finalizeEnrollment(snapshot: snap)
      return
    }
    launchCodexLogin()
    try await connectAfterLogin(pollSeconds: pollSeconds)
  }

  /// Poll for auth.json after login, then enroll + start proxy.
  private static func connectAfterLogin(pollSeconds: Int = 120) async throws {
    let deadline = Date().addingTimeInterval(TimeInterval(pollSeconds))
    while Date() < deadline {
      if let snap = CodexAuthService.loadSnapshot() {
        try await finalizeEnrollment(snapshot: snap)
        return
      }
      try await Task.sleep(nanoseconds: 2_000_000_000)
    }
    throw EnrollmentError.authFileMissing
  }

  static func disconnect() async {
    CodexAuthService.clearEnrollment()
    await CodexProxyService.shared.stop()
    await CodexProviderBootstrap.clearDaemonProviders()
    try? await APIClient.shared.deactivateChatGPT()
    await FloatingBarUsageLimiter.shared.fetchPlan()
  }

  private static func finalizeEnrollment(snapshot: CodexAuthService.AuthSnapshot) async throws {
    CodexAuthService.markEnrolled()
    await CodexProxyService.shared.ensureRunning()
    guard CodexProxyService.shared.isRunning else {
      CodexAuthService.clearEnrollment()
      throw EnrollmentError.proxyFailed(CodexProxyService.shared.lastError ?? "unknown")
    }

    let fingerprint = CodexAuthService.enrollmentFingerprint(for: snapshot.accountId)
    do {
      try await APIClient.shared.activateChatGPT(fingerprint: fingerprint)
    } catch {
      CodexAuthService.clearEnrollment()
      await CodexProxyService.shared.stop()
      throw EnrollmentError.backendFailed(error.localizedDescription)
    }

    await CodexProviderBootstrap.applyIfNeeded()
    await FloatingBarUsageLimiter.shared.fetchPlan()
    AppState.current?.isPaywalled = false
  }
}
