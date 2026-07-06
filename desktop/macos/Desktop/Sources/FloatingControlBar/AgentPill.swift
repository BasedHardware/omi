import Combine
import Foundation
import SwiftUI

/// A running or finished background "agent" launched from the Ask Omi floating
/// bar. Each pill owns its own `ChatProvider` so multiple agents can execute in
/// parallel without sharing message state.
@MainActor
final class AgentPill: ObservableObject, Identifiable {
    enum Status: Equatable {
        case queued
        case starting
        case running
        case done
        case stopped
        case failed(String)

        var displayLabel: String {
            switch self {
            case .queued: return "Queued"
            case .starting, .running: return "Running"
            case .done: return "Done"
            case .stopped: return "Stopped"
            case .failed: return "Failed"
            }
        }

        var tintColor: Color {
            switch self {
            case .queued: return Color(red: 0.20, green: 0.86, blue: 1.0)
            case .starting, .running: return Color(red: 1.0, green: 0.80, blue: 0.40)
            case .done: return Color(red: 0.27, green: 0.92, blue: 0.46)
            case .stopped: return Color(red: 0.64, green: 0.66, blue: 0.70)
            case .failed: return Color(red: 1.0, green: 0.42, blue: 0.42)
            }
        }

        var machineLabel: String {
            switch self {
            case .queued: return "queued"
            case .starting: return "starting"
            case .running: return "running"
            case .done: return "done"
            case .stopped: return "stopped"
            case .failed: return "failed"
            }
        }

        var isFinished: Bool {
            switch self {
            case .done, .stopped, .failed: return true
            default: return false
            }
        }

    }

    let id = UUID()
    let query: String
    let createdAt: Date
    let model: String
    let bridgeHarnessOverride: AgentHarnessMode?

    /// Remaining auto-selected providers to try if this pill fails before doing
    /// any work (startup-class failures only: not installed / not signed in /
    /// adapter unavailable). Set by the router spawn path; empty for pills the
    /// user directed at a specific provider.
    var autoFallbackCandidates: [AgentPillsManager.DirectedProvider] = []

    /// True when the provider was chosen by the router (not the user). Only
    /// router-selected pills may terminally fall back to Omi's built-in agent
    /// after every external candidate fails at startup.
    var wasRouterSelected = false

    @Published var title: String
    @Published var status: Status = .queued
    @Published var latestActivity: String = "Queued…"
    @Published var transcript: [String] = []
    @Published var aiMessage: ChatMessage?
    @Published var conversationMessages: [ChatMessage] = []
    @Published var completedAt: Date?
    @Published var viewedAt: Date?
    @Published var suggestedFollowUps: [String] = []
    @Published var contentRevision: Int = 0

    /// Convenience: how long the agent has been running (or ran).
    var elapsed: TimeInterval {
        (completedAt ?? Date()).timeIntervalSince(createdAt)
    }

    init(query: String, model: String, bridgeHarnessOverride: AgentHarnessMode? = nil) {
        self.query = query
        self.model = model
        self.bridgeHarnessOverride = bridgeHarnessOverride
        self.title = AgentPill.deriveTitle(from: query)
        self.createdAt = Date()
    }

    func markContentChanged() {
        contentRevision &+= 1
    }

    /// Pull a short uppercase title out of the query for the pill popover header.
    /// "open google.com and find vegan ramen" → "OPEN GOOGLE.COM"
    private static func deriveTitle(from query: String) -> String {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let words = trimmed
            .split(separator: " ", maxSplits: 4, omittingEmptySubsequences: true)
            .prefix(3)
            .map(String.init)
        let joined = words.joined(separator: " ").uppercased()
        if joined.count > 32 {
            return String(joined.prefix(32)) + "…"
        }
        return joined.isEmpty ? "AGENT" : joined
    }
}

/// Singleton that owns the running `AgentPill`s. Spawning a pill creates a new
/// `ChatProvider` and observes its message stream until the agent finishes.
@MainActor
final class AgentPillsManager: ObservableObject {
    static let shared = AgentPillsManager()

    @Published private(set) var pills: [AgentPill] = []
    @Published var hoveredPillID: UUID?
    @Published var pinnedPillID: UUID?

    /// Configurable soft cap so the row never grows past a reasonable width.
    private let maxPills: Int = 8

    /// One ChatProvider (and therefore one ACP node subprocess) per pill so
    /// pills can truly run in parallel — each provider has its own bridge,
    /// `isSending` flag, and interrupt scope. Bridges are heavy to boot, so we
    /// stagger their startup via `bootChain` to avoid the race we saw the first
    /// time around. After boot completes, every pill's `sendMessage` runs in
    /// parallel with the others.
    private var providersByPill: [UUID: ChatProvider] = [:]
    private var streamsByPill: [UUID: AnyCancellable] = [:]
    private var projectionStreamsByPill: [UUID: AnyCancellable] = [:]
    private var messageCountByPill: [UUID: Int] = [:]
    private var runTasksByPill: [UUID: Task<Void, Never>] = [:]
    private var viewedExpirationWorkItemsByPill: [UUID: DispatchWorkItem] = [:]
    private var bootChain: Task<Void, Never> = Task {}

    private static let backgroundAgentSystemPromptSuffix = """
    You are running inside a visible floating background agent pill. Do the requested work now; do not merely acknowledge, promise, or say that you are working on it. Use the available tools when the task requires local data, browser/app/file actions, or multi-step investigation. Finish only after you have either completed the task or hit a concrete blocker, then give a concise final summary of the outcome.

    This is already the spawned background agent. Do not call spawn_agent or delegate_agent just to hand off this same task.
    """

    /// Shared agent-noun pattern used by negation guard, intent detection, and
    /// task extraction. Kept word-boundary-free so callers can embed it inside
    /// larger patterns and add `\b` anchors themselves. (Cubic P2 — single
    /// source of truth for agent-noun regex.)
    private nonisolated static let agentNounPattern = #"(?:sub\s*agents?|subagents?|background\s+agents?|floating\s+agents?|agents?|pills?)"#

    /// Which pill (if any) is currently capturing a voice follow-up — drives the
    /// pill popover's mic button state.
    @Published var recordingPillID: UUID?

    private let viewedFinishedTTL: TimeInterval = 10 * 60

    private init() {}

    /// Routing decision for an Ask Omi message — does it stay inline in the
    /// floating bar, or get hoisted into a background agent pill?
    enum Route: String { case chat, agent }

    /// Explicit UI/control-plane handoff: the parent turn is the user's request
    /// to create a background agent, while `agentTask` is the work the child
    /// agent should actually perform. Keeping these separate prevents the child
    /// prompt from inheriting control words like "spawn a subagent".
    struct FloatingAgentHandoff: Equatable {
        let originalRequest: String
        let agentTask: String
    }

    /// Combined router result. Title/ack are pre-computed alongside the route
    /// so we don't need a second Haiku call when the answer is "agent".
    struct RouterDecision {
        let route: Route
        let title: String?
        let ack: String?
        /// Best-suited connected external providers for this task, ranked by the
        /// router. Empty means run Omi's built-in agent. The first entry is
        /// spawned; the rest become the pill's startup-failure fallback chain.
        var rankedProviders: [DirectedProvider] = []
    }

    enum DirectedProvider: String, Equatable {
        case hermes
        case openclaw
        case codex

        var displayName: String {
            switch self {
            case .hermes: return "Hermes"
            case .openclaw: return "OpenClaw"
            case .codex: return "Codex"
            }
        }

        var harnessMode: AgentHarnessMode {
            switch self {
            case .hermes: return .hermes
            case .openclaw: return .openclaw
            case .codex: return .codex
            }
        }

