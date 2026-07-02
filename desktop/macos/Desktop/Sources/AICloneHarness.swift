import Foundation

/// Headless automation actions for the AI Clone pipeline, registered on the local
/// automation bridge (non-production bundles only). They let an agent run the full
/// train → backtest loop against real iMessage history without driving the UI, and
/// dump machine-readable results to disk for inspection.
///
/// Actions:
///   ai_clone_contacts                          — list top contacts (rank, handle, count)
///   ai_clone_run rank=1 holdout=12 seed=42 …   — start persona+backtest in background
///   ai_clone_respond rank=1 message="…"        — one-shot reply via the trained persona
///
/// `ai_clone_run` returns immediately; progress lines stream to `<out>.progress` and the
/// final JSON report is written to `out` (default /tmp/ai-clone-run.json).
enum AICloneHarness {

  @MainActor private static var runInFlight = false

  @MainActor
  static func register(on registry: DesktopAutomationActionRegistry) {
    registry.register(
      name: "ai_clone_contacts",
      summary: "List top iMessage contacts available to the AI Clone pipeline",
      params: ["limit"]
    ) { params in
      let limit = Int(params["limit"] ?? "") ?? 10
      let contacts = try await IMessageReaderService.shared.topContacts(limit: limit)
      let listing = contacts.enumerated()
        .map { "\($0.offset + 1)\t\($0.element.id)\t\($0.element.messageCount)" }
        .joined(separator: "\n")
      return ["contacts": listing]
    }

    registry.register(
      name: "ai_clone_run",
      summary: "Run AI Clone train/backtest headlessly; JSON report written to 'out'",
      params: ["rank", "holdout", "seed", "iterations", "messages", "out", "reuse_persona", "eval_from"]
    ) { params in
      guard !runInFlight else { return ["error": "a run is already in flight"] }
      let rank = Int(params["rank"] ?? "") ?? 1
      let holdout = Int(params["holdout"] ?? "") ?? 12
      let seed = UInt64(params["seed"] ?? "") ?? 42
      let iterations = Int(params["iterations"] ?? "") ?? 0
      let messageLimit = Int(params["messages"] ?? "") ?? 1500
      let out = params["out"] ?? "/tmp/ai-clone-run.json"
      let reusePersona = (params["reuse_persona"] ?? "false") == "true"
      let evalFrom = params["eval_from"]

      runInFlight = true
      Task.detached(priority: .userInitiated) {
        defer { Task { @MainActor in runInFlight = false } }
        await Self.executeRun(
          rank: rank, holdout: holdout, seed: seed, iterations: iterations,
          messageLimit: messageLimit, out: out, reusePersona: reusePersona, evalFrom: evalFrom)
      }
      return ["started": "true", "out": out, "progress": out + ".progress"]
    }

    registry.register(
      name: "ai_clone_rejudge",
      summary: "Re-score an existing run report's predictions N times each (judge variance)",
      params: ["report", "samples", "out"]
    ) { params in
      guard !runInFlight else { return ["error": "a run is already in flight"] }
      guard let report = params["report"] else { return ["error": "missing 'report'"] }
      let samples = Int(params["samples"] ?? "") ?? 3
      let out = params["out"] ?? (report + ".rejudged.json")
      runInFlight = true
      Task.detached(priority: .userInitiated) {
        defer { Task { @MainActor in runInFlight = false } }
        await Self.executeRejudge(report: report, samples: samples, out: out)
      }
      return ["started": "true", "out": out]
    }

    registry.register(
      name: "ai_clone_respond",
      summary: "Predict a reply to 'message' using the trained persona for contact 'rank'",
      params: ["rank", "message"]
    ) { params in
      let rank = Int(params["rank"] ?? "") ?? 1
      guard let message = params["message"], !message.isEmpty else {
        return ["error": "missing 'message'"]
      }
      let contacts = try await IMessageReaderService.shared.topContacts(limit: rank)
      guard contacts.count >= rank else { return ["error": "no contact at rank \(rank)"] }
      let contact = contacts[rank - 1].asImportedContact()
      guard let persona = await AIClonePersonaService.shared.existingPersona(for: contact.id)
      else { return ["error": "no persona trained for \(contact.id)"] }
      let reply = try await AIClonePersonaService.shared.respond(as: persona, to: message)
      return ["reply": reply]
    }
  }

