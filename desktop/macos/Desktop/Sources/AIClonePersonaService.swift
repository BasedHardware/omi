import Foundation

/// A real verbatim exchange pulled from the message history: what the contact said and
/// how the user actually replied. Used both as few-shot examples inside the system prompt
/// and to exclude training rows from the backtest holdout.
struct ContactExampleExchange: Codable, Sendable, Hashable {
  let them: String
  let me: String
}

/// One prior message in a conversation, used as rolling context for `respond()` so the clone
/// predicts a reply in the flow of the chat rather than from a single out-of-context line.
struct ConversationTurn: Sendable {
  let isFromMe: Bool
  let text: String
}

/// A generated "persona" for one iMessage contact — a system prompt that captures how
/// the user (me) writes to that specific person, synthesized from our real message
/// history via the agent bridge (same pattern as `AppleNotesReaderService`).
struct ContactPersona: Codable, Sendable {
  let contactId: String
  let contactHandle: String
  /// The full, ready-to-use system prompt — includes the model's style description,
  /// the few-shot example exchanges, and the hard "stay in character" rules.
  let systemPrompt: String
  let generatedAt: Date
  let messageCountUsed: Int
  /// Short human-readable bullets describing recurring patterns the model noticed.
  var notablePatterns: [String] = []
  /// Real verbatim (them → me) pairs baked into `systemPrompt` as few-shot examples.
  var exampleExchanges: [ContactExampleExchange] = []
}

extension ContactPersona {
  private enum CodingKeys: String, CodingKey {
    case contactId, contactHandle, systemPrompt, generatedAt, messageCountUsed
    case notablePatterns, exampleExchanges
  }

  // Lenient decode so personas persisted before `exampleExchanges` existed still load
  // (missing arrays default to empty rather than failing the whole decode).
  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    contactId = try c.decode(String.self, forKey: .contactId)
    contactHandle = try c.decode(String.self, forKey: .contactHandle)
    systemPrompt = try c.decode(String.self, forKey: .systemPrompt)
    generatedAt = try c.decode(Date.self, forKey: .generatedAt)
    messageCountUsed = try c.decode(Int.self, forKey: .messageCountUsed)
    notablePatterns = try c.decodeIfPresent([String].self, forKey: .notablePatterns) ?? []
    exampleExchanges =
      try c.decodeIfPresent([ContactExampleExchange].self, forKey: .exampleExchanges) ?? []
  }
}

enum AIClonePersonaError: LocalizedError {
  case notEnoughMessages
  case synthesisFailed(String)
  case emptyResponse

  var errorDescription: String? {
    switch self {
    case .notEnoughMessages:
      return "Not enough message history with this contact to build a persona."
    case .synthesisFailed(let detail):
      return detail.isEmpty ? "Persona generation failed. Please try again." : detail
    case .emptyResponse:
      return "The model returned an empty persona. Please try again."
    }
  }
}

