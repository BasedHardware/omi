import Foundation

/// One promise the user made to a contact, pulled verbatim from imported message history.
/// `commitmentText` is a verb-first task title naming the contact; `context` is the real
/// surrounding line it came from (never invented); `saidOn` is when it was said (best-effort).
struct ExtractedCommitment: Sendable, Hashable {
  /// Verb-first task title, e.g. "Send Priya the signed lease by Friday".
  let commitmentText: String
  /// When the user made the commitment, if the model could resolve it. Best-effort.
  let saidOn: Date?
  /// The real surrounding message the commitment came from, kept for reference on the task.
  let context: String
  /// Model confidence 0.0–1.0 that this is a genuine, still-open commitment.
  let confidence: Double
}

/// Result of running a commitment scan on one contact: what was found, and how those
/// findings turned into tasks (some may be skipped as duplicates of already-tracked tasks).
struct CommitmentScanOutcome: Sendable {
  let found: [ExtractedCommitment]
  let created: Int
  let duplicatesSkipped: Int
}

enum CommitmentExtractionError: LocalizedError {
  case notEnoughMessages
  case llmFailed(String)

  var errorDescription: String? {
    switch self {
    case .notEnoughMessages:
      return "Not enough message history with this contact to scan for commitments."
    case .llmFailed(let detail):
      return detail.isEmpty ? "Commitment scan failed. Please try again." : detail
    }
  }
}

