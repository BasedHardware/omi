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
        case connected
        case failed(message: String)

        var isBusy: Bool { self == .onboarding }

        var automationValue: String {
            switch self {
            case .idle: return "idle"
            case .onboarding: return "onboarding"
            case .connected: return "connected"
            case .failed: return "failed"
            }
        }
    }

    static let shared = OpenClawConnectService()

    @Published private(set) var phase: Phase = .idle

    private var task: Task<Void, Never>?

    var isOnboarded: Bool { OpenClawOnboardProbe.isOnboarded() }

    /// Idempotent, non-interactive onboarding. Installs the Gateway daemon and
    /// configures the default model via the local Claude credential.
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
        guard phase.isBusy else { return }
        task?.cancel()
        task = nil
        phase = .idle
    }

    /// Re-check onboarding on demand (e.g. when a settings card appears).
    func refreshConnectionState() {
        guard !phase.isBusy else { return }
        if case .failed = phase { return }
        phase = isOnboarded ? .connected : .idle
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