  // MARK: - Run execution

  private static func executeRun(
    rank: Int, holdout: Int, seed: UInt64, iterations: Int, messageLimit: Int,
    out: String, reusePersona: Bool, evalFrom: String?
  ) async {
    let progressPath = out + ".progress"
    FileManager.default.createFile(atPath: progressPath, contents: nil)
    func progress(_ line: String) {
      log("AICloneHarness: \(line)")
      appendLine(line, to: progressPath)
    }

    // Optional pinned eval set: reuse the exact (them → actual) pairs of a previous
    // report so architectures are compared on identical data.
    var pinned: [(them: String, me: String)]? = nil
    if let evalFrom,
      let data = FileManager.default.contents(atPath: evalFrom),
      let previous = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let previousPairs = previous["pairs"] as? [[String: Any]]
    {
      pinned = previousPairs.compactMap { pair in
        guard let them = pair["them"] as? String, let actual = pair["actual"] as? String,
          !them.isEmpty, !actual.isEmpty
        else { return nil }
        return (them, actual)
      }
      progress("pinned eval set: \(pinned?.count ?? 0) pairs from \(evalFrom)")
    }

    do {
      let contacts = try await IMessageReaderService.shared.topContacts(limit: max(rank, 1))
      guard contacts.count >= rank else {
        try writeJSON(["error": "no contact at rank \(rank)"], to: out)
        return
      }
      let contact = contacts[rank - 1].asImportedContact()
      let messages = try await IMessageReaderService.shared.messages(
        for: contacts[rank - 1], limit: messageLimit
      ).map { $0.asImportedMessage() }
      progress("contact rank=\(rank) messages=\(messages.count)")

      let started = Date()
      // Pinned eval pairs must never appear in a persona's few-shot examples.
      let evalKeys = Set(
        (pinned ?? []).map { AICloneBacktestService.pairKey(them: $0.them, me: $0.me) })
      var persona: ContactPersona
      if reusePersona, let existing = await AIClonePersonaService.shared.existingPersona(
        for: contact.id)
      {
        persona = existing
        progress("reusing stored persona (generated \(existing.generatedAt))")
      } else {
        progress("generating persona…")
        persona = try await AIClonePersonaService.shared.generatePersona(
          for: contact, messages: messages, excludeExchangeKeys: evalKeys)
        progress("persona generated (\(persona.systemPrompt.count) chars)")
      }

      var result: BacktestResult
      if iterations <= 1 {
        progress("backtesting holdout=\(holdout) seed=\(seed) pinned=\(pinned?.count ?? 0)…")
        result = try await AICloneBacktestService.shared.runBacktest(
          for: contact, messages: messages, persona: persona,
          holdoutCount: holdout, seed: seed, pinnedPairs: pinned)
      } else {
        // Training iterations must never sample (or memorize) the eval pairs.
        progress("training loop iterations=\(iterations) holdout=\(holdout) evalExcluded=\(evalKeys.count)…")
        let trained = try await AICloneBacktestService.shared.trainToTarget(
          for: contact, messages: messages,
          maxIterations: iterations, holdoutCount: holdout,
          excludePairKeys: evalKeys,
          onProgress: { tick in
            appendLine(
              "iter \(tick.iteration)/\(tick.maxIterations) \(tick.phase)"
                + (tick.latestAverage.map { String(format: " best=%.3f", $0) } ?? ""),
              to: progressPath)
          })
        persona = trained.persona
        result = trained.result
        // Score the winner on the fixed eval set for cross-run comparability.
        progress("final eval (pinned=\(pinned?.count ?? 0), seed=\(seed))…")
        result = try await AICloneBacktestService.shared.runBacktest(
          for: contact, messages: messages, persona: persona,
          holdoutCount: holdout, seed: seed, pinnedPairs: pinned)
      }

      let elapsed = Date().timeIntervalSince(started)
      progress(String(format: "done avg=%.3f in %.0fs", result.averageScore, elapsed))

      let report: [String: Any] = [
        "contactId": contact.id,
        "rank": rank,
        "seed": seed,
        "holdout": holdout,
        "iterations": iterations,
        "messageCount": messages.count,
        "averageScore": result.averageScore,
        "elapsedSeconds": elapsed,
        "systemPrompt": persona.systemPrompt,
        "pairs": result.pairs.map { pair -> [String: Any] in
          [
            "them": pair.contactMessage,
            "actual": pair.actualReply,
            "predicted": pair.predictedReply ?? "",
            "score": pair.similarityScore ?? -1,
            "reasoning": pair.judgeReasoning ?? "",
            "context": pair.context.map { "\($0.isFromMe ? "me" : "them"): \($0.text)" },
          ]
        },
      ]
      try writeJSON(report, to: out)
      progress("report written to \(out)")
    } catch {
      progress("FAILED: \(error.localizedDescription)")
      try? writeJSON(["error": error.localizedDescription], to: out)
    }
  }

