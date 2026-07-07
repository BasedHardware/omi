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

/// A generated "persona" for one contact — everything the clone needs to reply as the user:
/// LLM-written voice notes (vocabulary, tone, topics), an algorithmically measured style
/// card (lengths, bursts, casing, punctuation, emoji — computed from the data, not inferred),
/// and real few-shot exchanges. `systemPrompt` is the composed, ready-to-use result.
struct ContactPersona: Codable, Sendable {
  let contactId: String
  let contactHandle: String
  /// The full, ready-to-use system prompt (voice notes + measured style card + hard rules).
  let systemPrompt: String
  let generatedAt: Date
  let messageCountUsed: Int
  /// Short human-readable bullets describing recurring patterns the model noticed.
  var notablePatterns: [String] = []
  /// Real verbatim (them → me) pairs baked into `systemPrompt` as few-shot examples.
  var exampleExchanges: [ContactExampleExchange] = []
  /// The LLM-written portion of the prompt (revised by refinement iterations).
  var voiceNotes: String = ""
  /// The measured-style block (computed in code; stable across refinements).
  var styleCard: String = ""
  /// Raw measured features, used for deterministic candidate scoring at respond time.
  var styleFeatures: StyleFeatures? = nil
}

extension ContactPersona {
  private enum CodingKeys: String, CodingKey {
    case contactId, contactHandle, systemPrompt, generatedAt, messageCountUsed
    case notablePatterns, exampleExchanges, voiceNotes, styleCard, styleFeatures
  }

  // Lenient decode so personas persisted before newer fields existed still load.
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
    voiceNotes = try c.decodeIfPresent(String.self, forKey: .voiceNotes) ?? ""
    styleCard = try c.decodeIfPresent(String.self, forKey: .styleCard) ?? ""
    styleFeatures = try c.decodeIfPresent(StyleFeatures.self, forKey: .styleFeatures)
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
  /// Also (re)builds the retrieval index used for dynamic few-shot examples.
  /// `excludeExchangeKeys` (pair-keys via `AICloneBacktestService.pairKey`) prevents
  /// specific exchanges from being baked into the persona's few-shot examples — the
  /// backtest harness passes its eval set so measurement stays leak-free.
  func generatePersona(
    for contact: ImportedContact, messages: [ImportedMessage],
    excludeExchangeKeys: Set<String> = []
  ) async throws -> ContactPersona {
    guard messages.count >= 4 else {
      throw AIClonePersonaError.notEnoughMessages
    }

    // Measured style: computed directly from the data, never inferred by the model.
    let features = AICloneStyleAnalyzer.extract(from: messages)
    let styleCard = AICloneStyleAnalyzer.renderStyleCard(features, contactName: contact.displayName)

    // Retrieval index for dynamic few-shot examples (embedding-backed, lexical fallback).
    await AICloneRetrievalService.shared.ensureIndex(contactId: contact.id, messages: messages)

    // Readers return newest-first; render oldest-first so the transcript reads
    // chronologically, which is how the model reasons about tone/flow best.
    let transcript = Self.formatTranscript(messages.reversed(), contact: contact)
    let synthesisPrompt = Self.buildPrompt(
      transcript: transcript, contact: contact, messageCount: messages.count)

    let persona = try await makePersona(
      fromSynthesisPrompt: synthesisPrompt, contact: contact, messageCount: messages.count,
      styleCard: styleCard, styleFeatures: features, excludeExchangeKeys: excludeExchangeKeys)

    store(persona)
    return persona
  }

  /// Regenerate a persona given the current one plus its worst-scoring backtest pairs,
  /// asking the model to revise the voice notes to close those specific gaps. The measured
  /// style card is code-derived and stays fixed. Does NOT persist — the training loop
  /// decides which iteration's persona to keep.
  func refinePersona(
    for contact: ImportedContact,
    messages: [ImportedMessage],
    previous: ContactPersona,
    worstPairs: [(contactMessage: String, predicted: String, actual: String, reasoning: String)],
    excludeExchangeKeys: Set<String> = []
  ) async throws -> ContactPersona {
    guard messages.count >= 4 else { throw AIClonePersonaError.notEnoughMessages }

    let refinePrompt = Self.buildRefinePrompt(
      contact: contact, previous: previous, worstPairs: worstPairs)
    return try await makePersona(
      fromSynthesisPrompt: refinePrompt, contact: contact, messageCount: messages.count,
      styleCard: previous.styleCard, styleFeatures: previous.styleFeatures,
      excludeExchangeKeys: excludeExchangeKeys)
  }

