import Foundation

/// Central semantic gate for background-agent delegation.
///
/// UI surfaces and realtime tools may request delegation, but this resolver is
/// the only place that may turn a top-level utterance into a child-agent brief.
/// The invariant is simple: child agents only receive self-contained work.
@MainActor
final class AgentDelegationResolver {
    static let shared = AgentDelegationResolver()

    enum Surface: String {
        case floatingText = "floating_text"
        case realtimeVoice = "realtime_voice"
    }

    enum Action: String {
        case chat
        case clarify
        case spawn
    }

    struct Request {
        let surface: Surface
        let userText: String
        let proposedBrief: String
        let proposedTitle: String?
        let proposedAck: String?
        let directedProvider: AgentPillsManager.DirectedProvider?
        let topLevelContext: String
        let agentStatusSummary: String
        let explicitDelegationRequested: Bool
    }

    struct Decision: Equatable {
        let action: Action
        let brief: String?
        let title: String?
        let ack: String?
        let directedProvider: AgentPillsManager.DirectedProvider?
        let reason: String?

        var userFacingText: String {
            let text = ack?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return text.isEmpty ? "What would you like the agent to do?" : text
        }
    }

    private struct ModelPayload: Decodable {
        let action: String
        let brief: String?
        let title: String?
        let ack: String?
        let provider: String?
        let reason: String?
    }

    private init() {}

    func resolve(_ request: Request) async -> Decision {
        guard let decision = await runResolverCall(for: request) else {
            return fallbackDecision(for: request)
        }
        return decision
    }

    private func runResolverCall(for request: Request) async -> Decision? {
        let baseURL = await APIClient.shared.rustBackendURL
        guard !baseURL.isEmpty else {
            log("AgentDelegationResolver: skipped — rustBackendURL empty")
            return nil
        }
        let normalized = baseURL.hasSuffix("/") ? baseURL : baseURL + "/"
        guard let url = URL(string: normalized + "v2/chat/completions") else {
            log("AgentDelegationResolver: skipped — bad URL")
            return nil
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.timeoutInterval = 6
        do {
            let headers = try await APIClient.shared.buildHeaders(requireAuth: true)
            for (key, value) in headers {
                urlRequest.setValue(value, forHTTPHeaderField: key)
            }
        } catch {
            log("AgentDelegationResolver: skipped — auth header unavailable (\(error.localizedDescription))")
            return nil
        }

        let prompt = Self.prompt(for: request)
        let body: [String: Any] = [
            "model": "claude-sonnet-4-6",
            "max_tokens": 420,
            "messages": [["role": "user", "content": prompt]],
            "stream": false,
        ]

        do {
            urlRequest.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (data, response) = try await URLSession.shared.data(for: urlRequest)
            guard let http = response as? HTTPURLResponse else {
                log("AgentDelegationResolver: failed — no HTTP response")
                return nil
            }
            guard (200..<300).contains(http.statusCode) else {
                log("AgentDelegationResolver: HTTP \(http.statusCode) bodyBytes=\(data.count)")
                return nil
            }
            guard let text = Self.chatCompletionText(from: data),
                  let payload = Self.decodePayload(from: text)
            else {
                log("AgentDelegationResolver: response parse failed")
                return nil
            }
            return Self.decision(from: payload, request: request)
        } catch {
            log("AgentDelegationResolver: threw — \(error.localizedDescription)")
            return nil
        }
    }

    private static func prompt(for request: Request) -> String {
        let provider = request.directedProvider?.rawValue ?? ""
        return """
        You are Omi's delegation resolver. Decide whether the latest top-level user message should stay in the top-level chat, ask a clarification, or spawn one background child agent.

        Hard invariants:
        - Child-agent briefs must be self-contained. Never pass vague follow-ups like "another search", "do that again", "same thing", or "continue" unless you reconstruct the full concrete task from context.
        - If context is insufficient to reconstruct a concrete task, return clarify.
        - Do not spawn an agent just because the user used words like search/find/look up; spawn only for work that should run as a visible background agent or when the user explicitly asked for one.
        - Preserve an explicit provider when present, unless the request should not spawn.
        - For provider-directed requests, include the provider in the result and make the brief describe exactly what that provider should do.
        - Output only one JSON object. No markdown.

        JSON schema:
        {"action":"chat"|"clarify"|"spawn","brief":"self-contained child task or null","title":"3-5 word Title Case title or null","ack":"short top-level response or clarification question","provider":"hermes"|"openclaw"|null,"reason":"short internal reason"}

        Surface: \(request.surface.rawValue)
        Explicit delegation requested: \(request.explicitDelegationRequested)
        Directed provider: \(provider.isEmpty ? "none" : provider)

        Latest user message:
        \(request.userText)

        Proposed child brief from caller/tool:
        \(request.proposedBrief)

        Proposed title:
        \(request.proposedTitle ?? "none")

        Proposed acknowledgement:
        \(request.proposedAck ?? "none")

        Top-level conversation context:
        \(request.topLevelContext.isEmpty ? "none" : request.topLevelContext)

        Current and recent background agents:
        \(request.agentStatusSummary)
        """
    }

    private static func chatCompletionText(from data: Data) -> String? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let choices = json["choices"] as? [[String: Any]],
              let message = choices.first?["message"] as? [String: Any],
              let text = message["content"] as? String
        else {
            return nil
        }
        return text
    }

    private nonisolated static func decodePayload(from text: String) -> ModelPayload? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let jsonBody: String
        if let firstBrace = trimmed.firstIndex(of: "{"),
           let lastBrace = trimmed.lastIndex(of: "}"),
           firstBrace <= lastBrace {
            jsonBody = String(trimmed[firstBrace...lastBrace])
        } else {
            jsonBody = trimmed
        }
        guard let data = jsonBody.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(ModelPayload.self, from: data)
    }

    private static func decision(from payload: ModelPayload, request: Request) -> Decision {
        let action = Action(rawValue: payload.action.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()) ?? .chat
        let provider = directedProvider(from: payload.provider) ?? request.directedProvider
        let brief = clean(payload.brief)
        let title = clean(payload.title).map { String($0.prefix(48)) }
        let ack = clean(payload.ack).map { String($0.prefix(220)) }
        let reason = clean(payload.reason).map { String($0.prefix(180)) }

        if action == .spawn,
           (brief?.isEmpty != false
            || !DelegationBriefValidator.isStructurallyAcceptable(brief: brief ?? "", rawIntent: request.proposedBrief)) {
            return Decision(
                action: .clarify,
                brief: nil,
                title: nil,
                ack: "What should the background agent do?",
                directedProvider: provider,
                reason: "spawn decision missing self-contained brief"
            )
        }

        return Decision(
            action: action,
            brief: brief,
            title: title,
            ack: ack,
            directedProvider: provider,
            reason: reason
        )
    }

    private static func clean(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmed.isEmpty, trimmed.lowercased() != "null" else { return nil }
        return trimmed
    }

    private static func directedProvider(from value: String?) -> AgentPillsManager.DirectedProvider? {
        switch clean(value)?.lowercased().replacingOccurrences(of: " ", with: "") {
        case "hermes": return .hermes
        case "openclaw": return .openclaw
        default: return nil
        }
    }

    private func fallbackDecision(for request: Request) -> Decision {
        return Decision(
            action: request.explicitDelegationRequested ? .clarify : .chat,
            brief: nil,
            title: nil,
            ack: request.explicitDelegationRequested ? "What should the background agent do?" : nil,
            directedProvider: nil,
            reason: "resolver unavailable; conservative no-spawn fallback"
        )
    }
}
