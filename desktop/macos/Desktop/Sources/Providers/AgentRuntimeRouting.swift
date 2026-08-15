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

  static func usesNativeModelChoice(for rawHarnessMode: String) -> Bool {
    switch harnessMode(from: rawHarnessMode) {
    case .hermes?, .openclaw?, .codex?:
      return true
    default:
      return false
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
    "I don't see \(provider.displayName) installed. Install it with `\(provider.installCommand)`, then run `\(provider.loginCommand)`."
  }

  var spokenInstallGuide: String {
    "I don't see \(provider.displayName) installed. Check the chat for the installation steps."
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
      environment: environment,
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
    availability(for: provider, environment: environment, fileManager: fileManager, homeDirectory: homeDirectory)
      .isAvailable
  }

  private static func configuredCommand(
    for provider: AgentPillsManager.DirectedProvider,
    environment: [String: String]
  ) -> String? {
    let key = provider.commandEnvironmentName
    let value = environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return value.isEmpty ? nil : value
  }

  static func firstExecutable(
    named name: String,
    fileManager: FileManager,
    environment: [String: String] = ProcessInfo.processInfo.environment,
    homeDirectory: String,
    searchDirectories: [String]? = nil
  ) -> String? {
    let directories =
      searchDirectories
      ?? adapterActivationSearchDirectories(
        environment: environment, homeDirectory: homeDirectory, fileManager: fileManager)
    for dir in directories {
      let path = (dir as NSString).appendingPathComponent(name)
      if fileManager.isExecutableFile(atPath: path) {
        return path
      }
    }
    return nil
  }

  // Detection is intentionally hermetic: it uses only the supplied PATH and
  // home directory (plus an explicit OMI_* command), never ProcessInfo's
  // ambient environment or NSHomeDirectory. This makes tests and app launch
  // behavior agree even on machines with globally-installed adapters.
  static func adapterActivationSearchDirectories(
    environment: [String: String],
    homeDirectory: String,
    fileManager: FileManager = .default
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
        "\(homeDirectory)/.local/bin",
      ]
      + managedNodeBinDirectories(homeDirectory: homeDirectory, fileManager: fileManager)
    return candidates.reduce(into: [String]()) { result, directory in
      if !result.contains(directory) { result.append(directory) }
    }
  }

  /// npm-global CLIs (`codex`, `openclaw`) land in the bin directory of
  /// whichever Node version manager installed them. A directly launched app
  /// bundle inherits none of those shell-managed PATH entries, so detection
  /// must enumerate the stable, home-scoped install roots itself. Machine-wide
  /// roots stay out: detection is hermetic in the supplied home directory.
  static func managedNodeBinDirectories(
    homeDirectory: String,
    fileManager: FileManager = .default
  ) -> [String] {
    let roots = [
      "\(homeDirectory)/.nvm/versions/node",
      "\(homeDirectory)/.fnm/node-versions",
      "\(homeDirectory)/.local/share/fnm/node-versions",
      "\(homeDirectory)/.nodenv/versions",
      "\(homeDirectory)/.asdf/installs/nodejs",
    ]
    return roots.flatMap { root -> [String] in
      guard let versions = try? fileManager.contentsOfDirectory(atPath: root) else { return [] }
      return versions.sorted().compactMap { version in
        let versionDirectory = (root as NSString).appendingPathComponent(version)
        let directBin = (versionDirectory as NSString).appendingPathComponent("bin")
        if fileManager.fileExists(atPath: directBin) { return directBin }
        let installationBin = (versionDirectory as NSString).appendingPathComponent("installation/bin")
        if fileManager.fileExists(atPath: installationBin) { return installationBin }
        return nil
      }
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

enum AgentSpawnFallbackPolicy {
  static func remainingProviders(from context: AgentSpawnContext) -> [AgentPillsManager.DirectedProvider?] {
    var remaining: [AgentPillsManager.DirectedProvider?] = []
    for harness in context.fallbackChain {
      guard !context.attemptedHarnesses.contains(where: { $0 == harness }) else { continue }
      if let harness {
        switch harness {
        case .hermes: remaining.append(.hermes)
        case .openclaw: remaining.append(.openclaw)
        case .codex: remaining.append(.codex)
        case .piMono, .acp: continue
        }
      } else {
        remaining.append(nil)
      }
    }
    return remaining
  }

  static func takeNextFallback(
    remaining: inout [AgentPillsManager.DirectedProvider?],
    error: Error
  ) -> AgentPillsManager.DirectedProvider?? {
    guard LocalAgentProviderRouting.isRetriableSpawnFailure(error), !remaining.isEmpty else {
      return nil
    }
    return .some(remaining.removeFirst())
  }

  static func rawSpawnFailureMessage(for error: Error) -> String {
    if let runtime = error as? BridgeError, case .agentRuntimeFailure(let failure) = runtime {
      return failure.displayMessage
    }
    return (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
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
    switch AgentProviderRouter.classify(text) {
    case .coding:
      return .coding
    case .computerUse:
      return .automation
    case .general:
      return .general
    }
  }

  static func preferredProviders(for task: AgentTaskKind) -> [AgentPillsManager.DirectedProvider] {
    let kind: AgentProviderRouter.TaskKind
    switch task {
    case .coding:
      kind = .coding
    case .automation:
      kind = .computerUse
    case .general:
      kind = .general
    }
    return AgentProviderRouter.prior(for: kind)
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

  static func isRetriableSpawnFailure(_ error: Error) -> Bool {
    if let runtime = error as? BridgeError, case .agentRuntimeFailure(let failure) = runtime {
      return failure.isStartupPhase
    }
    return isRetriableSpawnFailure(AgentSpawnFallbackPolicy.rawSpawnFailureMessage(for: error))
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
    let explicit =
      userText.isEmpty
      ? nil
      : (explicitProvider(in: userText)
        ?? AgentPillsManager.DirectedProvider.allCases.first {
          isExplicitProviderRequest($0, in: userText) && !isNegated($0, in: userText)
        })
    // For the chat tool (no user transcript), the model's `provider` argument
    // is deliberate explicit intent — treat it like a user-directive.
    let effectiveExplicit = explicit ?? (treatRequestedAsExplicit ? requestedProvider : nil)

    if let effectiveExplicit {
      let readiness = AgentProviderHealth.report(
        for: effectiveExplicit,
        environment: environment,
        fileManager: fileManager,
        homeDirectory: homeDirectory
      )
      guard readiness.readiness == .ready else {
        return .setupRequired(
          provider: effectiveExplicit,
          prompt: readiness.detail.isEmpty
            ? "I don't see \(effectiveExplicit.displayName) installed. Install it with `\(effectiveExplicit.installCommand)`, then run `\(effectiveExplicit.loginCommand)`."
            : readiness.detail,
          spokenStatus: readiness.detail.isEmpty
            ? "I don't see \(effectiveExplicit.displayName) installed. Check the chat for the installation steps."
            : readiness.detail
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
      AgentProviderHealth.isReady(
        for: $0,
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
    if taskKind != .general, let requestedProvider,
      !AgentProviderHealth.isReady(
        for: requestedProvider,
        environment: environment,
        fileManager: fileManager,
        homeDirectory: homeDirectory
      ), let fallbackProvider = availableProviders.first
    {
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

    if taskKind != .general, let primary = availableProviders.first {
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
    if explicitProvider != nil {
      return AgentSpawnContext(
        taskKind: taskKind,
        explicitProvider: explicitProvider,
        fallbackChain: [],
        attemptedHarnesses: [selectedHarness]
      )
    }
    let availableHarnesses = preferredProviders(for: taskKind)
      .filter {
        AgentProviderHealth.isReady(
          for: $0,
          environment: environment,
          fileManager: fileManager,
          homeDirectory: homeDirectory
        )
      }
      .map(\.harnessMode)
    let fallbackChain = availableHarnesses + [nil]
    return AgentSpawnContext(
      taskKind: taskKind,
      explicitProvider: nil,
      fallbackChain: fallbackChain,
      attemptedHarnesses: [selectedHarness]
    )
  }
}

extension AgentPillsManager {
  struct ProviderDirective: Equatable, Sendable {
    let provider: DirectedProvider
    let rewrittenQuery: String
    let title: String
    let ack: String
  }

  nonisolated static func providerDirective(from text: String) -> ProviderDirective? {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    let providerPattern = "(open\\s*claw|openclaw|hermes|codex)"
    let patterns = [
      #"(?i)^\s*(?:please\s+)?(?:(?:i\s+)?meant\s+)?(?:ask|tell|ping|message|run|use|try)\s+\#(providerPattern)\b(?:\s+(.*))?$"#,
      #"(?i)^\s*(?:please\s+)?\#(providerPattern)\s*[:,\-]\s*(.*)$"#,
    ]
    for pattern in patterns {
      guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
      let range = NSRange(trimmed.startIndex..., in: trimmed)
      guard let match = regex.firstMatch(in: trimmed, range: range),
        let providerRange = Range(match.range(at: 1), in: trimmed)
      else { continue }
      let providerToken = trimmed[providerRange].lowercased().replacingOccurrences(of: " ", with: "")
      guard let provider = DirectedProvider(rawValue: providerToken) else { continue }
      let rewrittenQuery: String
      if match.numberOfRanges > 2, let queryRange = Range(match.range(at: 2), in: trimmed) {
        rewrittenQuery = String(trimmed[queryRange]).trimmingCharacters(in: .whitespacesAndNewlines)
      } else {
        rewrittenQuery = "Say how it's going."
      }
      return ProviderDirective(
        provider: provider,
        rewrittenQuery: rewrittenQuery,
        title: provider.displayName,
        ack: "Asking \(provider.displayName)."
      )
    }
    return nil
  }
}

extension LocalAgentProviderRouting {
  /// Resolve a spawn WITHOUT auto-installing. When a provider needs setup,
  /// the caller receives `.setupRequired` and should direct the user to
  /// `setup_agent_provider` (which flows through
  /// `LocalAgentProviderInstaller.beginInstall` with the native consent
  /// dialog). Auto-install was removed to prevent third-party install
  /// commands running from ordinary spawn routing without explicit user
  /// confirmation.
  static func resolveSpawnWithAutoInstall(
    brief: String,
    requestedProvider: AgentPillsManager.DirectedProvider?,
    userRequestText: String?,
    title: String?,
    treatRequestedAsExplicit: Bool = false,
    environment: [String: String] = ProcessInfo.processInfo.environment,
    fileManager: FileManager = .default,
    homeDirectory: String = NSHomeDirectory()
  ) async -> Resolution {
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
}
