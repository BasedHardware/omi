import Foundation

struct LocalAgentInstallPlan: Equatable {
    let provider: AgentPillsManager.DirectedProvider
    let installCommand: String?
    let documentationURL: URL
    let postInstallInstruction: String

    var commandDisplay: String {
        installCommand ?? "Open setup documentation"
    }

    var primaryActionTitle: String {
        installCommand == nil ? "Open setup" : "Install \(provider.displayName)"
    }

    var docsActionTitle: String {
        "Open docs"
    }
}

enum AgentInstallPromptAction {
    case install
    case openDocs
}

enum AgentInstallStatus: Equatable {
    case ready
    case installing
    case cancelled
    case docsOpened
    case connected
    case commandFailed(exitCode: Int32, output: String)
    case finishedButMissing(output: String)

    var isBusy: Bool {
        if case .installing = self { return true }
        return false
    }
}

struct AgentInstallPromptState: Equatable {
    let plan: LocalAgentInstallPlan
    var status: AgentInstallStatus = .ready

    var detailText: String {
        switch status {
        case .ready:
            if let command = plan.installCommand {
                return "Official installer: \(command)"
            }
            return plan.postInstallInstruction
        case .installing:
            return "Running installer, then checking whether \(plan.provider.displayName) is connected."
        case .cancelled:
            return "Install cancelled."
        case .docsOpened:
            return "Opened setup docs. \(plan.postInstallInstruction)"
        case .connected:
            return "\(plan.provider.displayName) is connected. Retry the request when you're ready."
        case .commandFailed(let exitCode, let output):
            let suffix = output.isEmpty ? "" : " \(output)"
            return "Installer failed with exit code \(exitCode).\(suffix)"
        case .finishedButMissing(let output):
            let suffix = output.isEmpty ? "" : " \(output)"
            return "Installer finished, but Omi still can't find \(plan.provider.displayName). \(plan.postInstallInstruction)\(suffix)"
        }
    }
}

struct ShellInstallCommandResult: Equatable {
    let exitCode: Int32
    let output: String
}

enum AgentInstallCommandRunner {
    static func run(_ command: String) async -> ShellInstallCommandResult {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                let outputPipe = Pipe()
                process.executableURL = URL(fileURLWithPath: "/bin/zsh")
                process.arguments = ["-lc", command]
                process.standardOutput = outputPipe
                process.standardError = outputPipe

                do {
                    try process.run()
                    process.waitUntilExit()
                    let data = outputPipe.fileHandleForReading.readDataToEndOfFile()
                    let output = String(data: data, encoding: .utf8) ?? ""
                    continuation.resume(
                        returning: ShellInstallCommandResult(
                            exitCode: process.terminationStatus,
                            output: trimmedInstallerOutput(output)))
                } catch {
                    continuation.resume(
                        returning: ShellInstallCommandResult(
                            exitCode: -1,
                            output: error.localizedDescription))
                }
            }
        }
    }

    private static func trimmedInstallerOutput(_ output: String) -> String {
        let collapsed = output
            .split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .suffix(6)
            .joined(separator: " ")
        guard collapsed.count > 700 else { return collapsed }
        return String(collapsed.suffix(700))
    }
}

extension AgentPillsManager.DirectedProvider {
    var installPlan: LocalAgentInstallPlan {
        switch self {
        case .hermes:
            return LocalAgentInstallPlan(
                provider: self,
                installCommand: "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash",
                documentationURL: URL(string: "https://hermes-agent.nousresearch.com/docs/getting-started/installation")!,
                postInstallInstruction: "Reload your shell or restart Omi, then run hermes once if setup asks for it.")
        case .openclaw:
            return LocalAgentInstallPlan(
                provider: self,
                installCommand: "curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard",
                documentationURL: URL(string: "https://docs.openclaw.ai/install")!,
                postInstallInstruction: "Run openclaw onboard if account setup is still needed, then retry.")
        case .codex:
            return LocalAgentInstallPlan(
                provider: self,
                installCommand: "curl -fsSL https://chatgpt.com/codex/install.sh | sh",
                documentationURL: URL(string: "https://developers.openai.com/codex/cli")!,
                postInstallInstruction: "Run codex once and sign in, then retry.")
        }
    }
}
