import Foundation

// MARK: - History-replay self-benchmark
//
// "Benchmark the agent against your own past decisions before letting go":
// walk the chat's real history, find the points where the user actually
// replied to someone, regenerate the clone's reply at that exact point (the
// clone only sees the thread *before* the real reply), then have an LLM judge
// score how close the clone came to what the user really sent. The per-chat
// score gates Auto mode.

struct AICloneBenchmarkSample: Equatable {
  /// Thread lines before the user's real reply (oldest first).
  var priorThreadLines: [String]
  var inboundText: String
  var inboundSenderName: String
  /// What the user actually sent.
  var actualReply: String
}

struct AICloneBenchmark {
  var engine: AICloneReplyEngine
  static let maxSamples = 8

  /// Extracts replay samples: an inbound text message followed by the user's
  /// own text reply. Messages must be oldest-first.
  static func samples(from history: [BeeperMessage]) -> [AICloneBenchmarkSample] {
    let usable = history.filter { $0.isDeleted != true && $0.isTextLike && !($0.text ?? "").isEmpty }
    var collected: [AICloneBenchmarkSample] = []
    for (index, message) in usable.enumerated() {
      guard message.isSender == true, index > 0 else { continue }
      let inbound = usable[index - 1]
      guard inbound.isSender != true else { continue }
      let prior = usable[..<(index - 1)].suffix(16).map { line -> String in
        let sender = line.isSender == true ? "Me" : (line.senderName ?? "Them")
        return "\(sender): \(AICloneReplyEngine.strippedText(line.text ?? ""))"
      }
      collected.append(
        AICloneBenchmarkSample(
          priorThreadLines: Array(prior),
          inboundText: AICloneReplyEngine.strippedText(inbound.text ?? ""),
          inboundSenderName: inbound.senderName ?? "Them",
          actualReply: AICloneReplyEngine.strippedText(message.text ?? "")))
    }
    // Newest exchanges are the most representative of how the user texts today.
    return Array(collected.suffix(maxSamples))
  }

  func run(
    chat: BeeperChat,
    history: [BeeperMessage],
    personaName: String,
    personaPrompt: String,
    memoryFacts: [String],
    judge: AICloneCompletionTransport
  ) async throws -> AICloneBenchmarkResult {
    let samples = Self.samples(from: history)
    guard !samples.isEmpty else {
      return AICloneBenchmarkResult(
        chatID: chat.id,
        chatTitle: chat.title ?? "Chat",
        sampleCount: 0,
        matchScore: 0,
        generatedAt: Date())
    }
    var scores: [Int] = []
    for sample in samples {
      let context = AICloneReplyContext(
        personaName: personaName,
        personaPrompt: personaPrompt,
        memoryFacts: memoryFacts,
        chatTitle: chat.title ?? "Chat",
        network: chat.network ?? "Beeper",
        isGroupChat: !chat.isSingle,
        threadLines: sample.priorThreadLines,
        inboundText: sample.inboundText,
        inboundSenderName: sample.inboundSenderName)
      let decision = try await engine.decide(context: context)
      guard decision.shouldReply, let generated = decision.reply, !generated.isEmpty else {
        // The user did reply here; a silent clone is a miss for this sample.
        scores.append(0)
        continue
      }
      let verdict = try await judge.complete(
        system: Self.judgeSystemPrompt,
        user: Self.judgeUserPrompt(sample: sample, generated: generated))
      scores.append(Self.parseJudgeScore(verdict) ?? 0)
    }
    let average = scores.isEmpty ? 0 : scores.reduce(0, +) / scores.count
    return AICloneBenchmarkResult(
      chatID: chat.id,
      chatTitle: chat.title ?? "Chat",
      sampleCount: scores.count,
      matchScore: average,
      generatedAt: Date())
  }

  static let judgeSystemPrompt = """
    You compare a person's REAL chat reply with a clone's generated reply at the same point in \
    the same conversation. Score how plausibly the generated reply could have come from the \
    same person answering the same message: 100 = same substance and voice, 50 = plausible but \
    noticeably off in content or tone, 0 = wrong substance, wrong voice, or factually \
    contradicts the real reply. Respond ONLY with JSON: {"score": 0-100}
    """

  static func judgeUserPrompt(sample: AICloneBenchmarkSample, generated: String) -> String {
    """
    Incoming message from \(sample.inboundSenderName):
    \(sample.inboundText)

    REAL reply the person sent:
    \(sample.actualReply)

    CLONE's generated reply:
    \(generated)
    """
  }

  static func parseJudgeScore(_ raw: String) -> Int? {
    guard let start = raw.range(of: "{"), let end = raw.range(of: "}", options: .backwards),
      start.lowerBound < end.upperBound,
      let data = String(raw[start.lowerBound..<end.upperBound]).data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return nil }
    if let score = object["score"] as? Int { return max(0, min(100, score)) }
    if let score = object["score"] as? Double { return max(0, min(100, Int(score))) }
    return nil
  }
}