actor AIClonePersonaService {
  static let shared = AIClonePersonaService()

  /// Single UserDefaults key holding a `[contactId: ContactPersona]` map, JSON-encoded.
  private let storageKey = "aiClonePersonas.v1"

  private var cache: [String: ContactPersona]

  init() {
    cache = Self.loadFromDisk(key: "aiClonePersonas.v1")
  }

  // MARK: - Public API

  /// Generates (or regenerates) a persona for `contact` from the provided `messages`
  /// (any platform, newest-first). Persists on success so re-opening the page keeps it.
  func generatePersona(
    for contact: ImportedContact, messages: [ImportedMessage]
  ) async throws -> ContactPersona {
    guard messages.count >= 4 else {
      throw AIClonePersonaError.notEnoughMessages
    }

    // Readers return newest-first; render oldest-first so the transcript reads
    // chronologically, which is how the model reasons about tone/flow best.
    let transcript = Self.formatTranscript(messages.reversed(), contact: contact)
    let synthesisPrompt = Self.buildPrompt(
      transcript: transcript, contact: contact, messageCount: messages.count)

    let persona = try await makePersona(
      fromSynthesisPrompt: synthesisPrompt, contact: contact, messageCount: messages.count)

    store(persona)
    return persona
  }

  /// Regenerate a persona given the current one plus its worst-scoring backtest pairs,
  /// asking the model to revise the style to close those specific gaps. Does NOT persist —
  /// the training loop decides which iteration's persona to keep.
  func refinePersona(
    for contact: ImportedContact,
    messages: [ImportedMessage],
    previous: ContactPersona,
    worstPairs: [(contactMessage: String, predicted: String, actual: String, reasoning: String)]
  ) async throws -> ContactPersona {
    guard messages.count >= 4 else { throw AIClonePersonaError.notEnoughMessages }

    let refinePrompt = Self.buildRefinePrompt(
      contact: contact, previous: previous, worstPairs: worstPairs)
    return try await makePersona(
      fromSynthesisPrompt: refinePrompt, contact: contact, messageCount: messages.count)
  }

  /// Persist a persona as the active one for its contact.
  func store(_ persona: ContactPersona) {
    cache[persona.contactId] = persona
    persist()
  }

  /// Run one synthesis call and turn its JSON into a ready-to-use persona (style prompt +
  /// few-shot examples + hard in-character rules baked into `systemPrompt`).
  private func makePersona(
    fromSynthesisPrompt prompt: String, contact: ImportedContact, messageCount: Int
  ) async throws -> ContactPersona {
    let responseText = try await runSynthesis(prompt: prompt, contact: contact)

    let jsonText = Self.extractJSONObject(from: responseText)
    guard
      let jsonData = jsonText.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
    else {
      throw AIClonePersonaError.synthesisFailed("Couldn't parse the model's response.")
    }

    let baseSystemPrompt = (parsed["system_prompt"] as? String ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !baseSystemPrompt.isEmpty else {
      throw AIClonePersonaError.emptyResponse
    }

    let patterns = (parsed["notable_patterns"] as? [String] ?? [])
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }

    let parsedExchanges: [ContactExampleExchange] = (parsed["example_exchanges"] as? [[String: Any]] ?? [])
      .compactMap { dict in
        let them = (dict["them"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let me = (dict["me"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !them.isEmpty, !me.isEmpty else { return nil }
        return ContactExampleExchange(them: them, me: me)
      }
    // Cap at 5 (dedup, keep first occurrences) so refine passes can't grow the few-shot
    // block unbounded across iterations.
    let exchanges = Self.dedupeAndCap(parsedExchanges, max: 5)

    let effectivePrompt = Self.composeSystemPrompt(
      base: baseSystemPrompt, exchanges: exchanges, contact: contact)

    return ContactPersona(
      contactId: contact.id,
      contactHandle: contact.id,
      systemPrompt: effectivePrompt,
      generatedAt: Date(),
      messageCountUsed: messageCount,
      notablePatterns: patterns,
      exampleExchanges: exchanges
    )
  }

  /// Returns a previously generated persona for this contact, if one is cached.
  func existingPersona(for contactId: String) -> ContactPersona? {
    cache[contactId]
  }

  /// All cached personas keyed by contact id (handle). Useful for hydrating the page.
  func allPersonas() -> [String: ContactPersona] {
    cache
  }

  /// Produce a reply *as the user* to an incoming message from this contact, using the
  /// persona's system prompt to steer the model. `context` is the preceding few messages
  /// (both directions, oldest first) so the clone replies in the flow of the conversation
  /// rather than from a single out-of-context line. Returns raw plain text (no JSON).
  func respond(
    as persona: ContactPersona, to incomingMessage: String, context: [ConversationTurn] = []
  ) async throws -> String {
    let trimmed = incomingMessage.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return "" }

    let userPrompt = Self.buildReplyPrompt(incoming: trimmed, context: context)

    // Retry on transient bridge/LLM failure, mirroring generatePersona. Fresh bridge per attempt.
    let maxAttempts = 2
    var lastError: Error?
    for attempt in 1...maxAttempts {
      do {
        let bridge = AgentBridge(harnessMode: "piMono")
        try await bridge.start()
        defer { Task { await bridge.stop() } }

        // Reinforce the burst/message-splitting format at call time (works for personas
        // generated before the format instruction existed, too). The delimiter is parsed
        // back out below so it never leaks into displayed text.
        let systemWithFormat = persona.systemPrompt + "\n\n" + Self.replyFormatInstruction

        let result = try await bridge.query(
          prompt: userPrompt,
          systemPrompt: systemWithFormat,
          model: ModelQoS.Claude.synthesis,
          onTextDelta: { @Sendable _ in },
          onToolCall: { @Sendable _, _, _ in "" },
          onToolActivity: { @Sendable _, _, _, _ in }
        )
        // Convert bubble delimiters into newlines so multi-bubble bursts render (and score)
        // the same way real replies do (buildPairs joins the user's message runs with "\n").
        let reply = Self.normalizeBubbles(result.text)
        guard !reply.isEmpty else { throw AIClonePersonaError.emptyResponse }
        return reply
      } catch {
        lastError = error
        if attempt < maxAttempts {
          log("AIClonePersonaService: respond attempt \(attempt) failed, retrying: \(error)")
          try? await Task.sleep(nanoseconds: 800_000_000)
          continue
        }
        log("AIClonePersonaService: respond failed after \(attempt) attempts: \(error)")
      }
    }
    throw AIClonePersonaError.synthesisFailed(lastError?.localizedDescription ?? "")
  }

  // MARK: - Synthesis (mirrors AppleNotesReaderService.synthesizeFromNotes)

  private func runSynthesis(prompt: String, contact: ImportedContact) async throws -> String {
    let systemPrompt =
      "You analyze a person's real text-message history with one contact and write a "
      + "system prompt that lets an AI reply exactly as that person would. Output only valid JSON."

    // Retry on transient bridge/LLM failure instead of dropping the whole request.
    // Each attempt uses a fresh bridge.
    let maxAttempts = 2
    var lastError: Error?
    for attempt in 1...maxAttempts {
      do {
        let bridge = AgentBridge(harnessMode: "piMono")
        try await bridge.start()
        defer { Task { await bridge.stop() } }

        let result = try await bridge.query(
          prompt: prompt,
          systemPrompt: systemPrompt,
          model: ModelQoS.Claude.synthesis,
          onTextDelta: { @Sendable _ in },
          onToolCall: { @Sendable _, _, _ in "" },
          onToolActivity: { @Sendable _, _, _, _ in }
        )
        return result.text
      } catch {
        lastError = error
        if attempt < maxAttempts {
          log("AIClonePersonaService: persona attempt \(attempt) failed, retrying: \(error)")
          try? await Task.sleep(nanoseconds: 800_000_000)
          continue
        }
        log("AIClonePersonaService: persona failed after \(attempt) attempts: \(error)")
      }
    }
    throw AIClonePersonaError.synthesisFailed(lastError?.localizedDescription ?? "")
  }

  // MARK: - Prompt + transcript formatting

  private static func formatTranscript(
    _ messages: some Sequence<ImportedMessage>, contact: ImportedContact
  ) -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d, HH:mm"

    let themLabel = contact.displayName
    return messages.map { message -> String in
      let stamp = formatter.string(from: message.date)
      let speaker = message.isFromMe ? "Me" : themLabel
      let body = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
      return "[\(stamp)] \(speaker): \(body)"
    }.joined(separator: "\n")
  }

  private static func buildPrompt(
    transcript: String, contact: ImportedContact, messageCount: Int
  ) -> String {
    """
    Below is a chronological transcript of \(messageCount) real text messages between the \
    user (labeled "Me") and their contact "\(contact.displayName)" (labeled by name). \
    Study, in forensic detail, how the user — "Me" — writes to this specific contact.

    TRANSCRIPT:
    \(transcript)

    Write a system prompt (second person, addressed to the AI, e.g. \
    "You are texting with \(contact.displayName)...") that lets an AI reply to this contact \
    INDISTINGUISHABLY from the real user. Be concrete and evidence-based:

    1. VERBATIM VOCABULARY: quote the user's actual recurring words/abbreviations and give \
       their meaning, pulled from real lines — e.g. `says "js" for "just"`, \
       `"highk" for "honestly kind of"`, `ends messages with no punctuation`. Do NOT write \
       vague descriptions like "uses casual slang" — quote the real tokens.
    2. LENGTH & BURSTS: state the typical reply length in words/characters, and describe the \
       multi-bubble burst pattern with a real example from the transcript (e.g. \
       "usually 1-4 words per bubble; fires 3-6 bubbles in a row when hyped, like: 'nah' / \
       'nah nah' / 'STOP'").
    3. EMOJI / CASING / PUNCTUATION: which exact emoji, how often, capitalization habits, \
       punctuation (or absence), all grounded in real lines.
    4. TOPICS: what they actually talk about with this contact.
    5. EXAMPLE EXCHANGES: pull 3-5 REAL (them → me) pairs VERBATIM from the transcript above \
       — copy the exact text, do not paraphrase — that best showcase the user's reply style.

    Respond ONLY with valid JSON (no markdown, no code fences):
    {
      "system_prompt": "the full second-person system prompt, rich with verbatim quotes",
      "notable_patterns": ["short concrete bullet", "another"],
      "example_exchanges": [
        {"them": "exact contact message", "me": "exact user reply (join multi-bubble with \\n)"}
      ]
    }

    RULES:
    - Ground EVERY observation in the actual transcript; never invent traits.
    - example_exchanges MUST be copied verbatim from the transcript (real, not fabricated).
    - The system prompt must be specific to THIS contact, not generic.
    - Keep notable_patterns to 3-6 concise, concrete bullets.
    """
  }

  /// Ask the model to revise a persona to fix the specific pairs it got most wrong. When the
  /// judge's reasoning points at a STRUCTURAL problem (message-splitting / length / bursts),
  /// we surface that as an explicit directive rather than leaving the model to infer it.
  private static func buildRefinePrompt(
    contact: ImportedContact,
    previous: ContactPersona,
    worstPairs: [(contactMessage: String, predicted: String, actual: String, reasoning: String)]
  ) -> String {
    let failures = worstPairs.enumerated().map { index, pair in
      let judge = pair.reasoning.isEmpty ? "" : "\n      Judge (why it was wrong): \(pair.reasoning)"
      return """
      FAILURE \(index + 1):
      They said: \(pair.contactMessage)
      Your clone replied: \(pair.predicted)
      What the user ACTUALLY said: \(pair.actual)\(judge)
      """
    }.joined(separator: "\n\n")

    // Detect a structural (shape) complaint across the judge reasoning and, if present, spell
    // out the fix explicitly instead of dumping raw reasoning and hoping the model infers it.
    let allReasoning = worstPairs.map { $0.reasoning.lowercased() }.joined(separator: " ")
    let structuralKeywords = [
      "split", "burst", "too brief", "too short", "one message", "single message",
      "paragraph", "too long", "length", "multiple messages", "multi-message", "fragment",
      "one sentence", "coherent sentence",
    ]
    let hasStructural = structuralKeywords.contains { allReasoning.contains($0) }
    let structuralDirective =
      hasStructural
      ? """


        CRITICAL STRUCTURAL FIX (highest priority): The clone's replies are NOT matching this \
        person's message-splitting and length pattern — the clone writes single, longer, \
        coherent sentences while the real person fires off multiple very short back-to-back \
        bubbles (and sometimes repeats words / name-spams). Rewrite the system prompt to \
        FORCE this: reply as multiple short bubbles (separated by a line with \
        "\(bubbleDelimiter)"), keep each bubble as short as the real replies above, and never \
        answer in one tidy sentence when they wouldn't.
        """
      : ""

    let priorExamples = previous.exampleExchanges.map { "{\"them\": \"\($0.them)\", \"me\": \"\($0.me)\"}" }
      .joined(separator: ",\n    ")

    return """
    You previously wrote this system prompt to imitate how the user texts \
    "\(contact.displayName)":

    CURRENT SYSTEM PROMPT:
    \(previous.systemPrompt)

    A backtest ran your clone against real history and an impartial judge scored each reply. \
    These are the cases where the clone diverged MOST from what the user actually said:

    \(failures)\(structuralDirective)

    Revise the persona to close these gaps. Diagnose what the clone got wrong (too long? too \
    formal? wrong slang? missed the multi-bubble burst? wrong emoji? too eager/explanatory?) \
    and rewrite the system prompt so it would produce replies far closer to the user's real \
    ones above. Keep everything that was already accurate.

    Respond ONLY with valid JSON (no markdown, no code fences):
    {
      "system_prompt": "the revised second-person system prompt",
      "notable_patterns": ["concrete bullet", "..."],
      "example_exchanges": [
        \(priorExamples.isEmpty ? "{\"them\": \"...\", \"me\": \"...\"}" : priorExamples)
      ]
    }

    RULES:
    - Keep or improve the verbatim quotes and example_exchanges; do not fabricate new history.
    - Focus your changes on the failure patterns above.
    """
  }

  /// Dedupe (by normalized them|me) and keep at most `max` exchanges, preserving order.
  private static func dedupeAndCap(
    _ exchanges: [ContactExampleExchange], max: Int
  ) -> [ContactExampleExchange] {
    var seen = Set<String>()
    var out: [ContactExampleExchange] = []
    for exchange in exchanges {
      let key =
        (exchange.them + "|||" + exchange.me)
        .lowercased()
        .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      if seen.insert(key).inserted {
        out.append(exchange)
      }
      if out.count >= max { break }
    }
    return out
  }

  /// Delimiter the model uses between separate message bubbles. Parsed back out of replies
  /// (via `normalizeBubbles`) so it never appears in displayed/scored text.
  static let bubbleDelimiter = "---"

  /// Call-time instruction that forces the model to mirror the person's message-splitting
  /// style: multiple short bubbles separated by the delimiter, or a single message if that's
  /// how they'd reply.
  private static var replyFormatInstruction: String {
    """
    REPLY FORMAT (critical — match how this person REALLY texts):
    - If this person fires off multiple short back-to-back messages (bursts), output EACH \
    separate message on its own line with a line containing exactly \(bubbleDelimiter) between \
    them. Keep each bubble as short as they really are. Example:
    nah
    \(bubbleDelimiter)
    nah nah nah
    \(bubbleDelimiter)
    STOP
    - If they'd send a single message, output just that one line with NO \(bubbleDelimiter).
    - Use \(bubbleDelimiter) ONLY as a separator between bubbles — never inside a message and \
    never as literal content. Output only the message text, nothing else.
    """
  }

  /// Build the user turn for `respond()`: the incoming message, optionally preceded by the
  /// recent conversation so the clone replies in context.
  private static func buildReplyPrompt(incoming: String, context: [ConversationTurn]) -> String {
    guard !context.isEmpty else { return incoming }
    let convo = context.map { "\($0.isFromMe ? "You" : "Them"): \($0.text)" }.joined(separator: "\n")
    return """
      Recent conversation so far (oldest first):
      \(convo)

      They just texted:
      Them: \(incoming)

      Write your reply (as "You"), staying in character.
      """
  }

  /// Turn a delimited reply into a newline-joined string of bubbles, stripping any stray
  /// delimiter tokens so they never leak into visible text.
  private static func normalizeBubbles(_ raw: String) -> String {
    raw
      .replacingOccurrences(of: bubbleDelimiter, with: "\n")
      .components(separatedBy: "\n")
      .map { $0.trimmingCharacters(in: .whitespaces) }
      .filter { !$0.isEmpty }
      .joined(separator: "\n")
  }

  /// Build the final, ready-to-use system prompt: the model's style description, the real
  /// few-shot example exchanges, and hard "stay in character" rules. Few-shot examples move
  /// reply-style matching more than descriptions alone, so they go directly in the prompt.
  private static func composeSystemPrompt(
    base: String, exchanges: [ContactExampleExchange], contact: ImportedContact
  ) -> String {
    var parts: [String] = [base]

    if !exchanges.isEmpty {
      let examples = exchanges.map { "Them: \($0.them)\nYou: \($0.me)" }.joined(separator: "\n\n")
      parts.append(
        """
        REAL PAST EXCHANGES — mimic this exact style (these actually happened):
        \(examples)
        """)
    }

    parts.append(
      """
      ABSOLUTE RULES (never break):
      - You ARE the user. Never say, hint, or imply that you are an AI, assistant, bot, \
      model, or "chatbot". Never break character, apologize as an assistant, or add \
      disclaimers or meta-commentary.
      - Reply ONLY with the raw message text the user would send — no quotation marks around \
      it, no explanations, nothing else.
      - Match the exact casing, punctuation (or lack of it), slang, and emoji shown above. \
      Match their message LENGTH and their multi-bubble burst rhythm — if they send several \
      short texts in a row, you must too (separated per the reply-format instruction).
      """)

    return parts.joined(separator: "\n\n")
  }

  // MARK: - JSON extraction (duplicated from AppleNotesReaderService)

  private static func extractJSONObject(from text: String) -> String {
    var responseText = text.trimmingCharacters(in: .whitespacesAndNewlines)

    if responseText.hasPrefix("```") {
      if let firstNewline = responseText.firstIndex(of: "\n") {
        responseText = String(responseText[responseText.index(after: firstNewline)...])
      }
      if responseText.hasSuffix("```") {
        responseText = String(responseText.dropLast(3)).trimmingCharacters(
          in: .whitespacesAndNewlines)
      }
    }

    if let braceIndex = responseText.firstIndex(of: "{") {
      responseText = String(responseText[braceIndex...])
    }

    return responseText.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  // MARK: - Persistence (UserDefaults, JSON-encoded)

  private func persist() {
    do {
      let data = try JSONEncoder().encode(cache)
      UserDefaults.standard.set(data, forKey: storageKey)
    } catch {
      log("AIClonePersonaService: failed to persist personas: \(error)")
    }
  }

  private static func loadFromDisk(key: String) -> [String: ContactPersona] {
    guard let data = UserDefaults.standard.data(forKey: key) else { return [:] }
    do {
      return try JSONDecoder().decode([String: ContactPersona].self, from: data)
    } catch {
      log("AIClonePersonaService: failed to decode stored personas: \(error)")
      return [:]
    }
  }
}
