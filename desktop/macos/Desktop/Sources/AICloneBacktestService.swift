import Foundation

// MARK: - Models

/// One held-out test case: what the contact said, what the user actually replied, what the
/// clone predicted, and how convincingly (LLM-judge score) the prediction passes as real.
struct BacktestPair: Sendable, Identifiable {
  let id = UUID()
  let contactMessage: String
  let actualReply: String
  /// When the contact's turn started — used to key this exact historical instance so
  /// retrieval can exclude it (and only it) while predicting its held-out reply.
  var turnDate: Date = Date(timeIntervalSinceReferenceDate: 0)
  /// The few messages (both directions, oldest first) that preceded `contactMessage`.
  var context: [ConversationTurn] = []
  var predictedReply: String?
  /// LLM-judge score normalized to 0–1 (judge rates 0–100 for how convincingly the
  /// predicted reply passes as the same person; we store /100).
  var similarityScore: Double?
  /// The judge's one-sentence justification for the score.
  var judgeReasoning: String?
}

/// The outcome of a backtest run (one iteration) or the best iteration of a training loop.
struct BacktestResult: Sendable {
  let contactId: String
  var pairs: [BacktestPair]
  var averageScore: Double
  let messageCountUsed: Int
  /// For `runBacktest` this is 1. For `trainToTarget` it's the total iterations executed.
  var iterationsRun: Int
}

/// Progress ticks emitted during `trainToTarget`, for the UI to render live status.
struct BacktestProgress: Sendable {
  let iteration: Int
  let maxIterations: Int
  let phase: String
  let latestAverage: Double?
}

enum BacktestError: LocalizedError {
  case notEnoughData
  case judgeParseFailed

  var errorDescription: String? {
    switch self {
    case .notEnoughData:
      return "Not enough back-and-forth history with this contact to run a backtest."
    case .judgeParseFailed:
      return "The scoring judge returned an unreadable response."
    }
  }
}

// MARK: - Service

