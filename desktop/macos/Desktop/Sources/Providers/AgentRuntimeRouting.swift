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
        case missing
    }

    let provider: AgentPillsManager.DirectedProvider
    let status: Status

    var isAvailable: Bool {
        if case .available = status { return true }
        return false
    }

    var setupPrompt: String {
        switch provider {
        case .hermes:
            return "I don't see Hermes installed. Make sure Hermes is installed first, then try again."
        case .openclaw:
            return "I don't see OpenClaw installed. Make sure OpenClaw is installed first, then try again."
        case .codex:
            return "I don't see Codex installed. Please run 'npm install -g @openai/codex' and run 'codex' in your terminal to sign in, then try again."
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
        if let command = configuredCommand(for: provider, environment: environment) {
            return LocalAgentProviderAvailability(provider: provider, status: .available(command: command))
        }

        if let path = firstExecutable(
            named: provider.executableName,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        ) {
            return LocalAgentProviderAvailability(provider: provider, status: .available(command: path))
        }

        return LocalAgentProviderAvailability(provider: provider, status: .missing)
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
        for dir in adapterActivationSearchDirectories(homeDirectory: homeDirectory, fileManager: fileManager) {
            let path = (dir as NSString).appendingPathComponent(name)
            if fileManager.isExecutableFile(atPath: path) {
                return path
            }
        }
        return nil
    }

    static func adapterActivationSearchDirectories(
        homeDirectory: String,
        fileManager: FileManager = .default
    ) -> [String] {
        var directories = [
            "\(homeDirectory)/.hermes/hermes-agent/venv/bin",
            "\(homeDirectory)/.hermes/node/bin",
            "\(homeDirectory)/.hermes/hermes-agent",
            "\(homeDirectory)/.local/bin",
            "\(homeDirectory)/.npm-global/bin",
            "\(homeDirectory)/.volta/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
        ]
        directories.append(contentsOf: nvmBinDirectories(homeDirectory: homeDirectory, fileManager: fileManager))
        return directories
    }

    private static func nvmBinDirectories(
        homeDirectory: String,
        fileManager: FileManager
    ) -> [String] {
        let nvmRoot = (homeDirectory as NSString).appendingPathComponent(".nvm/versions/node")
        guard let versions = try? fileManager.contentsOfDirectory(atPath: nvmRoot) else {
            return []
        }
        return versions
            .sorted { lhs, rhs in lhs.compare(rhs, options: .numeric) == .orderedDescending }
            .map { (nvmRoot as NSString).appendingPathComponent("\($0)/bin") }
    }
}

enum AgentTaskKind: Equatable {
    case coding
    case automation
    case general
}

struct AgentSpawnContext: Equatable {
    let taskKind: AgentTaskKind
    let explicitProvider: AgentPillsManager.DirectedProvider?
    let fallbackChain: [AgentHarnessMode?]
    var attemptedHarnesses: [AgentHarnessMode?]

    func nextFallback(after current: AgentHarnessMode?) -> AgentHarnessMode?? {
        guard let currentIndex = fallbackChain.firstIndex(where: { $0 == current }) else {
            return fallbackChain.first { harness in
                !attemptedHarnesses.contains(where: { $0 == harness })
            }
        }
        for harness in fallbackChain.dropFirst(currentIndex + 1) {
            if !attemptedHarnesses.contains(where: { $0 == harness }) {
                return harness
            }
        }
        return nil
    }

    mutating func recordAttempt(_ harness: AgentHarnessMode?) {
        if !attemptedHarnesses.contains(where: { $0 == harness }) {
            attemptedHarnesses.append(harness)
        }
    }
}

enum LocalAgentProviderRouting {
    enum Resolution: Equatable {
        case spawn(AgentSpawnPlan)
        case setupRequired(
            provider: AgentPillsManager.DirectedProvider,
            prompt: String,
            spokenStatus: String
        )
    }

    struct AgentSpawnPlan: Equatable {
        let harnessOverride: AgentHarnessMode?
        let title: String
        let ack: String
        let selectedProvider: AgentPillsManager.DirectedProvider?
        let usedFallback: Bool
        let fallbackNote: String?
        let context: AgentSpawnContext
    }