  /// Persist a persona as the active one for its contact.
  func store(_ persona: ContactPersona) {
    cache[persona.contactId] = persona
    persist()
  }

  /// Returns a previously generated persona for this contact, if one is cached.
  func existingPersona(for contactId: String) -> ContactPersona? {
    cache[contactId]
  }

  /// All cached personas keyed by contact id (handle). Useful for hydrating the page.
  func allPersonas() -> [String: ContactPersona] {
    cache
  }

  // MARK: - Respond (retrieve → generate candidates → select)

  /// Produce a reply *as the user* to an incoming message from this contact.
  ///
  /// Pipeline (accuracy-first, multiple LLM calls by design):
  ///   1. Retrieve the k most similar real (them → me) exchanges for THIS message and
  ///      inject the user's actual verbatim replies as situation-specific few-shots.
  ///   2. Generate 3 diverse candidate replies in one call (JSON bubbles — no fragile
  ///      text delimiters; each bubble is one message).
  ///   3. Score candidates deterministically against the measured style features and
  ///      have a critic call pick (and minimally fix) the most indistinguishable one.
  ///
  /// `excludingPairKeys` removes specific historical instances from retrieval — the
  /// backtest passes the held-out pair's own key so the clone can never be handed the
  /// answer it is being tested on.
  ///
  /// `includeLiveContext` (default on) enriches generation with the user's real saved
  /// Memories and — for scheduling-shaped messages — their real calendar, via
  /// `AICloneContextService`. Read-only and best-effort: a failed fetch just drops the
  /// block. The backtest turns it off because it replays historical exchanges, where
  /// today's calendar/memories would be anachronistic noise in the eval.
  ///
  /// Returns bubbles joined with "\n" (same shape as real multi-bubble replies in the
  /// history), so UI and judge treat predicted and real replies identically.
  func respond(
    as persona: ContactPersona, to incomingMessage: String, context: [ConversationTurn] = [],
    excludingPairKeys: Set<String> = [], includeLiveContext: Bool = true
  ) async throws -> String {
    let trimmed = incomingMessage.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return "" }

    // 1. Dynamic few-shot retrieval (best-effort — empty when no index exists).
    let retrievalQuery = ([trimmed] + context.suffix(2).map(\.text)).joined(separator: "\n")
    let examples = await AICloneRetrievalService.shared.retrieve(
      contactId: persona.contactId, incoming: retrievalQuery, k: 10,
      excluding: excludingPairKeys)

    // 1b. Live context enrichment: background facts always; real calendar only when the
    // message (plus recent turns) looks scheduling-related. Nil blocks silently drop out.
    var liveBlocks: [String] = []
    if includeLiveContext {
      var hasMemories = false
      var hasCalendar = false
      if let memoryBlock = await AICloneContextService.shared.memoryContext() {
        liveBlocks.append(memoryBlock)
        hasMemories = true
      }
      let scheduling = AICloneContextService.isSchedulingRelated(retrievalQuery)
      if scheduling, let calendarBlock = await AICloneContextService.shared.calendarContext() {
        liveBlocks.append(calendarBlock)
        hasCalendar = true
      }
      log(
        "AIClone respond: live context memories=\(hasMemories) scheduling=\(scheduling) calendar=\(hasCalendar)"
      )
    }

    // 2. Generate candidates.
    let generationPrompt = Self.buildGenerationPrompt(
      incoming: trimmed, context: context, examples: examples)
    let generationSystem = ([persona.systemPrompt] + liveBlocks + [Self.candidateFormatInstruction])
      .joined(separator: "\n\n")

    var candidates = try await generateCandidates(
      prompt: generationPrompt, system: generationSystem)
    candidates = candidates.map(Self.sanitizeBubbles).filter { !$0.isEmpty }
    guard !candidates.isEmpty else { throw AIClonePersonaError.emptyResponse }

    // 3. Deterministic style scoring + critic selection.
    let features = persona.styleFeatures
    let scored = candidates.map { bubbles in
      (
        bubbles: bubbles,
        style: features.map { AICloneStyleAnalyzer.styleScore(bubbles: bubbles, features: $0) }
          ?? 0.5
      )
    }

