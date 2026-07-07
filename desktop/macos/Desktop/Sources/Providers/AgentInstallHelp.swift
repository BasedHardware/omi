import Foundation

struct LocalAgentInstallPlan: Equatable {
    enum Kind: Equatable {
        /// Provider binary is missing — run the official installer.
        case install
        /// Provider is installed but signed out — run its sign-in flow.
        case authenticate
    }

    let provider: AgentPillsManager.DirectedProvider
    let installCommand: String?
    let documentationURL: URL
    let postInstallInstruction: String
    var kind: Kind = .install

    var commandDisplay: String {
        if kind == .authenticate {
            return "Opens the sign-in page in your browser"
        }
        return installCommand ?? "Open setup documentation"
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
    /// Open Terminal with the manual model-setup command pre-typed (OpenClaw
    /// without Claude Code).
    case openTerminalSetup
}

enum AgentInstallStatus: Equatable {
    case ready
    case confirming
    case installing
    case waitingForApproval(userCode: String?)
    /// The provider needs the user to connect a model themselves in Terminal
    /// (e.g. OpenClaw with no Claude Code credential to reuse). `command` is
    /// shown in the prompt and pre-typed into Terminal.
    case needsManualModelSetup(command: String)
    case cancelled
    case docsOpened
    case connected
    case commandFailed(exitCode: Int32, output: String)
    case authFailed(message: String)
    case finishedButMissing(output: String)

    var isBusy: Bool {
        switch self {
        case .installing, .waitingForApproval: return true
        default: return false
        }
    }

    var automationValue: String {
        switch self {
        case .ready: return "ready"
        case .confirming: return "confirming"
        case .installing: return "installing"
        case .waitingForApproval: return "waitingForApproval"
        case .needsManualModelSetup: return "needsManualModelSetup"
        case .cancelled: return "cancelled"
        case .docsOpened: return "docsOpened"
        case .connected: return "connected"
        case .commandFailed: return "commandFailed"
        case .authFailed: return "authFailed"
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
            if plan.kind == .authenticate {
                // OpenClaw's connect is a non-interactive setup run, not a
                // browser sign-in — describe it accurately.
                if plan.provider == .openclaw {
                    return "Omi will set up OpenClaw automatically (Gateway + your Claude sign-in), then check the connection."
                }
                return "Omi will open the sign-in page in your browser, then wait for your approval."
            }
            if plan.installCommand != nil {
                return "Omi will run the official setup command, then check the connection."
            }
            return plan.postInstallInstruction
        case .confirming:
            return "Ready to run the setup command shown below."
        case .installing:
            return "Connecting \(plan.provider.displayName)…"
        case .waitingForApproval(let userCode):
            if let userCode, !userCode.isEmpty {
                return "Waiting for approval in your browser… If the page asks for a code, enter the one below."
            }
            return "Waiting for approval in your browser…"
        case .needsManualModelSetup:
            return "Claude Code isn't set up on this Mac, so OpenClaw needs its own model key. "
                + "Get an openrouter.ai API key, run the command below with it, and "
                + "Omi will connect automatically."
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
        case .authFailed(let message):
            let suffix = message.isEmpty ? "" : " \(message)"
            return "Sign-in didn't finish.\(suffix) You can retry below."
        case .finishedButMissing(let output):
            let suffix = output.isEmpty ? "" : " \(output)"
            return "Setup finished, but Omi still can't find \(plan.provider.displayName). \(plan.postInstallInstruction)\(suffix)"
        }
    }

    var primaryActionTitle: String {
        switch status {
        case .confirming:
            return "Run setup"
        case .authFailed:
            return "Retry sign-in"
        case .needsManualModelSetup:
            return "Open Terminal"
        default:
            return "Connect \(plan.provider.displayName)"
        }
    }

    var primaryAction: AgentInstallPromptAction {
        switch status {
        case .confirming:
            return .runSetup
        case .needsManualModelSetup:
            return .openTerminalSetup
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
    /// Sign-in plan for a provider that is installed but has no usable
    /// credentials. Only Hermes has an app-driven flow today (Nous Portal
    /// device-code OAuth); other providers fall back to their install plan.
    var authenticationPlan: LocalAgentInstallPlan {
        switch self {
        case .hermes:
            return LocalAgentInstallPlan(
                provider: self,
                installCommand: nil,
                documentationURL: URL(string: "https://hermes-agent.nousresearch.com/docs/integrations/nous-portal")!,
                postInstallInstruction: "Approve the sign-in in your browser, then try your request again.",
                kind: .authenticate)
        case .openclaw:
            // OpenClaw's "sign-in" is a non-interactive `openclaw onboard` run
            // (Gateway daemon + model auth via the local Claude credential), so
            // no browser step — the connect action does it all.
            return LocalAgentInstallPlan(
                provider: self,
                installCommand: nil,
                documentationURL: URL(string: "https://docs.openclaw.ai/cli/onboard")!,
                postInstallInstruction: "Omi will set up OpenClaw's Gateway and connect it to your Claude sign-in, then try your request again.",
                kind: .authenticate)
        default:
            return installPlan
        }
    }

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
