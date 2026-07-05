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
        let override = environment[provider.commandEnvironmentName]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !override.isEmpty {
            return AgentProviderHealthReport(provider: provider, readiness: .ready, detail: "")
        }

        func executable(_ name: String) -> String? {
            LocalAgentProviderDetector.firstExecutable(
                named: name, fileManager: fileManager, homeDirectory: homeDirectory,
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
            return (size ?? 0) > 0
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
            let authPath = (homeDirectory as NSString).appendingPathComponent(".codex/auth.json")
            guard nonEmptyRegularFile(authPath) else {
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
}