        var executableName: String {
            switch self {
            case .hermes: return "hermes"
            case .openclaw: return "openclaw"
            // codex-acp is the ACP stdio bridge that drives the Codex CLI.
            case .codex: return "codex-acp"
            }
        }

        var commandEnvironmentName: String {
            switch self {
            case .hermes: return "OMI_HERMES_ADAPTER_COMMAND"
            case .openclaw: return "OMI_OPENCLAW_ADAPTER_COMMAND"
            case .codex: return "OMI_CODEX_ADAPTER_COMMAND"
            }
        }

        var setupNeededStatus: String {
            "\(displayName) needs setup"
        }

        /// One-line capability description fed to the routing model so it can
        /// pick the best-suited connected agent for a task.
        var routerBlurb: String {
            switch self {
            case .codex:
                return "OpenAI Codex — strongest for software engineering: writing/refactoring code, working in repos, builds, tests, scripts, technical files."
            case .openclaw:
                return "OpenClaw — general autonomous computer agent with its own gateway/tool config; good for messaging and automation flows the user has wired into OpenClaw."
            case .hermes:
                return "Hermes — general autonomous agent; good for research and long-form independent work."
            }
        }
    }

    /// External providers that are installed AND ready to run right now.
    /// (needsAuth/missing are excluded — offering them to the router would
    /// just route tasks into a guaranteed startup failure.)
    nonisolated static func connectedDirectedProviders() -> [DirectedProvider] {
        [.codex, .openclaw, .hermes].filter { LocalAgentProviderDetector.isAvailable($0) }
    }

    struct ProviderDirective: Equatable {
        let provider: DirectedProvider
        let rewrittenQuery: String
        let title: String
        let ack: String
    }

    struct Snapshot: Encodable {
        let id: String
        let title: String
        let status: String
        let latestActivity: String
        let query: String
        let createdAt: String
        let completedAt: String?
    }

    /// Error markers that indicate the chosen agent never started working
    /// (not installed / not signed in / adapter unavailable). Only these are
    /// safe to auto-retry on another agent — a mid-task failure may already
    /// have side effects (sent messages, edited files) and must NOT be
    /// silently re-run elsewhere.
    nonisolated static let startupFailureMarkers: [String] = [
        "not available",
        "installed",
        "signed in",
        "not authenticated",
        "needs setup",
        "adapter is unavailable",
        "requires omi_",
        // The adapter subprocess could not reach its backend at startup
        // (e.g. OpenClaw's `acp` bridge with the gateway daemon not running:
        // "ACP bridge failed: connect ECONNREFUSED 127.0.0.1:18789").
        // Connection-refused means no work was performed, so retrying on
        // another agent is safe.
        "econnrefused",
        "acp bridge failed",
    ]

    nonisolated static func isStartupClassFailure(
        _ errorText: String,
        failure: AgentRuntimeFailure? = nil
    ) -> Bool {
        // Prefer the runtime's own failure taxonomy when the bridge provided a
        // structured failure (failures.ts / kernel failAttemptBeforeExecution):
        // - source "adapter_process": the adapter subprocess errored/exited
        //   (spawn failure, backend unreachable) — no prompt was completed.
        // - binding/registration/config codes: the kernel failed the attempt
        //   before execution started.
        // - adapter_execution_failed: the prompt was already running — may
        //   have side effects, never re-run elsewhere.
        if let failure {
            if failure.source == "adapter_process" { return true }
            switch failure.code {
            case "binding_failed", "adapter_not_registered", "adapter_config_invalid", "stale_binding":
                return true
            case "adapter_execution_failed":
                return false
            default:
                break
            }
        }
        // Unstructured errors (plain bridge `type:"error"` messages) fall back
        // to marker matching on the display text.
        let lower = errorText.lowercased()
        return startupFailureMarkers.contains { lower.contains($0) }
    }

    /// If a router-selected pill failed before doing any work, retry the same
    /// task on the next ranked candidate (terminal fallback: Omi's built-in
    /// agent via nil override). User-directed pills never auto-fallback.
    private func maybeAutoFallback(
        for pill: AgentPill,
        errorText: String,
        failure: AgentRuntimeFailure? = nil,
        hadProgress: Bool = false
    ) {
        guard Self.isStartupClassFailure(errorText, failure: failure) else { return }
        // Extra safety: if the pill already streamed content or produced a
        // response, work happened — never silently re-run it elsewhere.
        guard !hadProgress else { return }

        if !pill.autoFallbackCandidates.isEmpty {
            var candidates = pill.autoFallbackCandidates
            pill.autoFallbackCandidates = []
            let next = candidates.removeFirst()
            log("AgentPill: auto-fallback after startup failure — retrying on \(next.displayName)")
            pill.latestActivity = "\(errorText) — trying \(next.displayName) instead"
            let replacement = spawnFromUserQuery(
                pill.query,
                model: pill.model,
                preFetchedTitle: pill.title,
                bridgeHarnessOverride: next.harnessMode
            )
            replacement.wasRouterSelected = true
            replacement.autoFallbackCandidates = candidates
            return
        }

        // Terminal fallback: every router-ranked external candidate failed at
        // startup — run the task on Omi's built-in agent (nil override).
        if pill.wasRouterSelected, pill.bridgeHarnessOverride != nil {
            log("AgentPill: auto-fallback exhausted external candidates — retrying on Omi built-in agent")
            pill.latestActivity = "\(errorText) — trying Omi's built-in agent instead"
            _ = spawnFromUserQuery(
                pill.query,
                model: pill.model,
                preFetchedTitle: pill.title
            )
        }
    }

    /// Ask Claude Haiku whether the message is a quick info question (→ chat)
    /// or a background task (→ agent). Falls back to `.chat` on error/timeout
    /// so we never accidentally hijack a question into a long-running pill.
    /// ~300-500ms via the desktop-backend's OpenAI-compatible proxy.
    static func classify(_ query: String) async -> RouterDecision {
        guard let result = await runRouterCall(for: query) else {
            return RouterDecision(route: .chat, title: nil, ack: nil)
        }
        return result
    }

