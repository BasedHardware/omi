import Foundation

/// Whether a local agent provider can actually take a task right now.
/// `LocalAgentProviderDetector` answers "is the binary on disk"; this layer
/// answers the question users care about — installed AND wired AND authed —
/// so the setup flow can say precisely what's missing.
enum AgentProviderReadiness: String, Equatable {
  case ready
  case needsSetup = "needs_setup"
  case missing
}

struct AgentProviderHealthReport: Equatable {
  let provider: AgentPillsManager.DirectedProvider
  let readiness: AgentProviderReadiness
  /// One sentence describing what's missing or broken (empty when ready).
  let detail: String
}

enum AgentProviderHealth {

  static func report(
    for provider: AgentPillsManager.DirectedProvider,
    environment: [String: String] = ProcessInfo.processInfo.environment,
    fileManager: FileManager = .default,
    homeDirectory: String = NSHomeDirectory(),
    searchDirectories: [String]? = nil
  ) -> AgentProviderHealthReport {
    // A manually wired adapter command overrides all probes: the user has
    // taken responsibility for how the adapter runs.
    let override =
      environment[provider.commandEnvironmentName]?
      .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !override.isEmpty {
      return AgentProviderHealthReport(provider: provider, readiness: .ready, detail: "")
    }

    func executable(_ name: String) -> String? {
      LocalAgentProviderDetector.firstExecutable(
        named: name, fileManager: fileManager, environment: environment, homeDirectory: homeDirectory,
        searchDirectories: searchDirectories)
    }

    // Config/credential probes must reject directories and empty
    // placeholders — `fileExists` alone would report a provider ready
    // and hand it a task doomed to fail in the adapter.
    func nonEmptyRegularFile(_ path: String) -> Bool {
      var isDirectory: ObjCBool = false
      guard fileManager.fileExists(atPath: path, isDirectory: &isDirectory),
        !isDirectory.boolValue
      else { return false }
      let size = (try? fileManager.attributesOfItem(atPath: path)[.size] as? Int) ?? 0
      return size > 0
    }

    switch provider {
    case .codex:
      guard executable("codex") != nil else {
        return AgentProviderHealthReport(
          provider: provider, readiness: .missing,
          detail: "The Codex CLI is not installed.")
      }
      guard executable("codex-acp") != nil else {
        return AgentProviderHealthReport(
          provider: provider, readiness: .needsSetup,
          detail: "Codex is installed but the codex-acp bridge is missing.")
      }
      // Codex-acp accepts either a local ChatGPT login (`~/.codex/auth.json`)
      // or an OpenAI API key. Settings BYOK is injected as OMI_BYOK_OPENAI and
      // mapped to OPENAI_API_KEY for the codex adapter — treat that as signed-in
      // so health-gated routing matches the working runtime path.
      func nonEmptyEnv(_ name: String) -> Bool {
        !(environment[name]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "").isEmpty
      }
      let authPath = (homeDirectory as NSString).appendingPathComponent(".codex/auth.json")
      let hasCodexCredentials =
        nonEmptyRegularFile(authPath)
        || nonEmptyEnv("OPENAI_API_KEY")
        || nonEmptyEnv("OMI_BYOK_OPENAI")
        || APIKeyService.byokKey(.openai) != nil
      guard hasCodexCredentials else {
        return AgentProviderHealthReport(
          provider: provider, readiness: .needsSetup,
          detail: "Codex is installed but not signed in (codex login).")
      }
      return AgentProviderHealthReport(provider: provider, readiness: .ready, detail: "")

    case .openclaw:
      guard executable("openclaw") != nil else {
        return AgentProviderHealthReport(
          provider: provider, readiness: .missing,
          detail: "OpenClaw is not installed.")
      }
      let configPath = (homeDirectory as NSString).appendingPathComponent(".openclaw/openclaw.json")
      guard nonEmptyRegularFile(configPath) else {
        return AgentProviderHealthReport(
          provider: provider, readiness: .needsSetup,
          detail: "OpenClaw is installed but not onboarded (openclaw onboard).")
      }
      return AgentProviderHealthReport(provider: provider, readiness: .ready, detail: "")

    case .hermes:
      guard executable("hermes") != nil else {
        return AgentProviderHealthReport(
          provider: provider, readiness: .missing,
          detail: "Hermes is not installed.")
      }
      return AgentProviderHealthReport(provider: provider, readiness: .ready, detail: "")
    }
  }

  static func reportsForAllProviders() -> [AgentProviderHealthReport] {
    [.codex, .openclaw, .hermes].map { report(for: $0) }
  }

  /// The single readiness predicate for spawn routing, fallback-chain
  /// construction, and runtime env seeding. Unlike
  /// `LocalAgentProviderDetector.isAvailable` (binary exists), this is true
  /// only when the provider is installed AND wired AND authed, so a Codex
  /// binary with no bridge or no sign-in never gets handed a task the
  /// adapter would fail on.
  static func isReady(
    for provider: AgentPillsManager.DirectedProvider,
    environment: [String: String] = ProcessInfo.processInfo.environment,
    fileManager: FileManager = .default,
    homeDirectory: String = NSHomeDirectory(),
    searchDirectories: [String]? = nil
  ) -> Bool {
    report(
      for: provider,
      environment: environment,
      fileManager: fileManager,
      homeDirectory: homeDirectory,
      searchDirectories: searchDirectories
    ).readiness == .ready
  }
}
