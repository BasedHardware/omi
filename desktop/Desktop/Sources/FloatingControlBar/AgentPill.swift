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
        case failed(String)

        var displayLabel: String {
            switch self {
            case .queued: return "Queued"
            case .starting, .running: return "Running"
            case .done: return "Done"
            case .failed: return "Failed"
            }
        }
    }

    let id = UUID()
    let query: String
    let createdAt: Date
    let model: String

    @Published var title: String
    @Published var status: Status = .queued
    @Published var latestActivity: String = "Queued…"
    @Published var transcript: [String] = []
    @Published var aiMessage: ChatMessage?
    @Published var completedAt: Date?
    @Published var suggestedFollowUps: [String] = []

    /// Convenience: how long the agent has been running (or ran).
    var elapsed: TimeInterval {
        (completedAt ?? Date()).timeIntervalSince(createdAt)
    }

    init(query: String, model: String) {
        self.query = query
        self.model = model
        self.title = AgentPill.deriveTitle(from: query)
        self.createdAt = Date()
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
    private var messageCountByPill: [UUID: Int] = [:]
    private var bootChain: Task<Void, Never> = Task {}

    private init() {}

    /// Routing decision for an Ask Omi message — does it stay inline in the
    /// floating bar, or get hoisted into a background agent pill?
    enum Route: String { case chat, agent }

    /// Combined router result. Title/ack are pre-computed alongside the route
    /// so we don't need a second Haiku call when the answer is "agent".
    struct RouterDecision {
        let route: Route
        let title: String?
        let ack: String?
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
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let payloadData = trimmed.data(using: .utf8),
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

    /// Spawn one or more pills for a user query. If the query says "spawn 3
    /// agents" we create 3 pills (each runs the same task on the shared
    /// queue). Returns the first pill so callers can inspect it.
    @discardableResult
    func spawnFromUserQuery(
        _ query: String,
        model: String,
        fromVoice: Bool = false,
        preFetchedTitle: String? = nil,
        preFetchedAck: String? = nil
    ) -> AgentPill {
        let count = AgentPillsManager.parseAgentCount(from: query)
        if count <= 1 {
            return spawn(
                query: query,
                model: model,
                fromVoice: fromVoice,
                preFetchedTitle: preFetchedTitle,
                preFetchedAck: preFetchedAck
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
                preFetchedAck: first == nil ? preFetchedAck : nil
            )
            if first == nil { first = pill }
        }
        return first ?? spawn(query: query, model: model, fromVoice: fromVoice)
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
        preFetchedAck: String? = nil
    ) -> AgentPill {
        let pill = AgentPill(query: query, model: model)
        if let preFetchedTitle, !preFetchedTitle.isEmpty {
            pill.title = preFetchedTitle
        }

        // Trim if we're at the cap — drop the oldest finished pill first.
        if pills.count >= maxPills {
            if let idx = pills.firstIndex(where: { isFinished($0.status) }) {
                cleanup(pillID: pills[idx].id)
            } else {
                cleanup(pillID: pills[0].id)
            }
        }

        pills.append(pill)

        let provider = ChatProvider()
        if let floating = FloatingControlBarManager.shared.sharedFloatingProvider {
            provider.workingDirectory = floating.workingDirectory
            provider.modelOverride = floating.modelOverride
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

        Task { [weak self, weak pill, weak provider] in
            await myBoot.value
            guard let self, let pill, let provider else { return }
            // Bridge is up; flip to running and fire the prompt. Concurrent
            // with any other pill that's already past this point.
            pill.status = .running
            await provider.sendMessage(
                pill.query,
                model: pill.model,
                systemPromptPrefix: ChatProvider.floatingBarSystemPromptPrefix,
                sessionKey: "agent-\(pill.id.uuidString)"
            )
            self.complete(pill: pill, provider: provider)
        }

        return pill
    }

    /// Force-dismiss a pill.
    func dismiss(pillID: UUID) {
        cleanup(pillID: pillID)
        if hoveredPillID == pillID { hoveredPillID = nil }
        if pinnedPillID == pillID { pinnedPillID = nil }
    }

    private func cleanup(pillID: UUID) {
        streamsByPill[pillID]?.cancel()
        streamsByPill[pillID] = nil
        providersByPill[pillID] = nil
        messageCountByPill[pillID] = nil
        pills.removeAll { $0.id == pillID }
    }

    /// Remove all completed (done or failed) pills.
    func clearCompleted() {
        pills.removeAll { isFinished($0.status) }
    }

    private func isFinished(_ status: AgentPill.Status) -> Bool {
        switch status {
        case .done, .failed: return true
        default: return false
        }
    }

    private func handle(messages: [ChatMessage], since: Int, for pill: AgentPill) {
        guard messages.count > since else { return }
        let recent = Array(messages.suffix(from: since))
        guard let aiMessage = recent.last(where: { $0.sender == .ai }) else { return }
        pill.aiMessage = aiMessage

        if pill.status == .starting {
            pill.status = .running
        }

        let activity = describeActivity(for: aiMessage)
        if !activity.isEmpty && activity != pill.latestActivity {
            pill.latestActivity = activity
            pill.transcript.append(activity)
        }
    }

    private func describeActivity(for message: ChatMessage) -> String {
        for block in message.contentBlocks.reversed() {
            switch block {
            case .toolCall(_, let name, _, _, let input, _):
                let display = ChatContentBlock.displayName(for: name)
                if let input, !input.summary.isEmpty {
                    return "\(display) — \(input.summary)"
                }
                return display
            case .text(_, let text):
                let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    return String(trimmed.prefix(110))
                }
            case .thinking, .discoveryCard:
                continue
            }
        }
        let trimmedFallback = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmedFallback.isEmpty {
            return String(trimmedFallback.prefix(110))
        }
        return "Working…"
    }

    private func complete(pill: AgentPill, provider: ChatProvider) {
        if let errorText = provider.errorMessage, !errorText.isEmpty {
            pill.status = .failed(errorText)
            pill.latestActivity = errorText
        } else {
            pill.status = .done
            if let last = pill.aiMessage, !last.text.isEmpty {
                let trimmed = last.text.trimmingCharacters(in: .whitespacesAndNewlines)
                pill.latestActivity = String(trimmed.prefix(140))
            } else {
                pill.latestActivity = "Done"
            }
        }
        pill.completedAt = Date()
        pill.suggestedFollowUps = AgentPillsManager.deriveFollowUps(for: pill)
        // Tear down this pill's stream so we stop holding the provider — the
        // node bridge process will deinit when no Swift references remain.
        streamsByPill[pill.id]?.cancel()
        streamsByPill[pill.id] = nil
        providersByPill[pill.id] = nil
        messageCountByPill[pill.id] = nil
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