    private static func runRouterCall(for query: String) async -> RouterDecision? {
        let baseURL = await APIClient.shared.rustBackendURL
        guard !baseURL.isEmpty else {
            log("AgentPill: router skipped — rustBackendURL empty, defaulting to chat")
            return nil
        }
        let normalized = baseURL.hasSuffix("/") ? baseURL : baseURL + "/"
        guard let url = URL(string: normalized + "v2/chat/completions") else { return nil }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 4
        do {
            let headers = try await APIClient.shared.buildHeaders(requireAuth: true)
            for (k, v) in headers { request.setValue(v, forHTTPHeaderField: k) }
        } catch {
            log("AgentPill: router skipped — auth header unavailable (\(error.localizedDescription))")
            return nil
        }

        let connectedProviders = connectedDirectedProviders()
        let agentsField: String
        let agentsSection: String
        if connectedProviders.isEmpty {
            agentsField = ""
            agentsSection = ""
        } else {
            agentsField = #","agents":["<provider id>",...]"#
            let providerLines = connectedProviders
                .map { "- \($0.rawValue): \($0.routerBlurb)" }
                .joined(separator: "\n")
            agentsSection = """

            The user also has these external local agents connected (beyond Omi's built-in agent):
            \(providerLines)

            When route is "agent", set "agents" to the connected external agents genuinely better suited to this task than Omi's built-in agent, best first. Omi's built-in agent is the safe default with full access to the user's apps, browser, calendar, and memory — use "agents":[] for general computer/app/browser tasks or whenever unsure. Only pick an external agent when the task clearly matches its strength. Examples: background coding / build a script / fix a repo -> ["codex"]; open-ended autonomous research -> ["hermes"]; a flow the user automated in OpenClaw -> ["openclaw"]; send a message / calendar / browse / summarize screen -> []. When route is "chat", use "agents":[].
            """
        }

        let prompt = """
        The user just sent this message in the Omi floating bar:

        "\(query)"

        Decide whether to (a) answer it inline in the chat bar, or (b) spawn a background agent that will do work on the user's computer/apps/browser.

        Reply with ONLY a single-line JSON object, no prose, no markdown:
        {"route":"chat"|"agent","title":"<3-5 word imperative title in Title Case, no trailing punctuation>","ack":"<one short spoken acknowledgement, max 7 words, friendly tone>"\(agentsField)}

        Use "agent" ONLY when the request requires the assistant to take real actions on the user's computer/browser/apps that will plausibly take more than ~10 seconds — building/coding something, sending/posting a message, editing or creating files, multi-step browser navigation, generating a long document.
        Use "chat" for everything else: questions, lookups (even if the user uses words like "search"/"find"/"look up"), definitions, single facts, explanations, short summaries, opinions, conversation. When in doubt, choose "chat".\(agentsSection)
        """

        let body: [String: Any] = [
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 120,
            "messages": [["role": "user", "content": prompt]],
            "stream": false,
        ]
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                log("AgentPill: router failed — no HTTP response, defaulting to chat")
                return nil
            }
            guard (200..<300).contains(http.statusCode) else {
                let bodyText = String(data: data.prefix(200), encoding: .utf8) ?? "<binary>"
                log("AgentPill: router HTTP \(http.statusCode) — \(bodyText), defaulting to chat")
                return nil
            }
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                let choices = json["choices"] as? [[String: Any]],
                let message = choices.first?["message"] as? [String: Any],
                let text = message["content"] as? String
            else {
                log("AgentPill: router response shape unexpected, defaulting to chat")
                return nil
            }
            // Haiku occasionally ignores the "no markdown" instruction and
            // wraps the JSON in ```json ... ``` fences, or emits leading
            // prose. Extract the first balanced {...} object instead of
            // trusting the whole response to be raw JSON.
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            let jsonBody: String
            if let firstBrace = trimmed.firstIndex(of: "{"),
                let lastBrace = trimmed.lastIndex(of: "}"),
                firstBrace < lastBrace
            {
                jsonBody = String(trimmed[firstBrace...lastBrace])
            } else {
                jsonBody = trimmed
            }
            guard let payloadData = jsonBody.data(using: .utf8),
                let payload = try? JSONSerialization.jsonObject(with: payloadData) as? [String: Any],
                let routeStr = (payload["route"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            else {
                log("AgentPill: router JSON parse failed — raw: \(String(trimmed.prefix(200))), defaulting to chat")
                return nil
            }
            let route = Route(rawValue: routeStr) ?? .chat
            let title = (payload["title"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
            let ack = (payload["ack"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
            // Provider ranking: keep only ids that map to a provider we offered
            // as connected — the model must not route to something we didn't.
            var rankedProviders: [DirectedProvider] = []
            if route == .agent, let agentIds = payload["agents"] as? [String] {
                var seen = Set<DirectedProvider>()
                for id in agentIds {
                    let normalized = id.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                    guard let provider = DirectedProvider(rawValue: normalized),
                        connectedProviders.contains(provider),
                        seen.insert(provider).inserted
                    else { continue }
                    rankedProviders.append(provider)
                }
            }
            log("AgentPill: router decided route=\(route.rawValue) title=\"\(title ?? "")\" agents=\(rankedProviders.map(\.rawValue))")
            return RouterDecision(
                route: route,
                title: (title?.isEmpty == false) ? String(title!.prefix(40)) : nil,
                ack: (ack?.isEmpty == false) ? String(ack!.prefix(120)) : nil,
                rankedProviders: rankedProviders
            )
        } catch {
            log("AgentPill: router threw — \(error.localizedDescription), defaulting to chat")
            return nil
        }
    }

    /// Parse phrases like "spawn 3 agents", "5 tasks", "two agents working in
    /// parallel" out of a user query. Returns 1 if no count is mentioned.
    /// Handles "3 test agents" — words between the number and the noun are
    /// allowed (up to 5 tokens) so demo phrasing doesn't fall through.
    static func parseAgentCount(from text: String) -> Int {
        let lower = text.lowercased()
        let nounGroup = "(?:agents?|tasks?|pills?|things?)"
        // Numeric: "3 agents", "spawn 5 in parallel", "3 test agents",
        // "spawn 3 of these", but NOT "in 30 seconds".
        // Allow up to ~5 short words between the number and the noun.
        let numericPattern = #"\b(\d+)(?:\s+\S+){0,5}\s+\#(nounGroup)\b"#
        if let regex = try? NSRegularExpression(pattern: numericPattern),
            let match = regex.firstMatch(in: lower, range: NSRange(lower.startIndex..., in: lower)),
            match.numberOfRanges > 1,
            let range = Range(match.range(at: 1), in: lower),
            let n = Int(lower[range]),
            n > 0
        {
            return min(n, 8)
        }
        // Word form: "two agents", "three tasks", "five test agents"
        let wordToNumber: [String: Int] = [
            "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        ]
        let wordPattern = #"\b(two|three|four|five|six|seven|eight)(?:\s+\S+){0,5}\s+\#(nounGroup)\b"#
        if let regex = try? NSRegularExpression(pattern: wordPattern),
            let match = regex.firstMatch(in: lower, range: NSRange(lower.startIndex..., in: lower)),
            match.numberOfRanges > 1,
            let range = Range(match.range(at: 1), in: lower),
            let n = wordToNumber[String(lower[range])]
        {
            return min(n, 8)
        }
        return 1
    }

    nonisolated static func providerDirective(from text: String) -> ProviderDirective? {
        providerDirective(from: text, contextualPreviousRequest: nil)
    }

    nonisolated static func providerDirective(
        from text: String,
        contextualPreviousRequest: String?
    ) -> ProviderDirective? {
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
            guard let match = regex.firstMatch(in: trimmed, range: range), match.numberOfRanges >= 2 else { continue }
            guard let providerRange = Range(match.range(at: 1), in: trimmed) else { continue }
            let providerToken = trimmed[providerRange]
                .lowercased()
                .replacingOccurrences(of: " ", with: "")
            let provider: DirectedProvider
            switch providerToken {
            case "openclaw": provider = .openclaw
            case "hermes": provider = .hermes
            case "codex": provider = .codex
            default: continue
            }

            let restIndex = match.numberOfRanges > 2 ? 2 : NSNotFound
            let rest: String
            if restIndex != NSNotFound,
                let restRange = Range(match.range(at: restIndex), in: trimmed) {
                rest = String(trimmed[restRange]).trimmingCharacters(in: .whitespacesAndNewlines)
            } else {
                rest = ""
            }
            let contextualObjective = contextualPreviousRequest
                .flatMap { providerObjective(from: $0) }?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let objective: String
            if rest.isEmpty, isProviderCorrection(trimmed), contextualObjective?.isEmpty == false {
                objective = contextualObjective!
            } else {
                objective = rest.isEmpty ? "Say how it's going." : rest
            }
            return ProviderDirective(
                provider: provider,
                rewrittenQuery: objective,
                title: provider.displayName,
                ack: "Asking \(provider.displayName)."
            )
        }

        return nil
    }

    nonisolated static func providerObjective(from text: String) -> String {
        let original = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !original.isEmpty else { return original }
        let patterns = [
            #"(?i)^\s*(?:please\s+)?(?:ask|tell|ping|message|run|use|try)\s+\S+\s+(?:to|about)\s+(.+)$"#,
            #"(?i)^\s*(?:please\s+)?(?:ask|tell|ping|message|run|use|try)\s+\S+\s+(.+)$"#,
        ]
        for pattern in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let range = NSRange(original.startIndex..., in: original)
            guard let match = regex.firstMatch(in: original, range: range),
                  match.numberOfRanges > 1,
                  let objectiveRange = Range(match.range(at: 1), in: original) else {
                continue
            }
            let objective = original[objectiveRange].trimmingCharacters(in: .whitespacesAndNewlines)
            if !objective.isEmpty {
                return objective
            }
        }
        return original
    }

    private nonisolated static func isProviderCorrection(_ text: String) -> Bool {
        let lower = text.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        return lower.hasPrefix("i meant")
            || lower.hasPrefix("meant")
            || lower.hasSuffix("instead")
            || lower.contains(" instead of ")
    }

    /// User control-plane request from the floating bar UI: create a visible sibling
    /// background agent. This is intentionally separate from an agent's own tool use;
    /// existing floating agents still cannot self-spawn nested pills.
    nonisolated static func floatingAgentHandoff(for text: String) -> FloatingAgentHandoff? {
        let original = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !original.isEmpty else { return nil }
        let lower = text.lowercased()
        // Exclude question-style starters — informational queries like
        // "how do I start a background agent?" or "can you explain how to run
        // agents?" should answer inline, not spawn a pill.
        let questionStarters = [
            "how do i", "how do you", "how to", "what is", "what are", "what does",
            "what can", "whats", "can you explain", "could you explain",
            "explain how", "tell me about", "tell me how", "why", "is it",
            "are agents", "do agents", "does the agent",
            // Modal question starters — queries like "can I run agents in the
            // background?", "will agents run while I work?", or "should I start
            // an agent?" contain an agent noun + an action verb but are questions,
            // not imperatives, so they should answer inline, not spawn a pill.
            "can i", "could i", "should i", "would i", "will agents",
            "will the agent", "may i", "do i need", "do i have",
        ]
        let trimmedLower = lower.trimmingCharacters(in: .whitespacesAndNewlines)
        if questionStarters.contains(where: { trimmedLower.hasPrefix($0) }) {
            return nil
        }
        // Negation guard (fully scoped): only suppress spawn when a negation
        // word appears in direct construction with BOTH a spawn action AND an
        // agent noun — e.g. "don't spawn an agent", "no agent", "without a
        // pill". Every pattern requires agent-noun proximity so unrelated
        // negation words (e.g. "don't make me laugh, spawn an agent") do not
        // false-suppress legitimate spawns. (Cubic P1 — tightens prior scoped
        // guard.)
        let agentNoun = Self.agentNounPattern
        let article = #"(?:a|an|any)\s+"#
        let negationOptOuts = [
            // "don't spawn an agent", "do not create a pill", "don't run agents"
            #"\b(?:don'?t|do not|never)\s+(?:spawn|start|launch|kick\s+off|create|make|run)\s+(?:"# + article + #")?"# + agentNoun + #"\b"#,
            // "no agent", "not an agent", "no pills", "not a subagent"
            #"\b(?:no|not)\s+(?:"# + article + #")?"# + agentNoun + #"\b"#,
            // "without spawning an agent", "without a pill",
            // "without creating subagents"
            #"\bwithout\s+(?:(?:spawning|creating|making|starting|launching|running)\s+(?:"# + article + #")?|"# + article + #")?"# + agentNoun + #"\b"#,
            // "not spawning an agent", "never creating pills"
            #"\b(?:not|never)\s+(?:spawning|creating|making|starting|launching|running)\s+(?:"# + article + #")?"# + agentNoun + #"\b"#,
        ]
        if negationOptOuts.contains(where: { lower.range(of: $0, options: .regularExpression) != nil }) {
            return nil
        }
        let agentPattern = #"\b"# + Self.agentNounPattern + #"\b"#
        let actionPattern = #"\b(?:spawn|start|launch|kick\s+off|create|make|run)\b"#
        guard lower.range(of: agentPattern, options: .regularExpression) != nil else { return nil }
        guard lower.range(of: actionPattern, options: .regularExpression) != nil else { return nil }

        return FloatingAgentHandoff(
            originalRequest: original,
            agentTask: extractFloatingAgentTask(from: original) ?? original
        )
    }

    nonisolated static func explicitlyRequestsFloatingAgent(_ text: String) -> Bool {
        floatingAgentHandoff(for: text) != nil
    }

    private nonisolated static func extractFloatingAgentTask(from text: String) -> String? {
        let nounPattern = #"\b"# + Self.agentNounPattern + #"\b"#
        guard let regex = try? NSRegularExpression(pattern: nounPattern, options: [.caseInsensitive]) else {
            return nil
        }
        let range = NSRange(text.startIndex..., in: text)
        guard let match = regex.firstMatch(in: text, range: range),
              let matchRange = Range(match.range, in: text)
        else {
            return nil
        }

        var task = String(text[matchRange.upperBound...])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let connectorPattern = #"^(?:to|for|that\s+can|that\s+will|which\s+can|which\s+will|and)\s+"#
        if let connectorRegex = try? NSRegularExpression(pattern: connectorPattern, options: [.caseInsensitive]) {
            task = connectorRegex.stringByReplacingMatches(
                in: task,
                range: NSRange(task.startIndex..., in: task),
                withTemplate: ""
            )
            .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard task.split(whereSeparator: \.isWhitespace).count >= 2 else { return nil }
        return task
    }

    /// Spawn one or more pills for a user query. If the query says "spawn 3
    /// agents" we create 3 pills (each runs the same task on the shared
    /// queue). Returns the first pill so callers can inspect it.
    @discardableResult
    func spawnFromUserQuery(
        _ query: String,
        model: String,
        fromVoice: Bool = false,
        preFetchedTitle: String? = nil,
        preFetchedAck: String? = nil,
        bridgeHarnessOverride: AgentHarnessMode? = nil
    ) -> AgentPill {
        let count = AgentPillsManager.parseAgentCount(from: query)
        if count <= 1 {
            return spawn(
                query: query,
                model: model,
                fromVoice: fromVoice,
                preFetchedTitle: preFetchedTitle,
                preFetchedAck: preFetchedAck,
                bridgeHarnessOverride: bridgeHarnessOverride
            )
        }
        var first: AgentPill?
        for i in 1...count {
            let labelled = "[\(i)/\(count)] \(query)"
            // Only the first pill speaks the acknowledgement when N > 1,
            // otherwise we'd hear N overlapping voices. Only the first pill
            // gets the pre-fetched title/ack — the others fall back to their
            // own title generation since their query text differs (the
            // [i/N] prefix changes the model's output).
            let pill = spawn(
                query: labelled,
                model: model,
                fromVoice: fromVoice && first == nil,
                preFetchedTitle: first == nil ? preFetchedTitle : nil,
                preFetchedAck: first == nil ? preFetchedAck : nil,
                bridgeHarnessOverride: bridgeHarnessOverride
            )
            if first == nil { first = pill }
        }
        return first ?? spawn(query: query, model: model, fromVoice: fromVoice, bridgeHarnessOverride: bridgeHarnessOverride)
    }

    @discardableResult
    func spawnFromHandoff(
        _ handoff: FloatingAgentHandoff,
        model: String,
        fromVoice: Bool = false,
        preFetchedTitle: String? = nil,
        preFetchedAck: String? = nil,
        bridgeHarnessOverride: AgentHarnessMode? = nil
    ) -> AgentPill {
        let count = AgentPillsManager.parseAgentCount(from: handoff.originalRequest)
        if count <= 1 {
            return spawn(
                query: handoff.agentTask,
                model: model,
                fromVoice: fromVoice,
                preFetchedTitle: preFetchedTitle,
                preFetchedAck: preFetchedAck,
                bridgeHarnessOverride: bridgeHarnessOverride
            )
        }
        var first: AgentPill?
        for i in 1...count {
            let labelled = "[\(i)/\(count)] \(handoff.agentTask)"
            let pill = spawn(
                query: labelled,
                model: model,
                fromVoice: fromVoice && first == nil,
                preFetchedTitle: first == nil ? preFetchedTitle : nil,
                preFetchedAck: first == nil ? preFetchedAck : nil,
                bridgeHarnessOverride: bridgeHarnessOverride
            )
            if first == nil { first = pill }
        }
        return first ?? spawn(
            query: handoff.agentTask,
            model: model,
            fromVoice: fromVoice,
            bridgeHarnessOverride: bridgeHarnessOverride
        )
    }

    /// Spawn a new agent pill. Each pill gets its own ChatProvider so the
    /// pills truly run in parallel. Bridge boots are staggered through
    /// `bootChain` so we never race ACP startup; once a pill's bridge is
    /// warmed it sends concurrently with everything else.
    @discardableResult
    func spawn(
        query: String,
        model: String,
        fromVoice: Bool = false,
        preFetchedTitle: String? = nil,
        preFetchedAck: String? = nil,
        systemPromptSuffix: String? = nil,
        bridgeHarnessOverride: AgentHarnessMode? = nil
    ) -> AgentPill {
        let pill = AgentPill(query: query, model: model, bridgeHarnessOverride: bridgeHarnessOverride)
        if let preFetchedTitle, !preFetchedTitle.isEmpty {
            pill.title = preFetchedTitle
        }

        trimForNewPillIfNeeded()
        if pills.count >= maxPills {
            // Last-resort trim: drop the oldest non-active pill. Never clean up
            // the pill the user is actively viewing in the agent chat surface —
            // doing so would drop the window state to stale/blank content.
            let activeChatPillID = FloatingControlBarManager.shared.activeAgentChatPillID
            if let victimID = pills.first(where: { $0.id != activeChatPillID })?.id {
                cleanup(pillID: victimID)
            }
        }

        pills.append(pill)

        let provider = ChatProvider(bridgeHarnessOverride: bridgeHarnessOverride)
        let hasBridgeHarnessOverride = bridgeHarnessOverride != nil
        if let floating = FloatingControlBarManager.shared.sharedFloatingProvider {
            provider.workingDirectory = floating.workingDirectory
            // Directed Hermes/OpenClaw pills must not inherit the floating bar's
            // Claude model override. Those harnesses can reject Omi's Claude
            // aliases during session/set_model, so leave model selection to the
            // provider-native default when a harness override is present.
            if !hasBridgeHarnessOverride {
                provider.modelOverride = floating.modelOverride
            }
        }
        providersByPill[pill.id] = provider

        let messageCountBefore = provider.messages.count
        messageCountByPill[pill.id] = messageCountBefore
        streamsByPill[pill.id] = provider.$messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self, weak pill] messages in
                guard let self, let pill else { return }
                self.handle(messages: messages, since: messageCountBefore, for: pill)
            }
        let surfaceRef = AgentSurfaceReference.floatingPill(pillId: pill.id)
        projectionStreamsByPill[pill.id] = AgentRuntimeStatusStore.shared.$projectionsBySurface
            .receive(on: DispatchQueue.main)
            .sink { [weak pill] projections in
                guard let pill, let projection = projections[surfaceRef.key] else { return }
                guard !pill.status.isFinished || projection.status.isTerminal else { return }
                AgentPillsManager.apply(projection: projection, to: pill)
            }

        // Stagger bridge boots: chain this pill's warmup after the previous
        // pill's. Once warmed, the actual sendMessage runs in parallel with
        // every other warmed pill.
        let previousBoot = bootChain
        let myBoot = Task { [weak provider] in
            await previousBoot.value
            await provider?.warmupBridge()
        }
        bootChain = myBoot

        pill.status = .starting
        if let preFetchedAck, !preFetchedAck.isEmpty {
            pill.latestActivity = preFetchedAck
        } else {
            pill.latestActivity = "Warming up…"
        }

        // For voice queries, speak the pre-fetched ack from the router (or a
        // random instant ack) BEFORE waiting for the bridge so the user
        // always hears confirmation that we heard them.
        if fromVoice {
            let phrase = (preFetchedAck?.isEmpty == false) ? preFetchedAck! : AgentPillsManager.randomAck()
            FloatingBarVoicePlaybackService.shared.speakOneShot(phrase)
        }

        // If the router already returned a title we don't need a second
        // Haiku call for title generation. Otherwise kick one off in the
        // background to upgrade the heuristic title.
        if preFetchedTitle == nil {
            Task { [weak pill] in
                guard let pill else { return }
                guard let result = await AgentPillsManager.generateTitleAndAck(for: pill.query) else { return }
                await MainActor.run {
                    pill.title = result.title
                    if pill.latestActivity == "Warming up…" || pill.latestActivity == "Starting…" {
                        pill.latestActivity = result.ack
                    }
                }
            }
        }

        let runTask = Task { [weak self, weak pill, weak provider] in
            await myBoot.value
            guard !Task.isCancelled else { return }
            guard let self, let pill, let provider else { return }
            // Bridge is up; flip to running and fire the prompt. Concurrent
            // with any other pill that's already past this point.
            pill.status = .running
            pill.completedAt = nil
            pill.suggestedFollowUps = []
            let finalText = await provider.sendMessage(
                pill.query,
                model: Self.modelForSend(pill: pill, provider: provider),
                systemPromptSuffix: systemPromptSuffix ?? Self.backgroundAgentSystemPromptSuffix,
                systemPromptStyle: .floating,
                sessionKey: "agent-\(pill.id.uuidString)",
                surfaceRef: surfaceRef,
                legacyClientScope: AgentLegacyClientScope.floatingPill
            )
            guard !Task.isCancelled else { return }
            self.complete(pill: pill, provider: provider, finalText: finalText)
        }
        runTasksByPill[pill.id] = runTask

        return pill
    }

    // MARK: - Voice follow-up (continue THIS agent's session)

    /// Tap the pill's mic button: start recording if idle, or stop + transcribe +
    /// send if this pill is already recording.
    func toggleFollowUpVoice(for pill: AgentPill) {
        if recordingPillID == pill.id {
            log("AgentPills: voice follow-up STOP tapped for \(pill.title)")
            recordingPillID = nil
            PushToTalkManager.shared.endPillFollowUp()
        } else if recordingPillID == nil {
            log("AgentPills: voice follow-up START tapped for \(pill.title)")
            recordingPillID = pill.id
            // Routes through the realtime omni STT (hub pipeline); the transcript comes
            // back into continueAgent(from:text:) for THIS pill's session.
            PushToTalkManager.shared.startPillFollowUp(for: pill)
        }
    }

    /// Send a follow-up to the SAME agent session — reuses the pill's ChatProvider +
    /// sessionKey so it keeps full context. Falls back to a fresh agent only if the
    /// session was already torn down (pill dismissed/trimmed).
    func continueAgent(from pill: AgentPill, text: String) {
        guard let provider = providersByPill[pill.id] else {
            spawnFromUserQuery(text, model: pill.model)
            return
        }
        pill.status = .running
        pill.completedAt = nil
        pill.suggestedFollowUps = []
        pill.latestActivity = "Working on your follow-up…"
        runTasksByPill[pill.id]?.cancel()
        let runTask = Task { @MainActor [weak self, weak pill, weak provider] in
            guard let self, let pill, let provider else { return }
            // If the provider is still streaming the previous turn, interrupt
            // it first and wait for the guard to clear before starting the next
            // agent turn. Otherwise the isSending guard returns nil and
            // complete() marks the pill as failed. (Codex P2.)
            if provider.isSending {
                provider.stopAgent()
                // stopAgent() has a 3s watchdog that force-releases isSending;
                // poll until the guard clears (bounded to ~4s total). Check
                // Task.isCancelled on every iteration so a cancelled follow-up
                // does not proceed to sendMessage. (Cubic P1.)
                for _ in 0..<80 {
                    if Task.isCancelled { return }
                    if !provider.isSending { break }
                    try? await Task.sleep(nanoseconds: 50_000_000)
                }
            }
            guard !Task.isCancelled else { return }
            let surfaceRef = AgentSurfaceReference.floatingPill(pillId: pill.id)
            let finalText = await provider.sendMessage(
                text, model: Self.modelForSend(pill: pill, provider: provider),
                systemPromptSuffix: Self.backgroundAgentSystemPromptSuffix,
                systemPromptStyle: .floating,
                sessionKey: "agent-\(pill.id.uuidString)",
                surfaceRef: surfaceRef,
                legacyClientScope: AgentLegacyClientScope.floatingPill)
            guard !Task.isCancelled else { return }
            self.complete(pill: pill, provider: provider, finalText: finalText)
        }
        runTasksByPill[pill.id] = runTask
    }

    /// Force-dismiss a pill.
    func dismiss(pillID: UUID) {
        // If the pill being dismissed is the one currently shown in the Ask Omi
        // surface, leave the agent surface first so conversationSurface does
        // not stay as .agent(id) pointing to a removed pill — which would leave
        // the view falling through to blank/stale Omi content. (Codex P2.)
        if FloatingControlBarManager.shared.activeAgentChatPillID == pillID {
            FloatingControlBarManager.shared.leaveActiveAgentSurfaceFromPillDismiss()
        }
        cleanup(pillID: pillID)
        if hoveredPillID == pillID { hoveredPillID = nil }
        if pinnedPillID == pillID { pinnedPillID = nil }
    }

    func stop(pillID: UUID) {
        guard let pill = pills.first(where: { $0.id == pillID }), !pill.status.isFinished else { return }
        log("AgentPills: stopping pill \(pill.title)")
        if recordingPillID == pillID {
            recordingPillID = nil
            PushToTalkManager.shared.cancelPillFollowUp(for: pillID)
        }
        providersByPill[pillID]?.stopAgent()
        runTasksByPill[pillID]?.cancel()
        runTasksByPill[pillID] = nil
        pill.status = .stopped
        pill.latestActivity = "Stopped by user"
        pill.completedAt = Date()
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        pill.markContentChanged()
        if pill.viewedAt != nil {
            scheduleViewedExpiration(for: pill)
        }
        AgentRuntimeStatusStore.shared.recordLocalCancellation(
            surface: .floatingPill(pillId: pillID),
            message: "Stopped by user"
        )
    }

    func markViewed(pillID: UUID) {
        guard let pill = pills.first(where: { $0.id == pillID }) else { return }
        pill.viewedAt = Date()
        scheduleViewedExpiration(for: pill)
        expireViewedFinishedPills(now: Date())
    }

    private func scheduleViewedExpiration(for pill: AgentPill) {
        viewedExpirationWorkItemsByPill[pill.id]?.cancel()
        guard pill.status.isFinished else { return }

        let pillID = pill.id
        let workItem = DispatchWorkItem { [weak self] in
            Task { @MainActor [weak self] in
                guard let self else { return }
                // If the pill is the one the user is actively viewing when the
                // timer fires, the expiration is skipped this round but the
                // timer must be re-armed — otherwise the one-shot DispatchWorkItem
                // is consumed and auto-expiration is permanently disabled for a
                // viewed finished pill even after the user navigates away.
                if FloatingControlBarManager.shared.activeAgentChatPillID == pillID {
                    if let pill = self.pills.first(where: { $0.id == pillID }) {
                        self.scheduleViewedExpiration(for: pill)
                    }
                    return
                }
                self.expireViewedFinishedPills(now: Date())
                self.viewedExpirationWorkItemsByPill[pillID] = nil
            }
        }
        viewedExpirationWorkItemsByPill[pillID] = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + viewedFinishedTTL, execute: workItem)
    }

    private func expireViewedFinishedPills(now: Date = Date()) {
        let activeChatPillID = FloatingControlBarManager.shared.activeAgentChatPillID
        let expiredIDs = pills
            .filter { pill in
                guard pill.status.isFinished, let viewedAt = pill.viewedAt else { return false }
                // Never expire the pill the user is actively viewing in the
                // floating bar's agent chat — otherwise the active chat
                // disappears/reverts while they are still reading it.
                guard pill.id != activeChatPillID else { return false }
                return now.timeIntervalSince(viewedAt) >= viewedFinishedTTL
            }
            .map(\.id)
        for id in expiredIDs {
            cleanup(pillID: id)
        }
    }

    private func trimForNewPillIfNeeded() {
        expireViewedFinishedPills()
        guard pills.count >= maxPills else { return }

        let activeChatPillID = FloatingControlBarManager.shared.activeAgentChatPillID

        if let oldestDoneID = pills
            .filter({ $0.status == .done && $0.id != activeChatPillID })
            .sorted(by: { ($0.completedAt ?? $0.createdAt) < ($1.completedAt ?? $1.createdAt) })
            .first?.id {
            cleanup(pillID: oldestDoneID)
            return
        }

        if let oldestFinishedID = pills
            .filter({ $0.status.isFinished && $0.id != activeChatPillID })
            .sorted(by: { ($0.completedAt ?? $0.createdAt) < ($1.completedAt ?? $1.createdAt) })
            .first?.id {
            cleanup(pillID: oldestFinishedID)
        }
    }

    func dismiss(pillIdString: String) -> Bool {
        guard let id = findPillId(from: pillIdString) else { return false }
        dismiss(pillID: id)
        return true
    }

    func replaceWithAutomationPills(count requestedCount: Int) -> [AgentPill] {
        let ids = pills.map(\.id)
        for id in ids {
            cleanup(pillID: id)
        }

        let count = min(max(requestedCount, 1), maxPills)
        let seeded = (0..<count).map { index -> AgentPill in
            let pill = AgentPill(query: "Automation subagent \(index + 1)", model: ModelQoS.Claude.defaultSelection)
            pill.title = index == 0 ? "SLEEP FOR 5" : "Sleep Subagent"
            if index == 0 {
                let aiMessage = ChatMessage(text: "Automation output for subagent \(index + 1).", sender: .ai)
                pill.status = .done
                pill.latestActivity = "Done — automation output."
                pill.aiMessage = aiMessage
                pill.conversationMessages = [
                    ChatMessage(text: pill.query, sender: .user),
                    aiMessage,
                ]
                pill.completedAt = Date()
            } else {
                pill.status = .running
                pill.latestActivity = "Working…"
                pill.aiMessage = nil
                pill.completedAt = nil
            }
            pill.markContentChanged()
            return pill
        }
        pills = seeded
        return seeded
    }

    private func cleanup(pillID: UUID) {
        if recordingPillID == pillID {
            recordingPillID = nil
            PushToTalkManager.shared.cancelPillFollowUp(for: pillID)
        }
        runTasksByPill[pillID]?.cancel()
        runTasksByPill[pillID] = nil
        viewedExpirationWorkItemsByPill[pillID]?.cancel()
        viewedExpirationWorkItemsByPill[pillID] = nil
        providersByPill[pillID]?.stopAgent()
        streamsByPill[pillID]?.cancel()
        streamsByPill[pillID] = nil
        projectionStreamsByPill[pillID]?.cancel()
        projectionStreamsByPill[pillID] = nil
        providersByPill[pillID] = nil
        messageCountByPill[pillID] = nil
        pills.removeAll { $0.id == pillID }
    }

    private static func modelForSend(pill: AgentPill, provider: ChatProvider) -> String? {
        provider.hasBridgeHarnessOverride ? nil : pill.model
    }

    /// Remove all completed (done or failed) pills.
    func clearCompleted() {
        let ids = pills.filter { $0.status.isFinished }.map(\.id)
        for id in ids {
            cleanup(pillID: id)
        }
    }

    private func isFinished(_ status: AgentPill.Status) -> Bool {
        status.isFinished
    }

    func snapshots(limit: Int = 20) -> [Snapshot] {
        let formatter = ISO8601DateFormatter()
        return pills
            .sorted { $0.createdAt > $1.createdAt }
            .prefix(limit)
            .map { pill in
                Snapshot(
                    id: pill.id.uuidString,
                    title: pill.title,
                    status: pill.status.machineLabel,
                    latestActivity: pill.latestActivity,
                    query: pill.query,
                    createdAt: formatter.string(from: pill.createdAt),
                    completedAt: pill.completedAt.map { formatter.string(from: $0) }
                )
            }
    }

    func snapshotJSON(limit: Int = 20) -> String {
        let payload: [String: [Snapshot]] = ["floating_agent_pills": snapshots(limit: limit)]
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(payload), let json = String(data: data, encoding: .utf8) else {
            return "{\"floating_agent_pills\":[]}"
        }
        return json
    }

    func statusSummary(limit: Int = 8) -> String {
        let recent = snapshots(limit: limit)
        guard !recent.isEmpty else {
            return "No floating agent pills are running or recently finished."
        }
        let lines = recent.map { snapshot in
            "- \(snapshot.title) [\(snapshot.id.prefix(8))]: \(snapshot.status); \(snapshot.latestActivity)"
        }
        return "Floating agent pills:\n" + lines.joined(separator: "\n")
    }

    func manage(action: String, agentId: String?) -> String {
        switch action.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "list", "status":
            return statusSummary()
        case "dismiss":
            guard let agentId, !agentId.isEmpty else {
                return "Missing agent_id. Call get_task_agent_status first and pass the floating_agent_pills id."
            }
            return dismiss(pillIdString: agentId)
                ? "Dismissed floating agent pill \(agentId)."
                : "No floating agent pill matched \(agentId)."
        case "clear_completed":
            let count = pills.filter { $0.status.isFinished }.count
            clearCompleted()
            return "Cleared \(count) completed floating agent pill(s)."
        default:
            return "Unknown action. Use list, dismiss, or clear_completed."
        }
    }

