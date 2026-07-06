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
        case missing
        /// Installed on disk, but with no usable inference credential — the
        /// runtime would fail with an opaque provider error, so route the
        /// user to sign-in instead of the installer.
        case needsAuthentication(command: String)
    }

    let provider: AgentPillsManager.DirectedProvider
    let status: Status

    var isAvailable: Bool {
        if case .available = status { return true }
        return false
    }

    var needsAuthentication: Bool {
        if case .needsAuthentication = status { return true }
        return false
    }

    var setupPrompt: String {
        if needsAuthentication, provider == .hermes {
            return "Hermes is installed but isn't signed in yet. I can open the Nous sign-in page in your browser to connect it."
        }
        switch provider {
        case .hermes:
            return "I don't see Hermes connected. I can run the official Hermes installer or open setup docs."
        case .openclaw:
            return "I don't see OpenClaw connected. I can run the official OpenClaw installer or open setup docs."
        case .codex:
            return "I don't see Codex connected. I can run the official Codex CLI installer or open setup docs."
        case .claudeCode:
            return "I don't see Claude Code connected. I can open setup docs so you can connect it."
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
        homeDirectory: String = NSHomeDirectory()
    ) -> LocalAgentProviderAvailability {
        if provider == .claudeCode {
            return claudeCodeAvailability(
                provider: provider,
                environment: environment,
                fileManager: fileManager,
                homeDirectory: homeDirectory
            )
        }
        if let command = configuredCommand(for: provider, environment: environment) {
            return LocalAgentProviderAvailability(provider: provider, status: .available(command: command))
        }

        if let path = firstExecutable(
            named: provider.executableName,
            environment: environment,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        ) {
            if provider == .hermes,
               !HermesAuthProbe.hasAnyInferenceCredential(
                   environment: environment,
                   fileManager: fileManager,
                   homeDirectory: homeDirectory
               ) {
                return LocalAgentProviderAvailability(provider: provider, status: .needsAuthentication(command: path))
            }
            return LocalAgentProviderAvailability(provider: provider, status: .available(command: path))
        }

        return LocalAgentProviderAvailability(provider: provider, status: .missing)
    }

    /// Resolved executable path for a provider's CLI, ignoring any
    /// `OMI_*_ADAPTER_COMMAND` override (those may embed adapter arguments).
    static func executablePath(
        for provider: AgentPillsManager.DirectedProvider,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) -> String? {
        firstExecutable(
            named: provider.executableName,
            environment: environment,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        )
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
        guard !key.isEmpty else { return nil }
        let value = environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? nil : value
    }

    private static func claudeCodeAvailability(
        provider: AgentPillsManager.DirectedProvider,
        environment: [String: String],
        fileManager: FileManager,
        homeDirectory: String
    ) -> LocalAgentProviderAvailability {
        let configPath = (homeDirectory as NSString)
            .appendingPathComponent("Library/Application Support/Claude/config.json")
        if fileManager.fileExists(atPath: configPath),
           let data = fileManager.contents(atPath: configPath),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let tokenCache = json["oauth:tokenCache"] as? String,
           !tokenCache.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return LocalAgentProviderAvailability(provider: provider, status: .available(command: "Claude Code OAuth token"))
        }

        if keychainHasClaudeCodeCredentials() {
            return LocalAgentProviderAvailability(provider: provider, status: .available(command: "Claude Code keychain token"))
        }

        if let path = firstExecutable(
            named: provider.executableName,
            environment: environment,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        ) {
            return LocalAgentProviderAvailability(provider: provider, status: .available(command: path))
        }

        return LocalAgentProviderAvailability(provider: provider, status: .missing)
    }

    private static func keychainHasClaudeCodeCredentials() -> Bool {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        process.arguments = ["find-generic-password", "-s", "Claude Code-credentials"]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus == 0
        } catch {
            return false
        }
    }

    private static func firstExecutable(
        named name: String,
        environment: [String: String],
        fileManager: FileManager,
        homeDirectory: String
    ) -> String? {
        for dir in adapterActivationSearchDirectories(homeDirectory: homeDirectory, environment: environment) {
            let path = (dir as NSString).appendingPathComponent(name)
            if fileManager.isExecutableFile(atPath: path) {
                return path
            }
        }
        return nil
    }

    private static func adapterActivationSearchDirectories(
        homeDirectory: String,
        environment: [String: String]
    ) -> [String] {
        uniqueDirectories(
            (environment["PATH"] ?? "").split(separator: ":").map(String.init) + [
            "\(homeDirectory)/.hermes/hermes-agent/venv/bin",
            "\(homeDirectory)/.hermes/node/bin",
            "\(homeDirectory)/.hermes/hermes-agent",
            "\(homeDirectory)/.openclaw/bin",
            "\(homeDirectory)/.openclaw/node/bin",
            "\(homeDirectory)/.local/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
        ])
    }

    private static func uniqueDirectories(_ directories: [String]) -> [String] {
        var seen = Set<String>()
        var result: [String] = []
        for directory in directories where !directory.isEmpty && !seen.contains(directory) {
            seen.insert(directory)
            result.append(directory)
        }
        return result
    }
}