    static func classifyTask(_ text: String) -> AgentTaskKind {
        let lower = text.lowercased()
        let codingSignals = [
            "code", "script", "debug", "refactor", "compile", "function", "class", "api",
            "bug", "implement", "python", "swift", "typescript", "javascript", "repo",
            "repository", "pull request", "unit test", "lint", "syntax",
        ]
        if codingSignals.contains(where: { lower.contains($0) }) {
            return .coding
        }
        let automationSignals = [
            "automate", "click", "open app", "send email", "browser", "download",
            "upload", "reminder", "notes app", "messages app", "files app", "folder",
        ]
        if automationSignals.contains(where: { lower.contains($0) }) {
            return .automation
        }
        return .general
    }

    static func preferredProviders(for task: AgentTaskKind) -> [AgentPillsManager.DirectedProvider] {
        switch task {
        case .coding:
            return [.codex, .hermes, .openclaw]
        case .automation:
            return [.openclaw, .codex, .hermes]
        case .general:
            return [.openclaw, .codex, .hermes]
        }
    }

    static func explicitProvider(in text: String) -> AgentPillsManager.DirectedProvider? {
        AgentPillsManager.providerDirective(from: text)?.provider
    }

    static func isExplicitProviderRequest(
        _ provider: AgentPillsManager.DirectedProvider,
        in text: String
    ) -> Bool {
        if explicitProvider(in: text) == provider {
            return true
        }
        let openClawPattern = #"(?i)\bopen\s*claw\b"#
        switch provider {
        case .openclaw:
            return text.range(of: openClawPattern, options: .regularExpression) != nil
        case .hermes, .codex:
            let pattern = #"(?i)\b\#(provider.rawValue)\b"#
            return text.range(of: pattern, options: .regularExpression) != nil
        }
    }

    static func isRetriableSpawnFailure(_ message: String) -> Bool {
        let lower = message.lowercased()
        return lower.contains("not available")
            || lower.contains("failed to start")
            || lower.contains("adapter")
            || lower.contains("enoent")
            || lower.contains("command not found")
            || lower.contains("activation")
    }