    private func findPillId(from text: String) -> UUID? {
        let needle = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return nil }
        if let exact = UUID(uuidString: text) {
            return pills.first(where: { $0.id == exact })?.id
        }
        return pills.first { pill in
            let id = pill.id.uuidString.lowercased()
            return id == needle || id.hasPrefix(needle)
        }?.id
    }

    private func handle(messages: [ChatMessage], since: Int, for pill: AgentPill) {
        guard messages.count > since else { return }
        let recent = Array(messages.suffix(from: since))
        let displayMessages = recent.filter { message in
            let trimmed = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
            return message.sender == .user || !trimmed.isEmpty || message.isStreaming || !message.contentBlocks.isEmpty
        }
        if !displayMessages.isEmpty {
            pill.conversationMessages = displayMessages
            pill.markContentChanged()
        }
        guard let aiMessage = recent.last(where: { $0.sender == .ai }) else { return }
        pill.aiMessage = aiMessage
        pill.markContentChanged()

        if pill.status.isFinished {
            return
        }

        if pill.status == .starting {
            pill.status = .running
        }

        let activity = Self.describeActivity(for: aiMessage)
        if !activity.isEmpty && activity != pill.latestActivity {
            pill.latestActivity = activity
            pill.transcript.append(activity)
            pill.markContentChanged()
        }
    }

    /// Pill-bar activity string for an AI message. While a message is still
    /// streaming, skip partial text chunks so the pill does not flicker through
    /// mid-token labels like "O..." or "Open..." before the final response lands.
    /// Tool calls still show immediately because they are atomic activity.
    private static func describeActivity(for message: ChatMessage) -> String {
        for block in message.contentBlocks.reversed() {
            switch block {
            case .toolCall(_, let name, _, _, let input, _):
                let display = ChatContentBlock.displayName(for: name)
                if let input, !input.summary.isEmpty {
                    return "\(display) — \(input.summary)"
                }
                return display
            case .text(_, let text):
                guard !message.isStreaming else { continue }
                let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    return String(trimmed.prefix(110))
                }
            case .thinking, .discoveryCard:
                continue
            }
        }
        let trimmedFallback = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !message.isStreaming, !trimmedFallback.isEmpty {
            return String(trimmedFallback.prefix(110))
        }
        return "Working…"
    }

    private func complete(pill: AgentPill, provider: ChatProvider, finalText: String?) {
        let trimmedFinalText = finalText?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let trimmedFinalText, !trimmedFinalText.isEmpty {
            if pill.aiMessage?.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false {
                var finalMessage = pill.aiMessage ?? ChatMessage(text: trimmedFinalText, sender: .ai)
                finalMessage.text = trimmedFinalText
                finalMessage.isStreaming = false
                pill.aiMessage = finalMessage
                if pill.conversationMessages.isEmpty {
                    pill.conversationMessages = [
                        ChatMessage(text: pill.query, sender: .user),
                        finalMessage,
                    ]
                } else if let index = pill.conversationMessages.firstIndex(where: { $0.id == finalMessage.id }) {
                    pill.conversationMessages[index] = finalMessage
                } else {
                    pill.conversationMessages.append(finalMessage)
                }
            }
            pill.latestActivity = String(trimmedFinalText.prefix(140))
            pill.markContentChanged()
        }
        if let projection = AgentRuntimeStatusStore.shared.floatingPillProjection(pillId: pill.id) {
            Self.apply(projection: projection, to: pill)
            if projection.status.isTerminal {
                pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
                if pill.viewedAt != nil {
                    scheduleViewedExpiration(for: pill)
                }
                return
            }
        }
        if let errorText = provider.errorMessage, !errorText.isEmpty {
            // Captured before ensureFailureMessage, which itself sets aiMessage.
            let hadProgress = !pill.transcript.isEmpty || pill.aiMessage != nil
            pill.status = .failed(errorText)
            pill.latestActivity = errorText
            pill.completedAt = Date()
            Self.ensureFailureMessage(errorText, for: pill)
            pill.markContentChanged()
            maybeAutoFallback(
                for: pill,
                errorText: errorText,
                failure: provider.lastAgentRuntimeFailure,
                hadProgress: hadProgress
            )
        } else if let trimmedFinalText, !trimmedFinalText.isEmpty {
            pill.status = .done
            pill.completedAt = Date()
            pill.markContentChanged()
            AgentRuntimeStatusStore.shared.recordLocalSuccess(
                surface: .floatingPill(pillId: pill.id),
                statusText: trimmedFinalText
            )
        } else {
            pill.status = .failed("Agent ended before reporting a final result")
            pill.completedAt = Date()
            pill.latestActivity = "Agent ended before reporting a final result"
            Self.ensureFailureMessage("Agent ended before reporting a final result", for: pill)
            pill.markContentChanged()
        }
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        if pill.viewedAt != nil {
            scheduleViewedExpiration(for: pill)
        }
        // Keep the provider + stream alive after completion so a voice/text follow-up
        // can continue THIS agent's session with full context. They're torn down on
        // dismiss, or when the pill is trimmed at the maxPills cap (see cleanup()).
    }

    private static func ensureFailureMessage(_ errorText: String, for pill: AgentPill) {
        guard let failureText = AgentFailureTranscriptFormatter.transcriptText(for: errorText) else { return }
        let failureMessage = ChatMessage(text: failureText, sender: .ai)
        if pill.conversationMessages.isEmpty {
            pill.conversationMessages = [
                ChatMessage(text: pill.query, sender: .user),
                failureMessage,
            ]
        } else if !pill.conversationMessages.contains(where: { message in
            message.sender == .ai
                && message.text.trimmingCharacters(in: .whitespacesAndNewlines) == failureMessage.text
        }) {
            pill.conversationMessages.append(failureMessage)
        }
        pill.aiMessage = failureMessage
    }

    private static func apply(projection: AgentRunProjection, to pill: AgentPill) {
        if pill.status == .stopped && projection.status != .cancelled {
            return
        }

        switch projection.status {
        case .queued:
            pill.status = .queued
        case .starting, .running, .waitingInput, .waitingApproval, .cancelling:
            pill.status = .running
            pill.completedAt = nil
        case .succeeded:
            pill.status = .done
            pill.completedAt = projection.completedAt ?? Date()
            if let statusText = projection.statusText?.trimmingCharacters(in: .whitespacesAndNewlines),
               !statusText.isEmpty {
                pill.latestActivity = String(statusText.prefix(140))
                pill.markContentChanged()
            } else if let last = pill.aiMessage {
                let trimmed = last.text.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    pill.latestActivity = String(trimmed.prefix(140))
                    pill.markContentChanged()
                }
            }
        case .failed, .timedOut, .orphaned:
            let message = projection.failure?.displayMessage ?? projection.errorMessage ?? "Agent failed"
            pill.status = .failed(message)
            pill.latestActivity = message
            pill.completedAt = projection.completedAt ?? Date()
            ensureFailureMessage(message, for: pill)
            pill.markContentChanged()
        case .cancelled:
            pill.status = .stopped
            pill.latestActivity = "Stopped by user"
            pill.completedAt = projection.completedAt ?? Date()
            pill.markContentChanged()
        case .idle:
            break
        }
        if !projection.status.isTerminal, let statusText = projection.statusText, !statusText.isEmpty {
            pill.latestActivity = statusText
            pill.markContentChanged()
        }
    }

    /// Tiny heuristic to suggest 1–2 follow-ups based on the original query.
    /// "Open chat" is intentionally omitted — the popover already has a
    /// dedicated "Open in chat" button, so adding it as a chip would duplicate.
    private static func deriveFollowUps(for pill: AgentPill) -> [String] {
        let lower = pill.query.lowercased()
        if lower.contains("email") || lower.contains("reply") {
            return ["Open thread", "Check for replies"]
        }
        if lower.contains("search") || lower.contains("find") || lower.contains("look") {
            return ["Open results", "Refine search"]
        }
        if lower.contains("schedule") || lower.contains("book") || lower.contains("calendar") {
            return ["Open calendar", "Add reminder"]
        }
        return ["Run again"]
    }

    /// Ask Claude Haiku for a short title (3–5 words, present participle) and
    /// a one-sentence acknowledgement we can speak aloud. Returns nil if the
    /// API key isn't available or the call fails — the caller keeps the
    /// existing heuristic title in that case.
    /// Short, instant acknowledgements spoken the moment a voice query spawns
    /// a pill. Random pick so consecutive PTT queries don't sound identical.
    private static let instantAcks: [String] = [
        "On it.",
        "Got it.",
        "Sure thing.",
        "Working on it.",
        "Alright, doing that now.",
        "Let me get that started.",
        "Okay, on it.",
    ]

    fileprivate static func randomAck() -> String {
        instantAcks.randomElement() ?? "On it."
    }

    fileprivate static func generateTitleAndAck(for query: String) async -> (title: String, ack: String)? {
        // Route through the desktop-backend's OpenAI-compatible proxy at
        // /v2/chat/completions instead of hitting api.anthropic.com directly.
        // This way we don't need a BYOK key (no partial-BYOK 403 risk), and
        // the request goes through the user's existing Firebase auth + plan.
        let baseURL = await APIClient.shared.rustBackendURL
        guard !baseURL.isEmpty else {
            log("AgentPill: title gen skipped — rustBackendURL empty")
            return nil
        }
        let normalized = baseURL.hasSuffix("/") ? baseURL : baseURL + "/"
        guard let url = URL(string: normalized + "v2/chat/completions") else {
            log("AgentPill: title gen failed — bad URL")
            return nil
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 8
        do {
            let headers = try await APIClient.shared.buildHeaders(requireAuth: true)
            for (k, v) in headers { request.setValue(v, forHTTPHeaderField: k) }
        } catch {
            log("AgentPill: title gen skipped — auth header unavailable (\(error.localizedDescription))")
            return nil
        }

        let prompt = """
        The user just kicked off a background agent with this request:

        "\(query)"

        Reply with a JSON object on a single line, no prose, no markdown:
        {"title":"<3-5 word imperative title in Title Case, no trailing punctuation>","ack":"<one short spoken acknowledgement, max 7 words, friendly tone, e.g. 'Got it, building Mario now.'>"}
        """

        // OpenAI-compatible body. The backend translates to Anthropic upstream.
        let body: [String: Any] = [
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 120,
            "messages": [["role": "user", "content": prompt]],
            "stream": false,
        ]
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                log("AgentPill: title gen failed — no HTTP response")
                return nil
            }
            guard (200..<300).contains(http.statusCode) else {
                let body = String(data: data.prefix(200), encoding: .utf8) ?? "<binary>"
                log("AgentPill: title gen HTTP \(http.statusCode) — \(body)")
                return nil
            }
            // OpenAI shape: { choices: [{ message: { content: "..." } }] }
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                let choices = json["choices"] as? [[String: Any]],
                let firstChoice = choices.first,
                let message = firstChoice["message"] as? [String: Any],
                let text = message["content"] as? String
            else {
                log("AgentPill: title gen response shape unexpected")
                return nil
            }
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let payloadData = trimmed.data(using: .utf8),
                let payload = try? JSONSerialization.jsonObject(with: payloadData) as? [String: Any],
                let title = (payload["title"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
                let ack = (payload["ack"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
                !title.isEmpty, !ack.isEmpty
            else {
                log("AgentPill: title gen JSON parse failed — raw: \(String(trimmed.prefix(200)))")
                return nil
            }
            log("AgentPill: title gen ok — title=\"\(title)\" ack=\"\(ack)\"")
            return (title: String(title.prefix(40)), ack: String(ack.prefix(120)))
        } catch {
            log("AgentPill: title gen threw — \(error.localizedDescription)")
            return nil
        }
    }
}
