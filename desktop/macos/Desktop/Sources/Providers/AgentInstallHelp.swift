import Foundation

struct LocalAgentInstallPlan: Equatable {
    let provider: AgentPillsManager.DirectedProvider
    let installCommand: String?
    let documentationURL: URL
    let postInstallInstruction: String

    var commandDisplay: String {
        installCommand ?? "Open setup documentation"
    }

    var docsActionTitle: String {
        "Open docs"
    }
}

struct AgentInstallRetryContext: Equatable {
    let originalRequest: String
    let rewrittenQuery: String
    let title: String
    let ack: String
    let fromVoice: Bool
}

enum AgentInstallPromptAction {
    case beginConnection
    case runSetup
    case openDocs
}

enum AgentInstallStatus: Equatable {
    case ready
    case confirming
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

    var automationValue: String {
        switch self {
        case .ready: return "ready"
        case .confirming: return "confirming"
        case .installing: return "installing"
        case .cancelled: return "cancelled"
        case .docsOpened: return "docsOpened"
        case .connected: return "connected"
        case .commandFailed: return "commandFailed"
        case .finishedButMissing: return "finishedButMissing"
        }
    }
}

struct AgentInstallPromptState: Equatable {
    static let setupConfirmationDelay: TimeInterval = 2.5

    let plan: LocalAgentInstallPlan
    let retryContext: AgentInstallRetryContext?
    var status: AgentInstallStatus = .ready
    var confirmingSince: Date?

    init(
        plan: LocalAgentInstallPlan,
        retryContext: AgentInstallRetryContext? = nil,
        status: AgentInstallStatus = .ready,
        confirmingSince: Date? = nil
    ) {
        self.plan = plan
        self.retryContext = retryContext
        self.status = status
        self.confirmingSince = confirmingSince
    }

    var detailText: String {
        switch status {
        case .ready:
            if plan.installCommand != nil {
                return "Omi will run the official setup command, then check the connection."
            }
            return plan.postInstallInstruction
        case .confirming:
            return "Ready to run the setup command shown below."
        case .installing:
            return "Connecting \(plan.provider.displayName)…"
        case .cancelled:
            return "Connection cancelled."
        case .docsOpened:
            return "Opened setup docs. \(plan.postInstallInstruction)"
        case .connected:
            if retryContext != nil {
                return "\(plan.provider.displayName) is connected. Retrying your request now."
            }
            return "\(plan.provider.displayName) is connected. Try your request again."
        case .commandFailed(let exitCode, let output):
            let suffix = output.isEmpty ? "" : " \(output)"
            return "Setup failed with exit code \(exitCode).\(suffix)"
        case .finishedButMissing(let output):
            let suffix = output.isEmpty ? "" : " \(output)"
            return "Setup finished, but Omi still can't find \(plan.provider.displayName). \(plan.postInstallInstruction)\(suffix)"
        }
    }

    var primaryActionTitle: String {
        switch status {
        case .confirming:
            return "Run setup"
        default:
            return "Connect \(plan.provider.displayName)"
        }
    }

    var primaryAction: AgentInstallPromptAction {
        switch status {
        case .confirming:
            return .runSetup
        default:
            return .beginConnection
        }
    }

    var primaryActionEnabled: Bool {
        switch status {
        case .installing, .connected:
            return false
        case .confirming:
            return confirmingSince == nil
        default:
            return true
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
        case .claudeCode:
            return LocalAgentInstallPlan(
                provider: self,
                installCommand: nil,
                documentationURL: URL(string: "https://claude.ai/code")!,
                postInstallInstruction: "Install Claude Code and sign in, then try again.")
        }
    }
}