/// Scores an AI Clone persona against real message history and iteratively refines it toward
/// a target accuracy. Each held-out reply is scored by an LLM judge (0–100, normalized to
/// 0–1) rating how convincingly the clone's prediction passes as the same person's real text.
actor AICloneBacktestService {
  static let shared = AICloneBacktestService()

  private init() {}

  // MARK: Backtest (Part 2)

  /// Score `persona` against `holdoutCount` real (their-message → my-reply) pairs that were
  /// NOT used as training examples. `messages` are any platform, newest-first. Returns the
  /// per-pair predictions/scores and the average.
  ///
  /// - `seed`: deterministic holdout sampling (same pairs every run for fair comparison).
  /// - `pinnedPairs`: evaluate exactly these (them → actual) pairs instead of sampling —
  ///   lets different architectures be scored on an identical eval set across runs.
  /// - `excludePairKeys`: text-keys never to sample (e.g. the fixed eval set, during
  ///   training iterations, so refinement can't memorize eval answers).
  func runBacktest(
    for contact: ImportedContact, messages: [ImportedMessage], persona: ContactPersona,
    holdoutCount: Int = 8, seed: UInt64? = nil,
    pinnedPairs: [(them: String, me: String)]? = nil,
    excludePairKeys: Set<String> = []
  ) async throws -> BacktestResult {
    let chronological = Array(messages.reversed())

    // The retrieval index must exist before respond() so dynamic few-shots work even when
    // the persona was loaded from disk in a fresh session.
    await AICloneRetrievalService.shared.ensureIndex(contactId: contact.id, messages: messages)

    // Extract real turn-pairs, then drop any that duplicate the persona's few-shot examples
    // so we never test on data the model was trained on.
    let trainingKeys = Set(persona.exampleExchanges.map { Self.pairKey(them: $0.them, me: $0.me) })
    let allPairs = Self.buildPairs(from: chronological)
    let pairs = allPairs.filter {
      let key = Self.pairKey(them: $0.contactMessage, me: $0.actualReply)
      return !trainingKeys.contains(key) && !excludePairKeys.contains(key)
    }
    guard !pairs.isEmpty else { throw BacktestError.notEnoughData }

    var sampled: [BacktestPair]
    if let pinnedPairs {
      let wanted = Set(pinnedPairs.map { Self.pairKey(them: $0.them, me: $0.me) })
      var seen = Set<String>()
      sampled = allPairs.filter { pair in
        let key = Self.pairKey(them: pair.contactMessage, me: pair.actualReply)
        return wanted.contains(key) && seen.insert(key).inserted
      }
      guard sampled.count >= max(1, pinnedPairs.count / 2) else {
        throw BacktestError.notEnoughData
      }
    } else {
      // With a seed the holdout is deterministic (same pairs every run) so different
      // architectures/personas are compared on identical data instead of fresh noise.
      sampled = Array(Self.sample(pairs, count: holdoutCount, seed: seed))
    }

    // Predict the user's reply for each held-out contact message. Sequential on purpose —
    // each respond() spins up its own agent bridge against the shared runtime, so we avoid
    // overlapping requests. Each pair excludes ITS OWN historical instance from retrieval
    // so the clone is never handed the exact answer it's being tested on.
    for index in sampled.indices {
      let pair = sampled[index]
      let leakKey = AICloneRetrievalService.instanceKey(
        them: pair.contactMessage, me: pair.actualReply, date: pair.turnDate)
      do {
        sampled[index].predictedReply = try await AIClonePersonaService.shared.respond(
          as: persona, to: pair.contactMessage, context: pair.context,
          excludingPairKeys: [leakKey])
      } catch {
        log("AICloneBacktest: prediction failed for a pair: \(error)")
        sampled[index].predictedReply = nil
      }
    }

    let scored = try await scorePairs(sampled)
    let validScores = scored.compactMap { $0.similarityScore }
    let average = validScores.isEmpty ? 0 : validScores.reduce(0, +) / Double(validScores.count)

    return BacktestResult(
      contactId: contact.id,
      pairs: scored,
      averageScore: average,
      messageCountUsed: messages.count,
      iterationsRun: 1
    )
  }

  /// Score each pair with an LLM judge on VOICE plausibility (not topic match): would this
  /// specific person plausibly send the predicted reply in this exact spot? Sets
  /// `similarityScore` (0–1) and `judgeReasoning` (which is tagged with the topic-match verdict
  /// so we can tell voice-match-without-topic-match apart from a true miss).
  private func scorePairs(_ pairs: [BacktestPair]) async throws -> [BacktestPair] {
    var result = pairs
    for index in result.indices {
      guard let predicted = result[index].predictedReply,
        !predicted.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      else { continue }
      do {
        let verdict = try await judge(
          them: result[index].contactMessage,
          actual: result[index].actualReply,
          predicted: predicted,
          context: result[index].context)
        result[index].similarityScore = verdict.score / 100.0
        // Prefix the reasoning with the structured topic-match tag so results (and refinement)
        // can distinguish "in-voice topic jump" from "generic on-topic but off-voice".
        let tag = verdict.topicMatch ? "[topic match]" : "[topic CHANGED]"
        result[index].judgeReasoning = "\(tag) \(verdict.reasoning)"
      } catch {
        log("AICloneBacktest: judge scoring failed for a pair: \(error)")
      }
    }
    return result
  }

  /// Ask the model to rate VOICE plausibility (not topic match) 0–100, plus whether the
  /// prediction matched the real reply's topic and a one-sentence justification.
  private func judge(
    them: String, actual: String, predicted: String, context: [ConversationTurn]
  ) async throws -> (score: Double, reasoning: String, topicMatch: Bool) {
    let systemPrompt =
      "You are a strict judge of texting-STYLE impersonation. You evaluate whether an AI's "
      + "predicted reply could plausibly be the SAME person's real next text — judging VOICE, "
      + "not topic. Output only valid JSON."

    let contextBlock =
      context.isEmpty
      ? ""
      : "Conversation leading up to this (oldest first):\n"
        + context.map { "\($0.isFromMe ? "Them-person(you're imitating)" : "Contact"): \($0.text)" }
        .joined(separator: "\n") + "\n\n"

    let prompt = """
      \(contextBlock)The contact just said:
      "\(them)"

      The person you're imitating REALLY replied with:
      "\(actual)"

      An AI clone predicted this reply instead:
      "\(predicted)"

      Rate 0–100 how plausibly THIS SPECIFIC PERSON could have sent the predicted reply in this \
      exact spot — judging VOICE, not topic. This person often changes topic abruptly, drops \
      non-sequiturs, and goes on their own tangents, so a predicted reply does NOT need to match \
      the real reply's TOPIC or CONTENT to score well.

      SCORE HIGH when the prediction nails their voice — tone, slang/vocabulary, capitalization, \
      punctuation, emoji use, brevity, and multi-message burst style — EVEN IF it's about a \
      totally different topic than the real reply (an in-voice topic-jump is authentic to them).

      SCORE LOW when the prediction sounds generic, too formal, too long/short, or off-voice — \
      EVEN IF it's on the exact same topic as the real reply. Correct topic in the wrong voice \
      is a failure; wrong topic in the right voice is a success.

      Also report whether the prediction happened to match the real reply's topic/content.

      Respond ONLY with valid JSON (no markdown, no code fences):
      {"score": <integer 0-100>, "topic_match": <true|false>, "reasoning": "<one sentence; \
      explicitly state whether voice matched and whether topic matched, e.g. 'in-voice but \
      different topic' or 'on-topic but off-voice'>"}
      """

    let maxAttempts = 2
    var lastError: Error?
    for attempt in 1...maxAttempts {
      do {
        let bridge = AgentBridge(harnessMode: "piMono")
        try await bridge.start()
        defer { Task { await bridge.stop() } }

        let response = try await bridge.query(
          prompt: prompt,
          systemPrompt: systemPrompt,
          model: ModelQoS.Claude.synthesis,
          onTextDelta: { @Sendable _ in },
          onToolCall: { @Sendable _, _, _ in "" },
          onToolActivity: { @Sendable _, _, _, _ in }
        )

        let jsonText = Self.extractJSONObject(from: response.text)
        guard
          let data = jsonText.data(using: .utf8),
          let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
          throw BacktestError.judgeParseFailed
        }

        let rawScore = (parsed["score"] as? Double) ?? Double(parsed["score"] as? Int ?? -1)
        guard rawScore >= 0 else { throw BacktestError.judgeParseFailed }
        let clamped = min(100, max(0, rawScore))
        let reasoning = (parsed["reasoning"] as? String ?? "")
          .trimmingCharacters(in: .whitespacesAndNewlines)
        let topicMatch = (parsed["topic_match"] as? Bool) ?? false
        return (clamped, reasoning, topicMatch)
      } catch {
        lastError = error
        if attempt < maxAttempts {
          try? await Task.sleep(nanoseconds: 600_000_000)
          continue
        }
      }
    }
    throw lastError ?? BacktestError.judgeParseFailed
  }

  // MARK: Training loop (Part 3)

  /// Generate a persona, backtest it, and refine toward `targetScore`, keeping the
  /// best-scoring persona seen across all iterations. Returns that best persona/result
  /// even if the target wasn't reached (loop hits `maxIterations`). Persists the winner.
  func trainToTarget(
    for contact: ImportedContact,
    messages: [ImportedMessage],
    // 0.80 is a deliberate calibration for the voice-plausibility rubric, not a placeholder:
    // real single-persona runs show that ~0.30 content-match cosine and even a strict topic
    // judge cap far below 0.95, because authentic texting includes unpredictable topic jumps.
    // Under the voice-not-topic judge, ~0.80 average is a genuinely strong, achievable bar.
    targetScore: Double = 0.80,
    maxIterations: Int = 5,
    holdoutCount: Int = 8,
    excludePairKeys: Set<String> = [],
    onProgress: (@Sendable (BacktestProgress) -> Void)? = nil
  ) async throws -> (persona: ContactPersona, result: BacktestResult) {
    func tick(_ iteration: Int, _ phase: String, _ avg: Double?) {
      onProgress?(
        BacktestProgress(
          iteration: iteration, maxIterations: maxIterations, phase: phase, latestAverage: avg))
    }

    tick(1, "Generating persona", nil)
    var current = try await AIClonePersonaService.shared.generatePersona(
      for: contact, messages: messages)

    var best: (persona: ContactPersona, result: BacktestResult)?
    var reachedTarget = false
    var totalIterations = 0

    for iteration in 1...maxIterations {
      totalIterations = iteration
      tick(iteration, "Backtesting", best?.result.averageScore)
      let result = try await runBacktest(
        for: contact, messages: messages, persona: current, holdoutCount: holdoutCount,
        excludePairKeys: excludePairKeys)

      if best == nil || result.averageScore > best!.result.averageScore {
        best = (current, result)
      }
      tick(iteration, "Scored", result.averageScore)

      if result.averageScore >= targetScore {
        reachedTarget = true
        log(
          "AICloneBacktest: target \(targetScore) reached at iteration \(iteration) "
            + "(score \(String(format: "%.3f", result.averageScore)))")
        break
      }

      guard iteration < maxIterations else { break }

      tick(iteration, "Refining persona", result.averageScore)
      let worst = Self.worstPairs(from: result, limit: 4)
      do {
        current = try await AIClonePersonaService.shared.refinePersona(
          for: contact, messages: messages, previous: current, worstPairs: worst)
      } catch {
        log("AICloneBacktest: refine failed at iteration \(iteration), stopping: \(error)")
        break
      }
    }

    guard var winner = best else { throw BacktestError.notEnoughData }
    winner.result.iterationsRun = totalIterations

    // Persist the best persona as the active one so Preview Chat / respond use it.
    await AIClonePersonaService.shared.store(winner.persona)

    if reachedTarget {
      log(
        "AICloneBacktest: DONE — target reached, final avg "
          + "\(String(format: "%.3f", winner.result.averageScore)) after \(totalIterations) iteration(s)")
    } else {
      log(
        "AICloneBacktest: DONE — hit maxIterations \(maxIterations) without reaching "
          + "\(targetScore); best avg \(String(format: "%.3f", winner.result.averageScore))")
    }

    return winner
  }

  // MARK: - Pair extraction & helpers

  /// How many preceding messages to attach as conversation context per pair.
  private static let contextWindow = 10

  /// A "my reply" only counts as a reply if it lands within this window of the contact's
  /// last message. Beyond it, the from-me run is me starting a new conversation, not
  /// answering — pairing those poisons both training examples and the holdout.
  private static let replyGapLimit: TimeInterval = 4 * 60 * 60

  /// Caps on how many bubbles of a run to keep (very long runs are monologues; keeping
  /// the boundary-adjacent bubbles preserves the actual stimulus/response).
  private static let maxThemBubbles = 6
  private static let maxMeBubbles = 8

  /// Walk the chronological transcript and emit (their-run → my-run) pairs. Consecutive
  /// messages from the same sender are concatenated (multi-bubble bursts become one turn).
  /// Each pair also carries up to `contextWindow` preceding messages as context.
  static func buildPairs(from chronological: [ImportedMessage]) -> [BacktestPair] {
    var pairs: [BacktestPair] = []
    var index = 0
    let count = chronological.count

    while index < count {
      // Skip until a contact (not-from-me) message starts a turn.
      guard !chronological[index].isFromMe else {
        index += 1
        continue
      }

      let themStart = index
      var themParts: [String] = []
      var themLastDate = chronological[index].date
      while index < count && !chronological[index].isFromMe {
        themParts.append(clean(chronological[index].text))
        themLastDate = chronological[index].date
        index += 1
      }

      guard index < count, chronological[index].isFromMe else { continue }

      // If my first message comes hours later, it's a new conversation I started — skip.
      guard chronological[index].date.timeIntervalSince(themLastDate) <= replyGapLimit else {
        continue
      }

      var meParts: [String] = []
      while index < count && chronological[index].isFromMe {
        meParts.append(clean(chronological[index].text))
        index += 1
      }

      let them = themParts.suffix(maxThemBubbles)
        .joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
      let me = meParts.prefix(maxMeBubbles)
        .joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
      // A reply that is only attachment placeholders can't be predicted from text — skip.
      let meIsOnlyAttachments = meParts.allSatisfy { $0 == "[attachment]" || $0.isEmpty }
      if !them.isEmpty, !me.isEmpty, !meIsOnlyAttachments {
        // Context = the messages immediately before this contact turn, oldest first.
        let contextSlice = chronological[max(0, themStart - contextWindow)..<themStart]
        let context = contextSlice.compactMap { message -> ConversationTurn? in
          let text = clean(message.text)
          return text.isEmpty ? nil : ConversationTurn(isFromMe: message.isFromMe, text: text)
        }
        pairs.append(
          BacktestPair(
            contactMessage: them, actualReply: me,
            turnDate: chronological[themStart].date, context: context))
      }
    }

    return pairs
  }

  /// Deterministically sample `count` pairs when `seed` is provided (SplitMix64-driven
  /// Fisher–Yates), otherwise fall back to system randomness.
  private static func sample(_ pairs: [BacktestPair], count: Int, seed: UInt64?) -> [BacktestPair] {
    guard let seed else { return Array(pairs.shuffled().prefix(count)) }
    var rng = SplitMix64(seed: seed)
    var indices = Array(pairs.indices)
    for i in stride(from: indices.count - 1, to: 0, by: -1) {
      let j = Int(rng.next() % UInt64(i + 1))
      indices.swapAt(i, j)
    }
    return indices.prefix(count).map { pairs[$0] }
  }

  /// The lowest-scoring predicted pairs (with the judge's reasoning), for refinement.
  private static func worstPairs(
    from result: BacktestResult, limit: Int
  ) -> [(contactMessage: String, predicted: String, actual: String, reasoning: String)] {
    result.pairs
      .filter { $0.predictedReply != nil && $0.similarityScore != nil }
      .sorted { ($0.similarityScore ?? 1) < ($1.similarityScore ?? 1) }
      .prefix(limit)
      .map { ($0.contactMessage, $0.predictedReply ?? "", $0.actualReply, $0.judgeReasoning ?? "") }
  }

  private static func clean(_ text: String) -> String {
    text.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Tiny deterministic RNG (SplitMix64) for reproducible holdout sampling.
  struct SplitMix64 {
    private var state: UInt64
    init(seed: UInt64) { state = seed }
    mutating func next() -> UInt64 {
      state &+= 0x9E37_79B9_7F4A_7C15
      var z = state
      z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
      z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
      return z ^ (z >> 31)
    }
  }

  static func pairKey(them: String, me: String) -> String {
    func norm(_ s: String) -> String {
      s.lowercased()
        .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return norm(them) + "|||" + norm(me)
  }

  /// Extract the leading JSON object from a model response (strip code fences / prose).
  private static func extractJSONObject(from text: String) -> String {
    var responseText = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if responseText.hasPrefix("```") {
      if let firstNewline = responseText.firstIndex(of: "\n") {
        responseText = String(responseText[responseText.index(after: firstNewline)...])
      }
      if responseText.hasSuffix("```") {
        responseText = String(responseText.dropLast(3))
          .trimmingCharacters(in: .whitespacesAndNewlines)
      }
    }
    if let braceIndex = responseText.firstIndex(of: "{") {
      responseText = String(responseText[braceIndex...])
    }
    return responseText.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
