import AppKit
import Foundation

/// Runs OpenClaw's onboarding from inside the app so a fresh install becomes a
/// working agent without the user dropping to a terminal.
///
/// Unlike Hermes (browser device-code OAuth), `openclaw onboard` runs fully
/// non-interactively: it installs/starts the Gateway daemon and wires the
/// default model to the user's local Claude sign-in (`--auth-choice
/// anthropic-cli`, reusing `~/.claude/.credentials.json` — the same credential
/// Claude Code, the app's native default agent, already uses). So this is a
/// one-shot command with no user interaction, mapped to a simple phase model.
@MainActor
final class OpenClawConnectService: ObservableObject {
    enum Phase: Equatable {
        case idle
        case onboarding
        /// Claude Code isn't available on this Mac, so `--auth-choice
        /// anthropic-cli` has no credential to reuse. The user connects
        /// OpenClaw to a model themselves (Terminal + their own API key)
        /// while the app watches for the config to appear.
        case needsManualModelSetup
        case connected
        case failed(message: String)

        var isBusy: Bool { self == .onboarding }

        var automationValue: String {
            switch self {
            case .idle: return "idle"
            case .onboarding: return "onboarding"
            case .needsManualModelSetup: return "needsManualModelSetup"
            case .connected: return "connected"
            case .failed: return "failed"
            }
        }
    }

    static let shared = OpenClawConnectService()

    @Published private(set) var phase: Phase = .idle

    private var task: Task<Void, Never>?
    private var manualWatchTask: Task<Void, Never>?

    /// Test-only: forces the Claude Code availability probe to a fixed value
    /// so the no-Claude-Code fallback can be exercised without touching the
    /// user's real credentials. Settable only through the local automation
    /// bridge, which exists on non-prod bundles only.
    var claudeCodeAvailabilityOverrideForTesting: Bool?

    private var isClaudeCodeAvailableForOnboard: Bool {
        if let forced = claudeCodeAvailabilityOverrideForTesting { return forced }
        return LocalAgentProviderDetector.isAvailable(.claudeCode)
    }

    var isOnboarded: Bool { OpenClawOnboardProbe.isOnboarded() }

    /// Idempotent, non-interactive onboarding. Installs the Gateway daemon and
    /// configures the default model via the local Claude credential. When no
    /// Claude credential exists, falls back to a user-driven Terminal setup
    /// with the user's own model API key (see `manualModelSetupCommand`).
    func connect() {
        guard !phase.isBusy else { return }
        guard let executable = openClawExecutablePath() else {
            phase = .failed(message: "OpenClaw is not installed. Install it first, then retry.")
            return
        }
        if isOnboarded {
            phase = .connected
            return
        }
        guard isClaudeCodeAvailableForOnboard else {
            // No keychain credential, config token, or claude binary —
            // `anthropic-cli` auth would fail. Hand the model connection to
            // the user and watch for the onboarded config to appear.
            phase = .needsManualModelSetup
            startManualOnboardWatch()
            return
        }

        phase = .onboarding
        log("OpenClawConnect: running non-interactive onboarding via \(executable)")

        task = Task { [weak self] in
            let result = await Self.runOnboard(executable: executable)
            guard let self else { return }
            // Trust the on-disk config over the exit code: a non-zero exit with
            // a fully-written config (e.g. an optional post-step failing) still
            // yields a working agent.
            if OpenClawOnboardProbe.isOnboarded() {
                self.log("OpenClawConnect: onboarded (exit \(result.exitCode))")
                self.phase = .connected
            } else {
                let detail = result.output.isEmpty ? "" : " \(result.output)"
                self.log("OpenClawConnect: onboarding failed (exit \(result.exitCode))\(detail)")
                self.phase = .failed(
                    message: detail.isEmpty ? "OpenClaw setup failed (exit \(result.exitCode))." : detail)
            }
        }
    }

    func cancel() {
        manualWatchTask?.cancel()
        manualWatchTask = nil
        guard phase.isBusy || phase == .needsManualModelSetup else { return }
        task?.cancel()
        task = nil
        phase = .idle
    }

    /// Re-check onboarding on demand (e.g. when a settings card appears).
    func refreshConnectionState() {
        guard !phase.isBusy else { return }
        if case .failed = phase { return }
        if phase == .needsManualModelSetup, !isOnboarded { return }
        phase = isOnboarded ? .connected : .idle
    }