/// Scans imported message history (iMessage / Telegram / WhatsApp) for things the user
/// *promised* a contact and hasn't visibly followed through on, and turns each into a real
/// Task via the exact same staged-task pipeline the screen-based `TaskAssistant` uses
/// (`StagedTaskStorage` + `APIClient.createStagedTask` + `TaskPromotionService`). Read-only
/// analysis: it never sends messages and never touches AI-Clone send-mode behavior.
actor CommitmentExtractionService {
  static let shared = CommitmentExtractionService()

  /// Bound the transcript window sent to the model to control cost/latency.
  private let maxMessagesScanned = 200
  /// Below this the model's guess is too unreliable to nag the user about.
  private let minConfidence = 0.6

  private init() {}

  // MARK: - Public API

  /// Identify explicit, still-open commitments the user (isFromMe) made to `contact`.
  /// Sends a bounded recent window through one LLM call; returns only findings whose
  /// confidence clears `minConfidence`. Does not create tasks — see `scanAndCreateTasks`.
  func scanForCommitments(
    contact: ImportedContact, messages: [ImportedMessage]
  ) async throws -> [ExtractedCommitment] {
    guard messages.count >= 4 else { throw CommitmentExtractionError.notEnoughMessages }

    // Readers hand back newest-first; take the most recent window and render it
    // chronologically so the model can see whether a promise was resolved later.
    let window = Array(messages.prefix(maxMessagesScanned)).reversed()
    let transcript = Self.formatTranscript(window, contact: contact)

    let prompt = Self.buildPrompt(transcript: transcript, contact: contact)
    let system =
      "You analyze a person's real text-message history with one contact and extract only "
      + "explicit, unfulfilled commitments THEY made. You are conservative and never invent "
      + "commitments. Output only valid JSON."

    let responseText = try await runLLM(prompt: prompt, system: system, label: "scan")
    let parsed = Self.parseCommitments(from: responseText, contact: contact)
    let filtered = parsed.filter { $0.confidence >= minConfidence }
    log(
      "Commitment: \(contact.platform)/\(contact.displayName) — model returned \(parsed.count), "
        + "\(filtered.count) above \(minConfidence) confidence")
    return filtered
  }

  /// Full pipeline: scan, then create a real staged Task for each fresh commitment (reusing
  /// the app's existing task-creation mechanism) and kick promotion so they surface on the
  /// Tasks page. Duplicates of already-tracked tasks are skipped via `isDuplicate`.
  func scanAndCreateTasks(
    contact: ImportedContact, messages: [ImportedMessage]
  ) async throws -> CommitmentScanOutcome {
    let commitments = try await scanForCommitments(contact: contact, messages: messages)
    guard !commitments.isEmpty else {
      return CommitmentScanOutcome(found: [], created: 0, duplicatesSkipped: 0)
    }

    // One snapshot of what's already tracked (staged + active/completed action items) so a
    // re-scan of the same contact never re-creates a task for the same commitment.
    let existing = await existingTaskTitles()

    // Score new commitments just below existing prioritized tasks (most-confident first) so
    // they're eligible for promotion into action_items — the same relevance-score mechanism
    // the screen pipeline uses — without jumping ahead of the user's established priorities.
    var nextScore = await nextRelevanceScore()
    let ordered = commitments.sorted { $0.confidence > $1.confidence }

    var created = 0
    var duplicates = 0
    var createdThisRun: Set<String> = []

    for commitment in ordered {
      let key = Self.normalizedTitle(commitment.commitmentText)
      if key.isEmpty { continue }
      if existing.contains(key) || createdThisRun.contains(key) {
        duplicates += 1
        log("Commitment: skipping duplicate — \"\(commitment.commitmentText)\"")
        continue
      }
      createdThisRun.insert(key)
      if await createTask(from: commitment, contact: contact, relevanceScore: nextScore) {
        created += 1
        nextScore += 1
      }
    }

    if created > 0 {
      // Same fast-path promotion the screen pipeline uses so the new tasks land on the
      // Tasks page (and fire their notification) within seconds, not on the next timer.
      await TaskPromotionService.shared.promoteIfNeeded()
    }

    log(
      "Commitment: \(contact.displayName) — created \(created), skipped \(duplicates) duplicates")
    return CommitmentScanOutcome(
      found: commitments, created: created, duplicatesSkipped: duplicates)
  }

  // MARK: - Task creation (reuses the existing staged-task pipeline)

  /// Create one real Task from a commitment using the SAME mechanism `TaskAssistant` uses:
  /// insert into `staged_tasks` locally, sync to the backend via `APIClient.createStagedTask`,
  /// and mark the local row synced. Tagged `commitment_tracking` + platform so these are
  /// visually distinct from screen-extracted tasks. Returns whether it was created.
  private func createTask(
    from commitment: ExtractedCommitment, contact: ImportedContact, relevanceScore: Int?
  ) async -> Bool {
    let tags = ["commitment_tracking", contact.platform]
    let sourceApp = Self.platformLabel(contact.platform)
    let noteContext = commitment.context.trimmingCharacters(in: .whitespacesAndNewlines)
    let saidOnStr = commitment.saidOn.map { Self.dayFormatter.string(from: $0) }

    var metadata: [String: Any] = [
      "source_app": sourceApp,
      "confidence": commitment.confidence,
      "tags": tags,
      "category": "commitment_tracking",
      "source_category": "direct_request",
      "source_subcategory": "commitment",
      "contact_name": contact.displayName,
      "contact_id": contact.id,
      "platform": contact.platform,
    ]
    if !noteContext.isEmpty { metadata["reasoning"] = "Promised in chat: \"\(noteContext)\"" }
    if let saidOnStr { metadata["said_on"] = saidOnStr }

    // Human-readable note describing where the commitment came from (shown on the task).
    var noteParts = ["Commitment to \(contact.displayName) via \(sourceApp)"]
    if let saidOnStr { noteParts.append("said \(saidOnStr)") }
    if !noteContext.isEmpty { noteParts.append("— \"\(noteContext)\"") }
    let contextSummary = noteParts.joined(separator: " ")

    let tagsJson = (try? JSONEncoder().encode(tags)).flatMap { String(data: $0, encoding: .utf8) }
    let metadataJson = (try? JSONSerialization.data(withJSONObject: metadata)).flatMap {
      String(data: $0, encoding: .utf8)
    }

    // 1. Local staged_tasks row (identical shape to TaskAssistant.saveTaskToSQLite).
    let record = StagedTaskRecord(
      backendSynced: false,
      description: commitment.commitmentText,
      source: "commitment",
      priority: TaskPriority.medium.rawValue,
      category: "commitment_tracking",
      tagsJson: tagsJson,
      confidence: commitment.confidence,
      sourceApp: sourceApp,
      contextSummary: contextSummary,
      metadataJson: metadataJson,
      relevanceScore: relevanceScore,
      scoredAt: relevanceScore != nil ? Date() : nil
    )

    let localId: Int64?
    do {
      // insertWithScoreShift keeps existing scores consistent when we slot a new task in —
      // the same call the screen pipeline makes for a scored task.
      let inserted =
        relevanceScore != nil
        ? try await StagedTaskStorage.shared.insertWithScoreShift(record)
        : try await StagedTaskStorage.shared.insertLocalStagedTask(record)
      localId = inserted.id
    } catch {
      logError("Commitment: failed to save staged task locally", error: error)
      localId = nil
    }

    // 2. Backend staged task (same call the screen pipeline makes), then mark synced.
    do {
      let response = try await APIClient.shared.createStagedTask(
        description: commitment.commitmentText,
        source: "commitment",
        priority: TaskPriority.medium.rawValue,
        category: "commitment_tracking",
        metadata: metadata,
        relevanceScore: relevanceScore
      )
      if let localId {
        try? await StagedTaskStorage.shared.markSynced(id: localId, backendId: response.id)
      }
      log("Commitment: created task \"\(commitment.commitmentText)\" (backend \(response.id))")
      return true
    } catch {
      logError("Commitment: failed to sync task to backend", error: error)
      // Local row still exists — count it only if the local insert succeeded so the user
      // sees an accurate "created N" and the promotion loop can still pick it up on sync.
      return localId != nil
    }
  }

  /// The relevance score to give the first new commitment: one past the largest score already
  /// in use across action_items and scored staged tasks, so commitments slot in just below
  /// the user's existing prioritized work (1 = most important; higher = less). Defaults to a
  /// mid value when nothing is scored yet so they still promote.
  private func nextRelevanceScore() async -> Int {
    var maxScore = 0
    if let range = try? await ActionItemStorage.shared.getRelevanceScoreRange() {
      maxScore = max(maxScore, range.max)
    }
    if let scoredStaged = try? await StagedTaskStorage.shared.getScoredStagedTasks(limit: 500) {
      for task in scoredStaged {
        if let score = task.relevanceScore { maxScore = max(maxScore, score) }
      }
    }
    return maxScore + 1
  }

  // MARK: - Dedup

  /// Normalized titles of everything already tracked — staged tasks plus active and recently
  /// completed action items — so a re-scan can skip commitments that are already tasks.
  private func existingTaskTitles() async -> Set<String> {
    var titles: Set<String> = []

    if let staged = try? await StagedTaskStorage.shared.getAllStagedTasks(limit: 2000) {
      for task in staged { titles.insert(Self.normalizedTitle(task.description)) }
    }
    if let active = try? await ActionItemStorage.shared.getRecentActiveTasks(limit: 500) {
      for task in active { titles.insert(Self.normalizedTitle(task.description)) }
    }
    if let completed = try? await ActionItemStorage.shared.getRecentCompletedTasks(limit: 200) {
      for task in completed { titles.insert(Self.normalizedTitle(task.description)) }
    }

    titles.remove("")
    return titles
  }

  /// Lowercased, alphanumerics+spaces only, whitespace collapsed. A re-scan produces the
  /// same commitment text → same normalized key → recognized as a duplicate.
  static func normalizedTitle(_ title: String) -> String {
    let lowered = title.lowercased()
    let cleaned = lowered.map { $0.isLetter || $0.isNumber || $0.isWhitespace ? $0 : " " }
    return String(cleaned).split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
  }

  // MARK: - Prompt + transcript

  private static let dayFormatter: DateFormatter = {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.dateFormat = "yyyy-MM-dd"
    return f
  }()

  private static func platformLabel(_ platform: String) -> String {
    switch platform {
    case "telegram": return "Telegram"
    case "whatsapp": return "WhatsApp"
    default: return "iMessage"
    }
  }

  private static func formatTranscript(
    _ messages: some Sequence<ImportedMessage>, contact: ImportedContact
  ) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "yyyy-MM-dd HH:mm"
    let themLabel = contact.displayName
    return messages.map { message -> String in
      let stamp = formatter.string(from: message.date)
      let speaker = message.isFromMe ? "Me" : themLabel
      let body = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
      return "[\(stamp)] \(speaker): \(body)"
    }.joined(separator: "\n")
  }

  private static func buildPrompt(transcript: String, contact: ImportedContact) -> String {
    let todayStr = dayFormatter.string(from: Date())
    return """
    Below is a chronological transcript of real text messages between the user (labeled "Me") \
    and "\(contact.displayName)". Today is \(todayStr).

    TRANSCRIPT:
    \(transcript)

    Find every case where "Me" (the user) EXPLICITLY committed to doing something for, sending \
    something to, or following up with \(contact.displayName) — and that commitment does NOT \
    appear fulfilled anywhere later in the visible conversation.

    What counts as a commitment (extract these):
    - "I'll send you the deck tomorrow"
    - "let me get back to you on the dates"
    - "I'll call the landlord this week"
    - "yeah let's do Thursday" when the user is the one agreeing to / proposing the plan
    - "I'll look into it and let you know"

    What does NOT count (never extract these):
    - Vague conversational filler ("we should hang out sometime", "lol yeah", "maybe")
    - Things the OTHER person committed to (only the user's own promises count)
    - A commitment that is clearly resolved later in the thread (they sent it, it happened, \
      it was cancelled, or the user says it's done)
    - Questions, opinions, reactions, or plans with no concrete action owned by the user

    Be conservative. When unsure whether something is a real, still-open commitment, leave it out.

    For each real, unfulfilled commitment, output:
    - commitment_text: a short verb-first task the user should do, naming \
    "\(contact.displayName)" (e.g. "Send \(contact.displayName) the signed lease"). 5–14 words.
    - said_on: the date the user made the commitment, as yyyy-MM-dd (from the transcript \
    timestamps). Empty string if you cannot tell.
    - context: the user's ACTUAL message text where they made the promise, copied verbatim \
    from the transcript (never paraphrased or invented).
    - confidence: 0.0–1.0 that this is a genuine, still-open commitment.

    Respond ONLY with valid JSON (no markdown, no code fences):
    {"commitments": [{"commitment_text": "...", "said_on": "2026-06-14", "context": "exact user line", "confidence": 0.9}]}

    If there are no clear unfulfilled commitments, respond with {"commitments": []}.
    """
  }

  /// Parse the model's JSON. Tolerant of code fences / trailing prose. Drops any entry whose
  /// commitment text is empty. `saidOn` parses yyyy-MM-dd; unparseable/empty → nil.
  static func parseCommitments(from text: String, contact: ImportedContact)
    -> [ExtractedCommitment]
  {
    let jsonText = extractJSONObject(from: text)
    guard
      let data = jsonText.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let rows = parsed["commitments"] as? [[String: Any]]
    else { return [] }

    return rows.compactMap { row -> ExtractedCommitment? in
      let commitmentText =
        (row["commitment_text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !commitmentText.isEmpty else { return nil }

      let context =
        (row["context"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)

      let saidOnRaw =
        (row["said_on"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      let saidOn = saidOnRaw.isEmpty ? nil : dayFormatter.date(from: saidOnRaw)

      let confidence: Double
      if let c = row["confidence"] as? Double {
        confidence = c
      } else if let c = row["confidence"] as? Int {
        confidence = Double(c)
      } else {
        confidence = 0.5
      }

      return ExtractedCommitment(
        commitmentText: commitmentText, saidOn: saidOn, context: context,
        confidence: max(0.0, min(1.0, confidence)))
    }
  }

  private static func extractJSONObject(from text: String) -> String {
    var responseText = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if responseText.hasPrefix("```") {
      if let firstNewline = responseText.firstIndex(of: "\n") {
        responseText = String(responseText[responseText.index(after: firstNewline)...])
      }
      if responseText.hasSuffix("```") {
        responseText = String(responseText.dropLast(3))
      }
    }
    if let braceIndex = responseText.firstIndex(of: "{") {
      responseText = String(responseText[braceIndex...])
    }
    if let lastBrace = responseText.lastIndex(of: "}") {
      responseText = String(responseText[...lastBrace])
    }
    return responseText.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  // MARK: - LLM plumbing (shared bridge, retry — mirrors AIClonePersonaService)

  private var sharedBridge: AgentBridge?
  private var llmBusy = false

  private func acquireBridge() async throws -> AgentBridge {
    if let bridge = sharedBridge, await bridge.isAlive { return bridge }
    let bridge = AgentBridge(harnessMode: "piMono")
    try await bridge.start()
    sharedBridge = bridge
    return bridge
  }

  private func discardBridge() {
    if let bridge = sharedBridge {
      Task { await bridge.stop() }
    }
    sharedBridge = nil
  }

  private static func isQuotaError(_ error: Error) -> Bool {
    if case BridgeError.quotaExceeded = error { return true }
    return false
  }

  private func runLLM(prompt: String, system: String, label: String) async throws -> String {
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
          model: ModelQoS.Claude.cloneVoice,
          onTextDelta: { @Sendable _ in },
          onToolCall: { @Sendable _, _, _ in "" },
          onToolActivity: { @Sendable _, _, _, _ in }
        )
        return result.text
      } catch {
        lastError = error
        discardBridge()
        if attempt < maxAttempts {
          log("CommitmentExtractionService: \(label) attempt \(attempt) failed, retrying: \(error)")
          if !Self.isQuotaError(error) {
            try? await Task.sleep(nanoseconds: 800_000_000)
          }
          continue
        }
        log("CommitmentExtractionService: \(label) failed after \(attempt) attempts: \(error)")
      }
    }
    throw CommitmentExtractionError.llmFailed(lastError?.localizedDescription ?? "")
  }
}
