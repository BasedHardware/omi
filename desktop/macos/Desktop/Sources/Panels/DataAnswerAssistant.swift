import AppKit
import Foundation

/// Finds what the user asked for out loud in their own data, and leaves it on the panel.
///
/// The realtime voice model is built for latency, not synthesis: give it five sources to
/// read and it answers from the first one. So `find_and_show` hands the question to a
/// model that searches — memories, profile, recent work, screen history, conversations —
/// until it can present values worth copying. The panel goes up before the first search
/// with a spinner, because the loop takes seconds and a silent gap reads as broken.
///
/// The loop speaks structured JSON, not Gemini function calling: the desktop proxy's
/// managed lanes have been observed returning a function call as one empty text part
/// (`parts:[{"text":""}]`, candidate tokens spent, 2026-08-28), which kills a tool loop
/// silently. `responseSchema` output rides the same lanes the shipped assistants use.
actor DataAnswerAssistant {
  enum Outcome: Sendable, Equatable {
    case answer(title: String, items: [VoicePanelItem], missing: [String])
    case nothing(reason: String)
  }

  /// One JSON turn of the search: a data tool to run next, or the finished answer.
  struct Step: Decodable, Sendable {
    let action: String
    let query: String?
    let title: String?
    let items: [Item]?
    let missing: [String]?

    struct Item: Decodable, Sendable {
      let label: String?
      let text: String
    }
  }

  private let geminiClient: GeminiClient
  private var runsToday: [Date] = []
  /// Loose on purpose: every run was asked for out loud. This bounds a stuck retry
  /// loop, not the user.
  private let dailyBudget = 40
  private static let maxToolTurns = 6
  /// A tool result past this adds context-window cost, not evidence.
  private static let maxToolResultLength = 8_000

  init() throws {
    geminiClient = try GeminiClient(
      model: ModelQoS.Gemini.proactive,
      fallbackModel: ModelQoS.Gemini.lightweight,
      workload: .extraction
    )
  }

  /// Answer the spoken request from the user's data because they asked for it out loud.
  /// The returned string is the tool result the voice model speaks one line about.
  func answerOnDemand(question: String) async -> String {
    guard RuntimeOwnerIdentity.currentOwnerId() != nil else { return "No signed-in Omi account." }
    let asked = question.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !asked.isEmpty else { return "Could not look that up: find_and_show needs the question." }

    let now = Date()
    runsToday = runsToday.filter { Calendar.current.isDate($0, inSameDayAs: now) }
    guard runsToday.count < dailyBudget else {
      return "Looking things up has spent its budget for today."
    }
    runsToday.append(now)

    let work = CancellableWork()
    await MainActor.run {
      PanelSession.present(
        title: "Finding that",
        subtitle: "Searching your data\u{2026}",
        fields: [
          CloudConnectorCopyField(
            id: "answer-pending", label: "", value: "", masksValue: false, wraps: true,
            isPending: true)
        ],
        // What the user asked for is about them, not the tab in front: it survives tab
        // changes and leaves with the app, exactly like show_panel.
        grain: .app,
        origin: .requested,
        onCancel: { work.cancel() }
      )
    }
    log("DataAnswer: on-demand lookup started, question=\(asked.count) chars")

    do {
      let outcome = try await work.run { try await self.explore(question: asked) }
      guard await !work.isCancelled else { return "Cancelled." }
      switch outcome {
      case .nothing(let reason):
        if !runsToday.isEmpty { runsToday.removeLast() }
        _ = await MainActor.run { PanelSession.dismiss() }
        log("DataAnswer: nothing found — \(reason)")
        // Spelled out because the voice model must not claim a panel it saw go up
        // during the search is still there.
        return "Nothing in the user's data answers that, and no panel is on screen: \(reason)"
      case .answer(let title, let items, let missing):
        let fields = VoicePanel.copyFields(from: items)
        guard !fields.isEmpty else {
          _ = await MainActor.run { PanelSession.dismiss() }
          return "Nothing in the user's data answers that, and no panel is on screen."
        }
        await MainActor.run {
          PanelSession.update(
            title: title,
            subtitle: fields.count == 1 ? "Copy it with the button." : "Copy each with its button.",
            fields: fields)
        }
        // Labels only: the values are on screen, and reading them back aloud is what the
        // panel exists to avoid.
        let named = fields.map(\.label).filter { !$0.isEmpty }
        log("DataAnswer: \(fields.count) item(s) on screen, \(missing.count) missing")
        return "Panel is on screen with \(fields.count) item\(fields.count == 1 ? "" : "s") to copy"
          + (named.isEmpty ? "." : ": \(named.joined(separator: ", ")).")
          + (missing.isEmpty ? "" : " Not found in the user's data: \(missing.joined(separator: ", ")).")
      }
    } catch is CancellationError {
      if !runsToday.isEmpty { runsToday.removeLast() }
      return "Cancelled."
    } catch {
      logError("DataAnswer: lookup failed", error: error)
      _ = await MainActor.run { PanelSession.dismiss() }
      return "Could not search the user's data."
    }
  }

  // MARK: - Exploration loop

  private func explore(question: String) async throws -> Outcome {
    var transcript = await Self.openingPrompt(question: question)

    for _ in 0..<Self.maxToolTurns {
      try Task.checkCancellation()
      let raw = try await geminiClient.sendRequest(
        prompt: transcript,
        systemPrompt: Self.systemPrompt,
        responseSchema: Self.stepSchema,
        thinkingBudget: 1024
      )
      guard let step = Self.decodeStep(raw) else {
        log("DataAnswer: undecodable step (\(raw.count) chars) — asking again")
        transcript += "\n\nThat response was not valid JSON for the schema. Answer again."
        continue
      }
      if let outcome = Self.outcome(of: step) { return outcome }

      guard let progress = Self.progressSubtitle(forTool: step.action) else {
        transcript += "\n\n\"\(step.action)\" is not one of the offered actions. Choose again."
        continue
      }
      await MainActor.run { PanelSession.update(subtitle: progress) }
      let query = step.query?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      log("DataAnswer: exploring via \(step.action)")
      let result = await ChatToolExecutor.execute(
        ToolCall(
          name: step.action,
          arguments: query.isEmpty ? [:] : ["query": query],
          thoughtSignature: nil))
      transcript += """


        == RESULT OF \(step.action)\(query.isEmpty ? "" : " for \"\(query)\"") ==
        \(String(result.prefix(Self.maxToolResultLength)))
        """
    }

    // Out of searches: the only move left is presenting what was gathered, or saying
    // honestly that nothing was.
    try Task.checkCancellation()
    transcript +=
      "\n\nNo more searches. Answer now with action=present_answer: items holds everything found, missing names the rest."
    let raw = try await geminiClient.sendRequest(
      prompt: transcript,
      systemPrompt: Self.systemPrompt,
      responseSchema: Self.stepSchema,
      thinkingBudget: 1024
    )
    guard let step = Self.decodeStep(raw), let outcome = Self.outcome(of: step) else {
      return .nothing(reason: "the search did not settle on an answer")
    }
    return outcome
  }

  nonisolated static func decodeStep(_ raw: String) -> Step? {
    guard let data = raw.data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode(Step.self, from: data)
  }

  /// The finished answer, if this step is one. A search step returns nil.
  nonisolated static func outcome(of step: Step) -> Outcome? {
    guard step.action == "present_answer" else { return nil }
    let items = (step.items ?? [])
      .map {
        VoicePanelItem(
          label: ($0.label ?? "").trimmingCharacters(in: .whitespacesAndNewlines),
          text: $0.text.trimmingCharacters(in: .whitespacesAndNewlines))
      }
      .filter { !$0.text.isEmpty }
    let missing = (step.missing ?? [])
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    guard !items.isEmpty else {
      return .nothing(
        reason: missing.isEmpty
          ? "the answer came back empty"
          : "not found: \(missing.joined(separator: ", "))")
    }
    let title = (step.title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    return .answer(title: title.isEmpty ? "Found for you" : title, items: items, missing: missing)
  }

  /// The subtitle while a data tool runs — and the allowlist: an action without one is
  /// not part of this loop and never reaches ChatToolExecutor.
  nonisolated static func progressSubtitle(forTool name: String) -> String? {
    switch name {
    case "search_memories", "get_memories": return "Reading your memories\u{2026}"
    case "get_work_context": return "Reading your recent work\u{2026}"
    case "search_screen_history": return "Searching your screen history\u{2026}"
    case "search_conversations": return "Searching your conversations\u{2026}"
    default: return nil
    }
  }

  // MARK: - Prompts and schema

  private static func openingPrompt(question: String) async -> String {
    let identity = await MainActor.run {
      (name: AuthService.shared.displayName, email: AuthState.shared.userEmail ?? "")
    }
    let profile =
      await AIUserProfileService.shared.getLatestProfile()?
      .profileText.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let front = await MainActor.run {
      NSWorkspace.shared.frontmostApplication?.localizedName ?? ""
    }
    // Presence only — the values are the user's own details and stay out of the log.
    log(
      "DataAnswer: context name=\(identity.name.isEmpty ? "absent" : "present")"
        + " email=\(identity.email.isEmpty ? "absent" : "present")"
        + " profile=\(profile.isEmpty ? "absent" : "\(profile.count) chars")")
    return """
      == WHAT THE USER ASKED FOR, OUT LOUD, JUST NOW ==
      \(question)

      == THE USER ==
      Name: \(identity.name.isEmpty ? "(unknown)" : identity.name)
      Email: \(identity.email.isEmpty ? "(unknown)" : identity.email)
      \(front.isEmpty ? "" : "App in front of them: \(front)")
      Today: \(DateFormatter.localizedString(from: Date(), dateStyle: .full, timeStyle: .none))
      \(profile.isEmpty
        ? ""
        : """

          == THEIR PROFILE, AS OMI KNOWS IT ==
          \(profile)
          """)
      """
  }

  private static let systemPrompt = """
    You are Omi's lookup assistant. The user asked out loud for something of their own,
    and your one job is to find it in their data and present it as copyable text. Each
    response is one JSON step: a search to run next, or the finished answer.

    The user block and profile are already-found data: an email, name, or fact stated
    there needs no search and belongs straight in the answer. Search for the rest.
    Choose the action the question points at: stored facts about the user live in
    search_memories and get_memories, what they were working on lives in
    get_work_context and search_screen_history, what was said lives in
    search_conversations. Set query for every search. Prefer a few targeted searches
    over many broad ones, and stop the moment you have the answer.

    The search ends with one action=present_answer step: everything you hold — from
    the blocks above or from a search result — goes in items, and the asked-for things
    that never turned up go in missing, by name. A short title, then one labeled item
    per value when there are several, or one unlabeled item for a single passage of
    text. Give values exactly as the user would paste them — a bare URL, a bare
    address, a bare number, with no commentary around it. Never leave a value you hold
    out of items because something else was missing; items is empty only when nothing
    at all was found.

    NEVER invent a value. Every item must be traceable to the user block, the profile,
    or a search result; the user will paste these somewhere real, so a wrong value
    costs far more than a missing one.
    """

  private static let stepSchema = GeminiRequest.GenerationConfig.ResponseSchema(
    type: "object",
    properties: [
      "action": .init(
        type: "string",
        enum: [
          "search_memories", "get_memories", "get_work_context", "search_screen_history",
          "search_conversations", "present_answer",
        ],
        description: "The next move: one search to run, or present_answer to finish."),
      "query": .init(
        type: "string",
        description: "For a search: what to look for. Empty for present_answer."),
      "title": .init(
        type: "string",
        description: "present_answer only: short title naming what was found. Empty otherwise."),
      "items": .init(
        type: "array",
        description:
          "present_answer only: everything found — one labeled entry per value, or one unlabeled entry for a single passage. Empty for a search step, and empty when nothing at all was found.",
        items: .init(
          type: "object",
          properties: [
            "label": .init(
              type: "string",
              description: "Short name for this value. Empty for a single passage of prose."),
            "text": .init(type: "string", description: "The exact text to show and copy."),
          ],
          required: ["text"])),
      "missing": .init(
        type: "array",
        description:
          "present_answer only: names of the asked-for things no search turned up. Empty otherwise.",
        items: .init(type: "string", properties: nil, required: nil)),
    ],
    required: ["action", "query", "title", "items", "missing"]
  )
}