    /// Placeholder the user replaces with their own key in Terminal. The key
    /// goes straight into OpenClaw's own credential store — the app never
    /// sees or stores it.
    static let manualSetupKeyPlaceholder = "YOUR_OPENROUTER_API_KEY"

    /// The Terminal command for connecting OpenClaw to a model without Claude
    /// Code. `--auth-choice openrouter-api-key` is the broadest single-key
    /// option `openclaw onboard` supports (one OpenRouter key covers many
    /// models — the same bring-your-own-key shape as the Hermes fallback);
    /// the remaining flags mirror `onboardArguments`.
    static let manualModelSetupCommand: String =
        "openclaw onboard --non-interactive --accept-risk "
        + "--auth-choice openrouter-api-key --openrouter-api-key \(manualSetupKeyPlaceholder) "
        + "--install-daemon --flow quickstart "
        + "--skip-channels --skip-search --skip-skills --skip-hooks --skip-ui"

    /// Open a fresh Terminal window with the manual setup command pre-typed
    /// but NOT executed: `print -z` pushes the text into zsh's next prompt
    /// buffer, so the user swaps in their real API key and presses return
    /// themselves. (zsh is the macOS default shell; on another shell the
    /// command is still visible in the prompt UI to copy.)
    func openTerminalPreloadedWithManualSetup() {
        // `osascript` subprocess rather than NSAppleScript: NSAppleScript is
        // main-thread-only and silently flaky off it.
        let script = """
        tell application "Terminal"
            activate
            do script "print -z '\(Self.manualModelSetupCommand)'"
        end tell
        """
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process()
            let pipe = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            process.arguments = ["-e", script]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = pipe
            do {
                try process.run()
                process.waitUntilExit()
                if process.terminationStatus != 0 {
                    let data = pipe.fileHandleForReading.readDataToEndOfFile()
                    NSLog("OpenClawConnect: failed to open Terminal: %@",
                          String(data: data, encoding: .utf8) ?? "unknown error")
                }
            } catch {
                NSLog("OpenClawConnect: failed to open Terminal: %@", error.localizedDescription)
            }
        }
    }

    /// Poll the on-disk config while the user completes the Terminal setup;
    /// flips to `.connected` the moment onboarding lands. Bounded (~15 min)
    /// so an abandoned prompt doesn't poll forever.
    private func startManualOnboardWatch() {
        manualWatchTask?.cancel()
        manualWatchTask = Task { [weak self] in
            for _ in 0..<450 {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                if Task.isCancelled { return }
                guard let self, self.phase == .needsManualModelSetup else { return }
                if OpenClawOnboardProbe.isOnboarded() {
                    self.log("OpenClawConnect: manual model setup detected — connected")
                    self.phase = .connected
                    return
                }
            }
        }
    }

    /// The exact arguments used to onboard non-interactively. Kept here (not
    /// inlined) so it is unit-testable and self-documenting.
    static let onboardArguments: [String] = [
        "onboard",
        "--non-interactive",
        "--accept-risk",
        "--auth-choice", "anthropic-cli",
        "--install-daemon",
        "--flow", "quickstart",
        "--skip-channels",
        "--skip-search",
        "--skip-skills",
        "--skip-hooks",
        "--skip-ui",
    ]

    private static func runOnboard(executable: String) async -> ShellInstallCommandResult {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                let pipe = Pipe()
                process.executableURL = URL(fileURLWithPath: executable)
                process.arguments = onboardArguments
                process.standardInput = FileHandle.nullDevice
                process.standardOutput = pipe
                process.standardError = pipe
                do {
                    try process.run()
                    process.waitUntilExit()
                    let data = pipe.fileHandleForReading.readDataToEndOfFile()
                    let output = String(data: data, encoding: .utf8) ?? ""
                    continuation.resume(returning: ShellInstallCommandResult(
                        exitCode: process.terminationStatus,
                        output: Self.tail(output)))
                } catch {
                    continuation.resume(returning: ShellInstallCommandResult(
                        exitCode: -1, output: error.localizedDescription))
                }
            }
        }
    }

    private static func tail(_ output: String) -> String {
        let collapsed = output
            .split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .suffix(6)
            .joined(separator: " ")
        guard collapsed.count > 700 else { return collapsed }
        return String(collapsed.suffix(700))
    }

    private func openClawExecutablePath() -> String? {
        LocalAgentProviderDetector.executablePath(for: .openclaw)
    }

    private func log(_ message: String) {
        NSLog("%@", message)
    }
}
