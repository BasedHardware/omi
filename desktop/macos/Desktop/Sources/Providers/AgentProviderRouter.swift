import Foundation

/// Picks the best local agent provider for a task and produces an ordered
/// fallback chain, so voice/chat can say "use the best agent" and a failed
/// provider hands the task to the next one instead of dead-ending.
///
/// Routing is deliberately a transparent heuristic (no extra LLM call on the
/// dispatch path): classify the task, apply a static capability prior per
/// provider, keep only providers that are actually installed, and always
/// terminate the chain with the default Omi orchestrator (`nil`) so a task
/// never fails solely because every external provider is missing or broken.
enum AgentProviderRouter {

    enum TaskKind: String {
        case coding
        case computerUse
        case general
    }

    struct Decision: Equatable {
        /// Provider to dispatch first. `nil` means the default Omi orchestrator.
        let primary: AgentPillsManager.DirectedProvider?
        /// Remaining providers to try, in order, when the previous one fails.
        /// A trailing `nil` is the default-orchestrator terminal fallback.
        let fallbacks: [AgentPillsManager.DirectedProvider?]
        /// Human-readable routing rationale for logs and audit.
        let reason: String
    }

    private static let codingKeywords: [String] = [
        "code", "coding", "script", "bug", "fix", "refactor", "compile", "build",
        "repo", "repository", "git", "commit", "branch", "pull request", " pr ",
        "function", "class", "api", "endpoint", "test", "unit test", "debug",
        "implement", "typescript", "javascript", "python", "swift", "rust",
        "html", "css", "sql", "regex", "json", "yaml", "readme", "hello world",
    ]

    private static let computerUseKeywords: [String] = [
        "browser", "chrome", "safari", "website", "web page", "webpage", "url",
        "click", "scroll", "tab", "form", "fill", "download", "upload",
        "open the app", "open app", "screenshot", "navigate", "sign in", "log in",
        "book", "order", "buy", "search the web",
    ]

    /// Static capability prior: which providers are strongest for each task
    /// kind, best first. Every provider appears in every prior so a lone
    /// installed provider is always eligible regardless of task kind.
    static func prior(for kind: TaskKind) -> [AgentPillsManager.DirectedProvider] {
        switch kind {
        case .coding:
            return [.codex, .hermes, .openclaw]
        case .computerUse:
            return [.openclaw, .hermes, .codex]
        case .general:
            return [.hermes, .codex, .openclaw]
        }
    }

    static func classify(_ task: String) -> TaskKind {
        let lowered = " " + task.lowercased() + " "
        let codingHits = codingKeywords.filter { lowered.contains($0) }.count
        let computerHits = computerUseKeywords.filter { lowered.contains($0) }.count
        if codingHits == 0 && computerHits == 0 { return .general }
        return codingHits >= computerHits ? .coding : .computerUse
    }

    /// Shared provider-name → dispatch decision used by every spawn surface
    /// (voice hub, desktop chat, automation bridge) so routing rules cannot
    /// drift between copies of the same switch. Returns nil for an unknown
    /// provider name; the caller owns the error message.
    ///
    /// Rules: explicit names dispatch directly (health is checked by the
    /// caller's preflight); "auto"/"best"/"any" always routes; an empty name
    /// routes only for coding/computer-use tasks when a ready external
    /// provider exists — general tasks stay on the default orchestrator,
    /// which uniquely has the user's Omi data tools.
    static func dispatchDecision(
        providerName: String,
        brief: String,
        availability: (AgentPillsManager.DirectedProvider) -> Bool = {
            AgentProviderHealth.report(for: $0).readiness == .ready
        }
    ) -> Decision? {
        switch providerName {
        case "openclaw":
            return Decision(primary: .openclaw, fallbacks: [], reason: "explicit")
        case "hermes":
            return Decision(primary: .hermes, fallbacks: [], reason: "explicit")
        case "codex":
            return Decision(primary: .codex, fallbacks: [], reason: "explicit")
        case "auto", "best", "any":
            return route(task: brief, availability: availability)
        case "":
            let decision = route(task: brief, availability: availability)
            if decision.primary != nil, classify(brief) != .general {
                return Decision(
                    primary: decision.primary,
                    fallbacks: decision.fallbacks,
                    reason: "default auto-routed: \(decision.reason)")
            }
            return Decision(primary: nil, fallbacks: [], reason: "default orchestrator")
        default:
            return nil
        }
    }

    /// Only providers that are actually ready (installed AND wired AND authed —
    /// see AgentProviderHealth) may enter a chain; a merely-installed binary
    /// with a dead gateway or missing auth would burn a hop on a doomed run.
    static func route(
        task: String,
        availability: (AgentPillsManager.DirectedProvider) -> Bool = {
            AgentProviderHealth.report(for: $0).readiness == .ready
        }
    ) -> Decision {
        let kind = classify(task)
        let ranked = prior(for: kind)
        let installed = ranked.filter(availability)

        guard let primary = installed.first else {
            return Decision(
                primary: nil,
                fallbacks: [],
                reason: "task=\(kind.rawValue) no local providers installed → default orchestrator"
            )
        }

        var fallbacks: [AgentPillsManager.DirectedProvider?] = installed.dropFirst().map { $0 }
        fallbacks.append(nil)  // default orchestrator is always the terminal fallback

        let chainText = ([primary].map(\.rawValue) + fallbacks.map { $0?.rawValue ?? "default" })
            .joined(separator: " → ")
        return Decision(
            primary: primary,
            fallbacks: fallbacks,
            reason: "task=\(kind.rawValue) chain=\(chainText)"
        )
    }
}
