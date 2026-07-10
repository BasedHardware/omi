import Combine
import Foundation
import SwiftUI

/// A visible background-agent projection launched from the Ask Omi floating
/// bar. Execution is owned by the canonical Omi agent runtime; this model only
/// drives the floating/notch-less pill UI.
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

    let id: UUID
    let query: String
    let createdAt: Date
    let model: String
    let bridgeHarnessOverride: AgentHarnessMode?
    var canonicalSessionId: String?
    var canonicalRunId: String?
    var canonicalAttemptId: String?

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

    init(id: UUID = UUID(), query: String, model: String, bridgeHarnessOverride: AgentHarnessMode? = nil) {
        self.id = id
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

/// Singleton that owns visible `AgentPill` projections. It never owns agent
/// execution; spawn/continue/stop delegate to the canonical runtime.
@MainActor
final class AgentPillsManager: ObservableObject {
    static let shared = AgentPillsManager()

    @Published private(set) var pills: [AgentPill] = []

    /// Configurable soft cap so the row never grows past a reasonable width.
    private let maxPills: Int = 8

    /// INV-8: ephemeral UI only — tracks in-flight projection poll/send tasks per pill;
    /// canonical run truth lives in the kernel (`canonicalSessionId` / `canonicalRunId`).
    private var runTasksByPill: [UUID: Task<Void, Never>] = [:]
    private var runAttemptGenerationByPill: [UUID: Int] = [:]
    private var viewedExpirationWorkItemsByPill: [UUID: DispatchWorkItem] = [:]
    private var pendingFollowUpsByPill: [UUID: [PendingAgentFollowUp]] = [:]

    /// Shared agent-noun pattern used by negation guard, intent detection, and
    /// task extraction. Kept word-boundary-free so callers can embed it inside
    /// larger patterns and add `\b` anchors themselves. (Cubic P2 — single
    /// source of truth for agent-noun regex.)
    private nonisolated static let agentNounPattern = #"(?:sub\s*agents?|subagents?|background\s+agents?|floating\s+agents?|agents?|pills?)"#

    /// Which pill (if any) is currently capturing a voice follow-up — drives the
    /// pill popover's mic button state.
    @Published var recordingPillID: UUID?

    private let viewedFinishedTTL: TimeInterval = 10 * 60

    private var projectionSyncCancellable: AnyCancellable?
    private var projectionRefreshTask: Task<Void, Never>?

    private init() {
        projectionSyncCancellable = AgentRuntimeStatusStore.shared.$projectionsBySurface
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in
                self?.applyRuntimeProjections()
            }
        projectionRefreshTask = Task { @MainActor [weak self] in
            await self?.refreshProjectedPillsFromKernel()
        }
    }

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

    private struct PendingAgentFollowUp {
        let text: String
        let attachments: [ChatAttachment]
    }

    /// Combined router result. Title/ack are pre-computed alongside the route
    /// so we don't need a second Haiku call when the answer is "agent".
    struct RouterDecision {
        let route: Route
        let title: String?
        let ack: String?
    }

    enum DirectedProvider: String, Equatable {
        case hermes
        case openclaw

        var displayName: String {
            switch self {
            case .hermes: return "Hermes"
            case .openclaw: return "OpenClaw"
            }
        }

        var harnessMode: AgentHarnessMode {
            switch self {
            case .hermes: return .hermes
            case .openclaw: return .openclaw
            }
        }

        var executableName: String {
            switch self {
            case .hermes: return "hermes"
            case .openclaw: return "openclaw"
            }
        }

        var commandEnvironmentName: String {
            switch self {
            case .hermes: return "OMI_HERMES_ADAPTER_COMMAND"
            case .openclaw: return "OMI_OPENCLAW_ADAPTER_COMMAND"
            }
        }

        var setupNeededStatus: String {
            "\(displayName) needs setup"
        }
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

        let prompt = """
        The user just sent this message in the Omi floating bar:

        "\(query)"

        Decide whether to (a) answer it inline in the chat bar, or (b) spawn a background agent that will do work on the user's computer/apps/browser.

        Reply with ONLY a single-line JSON object, no prose, no markdown:
        {"route":"chat"|"agent","title":"<3-5 word imperative title in Title Case, no trailing punctuation>","ack":"<one short spoken acknowledgement, max 7 words, friendly tone>"}

        Use "agent" ONLY when the request requires the assistant to take real actions on the user's computer/browser/apps that will plausibly take more than ~10 seconds — building/coding something, sending/posting a message, editing or creating files, multi-step browser navigation, generating a long document.
        Use "chat" for everything else: questions, lookups (even if the user uses words like "search"/"find"/"look up"), definitions, single facts, explanations, short summaries, opinions, conversation. When in doubt, choose "chat".
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
            log("AgentPill: router decided route=\(route.rawValue) title=\"\(title ?? "")\"")
            return RouterDecision(
                route: route,
                title: (title?.isEmpty == false) ? String(title!.prefix(40)) : nil,
                ack: (ack?.isEmpty == false) ? String(ack!.prefix(120)) : nil
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

        let providerPattern = "(open\\s*claw|openclaw|hermes)"
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
        let existingAgentFollowUpPattern = #"\b(?:ask|tell)\s+(?:this|that|the)\s+"# + Self.agentNounPattern + #"\b"#
        if lower.range(of: existingAgentFollowUpPattern, options: .regularExpression) != nil {
            return nil
        }
        let actionPattern = #"\b(?:spawn|start|launch|kick\s+off|create|make|run|ask|tell|have)\b"#
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

    /// Spawn a visible pill projection backed by a canonical background-agent
    /// session/run in the Omi runtime.
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
        let pillId = UUID()
        let pill = AgentPill(id: pillId, query: query, model: model, bridgeHarnessOverride: bridgeHarnessOverride)
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

        let surfaceRef = AgentSurfaceReference.floatingPill(pillId: pill.id)
        pills.append(pill)

        pill.status = .starting
        if let preFetchedAck, !preFetchedAck.isEmpty {
            pill.latestActivity = preFetchedAck
        } else {
            pill.latestActivity = "Starting…"
        }
        AgentRuntimeStatusStore.shared.beginRequest(surface: surfaceRef, statusText: pill.latestActivity)

        // For voice queries, play a cached deterministic kickoff sample before
        // the runtime accepts the run so the user always hears confirmation
        // without falling back to a different system voice.
        if fromVoice {
            FloatingBarVoicePlaybackService.shared.speakBackgroundAgentKickoff()
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

        let workingDirectory = FloatingControlBarManager.shared.sharedFloatingProvider?.workingDirectory
        let modelForSpawn = bridgeHarnessOverride == nil
            ? (FloatingControlBarManager.shared.sharedFloatingProvider?.modelOverride ?? pill.model)
            : nil
        let generation = nextRunAttemptGeneration(for: pill.id)
        let runTask = Task { @MainActor [weak self, weak pill] in
            guard !Task.isCancelled else { return }
            guard let self, let pill else { return }
            do {
                let accepted = try await DesktopCoordinatorService.shared.spawnAgent(
                    objective: pill.query,
                    title: pill.title,
                    pillId: pill.id,
                    provider: bridgeHarnessOverride?.rawValue,
                    parentRunId: nil,
                    visible: true,
                    model: modelForSpawn,
                    harnessMode: bridgeHarnessOverride,
                    cwd: workingDirectory
                )
                if Task.isCancelled || !self.isCurrentRunAttempt(pillID: pill.id, generation: generation) || !self.pills.contains(where: { $0.id == pill.id }) || pill.status.isFinished {
                    Task {
                        _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(runId: accepted.runId)
                    }
                    return
                }
                pill.canonicalSessionId = accepted.sessionId
                pill.canonicalRunId = accepted.runId
                pill.canonicalAttemptId = accepted.attemptId
                pill.title = accepted.title
                pill.status = .running
                pill.completedAt = nil
                pill.suggestedFollowUps = []
                pill.latestActivity = "Working…"
                Self.ensureStreamingAssistantMessage(for: pill)
                pill.markContentChanged()
                AgentRuntimeStatusStore.shared.recordAcceptedRun(
                    surface: surfaceRef,
                    sessionId: accepted.sessionId,
                    runId: accepted.runId,
                    attemptId: accepted.attemptId,
                    statusText: "Working…"
                )
                let queuedFollowUps = self.pendingFollowUpsByPill.removeValue(forKey: pill.id) ?? []
                if !queuedFollowUps.isEmpty {
                    self.continueAgent(
                        from: pill,
                        text: queuedFollowUps.map(\.text).joined(separator: "\n\n"),
                        attachments: queuedFollowUps.flatMap(\.attachments)
                    )
                    return
                }
                await self.pollCanonicalRun(for: pill, generation: generation)
            } catch {
                guard !Task.isCancelled, self.isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
                AgentRuntimeStatusStore.shared.recordLocalFailure(
                    surface: surfaceRef,
                    error: error.localizedDescription
                )
                self.fail(pill: pill, errorText: error.localizedDescription)
            }
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

    /// Send a follow-up to the same canonical background-agent session.
    func continueAgent(from pill: AgentPill, text: String, attachments: [ChatAttachment] = []) {
        // The floating agent runs locally with disk access, so attachments are
        // handed off by local_path in the prompt (see attachmentContextPrompt) —
        // no upload round-trip needed. The visible bubble still renders the files
        // through the shared ChatResource card UI.
        let prompt: String
        if let context = ChatProvider.attachmentContextPrompt(for: attachments) {
            prompt = text.isEmpty ? context : "\(text)\n\n\(context)"
        } else {
            prompt = text
        }
        guard let sessionId = pill.canonicalSessionId else {
            pendingFollowUpsByPill[pill.id, default: []].append(PendingAgentFollowUp(text: text, attachments: attachments))
            pill.latestActivity = "Queued follow-up until the agent starts…"
            pill.markContentChanged()
            return
        }
        pill.status = .running
        pill.completedAt = nil
        pill.suggestedFollowUps = []
        pill.latestActivity = "Interrupting current run…"
        pill.conversationMessages.append(
            ChatMessage(text: text, sender: .user, resources: attachments.map(ChatResource.attachment))
        )
        Self.ensureStreamingAssistantMessage(for: pill)
        pill.markContentChanged()
        let workingDirectory = FloatingControlBarManager.shared.sharedFloatingProvider?.workingDirectory
        let activeRunId = pill.canonicalRunId
        runTasksByPill[pill.id]?.cancel()
        let generation = nextRunAttemptGeneration(for: pill.id)
        let runTask = Task { @MainActor [weak self, weak pill] in
            guard let self, let pill else { return }
            guard !Task.isCancelled else { return }
            do {
                if let activeRunId, !activeRunId.isEmpty, !pill.status.isFinished {
                    switch await self.cancelActiveRunBeforeFollowUp(runId: activeRunId, pill: pill, generation: generation) {
                    case .stopped:
                        break
                    case .cancelled:
                        return
                    case .failed:
                        pendingFollowUpsByPill[pill.id, default: []].append(PendingAgentFollowUp(text: text, attachments: attachments))
                        pill.latestActivity = "Queued follow-up until the current run stops…"
                        pill.markContentChanged()
                        await self.pollCanonicalRun(for: pill, generation: generation)
                        guard self.pills.contains(where: { $0.id == pill.id }) else { return }
                        let queuedFollowUps = self.pendingFollowUpsByPill.removeValue(forKey: pill.id) ?? []
                        if !queuedFollowUps.isEmpty {
                            self.continueAgent(
                                from: pill,
                                text: queuedFollowUps.map(\.text).joined(separator: "\n\n"),
                                attachments: queuedFollowUps.flatMap(\.attachments)
                            )
                        }
                        return
                    }
                    guard !Task.isCancelled else { return }
                    guard self.pills.contains(where: { $0.id == pill.id }) else { return }
                }
                pill.latestActivity = "Working on your follow-up…"
                Self.ensureStreamingAssistantMessage(for: pill)
                pill.markContentChanged()
                let result = try await DesktopCoordinatorService.shared.continueAgent(
                    sessionId: sessionId,
                    prompt: prompt,
                    model: pill.bridgeHarnessOverride == nil ? pill.model : nil,
                    cwd: workingDirectory
                )
                guard !Task.isCancelled, self.isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
                guard pill.canonicalSessionId == sessionId else { return }
                self.updateCanonicalRun(
                    for: pill,
                    runId: result.runId ?? pill.canonicalRunId,
                    attemptId: result.attemptId,
                    preservingAttemptForSameRun: true
                )
                self.apply(inspection: result, to: pill, expectedRunId: pill.canonicalRunId, expectedAttemptId: pill.canonicalAttemptId)
            } catch {
                guard !Task.isCancelled, self.isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
                self.fail(pill: pill, errorText: error.localizedDescription)
            }
        }
        runTasksByPill[pill.id] = runTask
    }

    private enum ActiveRunCancellationResult {
        case stopped
        case cancelled
        case failed
    }

    private func nextRunAttemptGeneration(for pillID: UUID) -> Int {
        let next = (runAttemptGenerationByPill[pillID] ?? 0) + 1
        runAttemptGenerationByPill[pillID] = next
        return next
    }

    private func isCurrentRunAttempt(pillID: UUID, generation: Int) -> Bool {
        runAttemptGenerationByPill[pillID] == generation
    }

    private func updateCanonicalRun(
        for pill: AgentPill,
        runId nextRunId: String?,
        attemptId nextAttemptId: String?,
        preservingAttemptForSameRun: Bool
    ) {
        let previousRunId = pill.canonicalRunId
        pill.canonicalRunId = nextRunId
        if nextRunId != previousRunId {
            pill.canonicalAttemptId = nextAttemptId
        } else if preservingAttemptForSameRun {
            pill.canonicalAttemptId = nextAttemptId ?? pill.canonicalAttemptId
        } else {
            pill.canonicalAttemptId = nextAttemptId
        }
    }

    private func cancelActiveRunBeforeFollowUp(runId: String, pill: AgentPill, generation: Int) async -> ActiveRunCancellationResult {
        do {
            _ = try await DesktopCoordinatorService.shared.cancelAgentRun(runId: runId, reason: "Interrupted by follow-up")
        } catch {
            logError("AgentPills: failed to cancel active run before follow-up", error: error)
            return .failed
        }
        for _ in 0..<20 {
            if Task.isCancelled { return .cancelled }
            guard isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return .cancelled }
            guard pill.canonicalRunId == runId else { return .cancelled }
            do {
                let inspection = try await DesktopCoordinatorService.shared.inspectAgentRun(runId: runId)
                let status = inspection.status
                if ["succeeded", "completed", "failed", "timed_out", "orphaned", "cancelled"].contains(status) {
                    return .stopped
                }
                pill.latestActivity = status == "cancelling" ? "Stopping current run…" : "Waiting for current run to stop…"
                pill.markContentChanged()
            } catch {
                logError("AgentPills: failed to inspect active run before follow-up", error: error)
                return .failed
            }
            try? await Task.sleep(nanoseconds: 250_000_000)
        }
        return .failed
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
    }

    func stop(pillID: UUID) {
        guard let pill = pills.first(where: { $0.id == pillID }), !pill.status.isFinished else { return }
        log("AgentPills: stopping pill \(pill.title)")
        if recordingPillID == pillID {
            recordingPillID = nil
            PushToTalkManager.shared.cancelPillFollowUp(for: pillID)
        }
        let runId = pill.canonicalRunId
        runTasksByPill[pillID]?.cancel()
        runTasksByPill[pillID] = nil
        pill.status = .stopped
        pill.latestActivity = "Stopped by user"
        pill.completedAt = Date()
        Self.clearStreamingAssistantMessage(for: pill)
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        pill.markContentChanged()
        if pill.viewedAt != nil {
            scheduleViewedExpiration(for: pill)
        }
        AgentRuntimeStatusStore.shared.recordLocalCancellation(
            surface: .floatingPill(pillId: pillID),
            message: "Stopped by user"
        )
        if let runId, !runId.isEmpty {
            Task {
                _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(runId: runId)
            }
        }
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

    @discardableResult
    func dismiss(pillIdString: String) -> Bool {
        guard let id = findPillId(from: pillIdString) else { return false }
        guard let pill = pills.first(where: { $0.id == id }) else { return false }
        if let runId = pill.canonicalRunId, !runId.isEmpty {
            Task {
                try? await DesktopCoordinatorService.shared.dismissFloatingRunAttention(runId: runId)
                await refreshProjectedPillsFromKernel()
            }
        }
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
                Self.ensureStreamingAssistantMessage(for: pill)
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
        let pill = pills.first(where: { $0.id == pillID })
        let shouldCancelRun = pill?.status.isFinished == false
        let runId = pill?.canonicalRunId
        runTasksByPill[pillID]?.cancel()
        runTasksByPill[pillID] = nil
        runAttemptGenerationByPill[pillID] = nil
        viewedExpirationWorkItemsByPill[pillID]?.cancel()
        viewedExpirationWorkItemsByPill[pillID] = nil
        pendingFollowUpsByPill[pillID] = nil
        pills.removeAll { $0.id == pillID }
        if shouldCancelRun, let runId, !runId.isEmpty {
            Task {
                _ = try? await DesktopCoordinatorService.shared.cancelAgentRun(runId: runId)
            }
        }
    }

    private func removeRenderedProjection(pillID: UUID) {
        if recordingPillID == pillID {
            recordingPillID = nil
            PushToTalkManager.shared.cancelPillFollowUp(for: pillID)
        }
        runTasksByPill[pillID]?.cancel()
        runTasksByPill[pillID] = nil
        runAttemptGenerationByPill[pillID] = nil
        viewedExpirationWorkItemsByPill[pillID]?.cancel()
        viewedExpirationWorkItemsByPill[pillID] = nil
        pendingFollowUpsByPill[pillID] = nil
        pills.removeAll { $0.id == pillID }
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

    func refreshProjectedPillsFromKernel() async {
        do {
            let floating = try await DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)
            mergeProjectedPills(from: floating)
        } catch {
            logError("AgentPills: failed to refresh projected pills from kernel", error: error)
            applyRuntimeProjections()
        }
    }

    /// Resolve an agent identity for timeline open-by-id.
    /// Fast path: in-memory pill. Then refresh floating projections once.
    /// Then hydrate via session/run/externalRef from DesktopCoordinatorService.
    @discardableResult
    func resolveAndPresentAgent(
        pillId: UUID?,
        sessionId: String?,
        runId: String?
    ) async -> Bool {
        let preference = AgentTimelineHydratePreference.make(
            pillId: pillId,
            sessionId: sessionId,
            runId: runId
        )
        guard !preference.keys.isEmpty else {
            log("AgentPills: resolveAndPresentAgent called with empty identity")
            return false
        }

        if let pill = findPill(matching: preference) {
            return true
        }

        await refreshProjectedPillsFromKernel()
        if findPill(matching: preference) != nil {
            return true
        }

        let hydrated = await hydratePillFromKernel(preference: preference)
        if hydrated {
            return findPill(matching: preference) != nil
        }

        log(
            "AgentPills: resolveAndPresentAgent failed after refresh+hydrate "
                + "pillId=\(pillId?.uuidString ?? "nil") "
                + "sessionId=\(sessionId ?? "nil") "
                + "runId=\(runId ?? "nil")"
        )
        return false
    }

    /// Package-visible for hermetic preference-matching tests.
    func findPill(matching preference: AgentTimelineHydratePreference) -> AgentPill? {
        guard let matched = preference.firstMatchingKey(
            runIdMatches: { runId in pills.contains(where: { $0.canonicalRunId == runId }) },
            sessionIdMatches: { sessionId in pills.contains(where: { $0.canonicalSessionId == sessionId }) },
            pillIdMatches: { pillId in pills.contains(where: { $0.id == pillId }) }
        ) else {
            return nil
        }
        switch matched {
        case .runId(let runId):
            return pills.first(where: { $0.canonicalRunId == runId })
        case .sessionId(let sessionId):
            return pills.first(where: { $0.canonicalSessionId == sessionId })
        case .pillId(let pillId):
            return pills.first(where: { $0.id == pillId })
        }
    }

    /// Test hook: replace in-memory pills without kernel I/O.
    func replacePillsForTesting(_ next: [AgentPill]) {
        pills = next
        objectWillChange.send()
    }

    private func hydratePillFromKernel(preference: AgentTimelineHydratePreference) async -> Bool {
        do {
            for key in preference.keys {
                switch key {
                case .runId(let runId):
                    let inspection = try await DesktopCoordinatorService.shared.inspectAgentRun(runId: runId)
                    if upsertHydratedPill(
                        pillId: preference.keys.compactMap { key -> UUID? in
                            if case .pillId(let id) = key { return id }
                            return nil
                        }.first,
                        sessionId: inspection.sessionId,
                        runId: inspection.runId ?? runId,
                        attemptId: inspection.attemptId,
                        title: nil,
                        query: nil
                    ) {
                        return true
                    }
                case .sessionId(let sessionId):
                    let snapshot = await DesktopCoordinatorService.shared.awarenessSnapshot()
                    if let session = snapshot.sessions.first(where: { $0.sessionId == sessionId }) {
                        let resolvedPillId =
                            (session.externalRefKind == "pill"
                                ? session.externalRefId.flatMap(UUID.init(uuidString:))
                                : nil)
                            ?? preference.keys.compactMap { key -> UUID? in
                                if case .pillId(let id) = key { return id }
                                return nil
                            }.first
                        if upsertHydratedPill(
                            pillId: resolvedPillId,
                            sessionId: session.sessionId ?? sessionId,
                            runId: session.runId,
                            attemptId: session.attemptId,
                            title: session.title,
                            query: nil
                        ) {
                            return true
                        }
                    }
                    let floating = try await DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)
                    if let entry = floating.first(where: {
                        canonicalString($0["sessionId"]) == sessionId
                    }) {
                        mergeProjectedPills(from: [entry])
                        return findPill(matching: preference) != nil
                    }
                case .pillId(let pillId):
                    let floating = try await DesktopCoordinatorService.shared.listFloatingAgentPills(limit: 50)
                    if let entry = floating.first(where: { canonicalPillId(from: $0) == pillId }) {
                        mergeProjectedPills(from: [entry])
                        return findPill(matching: preference) != nil
                    }
                    let snapshot = await DesktopCoordinatorService.shared.awarenessSnapshot()
                    if let session = snapshot.sessions.first(where: {
                        $0.externalRefKind == "pill" && $0.externalRefId == pillId.uuidString
                    }) {
                        if upsertHydratedPill(
                            pillId: pillId,
                            sessionId: session.sessionId,
                            runId: session.runId,
                            attemptId: session.attemptId,
                            title: session.title,
                            query: nil
                        ) {
                            return true
                        }
                    }
                }
            }
        } catch {
            logError("AgentPills: kernel hydrate failed", error: error)
        }
        return false
    }

    @discardableResult
    private func upsertHydratedPill(
        pillId: UUID?,
        sessionId: String?,
        runId: String?,
        attemptId: String?,
        title: String?,
        query: String?
    ) -> Bool {
        let trimmedSession = sessionId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let trimmedRun = runId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmedSession.isEmpty || !trimmedRun.isEmpty || pillId != nil else {
            return false
        }
        let id = pillId ?? UUID()
        let model = ShortcutSettings.shared.selectedModel.isEmpty
            ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
        let pill: AgentPill
        if let existing = pills.first(where: { $0.id == id }) {
            pill = existing
        } else if let existing = pills.first(where: {
            (!trimmedRun.isEmpty && $0.canonicalRunId == trimmedRun)
                || (!trimmedSession.isEmpty && $0.canonicalSessionId == trimmedSession)
        }) {
            pill = existing
        } else {
            pill = AgentPill(
                id: id,
                query: (query?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false)
                    ? query! : "Background agent",
                model: model
            )
            pills.append(pill)
        }
        if let title, !title.isEmpty {
            pill.title = title
        } else if pill.title.isEmpty {
            pill.title = "Background agent"
        }
        if !trimmedSession.isEmpty {
            pill.canonicalSessionId = trimmedSession
        }
        if !trimmedRun.isEmpty {
            pill.canonicalRunId = trimmedRun
        }
        if let attemptId, !attemptId.isEmpty {
            pill.canonicalAttemptId = attemptId
        }
        Self.ensureStreamingAssistantMessage(for: pill)
        pill.markContentChanged()
        objectWillChange.send()
        return true
    }

    @MainActor
    func upsertSpawnedPill(
        id: UUID,
        query: String,
        title: String,
        sessionId: String,
        runId: String,
        attemptId: String?
    ) {
        let model = ShortcutSettings.shared.selectedModel.isEmpty
            ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
        let pill: AgentPill
        if let existing = pills.first(where: { $0.id == id }) {
            pill = existing
        } else {
            pill = AgentPill(id: id, query: query.isEmpty ? "Background agent" : query, model: model)
            pills.append(pill)
        }
        pill.title = title.isEmpty ? "Background agent" : title
        pill.canonicalSessionId = sessionId
        pill.canonicalRunId = runId
        pill.canonicalAttemptId = attemptId
        pill.status = .running
        pill.completedAt = nil
        pill.latestActivity = "Working…"
        Self.ensureStreamingAssistantMessage(for: pill)
        pill.markContentChanged()
        AgentRuntimeStatusStore.shared.recordAcceptedRun(
            surface: .floatingPill(pillId: pill.id),
            sessionId: sessionId,
            runId: runId,
            attemptId: attemptId,
            statusText: "Working…"
        )
        startCanonicalRunPolling(for: pill)
        objectWillChange.send()
    }

    private func startCanonicalRunPolling(for pill: AgentPill) {
        runTasksByPill[pill.id]?.cancel()
        let generation = nextRunAttemptGeneration(for: pill.id)
        runTasksByPill[pill.id] = Task { @MainActor [weak self, weak pill] in
            guard let self, let pill else { return }
            await self.pollCanonicalRun(for: pill, generation: generation)
        }
    }

    private func mergeProjectedPills(from floating: [[String: Any]]) {
        var seen = Set<UUID>()
        for entry in floating {
            guard let pillId = canonicalPillId(from: entry),
                  let sessionId = canonicalString(entry["sessionId"]),
                  let runId = canonicalString(entry["runId"])
            else { continue }
            seen.insert(pillId)
            let query = (entry["query"] as? String) ?? (entry["latestActivity"] as? String) ?? ""
            let model = ShortcutSettings.shared.selectedModel.isEmpty
                ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
            let pill: AgentPill
            if let existing = pills.first(where: { $0.id == pillId }) {
                pill = existing
            } else {
                pill = AgentPill(id: pillId, query: query.isEmpty ? "Background agent" : query, model: model)
                pills.append(pill)
            }
            if let title = entry["title"] as? String, !title.isEmpty {
                pill.title = title
            }
            pill.canonicalSessionId = sessionId
            pill.canonicalRunId = runId
            pill.canonicalAttemptId = canonicalString(entry["attemptId"])
            let projectedStatus = (entry["status"] as? String) ?? "running"
            applyProjectedStatus(projectedStatus, to: pill)
            if let activity = entry["latestActivity"] as? String, !activity.isEmpty {
                pill.latestActivity = activity
            }
            reconcileProjectedPillRun(entryStatus: projectedStatus, pill: pill)
            pill.markContentChanged()
        }
        let removable = pills.filter { pill in
            if runTasksByPill[pill.id] != nil {
                return false
            }
            guard let sessionId = pill.canonicalSessionId, !sessionId.isEmpty,
                  let runId = pill.canonicalRunId, !runId.isEmpty
            else {
                return !hasLocalTransientState(pillID: pill.id)
            }
            return !seen.contains(pill.id)
        }
        for pill in removable {
            removeRenderedProjection(pillID: pill.id)
        }
        objectWillChange.send()
    }

    private func applyRuntimeProjections() {
        for pill in pills {
            if let projection = AgentRuntimeStatusStore.shared.floatingPillProjection(pillId: pill.id) {
                Self.apply(projection: projection, to: pill)
            } else if let runId = pill.canonicalRunId,
                let projection = AgentRuntimeStatusStore.shared.projection(for: .floatingBarRun(runId: runId)) {
                Self.apply(projection: projection, to: pill)
            }
        }
    }

    private func applyProjectedStatus(_ status: String, to pill: AgentPill) {
        if pill.status.isFinished && !isTerminalProjectedStatus(status) {
            return
        }
        switch status {
        case "queued":
            pill.status = .queued
        case "starting":
            pill.status = .starting
        case "running", "waiting_input", "waiting_approval", "cancelling":
            pill.status = .running
        case "succeeded", "completed":
            pill.status = .done
        case "cancelled":
            pill.status = .stopped
        case "failed", "timed_out", "orphaned":
            pill.status = .failed("Agent failed")
        default:
            break
        }
    }

    private func reconcileProjectedPillRun(entryStatus: String, pill: AgentPill) {
        guard shouldPollCanonicalRun(for: pill, projectedStatus: entryStatus) else { return }
        startCanonicalRunPolling(for: pill)
    }

    private func shouldPollCanonicalRun(for pill: AgentPill, projectedStatus: String) -> Bool {
        guard pill.canonicalRunId?.isEmpty == false else { return false }
        if isTerminalProjectedStatus(projectedStatus) {
            return !Self.hasTerminalAssistantMessage(for: pill)
        }
        return !pill.status.isFinished && runTasksByPill[pill.id] == nil
    }

    private func isTerminalProjectedStatus(_ status: String) -> Bool {
        switch status {
        case "succeeded", "completed", "cancelled", "failed", "timed_out", "orphaned":
            return true
        default:
            return false
        }
    }

    private func canonicalPillId(from entry: [String: Any]) -> UUID? {
        guard let idString = canonicalString(entry["pillId"]) ?? canonicalString(entry["id"]) else { return nil }
        return UUID(uuidString: idString)
    }

    private func canonicalString(_ value: Any?) -> String? {
        guard let text = value as? String else { return nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func hasLocalTransientState(pillID: UUID) -> Bool {
        recordingPillID == pillID || pendingFollowUpsByPill[pillID]?.isEmpty == false
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

    private func pollCanonicalRun(for pill: AgentPill, generation: Int) async {
        defer {
            if isCurrentRunAttempt(pillID: pill.id, generation: generation) {
                runTasksByPill[pill.id] = nil
            }
        }
        while !Task.isCancelled {
            guard isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
            guard pills.contains(where: { $0.id == pill.id }) else { return }
            guard let runId = pill.canonicalRunId, !runId.isEmpty else { return }
            let attemptId = pill.canonicalAttemptId
            do {
                let inspection = try await DesktopCoordinatorService.shared.inspectAgentRun(
                    runId: runId
                )
                guard isCurrentRunAttempt(pillID: pill.id, generation: generation) else { return }
                guard pill.canonicalRunId == runId else {
                    ScreenContextToolTelemetry.trackInvariant(
                        "stale_inspection_ignored",
                        context: ScreenContextTelemetryContext.from(
                            surfaceRef: .floatingPill(pillId: pill.id),
                            runId: runId
                        ),
                        properties: [
                            "expected_run_id": runId,
                            "current_run_id": pill.canonicalRunId ?? "",
                        ]
                    )
                    return
                }
                if let attemptId, pill.canonicalAttemptId != attemptId {
                    ScreenContextToolTelemetry.trackInvariant(
                        "stale_inspection_ignored",
                        context: ScreenContextTelemetryContext.from(
                            surfaceRef: .floatingPill(pillId: pill.id),
                            runId: runId
                        ),
                        properties: [
                            "expected_attempt_id": attemptId,
                            "current_attempt_id": pill.canonicalAttemptId ?? "",
                        ]
                    )
                    return
                }
                apply(inspection: inspection, to: pill, expectedRunId: runId, expectedAttemptId: attemptId)
                if pill.status.isFinished { return }
            } catch {
                logError("AgentPills: failed to inspect canonical run \(runId)", error: error)
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
    }

    private func apply(
        inspection: DesktopCoordinatorAgentRunInspection,
        to pill: AgentPill,
        expectedRunId: String?,
        expectedAttemptId: String?
    ) {
        if let expectedRunId, let inspectedRunId = inspection.runId, inspectedRunId != expectedRunId {
            return
        }
        if let expectedAttemptId, let inspectedAttemptId = inspection.attemptId, inspectedAttemptId != expectedAttemptId {
            return
        }
        if let expectedRunId, pill.canonicalRunId != expectedRunId {
            return
        }
        if let expectedAttemptId, pill.canonicalAttemptId != expectedAttemptId {
            return
        }
        if pill.status.isFinished && !isTerminalProjectedStatus(inspection.status) {
            return
        }
        pill.canonicalSessionId = inspection.sessionId ?? pill.canonicalSessionId
        updateCanonicalRun(
            for: pill,
            runId: inspection.runId ?? pill.canonicalRunId,
            attemptId: inspection.attemptId,
            preservingAttemptForSameRun: true
        )
        switch inspection.status {
        case "queued", "starting":
            pill.status = .starting
            pill.latestActivity = "Starting…"
            Self.ensureStreamingAssistantMessage(for: pill)
        case "running", "waiting_input", "waiting_approval", "cancelling":
            pill.status = .running
            pill.latestActivity = inspection.status == "cancelling" ? "Stopping…" : "Working…"
            Self.ensureStreamingAssistantMessage(for: pill)
        case "succeeded", "completed":
            finish(
                pill: pill,
                finalText: inspection.finalText,
                resources: inspection.artifacts.map(ChatResource.artifact)
            )
        case "cancelled":
            pill.status = .stopped
            pill.latestActivity = "Stopped by user"
            pill.completedAt = Date()
            Self.clearStreamingAssistantMessage(for: pill)
            pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        case "failed", "timed_out", "orphaned":
            fail(pill: pill, errorText: inspection.errorMessage ?? "Agent failed")
        default:
            if let finalText = inspection.finalText, !finalText.isEmpty {
                finish(pill: pill, finalText: finalText)
            }
        }
        pill.markContentChanged()
        if pill.status.isFinished, pill.viewedAt != nil {
            scheduleViewedExpiration(for: pill)
        }
    }

    private func finish(pill: AgentPill, finalText: String?, resources: [ChatResource] = []) {
        let trimmed = finalText?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !trimmed.isEmpty || !resources.isEmpty {
            let messageText = trimmed.isEmpty ? "Done." : trimmed
            Self.removeEmptyStreamingAssistantMessages(for: pill)
            var finalMessage = Self.currentAssistantMessage(for: pill) ?? ChatMessage(text: messageText, sender: .ai)
            finalMessage.text = messageText
            finalMessage.resources = resources
            finalMessage.isStreaming = false
            Self.upsertAssistantMessage(finalMessage, for: pill)
            pill.latestActivity = ChatContinuityInvariants.agentPreviewText(
                prompt: pill.query,
                output: messageText
            )
            FloatingControlBarManager.shared.recordAgentArtifactCompletion(
                pillID: pill.id,
                runId: pill.canonicalRunId,
                userText: pill.query,
                title: pill.title,
                finalText: trimmed,
                resources: resources
            )
        } else {
            Self.clearStreamingAssistantMessage(for: pill)
            pill.latestActivity = "Done"
        }
        pill.status = .done
        pill.completedAt = Date()
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        pill.markContentChanged()
        if resources.isEmpty, !trimmed.isEmpty {
            Task {
                await FloatingControlBarManager.shared.recordPillTerminalCompletion(
                    pillID: pill.id,
                    runId: pill.canonicalRunId,
                    userText: pill.query,
                    assistantText: trimmed
                )
            }
        }
    }

    private func fail(pill: AgentPill, errorText: String) {
        pill.status = .failed(errorText)
        pill.latestActivity = errorText
        pill.completedAt = Date()
        Self.clearStreamingAssistantMessage(for: pill)
        Self.ensureFailureMessage(errorText, for: pill)
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        pill.markContentChanged()
        Task {
            await FloatingControlBarManager.shared.recordPillTerminalCompletion(
                pillID: pill.id,
                runId: pill.canonicalRunId,
                userText: pill.query,
                assistantText: "Background agent failed: \(errorText)"
            )
        }
    }

    private static func ensureStreamingAssistantMessage(for pill: AgentPill) {
        if let aiMessage = pill.aiMessage, aiMessage.isStreaming {
            if !pill.conversationMessages.contains(where: { $0.id == aiMessage.id }) {
                pill.conversationMessages.append(aiMessage)
            }
            return
        }

        if let index = pill.conversationMessages.lastIndex(where: { $0.sender == .ai && $0.isStreaming }) {
            pill.aiMessage = pill.conversationMessages[index]
            return
        }

        if pill.conversationMessages.isEmpty {
            pill.conversationMessages = [ChatMessage(text: pill.query, sender: .user)]
        }

        var streamingMessage = ChatMessage(text: "", sender: .ai)
        streamingMessage.isStreaming = true
        pill.aiMessage = streamingMessage
        pill.conversationMessages.append(streamingMessage)
    }

    private static func clearStreamingAssistantMessage(for pill: AgentPill) {
        guard let aiMessage = pill.aiMessage, aiMessage.isStreaming else { return }
        let hasVisibleContent =
            !aiMessage.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !aiMessage.contentBlocks.isEmpty
            || !aiMessage.displayResources.isEmpty

        if hasVisibleContent {
            var completedMessage = aiMessage
            completedMessage.isStreaming = false
            pill.aiMessage = completedMessage
            if let index = pill.conversationMessages.firstIndex(where: { $0.id == completedMessage.id }) {
                pill.conversationMessages[index] = completedMessage
            }
        } else {
            pill.aiMessage = nil
            pill.conversationMessages.removeAll { $0.id == aiMessage.id }
        }
    }

    private static func removeEmptyStreamingAssistantMessages(for pill: AgentPill) {
        pill.conversationMessages.removeAll { message in
            message.sender == .ai
                && message.isStreaming
                && !hasVisibleAssistantContent(message)
        }
        if let aiMessage = pill.aiMessage,
           aiMessage.isStreaming,
           !hasVisibleAssistantContent(aiMessage) {
            pill.aiMessage = nil
        }
    }

    private static func currentAssistantMessage(for pill: AgentPill) -> ChatMessage? {
        if let aiMessage = pill.aiMessage, hasVisibleAssistantContent(aiMessage) {
            return aiMessage
        }
        return pill.conversationMessages.last { message in
            message.sender == .ai && hasVisibleAssistantContent(message)
        }
    }

    private static func hasTerminalAssistantMessage(for pill: AgentPill) -> Bool {
        guard let message = currentAssistantMessage(for: pill) else { return false }
        return !message.isStreaming && hasVisibleAssistantContent(message)
    }

    private static func hasVisibleAssistantContent(_ message: ChatMessage) -> Bool {
        !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !message.contentBlocks.isEmpty
            || !message.displayResources.isEmpty
    }

    private static func upsertAssistantMessage(_ message: ChatMessage, for pill: AgentPill) {
        pill.aiMessage = message
        if pill.conversationMessages.isEmpty {
            pill.conversationMessages = [
                ChatMessage(text: pill.query, sender: .user),
                message,
            ]
        } else if let index = pill.conversationMessages.firstIndex(where: { $0.id == message.id }) {
            pill.conversationMessages[index] = message
        } else if !pill.conversationMessages.contains(where: { $0.id == message.id }) {
            pill.conversationMessages.append(message)
        }
    }

    private func handle(messages: [ChatMessage], since: Int, for pill: AgentPill) {
        guard messages.count > since else { return }
        let recent = Array(messages.suffix(from: since))
        var displayMessages = recent.filter { message in
            let trimmed = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
            return message.sender == .user
                || !trimmed.isEmpty
                || message.isStreaming
                || !message.contentBlocks.isEmpty
                || !message.displayResources.isEmpty
        }
        if displayMessages.contains(where: { message in
            message.sender == .ai
                && !message.isStreaming
                && Self.hasVisibleAssistantContent(message)
        }) {
            displayMessages.removeAll { message in
                message.sender == .ai
                    && message.isStreaming
                    && !Self.hasVisibleAssistantContent(message)
            }
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

        if !aiMessage.isStreaming, Self.hasVisibleAssistantContent(aiMessage) {
            Self.removeEmptyStreamingAssistantMessages(for: pill)
            pill.status = .done
            pill.completedAt = pill.completedAt ?? Date()
            pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
            pill.markContentChanged()
            if pill.viewedAt != nil {
                scheduleViewedExpiration(for: pill)
            }
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
            case .agentSpawn(_, _, _, _, let title, let objective):
                let label = objective.isEmpty ? title : objective
                let trimmed = label.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    return String(trimmed.prefix(110))
                }
            case .agentCompletion(_, _, _, _, let title, let promptSnippet, let output, _):
                let preview = ChatContinuityInvariants.agentPreviewText(
                    prompt: promptSnippet.isEmpty ? title : promptSnippet,
                    output: output
                )
                let trimmed = preview.trimmingCharacters(in: .whitespacesAndNewlines)
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
                Self.removeEmptyStreamingAssistantMessages(for: pill)
                var finalMessage = Self.currentAssistantMessage(for: pill) ?? ChatMessage(text: trimmedFinalText, sender: .ai)
                finalMessage.text = trimmedFinalText
                finalMessage.isStreaming = false
                Self.upsertAssistantMessage(finalMessage, for: pill)
            }
            pill.latestActivity = ChatContinuityInvariants.agentPreviewText(
                prompt: pill.query,
                output: trimmedFinalText
            )
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
        if let errorText = provider.displayErrorMessage, !errorText.isEmpty {
            pill.status = .failed(errorText)
            pill.latestActivity = errorText
            pill.completedAt = Date()
            Self.ensureFailureMessage(errorText, for: pill)
            pill.markContentChanged()
        } else if let trimmedFinalText, !trimmedFinalText.isEmpty {
            pill.status = .done
            pill.completedAt = Date()
            pill.markContentChanged()
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
        let failureText = AgentFailureTranscriptFormatter.transcriptText(for: errorText) ?? "Failed: \(errorText)"
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
        if pill.status.isFinished && !projection.status.isTerminal {
            return
        }

        switch projection.status {
        case .queued:
            pill.status = .queued
            ensureStreamingAssistantMessage(for: pill)
        case .starting, .running, .waitingInput, .waitingApproval, .cancelling:
            pill.status = .running
            pill.completedAt = nil
            ensureStreamingAssistantMessage(for: pill)
        case .succeeded:
            if let statusText = projection.statusText?.trimmingCharacters(in: .whitespacesAndNewlines),
               !statusText.isEmpty {
                removeEmptyStreamingAssistantMessages(for: pill)
                var finalMessage = currentAssistantMessage(for: pill) ?? ChatMessage(text: statusText, sender: .ai)
                finalMessage.text = statusText
                finalMessage.isStreaming = false
                upsertAssistantMessage(finalMessage, for: pill)
                pill.latestActivity = String(statusText.prefix(140))
            } else if let last = currentAssistantMessage(for: pill) {
                let trimmed = last.text.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    pill.latestActivity = String(trimmed.prefix(140))
                }
                clearStreamingAssistantMessage(for: pill)
            } else {
                clearStreamingAssistantMessage(for: pill)
            }
            pill.status = .done
            pill.completedAt = projection.completedAt ?? Date()
            pill.markContentChanged()
        case .failed, .timedOut, .orphaned:
            let message = projection.failure?.displayMessage ?? projection.errorMessage ?? "Agent failed"
            pill.status = .failed(message)
            pill.latestActivity = message
            pill.completedAt = projection.completedAt ?? Date()
            clearStreamingAssistantMessage(for: pill)
            ensureFailureMessage(message, for: pill)
            pill.markContentChanged()
        case .cancelled:
            pill.status = .stopped
            pill.latestActivity = "Stopped by user"
            pill.completedAt = projection.completedAt ?? Date()
            clearStreamingAssistantMessage(for: pill)
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