    static func resolveSpawn(
        brief: String,
        requestedProvider: AgentPillsManager.DirectedProvider?,
        userRequestText: String?,
        title: String?,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) -> Resolution {
        let taskKind = classifyTask(brief)
        // Only treat a provider as user-directed when it appears in the user's own
        // words. The model-authored `brief` often names a provider the model chose
        // (e.g. "use Hermes to refactor…") even when the user never said it.
        let userText = userRequestText?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let explicit = userText.isEmpty ? nil : AgentPillsManager.DirectedProvider.allCases.first {
            isExplicitProviderRequest($0, in: userText)
        }

        if let explicit {
            let availability = LocalAgentProviderDetector.availability(
                for: explicit,
                environment: environment,
                fileManager: fileManager,
                homeDirectory: homeDirectory
            )
            guard availability.isAvailable else {
                return .setupRequired(
                    provider: explicit,
                    prompt: availability.setupPrompt,
                    spokenStatus: explicit.setupNeededStatus
                )
            }
            let resolvedTitle = normalizedTitle(title, provider: explicit)
            return .spawn(
                AgentSpawnPlan(
                    harnessOverride: explicit.harnessMode,
                    title: resolvedTitle,
                    ack: "Asking \(explicit.displayName).",
                    selectedProvider: explicit,
                    usedFallback: false,
                    fallbackNote: nil,
                    context: spawnContext(
                        taskKind: taskKind,
                        explicitProvider: explicit,
                        selectedHarness: explicit.harnessMode,
                        environment: environment,
                        fileManager: fileManager,
                        homeDirectory: homeDirectory
                    )
                )
            )
        }

        let orderedProviders = preferredProviders(for: taskKind)
        let availableProviders = orderedProviders.filter {
            LocalAgentProviderDetector.isAvailable(
                $0,
                environment: environment,
                fileManager: fileManager,
                homeDirectory: homeDirectory
            )
        }

        if let requestedProvider {
            if LocalAgentProviderDetector.isAvailable(
                requestedProvider,
                environment: environment,
                fileManager: fileManager,
                homeDirectory: homeDirectory
            ) {
                let resolvedTitle = normalizedTitle(title, provider: requestedProvider)
                return .spawn(
                    AgentSpawnPlan(
                        harnessOverride: requestedProvider.harnessMode,
                        title: resolvedTitle,
                        ack: "Starting \(requestedProvider.displayName).",
                        selectedProvider: requestedProvider,
                        usedFallback: false,
                        fallbackNote: nil,
                        context: spawnContext(
                            taskKind: taskKind,
                            explicitProvider: nil,
                            selectedHarness: requestedProvider.harnessMode,
                            environment: environment,
                            fileManager: fileManager,
                            homeDirectory: homeDirectory
                        )
                    )
                )
            }

            if let fallbackProvider = availableProviders.first {
                let note = "\(requestedProvider.displayName) isn't installed; using \(fallbackProvider.displayName) instead."
                let resolvedTitle = normalizedTitle(title, provider: fallbackProvider)
                return .spawn(
                    AgentSpawnPlan(
                        harnessOverride: fallbackProvider.harnessMode,
                        title: resolvedTitle,
                        ack: note,
                        selectedProvider: fallbackProvider,
                        usedFallback: true,
                        fallbackNote: note,
                        context: spawnContext(
                            taskKind: taskKind,
                            explicitProvider: nil,
                            selectedHarness: fallbackProvider.harnessMode,
                            environment: environment,
                            fileManager: fileManager,
                            homeDirectory: homeDirectory
                        )
                    )
                )
            }
        }

        if let primary = availableProviders.first {
            let resolvedTitle = normalizedTitle(title, provider: primary)
            return .spawn(
                AgentSpawnPlan(
                    harnessOverride: primary.harnessMode,
                    title: resolvedTitle,
                    ack: "Starting \(primary.displayName).",
                    selectedProvider: primary,
                    usedFallback: false,
                    fallbackNote: nil,
                    context: spawnContext(
                        taskKind: taskKind,
                        explicitProvider: nil,
                        selectedHarness: primary.harnessMode,
                        environment: environment,
                        fileManager: fileManager,
                        homeDirectory: homeDirectory
                    )
                )
            )
        }

        let resolvedTitle = normalizedTitle(title, provider: nil)
        return .spawn(
            AgentSpawnPlan(
                harnessOverride: nil,
                title: resolvedTitle,
                ack: "Starting a background agent.",
                selectedProvider: nil,
                usedFallback: false,
                fallbackNote: nil,
                context: spawnContext(
                    taskKind: taskKind,
                    explicitProvider: nil,
                    selectedHarness: nil,
                    environment: environment,
                    fileManager: fileManager,
                    homeDirectory: homeDirectory
                )
            )
        )
    }

    private static func normalizedTitle(
        _ title: String?,
        provider: AgentPillsManager.DirectedProvider?
    ) -> String {
        let trimmed = title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !trimmed.isEmpty { return trimmed }
        return provider?.displayName ?? "Background agent"
    }

    private static func spawnContext(
        taskKind: AgentTaskKind,
        explicitProvider: AgentPillsManager.DirectedProvider?,
        selectedHarness: AgentHarnessMode?,
        environment: [String: String],
        fileManager: FileManager,
        homeDirectory: String
    ) -> AgentSpawnContext {
        let availableHarnesses = preferredProviders(for: taskKind)
            .filter {
                LocalAgentProviderDetector.isAvailable(
                    $0,
                    environment: environment,
                    fileManager: fileManager,
                    homeDirectory: homeDirectory
                )
            }
            .map(\.harnessMode)
        let fallbackChain = availableHarnesses + [nil]
        return AgentSpawnContext(
            taskKind: taskKind,
            explicitProvider: explicitProvider,
            fallbackChain: fallbackChain,
            attemptedHarnesses: [selectedHarness]
        )
    }
}
