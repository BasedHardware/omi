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
      return
        "I don't see the Codex ACP adapter installed. Install `@zed-industries/codex-acp` (the `codex-acp` binary) first, then try again."
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

  private static func firstExecutable(
    named name: String,
    fileManager: FileManager,
    environment: [String: String],
    homeDirectory: String
  ) -> String? {
    for dir in adapterActivationSearchDirectories(
      environment: environment,
      homeDirectory: homeDirectory
    ) {
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
        "\(homeDirectory)/.local/bin",
      ]
    return candidates.reduce(into: [String]()) { result, directory in
      if !result.contains(directory) { result.append(directory) }
    }
  }
}