  /// Re-judge every pair in a stored report `samples` times and write per-pair mean
  /// scores plus the overall mean — same predictions, tighter measurement.
  private static func executeRejudge(report: String, samples: Int, out: String) async {
    let progressPath = out + ".progress"
    FileManager.default.createFile(atPath: progressPath, contents: nil)
    do {
      guard let data = FileManager.default.contents(atPath: report),
        let parsed = try JSONSerialization.jsonObject(with: data) as? [String: Any],
        let pairs = parsed["pairs"] as? [[String: Any]]
      else {
        try writeJSON(["error": "unreadable report \(report)"], to: out)
        return
      }

      var rejudged: [[String: Any]] = []
      var means: [Double] = []
      for (index, pair) in pairs.enumerated() {
        guard let them = pair["them"] as? String,
          let actual = pair["actual"] as? String,
          let predicted = pair["predicted"] as? String, !predicted.isEmpty
        else { continue }
        let context: [ConversationTurn] = (pair["context"] as? [String] ?? []).compactMap { line in
          if line.hasPrefix("me: ") { return ConversationTurn(isFromMe: true, text: String(line.dropFirst(4))) }
          if line.hasPrefix("them: ") { return ConversationTurn(isFromMe: false, text: String(line.dropFirst(6))) }
          return nil
        }
        var scores: [Double] = []
        for _ in 0..<samples {
          if let verdict = try? await AICloneBacktestService.shared.judgeOnce(
            them: them, actual: actual, predicted: predicted, context: context)
          {
            scores.append(verdict.score)
          }
        }
        guard !scores.isEmpty else { continue }
        let mean = scores.reduce(0, +) / Double(scores.count)
        means.append(mean)
        rejudged.append(["them": them, "predicted": predicted, "scores": scores, "mean": mean])
        appendLine("pair \(index + 1)/\(pairs.count) mean=\(String(format: "%.3f", mean))", to: progressPath)
      }

      let overall = means.isEmpty ? 0 : means.reduce(0, +) / Double(means.count)
      try writeJSON(
        ["report": report, "samples": samples, "averageScore": overall, "pairs": rejudged],
        to: out)
      appendLine(String(format: "done overall=%.3f", overall), to: progressPath)
    } catch {
      appendLine("FAILED: \(error.localizedDescription)", to: progressPath)
      try? writeJSON(["error": error.localizedDescription], to: out)
    }
  }

  // MARK: - Helpers

  private static func appendLine(_ line: String, to path: String) {
    let stamped = "[\(ISO8601DateFormatter().string(from: Date()))] \(line)\n"
    guard let data = stamped.data(using: .utf8) else { return }
    if let handle = FileHandle(forWritingAtPath: path) {
      handle.seekToEndOfFile()
      handle.write(data)
      try? handle.close()
    } else {
      try? data.write(to: URL(fileURLWithPath: path))
    }
  }

  private static func writeJSON(_ object: [String: Any], to path: String) throws {
    let data = try JSONSerialization.data(
      withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: URL(fileURLWithPath: path))
  }
}
