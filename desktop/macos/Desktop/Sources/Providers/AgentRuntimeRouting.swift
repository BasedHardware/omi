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
    switch provider {
    case .hermes:
      return
        "I don't see Hermes installed. Install it by running: curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash — then try again."
    case .openclaw:
      return
        "I don't see OpenClaw installed. Install it by running: curl -fsSL https://openclaw.ai/install.sh | bash — then try again."
    case .codex:
      return
        "I don't see Codex set up for Omi. Install it by running: npm install -g @openai/codex @agentclientprotocol/codex-acp — then sign in with codex login and try again."
    }
  }

    /// The one-line install command surfaced by the install-helper UI.
    var installCommand: String { provider.installCommand }

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
        if codexAuthFileHasCredential(path: "\(homeDirectory)/.codex/auth.json") {
            return true
        }
        return byokOpenAIKeyPresent
    }

    /// A `codex login` session is only valid if auth.json actually carries a
    /// token — an empty/stale/corrupt `{}` file would otherwise pass the
    /// pre-flight and spawn Codex into a post-hoc auth failure.
    private static func codexAuthFileHasCredential(path: String) -> Bool {
        guard let data = FileManager.default.contents(atPath: path),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return false
        }
        // codex-acp / Codex store either an API key or an OAuth/ChatGPT token.
        let credentialKeys = ["OPENAI_API_KEY", "openai_api_key", "tokens", "access_token", "id_token"]
        return credentialKeys.contains { key in
            if let str = json[key] as? String { return !str.trimmingCharacters(in: .whitespaces).isEmpty }
            return json[key] != nil
        }
    }

    if let path = firstExecutable(
      named: provider.executableName,
      fileManager: fileManager,
      environment: environment,
      homeDirectory: homeDirectory
    ) {
      return LocalAgentProviderAvailability(provider: provider, status: .available(command: path))
    }

    return LocalAgentProviderAvailability(provider: provider, status: .missing)
  }

    static func firstExecutable(
        named name: String,
        fileManager: FileManager,
        homeDirectory: String,
        searchDirectories: [String]? = nil
    ) -> String? {
        for dir in adapterActivationSearchDirectories(homeDirectory: homeDirectory, fileManager: fileManager) {
            let path = (dir as NSString).appendingPathComponent(name)
            if fileManager.isExecutableFile(atPath: path) {
                return path
            }
        }
        return nil
    }

    /// Curated directories both the detector (here) and the runtime bridge
    /// (AgentRuntimeProcess) search for external agent binaries. Shared so the
    /// two never disagree about whether an agent is available. Deliberately a
    /// whitelist of well-known install locations (package managers + version
    /// managers) rather than the inherited PATH: discovered binaries are
    /// launched as child processes, so arbitrary user-controlled PATH entries
    /// must not participate in discovery.
    static func adapterActivationSearchDirectories(
        homeDirectory: String,
        fileManager: FileManager = .default
    ) -> [String] {
        var dirs = [
            "\(homeDirectory)/.hermes/hermes-agent/venv/bin",
            "\(homeDirectory)/.hermes/node/bin",
            "\(homeDirectory)/.hermes/hermes-agent",
            "\(homeDirectory)/.codex/bin",
            "\(homeDirectory)/.local/bin",
            "\(homeDirectory)/.volta/bin",
            "\(homeDirectory)/.asdf/shims",
            "\(homeDirectory)/.npm-global/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
        ]
        dirs.append(contentsOf: nvmVersionBinDirectories(homeDirectory: homeDirectory, fileManager: fileManager))
        return dirs
    }

    /// nvm installs global binaries under versioned dirs; include each
    /// installed version's bin (newest first). This is the only entry that
    /// needs filesystem I/O, and availability checks run on hot paths (router
    /// prompt builds, spawn pre-flights), so the scan is cached per home
    /// directory for the process lifetime — like the rest of the whitelist, a
    /// mid-session install is picked up after reconnect/restart. Tests that
    /// inject a custom FileManager bypass the cache to stay deterministic.
    private static let nvmBinDirsCache = ProcessLifetimeCache()

    private static func nvmVersionBinDirectories(homeDirectory: String, fileManager: FileManager) -> [String] {
        let compute: () -> [String] = {
            let nvmVersions = "\(homeDirectory)/.nvm/versions/node"
            guard let versions = try? fileManager.contentsOfDirectory(atPath: nvmVersions) else { return [] }
            return versions
                .sorted { $0.compare($1, options: .numeric) == .orderedDescending }
                .map { "\(nvmVersions)/\($0)/bin" }
        }
        guard fileManager === FileManager.default else { return compute() }
        return nvmBinDirsCache.value(forKey: homeDirectory, compute: compute)
    }

    private final class ProcessLifetimeCache: @unchecked Sendable {
        private let lock = NSLock()
        private var storage: [String: [String]] = [:]

        func value(forKey key: String, compute: () -> [String]) -> [String] {
            lock.lock()
            defer { lock.unlock() }
            if let cached = storage[key] { return cached }
            let value = compute()
            storage[key] = value
            return value
        }
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
        // Consider ALL unattempted providers in fallbackChain, not just ones
        // ranked after `current`. When the user explicitly requested a provider
        // that isn't the first in the preference order, we still want to try
        // higher-preference providers on failure.
        return fallbackChain.first { harness in
            harness != current && !attemptedHarnesses.contains(where: { $0 == harness })
        }
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

    /// Whether the provider name is preceded by a negation word, so a bare
    /// mention like "don't use Hermes" does not count as an explicit request.
    private static func isNegated(
        _ provider: AgentPillsManager.DirectedProvider,
        in text: String
    ) -> Bool {
        let lower = text.lowercased()
        let name = provider.rawValue
        let negationPhrases = [
            "don't use \(name)", "dont use \(name)", "don't ask \(name)",
            "dont ask \(name)", "not \(name)", "no \(name)",
            "without \(name)", "instead of \(name)",
        ]
        return negationPhrases.contains { lower.contains($0) }
    }

    static func isRetriableSpawnFailure(_ message: String) -> Bool {
        let lower = message.lowercased()
        return lower.contains("not available")
            || lower.contains("failed to start")
            || lower.contains("enoent")
            || lower.contains("command not found")
            || lower.contains("spawn")
            || lower.contains("no such file")
    }

    static func resolveSpawn(
        brief: String,
        requestedProvider: AgentPillsManager.DirectedProvider?,
        userRequestText: String?,
        title: String?,
        treatRequestedAsExplicit: Bool = false,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) -> Resolution {
        let taskKind = classifyTask(brief)
        // Only treat a provider as user-directed when it appears in the user's own
        // words. The model-authored `brief` often names a provider the model chose
        // (e.g. "use Hermes to refactor…") even when the user never said it.
        // Prefer a verb-based match ("use codex") over a bare mention so negated
        // phrases like "don't use Hermes, use Codex" route to the positively-
        // requested provider, not the first one that appears as a substring.
        // Negated mentions ("don't use X") are excluded from the bare fallback.
        let userText = userRequestText?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let explicit = userText.isEmpty ? nil : (explicitProvider(in: userText)
            ?? AgentPillsManager.DirectedProvider.allCases.first {
                isExplicitProviderRequest($0, in: userText) && !isNegated($0, in: userText)
            })
        // For the chat tool (no user transcript), the model's `provider` argument
        // is deliberate explicit intent — treat it like a user-directive.
        let effectiveExplicit = explicit ?? (treatRequestedAsExplicit ? requestedProvider : nil)

        if let effectiveExplicit {
            let availability = LocalAgentProviderDetector.availability(
                for: effectiveExplicit,
                environment: environment,
                fileManager: fileManager,
                homeDirectory: homeDirectory
            )
            guard availability.isAvailable else {
                return .setupRequired(
                    provider: effectiveExplicit,
                    prompt: availability.setupPrompt,
                    spokenStatus: availability.spokenInstallGuide
                )
            }
            let resolvedTitle = normalizedTitle(title, provider: effectiveExplicit)
            return .spawn(
                AgentSpawnPlan(
                    harnessOverride: effectiveExplicit.harnessMode,
                    title: resolvedTitle,
                    ack: "Asking \(effectiveExplicit.displayName).",
                    selectedProvider: effectiveExplicit,
                    usedFallback: false,
                    fallbackNote: nil,
                    context: spawnContext(
                        taskKind: taskKind,
                        explicitProvider: effectiveExplicit,
                        selectedHarness: effectiveExplicit.harnessMode,
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

        // When the user didn't explicitly name a provider, use the task-based
        // preference ranking — the model's `requestedProvider` suggestion should
        // NOT override the smart routing (e.g. model picking OpenClaw for a coding
        // task when Codex is the preferred and installed choice).
        // Exception: if the model's pick isn't installed and we DO have an
        // installed fallback, speak the fallback note so the user knows.
        if let requestedProvider, !LocalAgentProviderDetector.isAvailable(
            requestedProvider,
            environment: environment,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        ), let fallbackProvider = availableProviders.first {
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

enum LocalAgentProviderInstaller {
    /// Only Codex can be auto-installed (non-interactive `npm install -g`).
    /// Hermes needs interactive `hermes model` setup; OpenClaw has no public install.
    static func canAutoInstall(_ provider: AgentPillsManager.DirectedProvider) -> Bool {
        provider == .codex
    }

    static func installingStatus(for provider: AgentPillsManager.DirectedProvider) -> String {
        switch provider {
        case .codex:
            return "Codex isn't installed. Installing it for you now — this takes a moment."
        case .hermes, .openclaw:
            return "\(provider.displayName) needs manual setup."
        }
    }

    static func install(
        _ provider: AgentPillsManager.DirectedProvider,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) async -> Bool {
        switch provider {
        case .codex:
            return await installCodex(
                environment: environment,
                fileManager: fileManager,
                homeDirectory: homeDirectory
            )
        case .hermes, .openclaw:
            return false
        }
    }

    private static func installCodex(
        environment: [String: String],
        fileManager: FileManager,
        homeDirectory: String
    ) async -> Bool {
        guard let npmPath = findExecutable(
            named: "npm",
            environment: environment,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        ) else { return false }

        // `npm` is a Node script; a LaunchServices-launched GUI app inherits only a
        // minimal PATH, so prepend npm's own dir (which also holds `node`) to PATH,
        // otherwise the npm shebang can't find node and the install silently fails.
        let npmDir = (npmPath as NSString).deletingLastPathComponent
        var childEnv = environment
        let existingPath = childEnv["PATH"] ?? "/usr/bin:/bin"
        childEnv["PATH"] = "\(npmDir):\(existingPath)"

        return await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: npmPath)
                process.arguments = ["install", "-g", "@openai/codex"]
                process.environment = childEnv
                let sink = Pipe()
                process.standardOutput = sink
                process.standardError = sink

                // Guard against a hung npm (registry stall, unexpected prompt): kill
                // it after a bounded wait so the awaiting spawn path never blocks forever.
                let timeout = DispatchWorkItem {
                    if process.isRunning { process.terminate() }
                }
                DispatchQueue.global().asyncAfter(deadline: .now() + 180, execute: timeout)

                do {
                    try process.run()
                    process.waitUntilExit()
                    timeout.cancel()
                    continuation.resume(returning: process.terminationStatus == 0)
                } catch {
                    timeout.cancel()
                    continuation.resume(returning: false)
                }
            }
        }
    }

    private static func findExecutable(
        named name: String,
        environment: [String: String],
        fileManager: FileManager,
        homeDirectory: String
    ) -> String? {
        if let path = environment["PATH"] {
            for dir in path.split(separator: ":").map(String.init) {
                let full = (dir as NSString).appendingPathComponent(name)
                if fileManager.isExecutableFile(atPath: full) {
                    return full
                }
            }
        }
        for dir in LocalAgentProviderDetector.adapterActivationSearchDirectories(
            homeDirectory: homeDirectory,
            fileManager: fileManager
        ) {
            let full = (dir as NSString).appendingPathComponent(name)
            if fileManager.isExecutableFile(atPath: full) {
                return full
            }
        }
        return nil
    }
}

extension LocalAgentProviderRouting {
    /// Resolve a spawn, auto-installing Codex if the user explicitly asked for it
    /// but it's not installed. Calls `onInstallStart` before the install runs so
    /// the caller can speak/show a status message. Returns the final resolution.
    static func resolveSpawnWithAutoInstall(
        brief: String,
        requestedProvider: AgentPillsManager.DirectedProvider?,
        userRequestText: String?,
        title: String?,
        treatRequestedAsExplicit: Bool = false,
        onInstallStart: ((AgentPillsManager.DirectedProvider) -> Void)? = nil,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        homeDirectory: String = NSHomeDirectory()
    ) async -> Resolution {
        let resolution = resolveSpawn(
            brief: brief,
            requestedProvider: requestedProvider,
            userRequestText: userRequestText,
            title: title,
            treatRequestedAsExplicit: treatRequestedAsExplicit,
            environment: environment,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        )

        guard case .setupRequired(let provider, _, _) = resolution,
              LocalAgentProviderInstaller.canAutoInstall(provider)
        else { return resolution }

        onInstallStart?(provider)
        let installed = await LocalAgentProviderInstaller.install(
            provider,
            environment: environment,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        )

        guard installed else { return resolution }

        return resolveSpawn(
            brief: brief,
            requestedProvider: requestedProvider,
            userRequestText: userRequestText,
            title: title,
            treatRequestedAsExplicit: treatRequestedAsExplicit,
            environment: environment,
            fileManager: fileManager,
            homeDirectory: homeDirectory
        )
    }

    private static func nvmNodeBinDirectories(homeDirectory: String, fileManager: FileManager) -> [String] {
        let versionsDir = "\(homeDirectory)/.nvm/versions/node"
        let scanned = ((try? fileManager.contentsOfDirectory(atPath: versionsDir)) ?? [])
            .sorted { $0.compare($1, options: .numeric) == .orderedDescending }
            .map { "\(versionsDir)/\($0)/bin" }
        // `npm install -g` lands in nvm's DEFAULT version, which is not
        // necessarily the numerically-highest installed one — prefer it.
        guard let defaultBin = nvmDefaultAliasBinDirectory(homeDirectory: homeDirectory, fileManager: fileManager)
        else {
            return scanned
        }
        return [defaultBin] + scanned.filter { $0 != defaultBin }
    }

    /// Resolve `~/.nvm/alias/default` — a text file naming a version or another
    /// alias (e.g. "v20.11.0", or "lts/*" → "lts/jod" → "v20.11.0"). GUI apps
    /// never inherit NVM_BIN from the shell, so the alias file is the only
    /// reliable way to learn which version `npm install -g` targets.
    private static func nvmDefaultAliasBinDirectory(homeDirectory: String, fileManager: FileManager) -> String? {
        var alias = "default"
        for _ in 0..<3 {
            guard
                let contents = try? String(
                    contentsOfFile: "\(homeDirectory)/.nvm/alias/\(alias)", encoding: .utf8)
            else { return nil }
            let resolved = contents.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !resolved.isEmpty else { return nil }
            if resolved.hasPrefix("v") {
                let bin = "\(homeDirectory)/.nvm/versions/node/\(resolved)/bin"
                var isDirectory: ObjCBool = false
                return fileManager.fileExists(atPath: bin, isDirectory: &isDirectory) && isDirectory.boolValue
                    ? bin : nil
            }
            alias = resolved
        }
        return nil
    }
    return nil
  }

  // Detection is intentionally hermetic: it uses only the supplied PATH and
  // home directory (plus an explicit OMI_* command), never ProcessInfo's
  // ambient environment or NSHomeDirectory. This makes tests and app launch
  // behavior agree even on machines with globally-installed adapters.
  private static func adapterActivationSearchDirectories(
    environment: [String: String],
    homeDirectory: String
  ) -> [String] {
    let pathDirectories = (environment["PATH"] ?? "")
      .split(separator: ":")
      .map(String.init)
      .filter { !$0.isEmpty }
    let candidates =
      pathDirectories + [
        "\(homeDirectory)/.hermes/hermes-agent/venv/bin",
        "\(homeDirectory)/.hermes/node/bin",
        "\(homeDirectory)/.hermes/hermes-agent",
        "\(homeDirectory)/.codex/bin",
        "\(homeDirectory)/.local/bin",
      ]
    return candidates.reduce(into: [String]()) { result, directory in
      if !result.contains(directory) { result.append(directory) }
    }
  }
}