    var chosen = scored.max { $0.style < $1.style }!.bubbles
    if scored.count > 1 {
      if let selected = try? await selectCandidate(
        scored: scored, incoming: trimmed, context: context, persona: persona)
      {
        chosen = selected
      }
    }

    let reply = chosen.joined(separator: "\n")
    guard !reply.isEmpty else { throw AIClonePersonaError.emptyResponse }
    return reply
  }

  /// One LLM call producing up to 3 candidate replies as JSON bubble arrays. Retries once
  /// on unparseable output; a lenient string-extraction fallback guarantees raw JSON can
  /// never leak into a reply.
  private func generateCandidates(
    prompt: String, system: String
  ) async throws -> [[String]] {
    var lastResponse = ""
    for attempt in 1...2 {
      let responseText = try await runLLM(
        prompt: prompt, system: system, model: ModelQoS.Claude.cloneVoice, label: "generate")
      // Raw model output is personal-message content — log it for harness debugging on
      // dev/test bundles only, never in production.
      if AppBuild.isNonProduction {
        log("AIClone respond RAW: «\(responseText.replacingOccurrences(of: "\n", with: "⏎").prefix(500))»")
      }
      lastResponse = responseText

      if let parsed = Self.parseCandidates(from: responseText), !parsed.isEmpty {
        return parsed
      }
      log("AIClonePersonaService: candidate JSON parse failed (attempt \(attempt))")
    }
    // Lenient fallback: pull the quoted strings of the first candidate array out of the
    // malformed JSON. If the text isn't JSON-shaped at all, use its lines as bubbles.
    if let extracted = Self.extractFirstCandidateStrings(from: lastResponse), !extracted.isEmpty {
      return [extracted]
    }
    let lines = lastResponse
      .components(separatedBy: "\n")
      .map { $0.trimmingCharacters(in: .whitespaces) }
      .filter { !$0.isEmpty && !$0.contains("{") && !$0.contains("[") && !$0.contains("\"") }
    guard !lines.isEmpty else { throw AIClonePersonaError.emptyResponse }
    return [lines]
  }

  /// Critic pass: pick the candidate that is most indistinguishable from the real person,
  /// with permission to make minimal mechanical fixes (casing/punctuation/emoji) only.
  private func selectCandidate(
    scored: [(bubbles: [String], style: Double)],
    incoming: String,
    context: [ConversationTurn],
    persona: ContactPersona
  ) async throws -> [String] {
    let labels = ["A", "B", "C", "D", "E"]
    let block = scored.prefix(labels.count).enumerated().map { index, candidate in
      let rendered = candidate.bubbles.map { "    \($0)" }.joined(separator: "\n")
      return "CANDIDATE \(labels[index]) (style-fit \(String(format: "%.2f", candidate.style))):\n\(rendered)"
    }.joined(separator: "\n\n")

    let convo =
      context.isEmpty
      ? ""
      : "Conversation so far (oldest first):\n"
        + context.map { "\($0.isFromMe ? "Me" : "Them"): \($0.text)" }.joined(separator: "\n")
        + "\n\n"

    let system = """
      You are a forensic texting-style analyst. You know exactly how this person texts:

      \(persona.styleCard.isEmpty ? persona.systemPrompt : persona.styleCard)

      Judge ONLY authenticity of voice: would a close friend reading this reply believe this \
      specific person sent it? Output only valid JSON.
      """

    let prompt = """
      \(convo)They just texted: \(incoming)

      Candidate replies the person might send (each line inside a candidate = one separate \
      text message bubble; style-fit is a computed match to their measured style):

      \(block)

      Pick the candidate a close friend would LEAST suspect of being fake AND would actually \
      send in this moment. Polish is a tell of a fake — prefer rough and real over smooth and \
      complete. But a cold, thread-killing one-word reply to a message that clearly wanted a \
      response is ALSO fake for most people: if they're engaged, pick the reply that stays real \
      in this person's voice while keeping the conversation alive.
      HARD RULE: REJECT any candidate that introduces a topic, task, plan, or agenda the other \
      person did NOT bring up in this thread — a reply that answers them and then tacks on an \
      unrelated line ("Remove downtime", a random plan, an off-topic question) reads as a \
      malfunction, not a person. Answering cleanly and stopping ALWAYS beats padding with \
      something they didn't ask about.
      If their message is a natural closer ("all good?", "cool", "ok", "you good?"), the short \
      clean reply is the winner — do not reward a candidate for manufacturing a topic to keep a \
      finished conversation alive. Only prefer the reply that hands the conversation back when \
      the exchange is genuinely still live AND that reply stays on the topic they raised. You may \
      make tiny mechanical fixes to the winner (casing, punctuation, emoji, trimming an \
      out-of-character word or an off-topic tail bubble) but must NOT rewrite its content or add \
      new ideas.

      Respond ONLY with valid JSON (no markdown):
      {"winner": "A", "bubbles": ["final bubble 1", "final bubble 2"]}
      """

    let responseText = try await runLLM(
      prompt: prompt, system: system, model: ModelQoS.Claude.cloneVoice, label: "critic")
    let jsonText = Self.extractJSONObject(from: responseText)
    guard
      let data = jsonText.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { throw AIClonePersonaError.synthesisFailed("critic parse failed") }

    let winnerLabel = (parsed["winner"] as? String ?? "").trimmingCharacters(in: .whitespaces)
    let winnerIndex = labels.firstIndex(of: winnerLabel).map { min($0, scored.count - 1) }
    let winner = winnerIndex.map { scored[$0].bubbles }

    let edited = Self.sanitizeBubbles((parsed["bubbles"] as? [String]) ?? [])
    // Accept the critic's edited bubbles only if they stay close in size to the winner
    // (guards against the critic rewriting instead of lightly fixing).
    if let winner, !edited.isEmpty {
      let winnerLength = winner.joined(separator: " ").count
      let editedLength = edited.joined(separator: " ").count
      if editedLength <= max(winnerLength * 3 / 2, winnerLength + 12) {
        return edited
      }
      return winner
    }
    if let winner { return winner }
    if !edited.isEmpty { return edited }
    throw AIClonePersonaError.synthesisFailed("critic returned no candidate")
  }

  // MARK: - Persona synthesis

  /// Run one synthesis call and turn its JSON into a ready-to-use persona (voice notes +
  /// measured style card + few-shot examples + hard in-character rules).
  private func makePersona(
    fromSynthesisPrompt prompt: String, contact: ImportedContact, messageCount: Int,
    styleCard: String, styleFeatures: StyleFeatures?, excludeExchangeKeys: Set<String> = []
  ) async throws -> ContactPersona {
    let system =
      "You analyze a person's real text-message history with one contact and write notes "
      + "that let an AI reply exactly as that person would. Output only valid JSON."
    let responseText = try await runLLM(
      prompt: prompt, system: system, model: ModelQoS.Claude.cloneVoice, label: "persona")

    let jsonText = Self.extractJSONObject(from: responseText)
    guard
      let jsonData = jsonText.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
    else {
      throw AIClonePersonaError.synthesisFailed("Couldn't parse the model's response.")
    }

    // Accept both the new ("voice_notes") and legacy ("system_prompt") key.
    let voiceNotes = ((parsed["voice_notes"] as? String) ?? (parsed["system_prompt"] as? String) ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !voiceNotes.isEmpty else {
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
    // block unbounded across iterations. Excluded keys (the backtest eval set) can never
    // become few-shot examples, or the eval would leak into the prompt.
    // Match on the full pair key, and also on the contact-side alone (an exchange that
    // quotes an eval pair's trigger leaks even if the copied reply is partial).
    let excludedThemPrefixes = excludeExchangeKeys.compactMap { $0.components(separatedBy: "|||").first }
    let allowedExchanges = parsedExchanges.filter { exchange in
      let key = AICloneBacktestService.pairKey(them: exchange.them, me: exchange.me)
      guard !excludeExchangeKeys.contains(key) else { return false }
      let themSide = key.components(separatedBy: "|||").first ?? ""
      return !excludedThemPrefixes.contains(themSide)
    }
    let exchanges = Self.dedupeAndCap(allowedExchanges, max: 5)

    let effectivePrompt = Self.composeSystemPrompt(
      voiceNotes: voiceNotes, styleCard: styleCard, exchanges: exchanges, contact: contact)

    return ContactPersona(
      contactId: contact.id,
      contactHandle: contact.id,
      systemPrompt: effectivePrompt,
      generatedAt: Date(),
      messageCountUsed: messageCount,
      notablePatterns: patterns,
      exampleExchanges: exchanges,
      voiceNotes: voiceNotes,
      styleCard: styleCard,
      styleFeatures: styleFeatures
    )
  }

  // MARK: - LLM plumbing (persistent shared bridge, retry on failure)

  /// One long-lived bridge client reused across every clone LLM call. Creating a bridge
  /// per call (the old pattern) paid client registration plus a force-refreshed auth
  /// token round-trip on EVERY generate/critic/persona call — the single biggest source
  /// of reply latency. The persistent client keeps its token fresh on its own timer.
  private var sharedBridge: AgentBridge?
  /// The bridge serves one query at a time; actor reentrancy across `await` means two
  /// concurrent `respond()` calls could otherwise interleave into `requestAlreadyActive`.
  private var llmBusy = false

  private func acquireBridge() async throws -> AgentBridge {
    if let bridge = sharedBridge, await bridge.isAlive { return bridge }
    let bridge = AgentBridge(harnessMode: "piMono")
    try await bridge.start()
    sharedBridge = bridge
    return bridge
  }

  private static func isQuotaError(_ error: Error) -> Bool {
    if case BridgeError.quotaExceeded = error { return true }
    return false
  }

  /// Drop (and unregister) the shared bridge so the next call builds a fresh one.
  private func discardBridge() {
    if let bridge = sharedBridge {
      Task { await bridge.stop() }
    }
    sharedBridge = nil
  }

  private func runLLM(
    prompt: String, system: String, model: String, label: String
  ) async throws -> String {
    while llmBusy { try? await Task.sleep(nanoseconds: 50_000_000) }
    llmBusy = true
    defer { llmBusy = false }

    let maxAttempts = 2
    var lastError: Error?
    for attempt in 1...maxAttempts {
      do {
        let bridge = try await acquireBridge()
        let result = try await bridge.query(
          prompt: prompt,
          systemPrompt: system,
          model: model,
          onTextDelta: { @Sendable _ in },
          onToolCall: { @Sendable _, _, _ in "" },
          onToolActivity: { @Sendable _, _, _, _ in }
        )
        return result.text
      } catch {
        lastError = error
        // A failed query may leave the client wedged — rebuild on the next attempt.
        discardBridge()
        if attempt < maxAttempts {
          log("AIClonePersonaService: \(label) attempt \(attempt) failed, retrying: \(error)")
          // A cached quota verdict fails instantly and a fresh bridge re-checks against
          // the server — only real (network/runtime) failures earn a backoff pause.
          if !Self.isQuotaError(error) {
            try? await Task.sleep(nanoseconds: 800_000_000)
          }
          continue
        }
        log("AIClonePersonaService: \(label) failed after \(attempt) attempts: \(error)")
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

    Write VOICE NOTES (second person, addressed to the AI that will impersonate the user, \
    e.g. "You are texting with \(contact.displayName)…") capturing everything statistical \
    analysis can NOT: their relationship, running topics and in-jokes, attitude and humor, \
    how the user reacts to different kinds of messages (questions, banter, plans, drama, \
    good/bad news), and their VERBATIM vocabulary. Do not describe message lengths, burst \
    counts, or punctuation frequencies — those are measured separately and injected as data.

    Be concrete and evidence-based:
    1. VERBATIM VOCABULARY: quote the user's actual recurring words/abbreviations with \
       meaning, pulled from real lines — e.g. `says "js" for "just"`, `"ts" for "this"`, \
       `"highk" for "highkey"`. Do NOT write vague descriptions like "uses casual slang".
    2. RELATIONSHIP & TOPICS: what they talk about, the dynamic (who teases whom, shared \
       projects, rivalries), names that come up and who they are.
    3. REACTION PATTERNS: how the user responds to being asked for help, to jokes, to \
       plans, to boring updates — with real examples.
    4. EXAMPLE EXCHANGES: pull 3-5 REAL (them → me) pairs VERBATIM from the transcript \
       (copy exact text; join the user's multi-bubble replies with \\n) that best showcase \
       the reply style.

    Respond ONLY with valid JSON (no markdown, no code fences):
    {
      "voice_notes": "the full second-person voice notes, rich with verbatim quotes",
      "notable_patterns": ["short concrete bullet", "another"],
      "example_exchanges": [
        {"them": "exact contact message", "me": "exact user reply (join multi-bubble with \\n)"}
      ]
    }

    RULES:
    - Ground EVERY observation in the actual transcript; never invent traits.
    - example_exchanges MUST be copied verbatim from the transcript (real, not fabricated).
    - The notes must be specific to THIS contact, not generic.
    - Keep notable_patterns to 3-6 concise, concrete bullets.
    """
  }

  /// Ask the model to revise the persona's voice notes to fix the specific pairs it got
  /// most wrong. The measured style card stays fixed (it is data, not opinion).
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

    let priorExamples = previous.exampleExchanges
      .map { "{\"them\": \"\($0.them)\", \"me\": \"\($0.me)\"}" }
      .joined(separator: ",\n    ")

    return """
    You previously wrote these voice notes to imitate how the user texts \
    "\(contact.displayName)":

    CURRENT VOICE NOTES:
    \(previous.voiceNotes.isEmpty ? previous.systemPrompt : previous.voiceNotes)

    A backtest ran your clone against real history and an impartial judge scored each reply. \
    These are the cases where the clone diverged MOST from what the user actually said:

    \(failures)

    Revise the voice notes to close these gaps. Diagnose what the clone got wrong (wrong \
    attitude? too eager/explanatory? wrong slang? missed how they react to this kind of \
    message?) and rewrite so it would produce replies far closer to the user's real ones \
    above. Keep everything that was already accurate. Message lengths / burst counts / \
    punctuation stats are handled separately — focus on voice, vocabulary, and reactions.

    Respond ONLY with valid JSON (no markdown, no code fences):
    {
      "voice_notes": "the revised second-person voice notes",
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

  // MARK: - Respond prompts & parsing

  /// Output contract for candidate generation. JSON with explicit bubble arrays — no text
  /// delimiters to leak into UI or judge input (each array element = one message bubble).
  private static var candidateFormatInstruction: String {
    """
    OUTPUT FORMAT (critical):
    Respond ONLY with valid JSON, no markdown, no commentary:
    {"candidates": [["bubble 1", "bubble 2"], ["bubble 1"], ["bubble 1", "bubble 2", "bubble 3"]]}
    - Produce EXACTLY 3 candidate replies. Each candidate is the reply you might really send, \
    as an array of message bubbles (one array element = one separate text message).
    - Candidate 1: the pure in-the-moment reaction — however you'd really fire back first \
    (often short).
    - Candidate 2: the fragmented burst — 2-4 very short bubbles fired back to back, the way \
    you actually split thoughts mid-stream (not one tidy sentence chopped up).
    - Candidate 3: the one that KEEPS IT GOING — react like yourself, then hand the \
    conversation back by engaging with WHAT THEY JUST SAID: a question about their message, a \
    reaction that invites more, riffing on their point. Still fully your voice — never an \
    interview question or a customer-service "let me know if…".
    - STAY ON THEIR TOPIC. Every candidate must respond to what THEY actually said. Do NOT \
    introduce a new subject, task, plan, or agenda they didn't bring up — a reply that tacks on \
    an unrelated line reads as a glitch, not a person. "Keep it going" means warmth and \
    engagement on the current thread, never changing the subject.
    - SOME MESSAGES ARE CLOSERS. "all good?", "you good?", "cool", "ok", "lol", "kk", "sounds \
    good" are wind-downs — a short clean reply ("yeah all good", "yep") is the correct, complete, \
    human answer. Do NOT manufacture a topic to keep a finished conversation alive; forcing one \
    is what reads as robotic.
    - MATCH THEIR ENERGY. If they asked a real question, shared news, or are clearly engaged, \
    ENGAGE BACK on that — a flat one-word reply there kills the thread and reads as cold. If \
    their message is a natural dead-end, a short reply is right.
    - Real texting is unpolished: half-thoughts, reactions, your own tangents. Do NOT write \
    smooth, complete, well-reasoned sentences unless the real person does. But dry is not the \
    goal: mirror the person, and when they hand you something to run with, run with it.
    - Never mention being an AI. Each bubble is raw message text only.
    """
  }

  /// Build the user turn for candidate generation: retrieved real exchanges, the recent
  /// conversation, and the incoming message.
  private static func buildGenerationPrompt(
    incoming: String, context: [ConversationTurn], examples: [RetrievedExchange]
  ) -> String {
    var sections: [String] = []

    if !examples.isEmpty {
      let block = examples.enumerated().map { index, example -> String in
        let reply = example.me.components(separatedBy: "\n")
          .map { "    \($0)" }.joined(separator: "\n")
        return "\(index + 1). Them: \(example.them.replacingOccurrences(of: "\n", with: " / "))\n   You really replied:\n\(reply)"
      }.joined(separator: "\n")
      sections.append(
        """
        REAL PAST MOMENTS most similar to right now — these are your ACTUAL verbatim replies \
        to similar messages from them (each indented line = one separate message bubble you sent). \
        Mirror this voice exactly:
        \(block)
        """)
    }

    if !context.isEmpty {
      let convo = context.map { "\($0.isFromMe ? "You" : "Them"): \($0.text)" }
        .joined(separator: "\n")
      sections.append("CURRENT CONVERSATION (oldest first):\n\(convo)")
    }

    sections.append(
      """
      They just texted:
      Them: \(incoming)

      Write the 3 candidate replies (as "You"), staying fully in character.
      """)

    return sections.joined(separator: "\n\n")
  }

  /// Parse `{"candidates": [["…"], …]}` from a model response.
  static func parseCandidates(from text: String) -> [[String]]? {
    var jsonText = extractJSONObject(from: text)
    // Drop trailing prose after the closing brace (extractJSONObject only trims the front).
    if let lastBrace = jsonText.lastIndex(of: "}") {
      jsonText = String(jsonText[...lastBrace])
    }
    guard
      let data = jsonText.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return nil }
    if let arrays = parsed["candidates"] as? [[String]] {
      return arrays
    }
    // Tolerate a single flat candidate: {"candidates": ["a", "b"]}
    if let flat = parsed["candidates"] as? [String] {
      return [flat]
    }
    return nil
  }

  /// Last-resort extraction from malformed candidate JSON: the quoted strings of the
  /// first `[...]` bubble array after "candidates". Never returns JSON syntax as content.
  static func extractFirstCandidateStrings(from text: String) -> [String]? {
    guard let anchor = text.range(of: "\"candidates\"") else { return nil }
    guard let open = text.range(of: "[", range: anchor.upperBound..<text.endIndex) else {
      return nil
    }
    var bubbles: [String] = []
    var current = ""
    var inString = false
    var escaped = false
    var depth = 1
    for character in text[open.upperBound...] {
      if inString {
        if escaped {
          current.append(character == "n" ? "\n" : character)
          escaped = false
        } else if character == "\\" {
          escaped = true
        } else if character == "\"" {
          inString = false
          bubbles.append(current)
          current = ""
        } else {
          current.append(character)
        }
        continue
      }
      switch character {
      case "\"": inString = true
      case "[": depth += 1
      case "]":
        depth -= 1
        // End of the first candidate's bubble array (depth 2→1) or of all candidates.
        if depth <= 1, !bubbles.isEmpty { return bubbles }
      default: break
      }
    }
    return bubbles.isEmpty ? nil : bubbles
  }

  /// Clean one candidate's bubbles: split embedded newlines, trim, drop empties and
  /// attachment placeholders, cap the burst length.
  static func sanitizeBubbles(_ bubbles: [String]) -> [String] {
    bubbles
      .flatMap { $0.components(separatedBy: "\n") }
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty && $0 != "[attachment]" }
      .prefix(8)
      .map { String($0) }
  }

  /// Compose the final system prompt: LLM voice notes + real few-shot exchanges +
  /// measured style card + hard "stay in character" rules.
  private static func composeSystemPrompt(
    voiceNotes: String, styleCard: String, exchanges: [ContactExampleExchange],
    contact: ImportedContact
  ) -> String {
    var parts: [String] = [voiceNotes]

    if !exchanges.isEmpty {
      let examples = exchanges.map { "Them: \($0.them)\nYou: \($0.me)" }.joined(separator: "\n\n")
      parts.append(
        """
        REAL PAST EXCHANGES — mimic this exact style (these actually happened; a line break \
        in your reply = a separate message bubble):
        \(examples)
        """)
    }

    if !styleCard.isEmpty {
      parts.append(styleCard)
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
      short texts in a row, you must too.
      - Match the OTHER person's energy. When they ask something, share news, or are engaged, \
      reply like you actually care and give the thread somewhere to go — a question back, a \
      real reaction, your own take. Don't dead-end a live conversation with a cold one-word \
      reply you'd only send if you were annoyed. When their message is a throwaway, a short \
      reply is right. Never be more helpful, formal, or complete than the real person would — \
      stay rough and real, just don't let the conversation die.
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
