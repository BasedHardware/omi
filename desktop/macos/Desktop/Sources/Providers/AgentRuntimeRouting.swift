import Foundation

enum AgentHarnessMode: String {
    case piMono = "piMono"
    case acp = "acp"
    case hermes = "hermes"
    case openclaw = "openclaw"
    case codex = "codex"
}

extension Optional where Wrapped == AgentHarnessMode {
    /// Whether a pill renders an external-provider identity mark (a dedicated
    /// logo, or the robot catch-all) instead of the native Omi dot/badge.
    /// Omi-native agents (`nil` override) keep their round dot.
    var rendersProviderMark: Bool { self != nil }
}

enum AgentAdapterId: String {
    case piMono = "pi-mono"
    case acp = "acp"
    case hermes = "hermes"
    case openclaw = "openclaw"
    case codex = "codex"
}

enum AgentRuntimeRouting {
    static func harnessMode(for mode: ChatProvider.BridgeMode) -> AgentHarnessMode {
        switch mode {
        case .omiAI, .piMono:
            return .piMono
        case .userClaude:
            return .acp
        case .hermes:
            return .hermes
        case .openClaw:
            return .openclaw
        case .codex:
            return .codex
        }
    }

    static func harnessMode(from rawValue: String) -> AgentHarnessMode? {
        switch rawValue {
        case AgentHarnessMode.piMono.rawValue, "pi-mono":
            return .piMono
        case AgentHarnessMode.acp.rawValue:
            return .acp
        case AgentHarnessMode.hermes.rawValue:
            return .hermes
        case AgentHarnessMode.openclaw.rawValue, "openClaw":
            return .openclaw
        case AgentHarnessMode.codex.rawValue:
            return .codex
        default:
            return nil
        }
    }

    static func adapterId(for harnessMode: AgentHarnessMode) -> AgentAdapterId {
        switch harnessMode {
        case .piMono:
            return .piMono
        case .acp:
            return .acp
        case .hermes:
            return .hermes
        case .openclaw:
            return .openclaw
        case .codex:
            return .codex
        }
    }
}

struct LocalAgentProviderAvailability: Equatable {
    enum Status: Equatable {
        case available(command: String)
        /// The binary is installed but no credential was found (Codex only).
        /// Spawning would fail after the fact, so callers should surface
        /// `setupPrompt` instead of starting the agent.
        case needsAuth(command: String)
        case missing
    }

    let provider: AgentPillsManager.DirectedProvider
    let status: Status

    var isAvailable: Bool {
        if case .available = status { return true }
        return false
    }

    var setupPrompt: String {
        if case .needsAuth = status {
            switch provider {
            case .codex:
                return "Codex is installed but not signed in. Run `codex login` in Terminal, or add an OpenAI API key in Omi Settings, then try again."
            case .hermes, .openclaw:
                return "\(provider.displayName) needs setup before it can run. Check its sign-in, then try again."
            }
        }
        switch provider {
        case .hermes:
            return "I don't see Hermes installed. Install the Hermes agent from Nous Research (hermes-agent.nousresearch.com), then try again."
        case .openclaw:
            return "I don't see OpenClaw installed. Install it with `npm i -g openclaw`, start it with `openclaw gateway`, then try again."
        case .codex:
            return "I don't see Codex installed. Install it with `npm i -g @openai/codex @agentclientprotocol/codex-acp`, then try again."
        }
    }

    var toolError: String {
        "Error: \(setupPrompt)"
    }
}

enum LocalAgentProviderDetector {
    static func availability(
        for provider: AgentPillsManager.DirectedProvider,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory(),
        byokOpenAIKeyPresent: Bool? = nil
    ) -> LocalAgentProviderAvailability {
        let command: String? =
            configuredCommand(for: provider, environment: environment)
            ?? firstExecutable(
                named: provider.executableName,
                fileManager: fileManager,
                homeDirectory: homeDirectory
            )

        guard let command else {
            return LocalAgentProviderAvailability(provider: provider, status: .missing)
        }

        // Codex pre-flight: the binary alone isn't enough — codex-acp fails
        // post-spawn without a credential (NO_BROWSER blocks interactive
        // login). Detect that up front so callers show sign-in guidance
        // instead of spawning into a guaranteed failure.
        if provider == .codex,
            !codexCredentialPresent(
                environment: environment,
                fileManager: fileManager,
                homeDirectory: homeDirectory,
                byokOpenAIKeyPresent: byokOpenAIKeyPresent ?? (APIKeyService.byokKey(.openai) != nil)
            )
        {
            return LocalAgentProviderAvailability(provider: provider, status: .needsAuth(command: command))
        }

        return LocalAgentProviderAvailability(provider: provider, status: .available(command: command))
    }

    /// Whether any Codex credential source is present: an API key in the
    /// environment, a `codex login` session (~/.codex/auth.json), or an
    /// in-app BYOK OpenAI key (seeded as OPENAI_API_KEY at bridge spawn).
    static func codexCredentialPresent(
        environment: [String: String],
        fileManager: FileManager,
        homeDirectory: String,
        byokOpenAIKeyPresent: Bool
    ) -> Bool {
        for key in ["OPENAI_API_KEY", "CODEX_API_KEY"] {
            if !(environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true) {
                return true
            }
        }
        if fileManager.fileExists(atPath: "\(homeDirectory)/.codex/auth.json") {
            return true
        }
        return byokOpenAIKeyPresent
    }

    static func isAvailable(
        _ provider: AgentPillsManager.DirectedProvider,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) -> Bool {
        availability(for: provider, environment: environment, fileManager: fileManager, homeDirectory: homeDirectory).isAvailable
    }

    private static func configuredCommand(
        for provider: AgentPillsManager.DirectedProvider,
        environment: [String: String]
    ) -> String? {
        let key = provider.commandEnvironmentName
        let value = environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? nil : value
    }

    private static func firstExecutable(
        named name: String,
        fileManager: FileManager,
        homeDirectory: String
    ) -> String? {
        for dir in adapterActivationSearchDirectories(homeDirectory: homeDirectory) {
            let path = (dir as NSString).appendingPathComponent(name)
            if fileManager.isExecutableFile(atPath: path) {
                return path
            }
        }
        return nil
    }

    private static func adapterActivationSearchDirectories(homeDirectory: String) -> [String] {
        [
            "\(homeDirectory)/.hermes/hermes-agent/venv/bin",
            "\(homeDirectory)/.hermes/node/bin",
            "\(homeDirectory)/.hermes/hermes-agent",
            "\(homeDirectory)/.codex/bin",
            "\(homeDirectory)/.local/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
        ]
    }
}
